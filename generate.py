"""Entry point for controlled hierarchy and table-ownership synthesis."""
import argparse
from pathlib import Path
from core.fonts import verify_resources
from core.benchmark_config import load_config,validate_config,ROOT
from core.benchmark_pipeline import run_batch
from content.benchmark_content import DOMAINS


def main():
    parser=argparse.ArgumentParser(description='Controlled heading hierarchy and table ownership benchmark')
    parser.add_argument('--type',choices=list(DOMAINS)+['mixed','all'],default='paper')
    parser.add_argument('--task',choices=['level','ownership','joint'],default='joint')
    parser.add_argument('--config',type=Path,help='YAML overrides for base/type/task configuration')
    parser.add_argument('--count',type=int,help='Documents; with --type all, documents PER genre')
    parser.add_argument('--content',choices=['template','llm','library'])
    parser.add_argument('--seed',type=int)
    parser.add_argument('--depth',type=int,choices=range(2,7))
    parser.add_argument('--output',type=Path,default=ROOT/'outputs')
    parser.add_argument('--delivery',choices=['L1','L2','L3'],default='L3')
    args=parser.parse_args()
    try:
        cfg=load_config(args.type,args.task,args.config)
        if args.seed is not None:cfg['seed']=args.seed
        if args.count is not None:cfg['count']=args.count
        if args.content is not None:cfg['content_provider']=args.content
        if args.type=='all':
            cfg['count']*=len(DOMAINS);cfg['domains']={k:1 for k in DOMAINS}
        if args.depth is not None:cfg['depths']={args.depth:1}
        if args.task=='level':cfg['objects_per_document']=0
        validate_config(cfg);verify_resources()
        print('Content provider:',cfg.get('content_provider','template'),flush=True)
        path,composition,stats=run_batch(args.type,args.task,cfg,args.output,args.delivery)
    except (ValueError,RuntimeError) as exc:parser.exit(1,str(exc)+'\n')
    print(f'Accepted: {composition["docs"]} documents, {composition["pages"]} pages, {composition["headings"]} headings, {composition["objects"]} objects (tables + figures)')
    if composition['objects']:print(f'Rendered conflict ratio: {composition["conflict_ratio"]:.1%}; subtypes: {composition["by_subtype"]}')
    print(f'Attempt: {stats["attempts"]}; gold: {path / "docanno" / "docs.jsonl"}')
    print(f'PDF files: {path / "documents"}')

if __name__=='__main__':main()
