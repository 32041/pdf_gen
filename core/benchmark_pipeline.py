"""Generate -> render -> measure -> accept -> export, with deterministic retries."""
from pathlib import Path
from collections import Counter,defaultdict
import json,random,shutil,tempfile,platform
import pymupdf
from core.planner import allocate
from core.benchmark_schema import validate_graph
from core.benchmark_plan import assign_objects,replan_bindings
from core.benchmark_audit import audit_benchmark
from core.benchmark_export import export_document,export_inputs,summarize,write_json
from content.benchmark_content import build_document,DOMAINS
from render.benchmark_pdf import render_benchmark
from core.fonts import FONT_DIR
from core.provider_config import public_config


def plan_documents(kind,cfg,seed):
    rng=random.Random(seed);n=cfg['count']
    kinds=allocate(cfg['domains'],n,rng) if kind in ('mixed','all') else [kind]*n
    dims={name:allocate(cfg[key],n,rng) for name,key in [('language','languages'),('depth','depths'),('title','has_title'),
          ('numbering','numbering_modes'),('family','numbering_families'),('style','styles'),('template','templates'),('paper','paper_sizes')]}
    if cfg.get('require_depth_numbering_coverage',False):
        depth_counts=Counter(dims['depth']);mode_counts=Counter(dims['numbering'])
        modes=list(mode_counts);grid={d:[] for d in depth_counts}
        if any(v<len(modes) for v in depth_counts.values()) or any(v<len(depth_counts) for v in mode_counts.values()):
            raise ValueError('Depth x numbering coverage is infeasible at these integer quotas; increase count or balance weights.')
        for depth in grid:
            for mode in modes:grid[depth].append(mode);mode_counts[mode]-=1
        for depth in grid:
            while len(grid[depth])<depth_counts[depth]:
                mode=max(mode_counts,key=lambda x:mode_counts[x]);grid[depth].append(mode);mode_counts[mode]-=1
            rng.shuffle(grid[depth])
            for i,mode in zip([i for i,d in enumerate(dims['depth']) if d==depth],grid[depth]):dims['numbering'][i]=mode
    columns=[None]*n
    for k in sorted(set(kinds)):
        indices=[i for i,x in enumerate(kinds) if x==k]
        weights=cfg.get('columns') or cfg['columns_by_domain'][DOMAINS[k]]
        sampled=allocate(weights,len(indices),rng)
        for i,value in zip(indices,sampled):columns[i]=int(value)
    documents=[]
    for i,k in enumerate(kinds):
        template=dims['template'][i];profile=cfg['template_profiles'][template]
        documents.append(build_document(f'{i+1:04d}',k,dims['language'][i],seed+i,int(dims['depth'][i]),dims['title'][i]=='yes',
                         dims['numbering'][i],dims['family'][i],dims['style'][i],template,columns[i],profile['margin_pt'],profile['font_size']))
    variants=Counter()
    for doc,paper in zip(documents,dims['paper']):
        variants[doc.kind]+=1;doc.variant_index=variants[doc.kind]
        doc.paper=paper;doc.style_ladder=cfg['style_profiles'][doc.style]
        doc.page_width,doc.page_height={'A4':(595.276,841.89),'Letter':(612.0,792.0)}[paper]
    targets=assign_objects(documents,cfg,rng)
    from core.level_balance import balance_levels
    targets['level_balance_adjustments']=balance_levels(documents,cfg)
    from core.heading_policy import apply_heading_policy
    apply_heading_policy(documents,cfg,seed)
    targets['document_quotas']={name:dict(Counter(values)) for name,values in {
        'depth':[d.target_depth for d in documents],'language':[d.language for d in documents],
        'numbering':[d.numbering_mode for d in documents],'style':[d.style for d in documents],
        'domain':[d.domain for d in documents],'columns':[d.columns for d in documents],
        'family':[d.numbering_family for d in documents],'template':[d.template for d in documents],
        'title':['yes' if d.has_title else 'no' for d in documents],'paper':[d.paper for d in documents]}.items()}
    return documents,targets


def run_batch(kind,task,cfg,output,delivery='L3'):
    parent=Path(output).resolve()/kind;parent.mkdir(parents=True,exist_ok=True)
    destination=parent/task;marker='.pdf_synth_generated.json'
    if destination.exists() and not (destination/marker).is_file():
        raise ValueError(f'Refusing to overwrite unmarked directory: {destination}')
    failures=[];successful=None
    for attempt in range(cfg['max_attempts']):
        seed=cfg['seed']+attempt*100003
        stage=Path(tempfile.mkdtemp(prefix=f'.{task}-pending-',dir=parent))
        try:
            documents,targets=plan_documents(kind,cfg,seed)
            from content.llm_provider import prepare_documents
            prepare_documents(documents,cfg)
            from assets.figure_provider import prepare_figures
            prepare_figures(documents,cfg)
            layouts=[];all_blocks=[];audits=[];records=[]
            for doc in documents:
                folder=stage/'documents'/doc.doc_id;folder.mkdir(parents=True)
                repairs=[]
                repair=0
                while True:
                    layout=[]
                    try:
                        layout=render_benchmark(doc,folder)
                        blocks,audit=audit_benchmark(doc,folder,layout)
                        audit['rejected_renderings']=repairs
                        break
                    except (ValueError,RuntimeError) as exc:
                        if doc.content and 'continuation pool exhausted' in str(exc):
                            from content.llm_provider import extend_continuations
                            repairs.append(str(exc));extend_continuations(doc,cfg)
                            continue
                        if repair>=cfg.get('document_retries',3):
                            raise ValueError(f'Document {doc.doc_id} (seed={doc.seed}): {exc}') from exc
                        repairs.append(str(exc));repair+=1;doc.repair_count=repair;doc.repair_seed=doc.seed+repair*7919
                        replan_bindings(doc,doc.repair_seed,layout)
                write_json(folder/'document.json',doc.to_dict());write_json(folder/'audit.json',audit)
                records.append(export_document(doc,folder,stage/'docanno',blocks,audit,cfg['dpi'],'L1'))
                layouts.append(layout);all_blocks.append(blocks);audits.append(audit)
            composition,stats=summarize(documents,records,audits,targets,cfg,seed)
            stats['attempts']=attempt+1;stats['rejected_attempts']=failures
            stats['document_repairs']={d.doc_id:d.repair_count for d in documents if d.repair_count}
            successful=(stage,documents,targets,layouts,all_blocks,audits,composition,stats)
            break
        except (ValueError,RuntimeError) as exc:
            failures.append(dict(attempt=attempt+1,seed=seed,error=str(exc)))
            shutil.rmtree(stage)
    if successful is None:
        report=parent/f'{task}_failure_report.json'
        write_json(report,{'passed':False,'failures':failures,'config':public_config(cfg)})
        raise RuntimeError(f'No accepted batch after {cfg["max_attempts"]} attempts. Last error: {failures[-1]["error"][:500]}. Inspect {report}. Existing accepted data were preserved.')
    stage,documents,targets,layouts,all_blocks,audits,composition,stats=successful
    try:
        annotation=stage/'docanno';annotation.mkdir(parents=True,exist_ok=True);records=[]
        for doc,blocks,audit in zip(documents,all_blocks,audits):
            records.append(export_document(doc,stage/'documents'/doc.doc_id,annotation,blocks,audit,cfg['dpi'],delivery))
        (annotation/'docs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
        export_inputs(records,annotation,delivery)
        cases=[dict(doc_id=d.doc_id,**c) for d,a in zip(documents,audits) for c in a['cases']]
        (annotation/'ownership_cases.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in cases),encoding='utf-8')
        write_json(annotation/'composition.json',composition);write_json(annotation/'stats.json',stats)
        write_json(annotation/'targets.json',targets)
        write_json(annotation/'config.json',public_config(cfg))
        write_json(annotation/'render.json',dict(engine='pymupdf-custom-pagination',task=task,version='0.5.0',paper='per-document A4/Letter',unit='pt',dpi=cfg['dpi'],
                   fonts={'zh':'Bundled Noto Sans SC (wght=400)','en':'Bundled DejaVu Sans','bold':'Bundled DejaVu Sans Bold'},
                   font_hashes=json.loads((FONT_DIR/'manifest.json').read_text(encoding='utf-8')),style_ladders=cfg['style_profiles'],margins_and_fonts='per document render_meta and template_profiles in config.json',
                   python=platform.python_version(),pymupdf=pymupdf.VersionBind,seed=cfg['seed'],accepted_attempt_seed=stats['attempt_seed'],
                   object_numbering='ascending final reading order; stable internal IDs',unicode_mapping='used CID to strict UTF-16BE bfchar',float_policy=dict(far_float_min_owner_page_delta=2,plate_heading_count=0,plate_min_objects=2,plate_max_objects=cfg['plate_max_objects'],allow_end_of_doc=True),delivery=delivery))
        from core.reference_alignment import compare_reference
        write_json(annotation/'reference_alignment.json',compare_reference(all_blocks,layouts))
        from verify_dataset import verify
        stats['export_validation']=verify(annotation)
        write_json(annotation/'stats.json',stats)
        write_json(stage/marker,{'version':'0.5.0','task':task,'seed':stats['attempt_seed']})
        if destination.exists():
            backup=parent/f'.{task}-previous'
            if backup.exists():raise RuntimeError(f'Backup directory already exists: {backup}')
            destination.rename(backup)
            try:stage.rename(destination)
            except BaseException:backup.rename(destination);raise
            shutil.rmtree(backup)
        else:stage.rename(destination)
        old_report=parent/f'{task}_failure_report.json'
        if old_report.exists():old_report.unlink()
        return destination,composition,stats
    except BaseException:
        if stage.exists():shutil.rmtree(stage)
        raise
