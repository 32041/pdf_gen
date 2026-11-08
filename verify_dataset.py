"""Read-only validation of exported gold, images, source PDFs and redacted inputs."""
import argparse,json,re
from pathlib import Path


def verify(root):
    root=Path(root)
    records=[json.loads(l) for l in (root/'docs.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    cases=[json.loads(l) for l in (root/'ownership_cases.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    if len({r['doc_id'] for r in records})!=len(records):raise ValueError('Duplicate doc ID')
    objects=0;headings=0
    by_doc={r['doc_id']:r for r in records}
    for record in records:
        if not (root.parent/record['source_doc_id']).is_file():raise ValueError('Missing PDF')
        blocks=record['blocks'];by_id={b['id']:b for b in blocks}
        if len(by_id)!=len(blocks):raise ValueError('Duplicate block ID')
        orders=[b['order'] for b in blocks]
        if orders!=sorted(set(orders)):raise ValueError('Reading order is not strictly increasing')
        heading=[b for b in blocks if b['type']=='title'];headings+=len(heading)
        if len({b['text'] for b in heading})!=len(heading):raise ValueError('Repeated heading text')
        if max(b['level'] for b in heading)!=record['render_meta']['target_depth']:raise ValueError('Wrong depth')
        children={}
        for b in blocks:
            if b['parent_id']!='root' and b['parent_id'] not in by_id:raise ValueError('Broken parent')
            if b['type']=='title':
                children.setdefault(b['parent_id'],[]).append(b['id'])
                if b['parent_id']!='root' and b['level']!=by_id[b['parent_id']]['level']+1:raise ValueError('Heading depth jump')
            elif b['level'] is not None:raise ValueError('Non-heading has level gold')
            if b['type']=='page_furniture' and b['text'] in {h['text'] for h in heading}:raise ValueError('Furniture promoted into heading')
            if b.get('image') and not (root/b['image']).is_file():raise ValueError('Missing block crop')
            if 'box' in b:
                w=record['pages'][b['page']-1]['width'];h=record['pages'][b['page']-1]['height']
                x0,y0,x1,y1=b['box']
                if not 0<=x0<x1<=w or not 0<=y0<y1<=h:raise ValueError('Invalid block box')
            if b['type'] in ('table','figure'):
                objects+=1
                if b['belongs_to'] not in by_id or by_id[b['belongs_to']]['type']!='title' or b['parent_id']!=b['belongs_to']:raise ValueError('Broken ownership')
                for cid in b['caption_ids']:
                    if by_id[cid]['parent_id']!=b['id']:raise ValueError('Broken caption edge')
                    if b.get('page')!=by_id[cid].get('page'):raise ValueError('Detached caption')
        if any(len(v)==1 for k,v in children.items() if k!='root'):raise ValueError('Singleton heading child')
        if record['render_meta'].get('explicit_hierarchy'):
            paths={};counts={};family=record['render_meta']['numbering']
            for h in heading:
                if record['render_meta']['has_title'] and h['parent_id']=='root':
                    paths[h['id']]=();continue
                parent=h['parent_id'];counts[parent]=counts.get(parent,0)+1
                path=paths.get(parent,())+(counts[parent],);paths[h['id']]=path
                prefix=('.'.join(map(str,path)) if family=='arabic_dotted' else chr(64+path[0])+''.join('.'+str(v) for v in path[1:]))
                if family not in ('arabic_dotted','alpha_dotted') or not h['text'].startswith(prefix+' '):raise ValueError('Explicit hierarchy numbering does not match semantic tree')
        visible={'table':0,'figure':0}
        for b in blocks:
            if b['type'] not in ('table','figure'):continue
            kind=b['type'];visible[kind]+=1
            pattern=r'(?:图|Figure)' if kind=='figure' else r'(?:表|Table)'
            caption=by_id[b['caption_ids'][0]]['text']
            match=re.match(pattern+r'\s*(\d+)',caption)
            if not match or int(match[1])!=visible[kind]:raise ValueError('Visible table numbers are not ascending')
            reference=' '.join(x['text'] for x in blocks if x.get('refers_to')==b['id'])
            if not re.search(pattern+r'\s*'+str(visible[kind])+r'(?!\d)',reference):raise ValueError('Reference number disagrees with caption')
        for p in record['pages']:
            if p.get('image') and not (root/p['image']).is_file():raise ValueError('Missing page image')
    for case in cases:
        record=by_doc[case['doc_id']];by_id={b['id']:b for b in record['blocks']};obj=by_id[case['object_id']]
        previous=max((b for b in record['blocks'] if b['type']=='title' and b['order']<obj['order']),key=lambda b:b['order'])
        if previous['id']!=case['previous_heading_id'] or obj['belongs_to']!=case['owner_id']:raise ValueError('Ownership case disagrees with exported order/edges')
        if case['conflict']!=(previous['id']!=obj['belongs_to']):raise ValueError('Conflict label mismatch')
    for path in (root/'inputs').glob('*.jsonl'):
        for line in path.read_text(encoding='utf-8').splitlines():
            for b in json.loads(line)['blocks']:
                if set(b)&{'level','parent_id','belongs_to','target_subtype','target_relation'}:raise ValueError('Gold leakage in model inputs')
    composition=json.loads((root/'composition.json').read_text(encoding='utf-8'))
    if (len(records),headings,objects)!=(composition['docs'],composition['headings'],composition['objects']):raise ValueError('Composition totals disagree')
    return dict(docs=len(records),headings=headings,objects=objects,passed=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('docanno',type=Path)
    print(json.dumps(verify(parser.parse_args().docanno)))
