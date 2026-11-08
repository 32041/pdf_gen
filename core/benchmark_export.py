"""Export DocAnno-compatible gold plus three input views without target labels."""
from collections import Counter,defaultdict
from pathlib import Path
import json
import pymupdf as fitz


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def export_document(doc,folder,root,blocks,audit,dpi,delivery):
    pdf=fitz.open(folder/'document.pdf');pages=[]
    for index,page in enumerate(pdf,1):
        desc=dict(page=index,width=page.rect.width,height=page.rect.height,unit='pt',dpi=dpi,is_toc_page=False)
        if delivery=='L3':
            image=f'pages/{doc.doc_id}/p{index:04d}.jpg';p=root/image;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(page.get_pixmap(dpi=dpi).tobytes('jpg',jpg_quality=85));desc['image']=image
        pages.append(desc)
    clean=[]
    for b in blocks:
        item={k:v for k,v in b.items() if not k.startswith('_') and k!='float_box'}
        if delivery in ('L2','L3'):
            image=f'blocks/{doc.doc_id}/{b["id"]}.jpg';p=root/image;p.parent.mkdir(parents=True,exist_ok=True)
            clip=fitz.Rect(b['box']) & pdf[b['page']-1].rect
            if clip.is_empty:raise ValueError('Empty block crop')
            p.write_bytes(pdf[b['page']-1].get_pixmap(dpi=dpi,clip=clip).tobytes('jpg',jpg_quality=85));item['image']=image
        if delivery in ('L1','L2'):
            item.pop('page',None);item.pop('box',None)
        clean.append(item)
    pdf.close()
    numbered=sum(h.text!=h.title for h in doc.headings)
    return dict(doc_id=doc.doc_id,split='train',lang=doc.language,source_doc_id=f'documents/{doc.doc_id}/document.pdf',
                page_count=len(pages),render_meta=dict(domain=doc.domain,template=doc.template,columns=doc.columns,
                numbered=numbered>0,numbered_share=numbered/len(doc.headings),numbering=doc.numbering_family,
                numbering_mode=doc.numbering_mode,explicit_hierarchy=doc.explicit_hierarchy,title_alignment=doc.title_alignment,object_numbering="visual_reading_order",has_title=doc.has_title,target_depth=doc.target_depth,
                content_provider=doc.content.get('provenance',{}).get('provider','template'),content_hash=doc.content.get('provenance',{}).get('request_hash'),style=doc.style,repair_count=doc.repair_count,repair_seed=doc.repair_seed,paper=doc.paper,margin_pt=doc.margin_pt,font_size=doc.font_size,seed=doc.seed,toc_title_in_tree=False),pages=pages,blocks=clean)


def export_inputs(records,root,delivery):
    # Gold labels and generator difficulty flags must never be supplied as inputs.
    available=['L1']+(['L2'] if delivery in ('L2','L3') else [])+(['L3'] if delivery=='L3' else [])
    for mode in available:
        inputs=[]
        for record in records:
            item={k:record[k] for k in ['doc_id','lang','page_count']}
            item['has_title']=record['render_meta']['has_title']
            if mode=='L3':item['pages']=record['pages']
            item['blocks']=[]
            for block in record['blocks']:
                allowed=['id','display_id','type','text','order']
                if mode in ('L2','L3'):allowed+=['image']
                if mode=='L3':allowed+=['page','box']
                item['blocks'].append({k:block[k] for k in allowed if k in block})
            inputs.append(item)
        path=root/'inputs'/f'{mode}.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in inputs),encoding='utf-8')


def summarize(documents,records,audits,targets,cfg,attempt_seed):
    headings=[b for r in records for b in r['blocks'] if b['type']=='title']
    cases=[c for a in audits for c in a['cases']]
    conflicts=[c for c in cases if c['conflict']]
    eligible=len(cases)
    relation_by_subtype={}
    for subtype in ['after_section','far_float','before_heading','plate']:
        relation_by_subtype[subtype]=dict(Counter(c['relation'] for c in conflicts if c['subtype']==subtype))
    actual=dict(by_object_type=dict(Counter(o.object_type for d in documents for o in d.objects)),
                by_figure_status=dict(Counter(o.figure_status for d in documents for o in d.objects if o.object_type=='figure')),
                explicit_hierarchy_documents=sum(d.explicit_hierarchy for d in documents),
                explicit_hierarchy_ratio=sum(d.explicit_hierarchy for d in documents)/len(documents),
                title_alignment=dict(Counter(d.title_alignment for d in documents)),
                docs=len(records),pages=sum(r['page_count'] for r in records),headings=len(headings),objects=eligible,
                by_domain=dict(Counter(d.domain for d in documents)),by_columns=dict(Counter(d.columns for d in documents)),
                by_language=dict(Counter(d.language for d in documents)),
                by_numbering=dict(Counter(d.numbering_mode for d in documents)),
                by_numbering_family=dict(Counter(d.numbering_family for d in documents)),
                by_max_depth=dict(Counter(d.target_depth for d in documents)),
                by_paper=dict(Counter(d.paper for d in documents)),by_style=dict(Counter(d.style for d in documents)),by_template=dict(Counter(d.template for d in documents)),
                by_title_layer=dict(Counter('yes' if d.has_title else 'no' for d in documents)),
                by_numbered_share=dict(Counter('none' if r['render_meta']['numbered_share']<.2 else 'some' if r['render_meta']['numbered_share']<=.7 else 'most' for r in records)),by_level=dict(Counter(h['level'] for h in headings)),
                by_subtype=dict(Counter(c['subtype'] for c in cases)),by_order_relation=dict(Counter(c['relation'] for c in cases)),
                by_owner_page_delta=dict(Counter(c['owner_page_delta'] for c in cases)),
                by_reference_page_delta=dict(Counter(c['reference_page_delta'] for c in cases)),
                by_float_page=dict(Counter('before_owner_page' if c['owner_page_delta']<0 else 'same_owner_page' if c['owner_page_delta']==0 else 'one_page_after_owner' if c['owner_page_delta']==1 else 'two_plus_pages_after_owner' for c in cases)),
                relations_by_subtype=relation_by_subtype,
                conflict_ratio=len(conflicts)/eligible if eligible else None,
                cross_page_ratio=sum(c['owner_page_delta']!=0 for c in cases)/eligible if eligible else None,
                reference_cross_page_ratio=sum(c['reference_page_delta']!=0 for c in cases)/eligible if eligible else None,
                sibling_ratio=sum(c['relation']=='siblings' for c in conflicts)/len(conflicts) if conflicts else None,
                tolerance='Exact integer quotas; fractional weights use largest-remainder rounding. Optional level-share bounds are strict.',
                hard_ratio=None,hard_ratio_definition='Not defined; do not equate hard with conflict.',
                units=dict(depth='documents',level='headings',conflict='objects with owner and preceding heading',
                           sibling_ratio='conflicting objects',cross_page_ratio='object page differs from OWNER heading page'))
    mismatches=[]
    share=cfg.get('heading_numbering',{}).get('explicit_document_ratio')
    if share is not None and abs(actual['explicit_hierarchy_ratio']-share)>1/len(documents)+1e-9:mismatches.append('explicit hierarchy document quota')
    if eligible!=targets['objects']:mismatches.append('object count')
    if len(conflicts)!=targets.get('conflicts',0):mismatches.append('conflict count')
    for subtype,n in targets['subtypes'].items():
        if actual['by_subtype'].get(subtype,0)!=n:mismatches.append('subtype '+subtype)
    for subtype,counts in targets['relations_by_subtype'].items():
        measured=Counter(c['relation'] for c in cases if c['subtype']==subtype)
        if measured!=Counter(counts):mismatches.append('tree relation '+subtype)
    for name,values in targets['document_quotas'].items():
        field={'depth':'by_max_depth','language':'by_language','numbering':'by_numbering','style':'by_style','domain':'by_domain','columns':'by_columns','family':'by_numbering_family','template':'by_template','title':'by_title_layer','paper':'by_paper'}[name]
        if Counter(actual[field])!=Counter(values):mismatches.append(name+' quota')
    actual['depth_numbering_grid']={str(depth):dict(Counter(d.numbering_mode for d in documents if d.target_depth==depth)) for depth in sorted({d.target_depth for d in documents})}
    n=max(eligible,1)
    target_ratio=cfg['conflict_ratio'] if eligible else None
    if eligible and abs(actual['conflict_ratio']-target_ratio)>1/n+1e-9:mismatches.append('conflict rate rounding')
    shares={int(k):v/max(len(headings),1) for k,v in actual['by_level'].items()}
    actual['level_shares']=shares
    for group,bounds in cfg.get('level_share_constraints',{}).items():
        levels=[int(v) for v in str(group).split(',')]
        share=sum(shares.get(level,0) for level in levels)
        if not bounds[0] <= share <= bounds[1]:mismatches.append(f'level share {group}: {share:.4f} outside {bounds}')
    if mismatches:raise ValueError('Batch acceptance failed: '+', '.join(mismatches))
    stats=dict(passed=True,attempt_seed=attempt_seed,rendered_documents=len(records),rendered_objects=eligible,
               checks=sorted({c for a in audits for c in a['checks']}),quota_checks='Exact integer quota checks passed',
               requested_conflict_ratio=target_ratio,actual_conflict_ratio=actual['conflict_ratio'],
               rounding_resolution=1/n if eligible else None,baselines={})
    g_correct=sum(not c['conflict'] for c in cases);parent_correct=0;caption_correct=0
    for doc,audit in zip(documents,audits):
        by_id={h.id:h for h in doc.headings};objects={o.id:o for o in doc.objects}
        for c in audit['cases']:
            parent_correct+=by_id[c['previous_heading_id']].parent_id==c['owner_id']
            caption=objects[c['object_id']].caption.casefold()
            hits=[h for h in doc.headings if h.title.casefold() in caption]
            guess=max(hits,key=lambda h:len(h.title)).id if hits else None
            caption_correct+=guess==c['owner_id']
    stats['baselines']={name:correct/eligible if eligible else None for name,correct in [('nearest_heading',g_correct),('parent_of_nearest',parent_correct),('caption_title_literal',caption_correct)]}
    stats['semantic_limit']=('LLM prose and tables: numeric tokens, schema and geometry validated; semantic coherence still needs human review.' if any(d.content for d in documents) else 'Current captions explicitly name topics. Samples validate structure/geometry, not mature semantic difficulty.')
    stats['content_models']=dict(Counter(d.content.get('provenance',{}).get('model','template') for d in documents))
    return actual,stats
