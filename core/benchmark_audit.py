"""Read geometry back from the final PDF, then recompute g(o), subtypes and relations."""
from collections import Counter,defaultdict
import pymupdf as fitz
import unicodedata
import re
from core.pdf_unicode import audit_unicode_maps
from core.benchmark_schema import relation, validate_graph


def lane_key(block):
    lane=block.get('_lane','column0')
    rank=-1 if lane=='spanning_top' else 9 if lane=='footer' else 0 if lane=='spanning_body' else int(lane.removeprefix('column'))
    return (block['page'],rank,block['box'][1],block['box'][0],block['id'])


def collect_blocks(layout):
    grouped={}
    for page in layout:
        for op in page['operations']:
            key=(op['block_id'],page['page'],op['lane'])
            if key not in grouped:
                grouped[key]=dict(id=op['block_id'],type=op['type'],text='',page=page['page'],box=op['box'][:],
                                  level=op.get('level'),parent_id=op['parent_id'],belongs_to=op.get('belongs_to'),
                                  caption_ids=op.get('caption_ids',[]),_lane=op['lane'],_lines=[],source_block_id=op['block_id'])
                if op.get('refers_to'):grouped[key]['refers_to']=op['refers_to']
                if op.get('float_box'):grouped[key]['float_box']=op['float_box']
            b=grouped[key]
            if op['kind']=='text':b['_lines'].append(op['text'])
            b['box']=[min(b['box'][0],op['box'][0]),min(b['box'][1],op['box'][1]),max(b['box'][2],op['box'][2]),max(b['box'][3],op['box'][3])]
    counts=Counter(b['id'] for b in grouped.values());fragment=Counter()
    blocks=list(grouped.values())
    for b in blocks:
        b['text']='\n'.join(b.pop('_lines'))
        if counts[b['id']]>1:
            base=b['id'];fragment[base]+=1;b['id']=base+f'_part{fragment[base]}'
    blocks.sort(key=lane_key)
    heading_no=0;object_no=0
    for i,b in enumerate(blocks,1):
        b['order']=float(i)
        if b['type']=='title':heading_no+=1;b['display_id']=f'B{heading_no}'
        elif b['type'] in ('table','figure'):object_no+=1;b['display_id']=f'O{object_no}'
        else:b['display_id']=None
    return blocks


def classify(obj,owner,previous,blocks):
    same_page=[b for b in blocks if b['page']==obj['page']]
    if not any(b['type']=='title' for b in same_page) and sum(b['type'] in ('figure','table') for b in same_page)>=2:
        return 'plate'
    if obj['page']==owner['page'] and obj['order']<owner['order']:return 'before_heading'
    if obj['page']-owner['page']>=2:return 'far_float'
    return 'after_section'


def audit_benchmark(doc,folder,layout):
    validate_graph(doc)
    blocks=collect_blocks(layout);by_id={b['id']:b for b in blocks}
    if len(by_id)!=len(blocks):raise ValueError('Duplicate rendered block ID')
    pdf=fitz.open(folder/'document.pdf');errors=[];cases=[]
    audit_unicode_maps(pdf)
    table_blocks=[b for b in blocks if b['type'] in ('table','figure')]
    planned_by_id={o.id:o for o in doc.objects}
    numbers=Counter()
    for b in table_blocks:
        numbers[b['type']]+=1;number=numbers[b['type']]
        label=('图' if b['type']=='figure' else '表') if doc.language=='zh' else ('Figure' if b['type']=='figure' else 'Table')
        obj=planned_by_id[b['id']]
        cap=by_id[b['caption_ids'][0]]
        found=re.match(re.escape(label)+r'\s*(\d+)',cap['text'])
        reference_text=' '.join(t['text'] for t in blocks if t.get('refers_to')==obj.id)
        if obj.display_number!=number or not found or int(found[1])!=number:errors.append(f'{obj.id}: nonascending visible number')
        if not re.search(re.escape(label)+r'\s*'+str(number)+r'(?!\d)',reference_text):errors.append(f'{obj.id}: reference number mismatch')
    for pno,page in enumerate(pdf,1):
        for font in page.get_fonts():
            if not pdf.extract_font(font[0])[3]:errors.append(f'p{pno}: unembedded font {font[3]}')
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    box=fitz.Rect(span['bbox'])
                    if '\x00' in span['text'] or '\ufffd' in span['text']:errors.append(f'p{pno}: invalid text')
                    if box.x0<-.5 or box.y0<-.5 or box.x1>page.rect.width+.5 or box.y1>page.rect.height+.5:errors.append(f'p{pno}: text outside page')
    for b in blocks:
        if not b['text']:continue
        # Clip to planned line boxes and confirm that text actually exists in saved PDF.
        actual=pdf[b['page']-1].get_textbox(fitz.Rect(b['box'])+(-.5,-.5,.5,.5))
        normal=lambda s:''.join(unicodedata.normalize('NFKC',s).split())
        if normal(b['text']) not in normal(actual):errors.append(f'{b["id"]}: PDF text does not match layout')
    first=by_id[doc.headings[0].id]
    if doc.title_alignment=='center' and abs((first['box'][0]+first['box'][2])/2-doc.page_width/2)>.6:errors.append('First heading is not centered')
    for planned in doc.objects:
        obj=by_id[planned.id];owner=by_id[planned.owner_id]
        candidates=[b for b in blocks if b['type']=='title' and b['order']<obj['order']]
        previous=max(candidates,key=lambda b:b['order']) if candidates else None
        if previous is None:errors.append(f'{obj["id"]}: no preceding heading');continue
        conflict=previous['id']!=planned.owner_id
        actual_subtype=classify(obj,owner,previous,blocks) if conflict else 'normal'
        actual_relation=relation(planned.owner_id,previous['id'],doc.headings)
        ref=next(b for b in blocks if b.get('refers_to')==obj['id'])
        cases.append(dict(object_id=obj['id'],owner_id=owner['id'],previous_heading_id=previous['id'],
                          conflict=conflict,subtype=actual_subtype,relation=actual_relation,
                          owner_page_delta=obj['page']-owner['page'],reference_page_delta=obj['page']-ref['page'],
                          target_subtype=planned.target_subtype,target_relation=planned.target_relation,object_type=planned.object_type,figure_status=planned.figure_status))
        if actual_subtype!=planned.target_subtype:errors.append(f'{obj["id"]}: expected {planned.target_subtype}, got {actual_subtype}')
        if actual_relation!=planned.target_relation:errors.append(f'{obj["id"]}: expected {planned.target_relation}, got {actual_relation}')
        if previous['id']!=planned.target_previous_id:errors.append(f'{obj["id"]}: predecessor changed after rendering')
        cap=by_id[obj['caption_ids'][0]]
        if cap['page']!=obj['page']:errors.append(f'{obj["id"]}: caption detached')
        float_box=fitz.Rect(obj['float_box'])
        for other in blocks:
            if other['page']!=obj['page'] or other['id'] in [obj['id'],cap['id']]:continue
            if not (float_box & fitz.Rect(other['box'])).is_empty:errors.append(f'{obj["id"]}: float overlaps {other["id"]}')
    pdf.close()
    if errors:raise ValueError('; '.join(errors[:12]))
    return blocks,dict(passed=True,pages=len(layout),cases=cases,checks=['visual object numbering','reference numbers','strict ToUnicode UTF-16','tree','PDF text','embedded fonts','bounds','float overlap','caption coupling','rendered predecessor','subtype','tree relation'])
