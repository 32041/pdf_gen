"""Validate saved PDF geometry and compare actual text with the pagination record."""
import json
import pymupdf as fitz


def audit(folder,doc):
    plan=json.loads((folder/'layout.json').read_text(encoding='utf-8'))
    pdf=fitz.open(folder/'document.pdf')
    assets=[]
    refs={}
    placed={}
    for page in plan['pages']:
        for op in page['operations']:
            if op.get('reference_id') is not None: refs[op['reference_id']]=(page['page'],op)
            if op['kind']=='asset': placed[op['asset_id']]=(page['page'],op,page['float_only'])
    missing_text=[]
    out_of_bounds=[]
    unembedded=[]
    invalid_text=[]
    for pno,page in enumerate(pdf,1):
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    if '\x00' in span['text'] or '\ufffd' in span['text']:
                        invalid_text.append(dict(page=pno,text=span['text']))
                    box=fitz.Rect(span['bbox'])
                    if box.x0 < -.5 or box.y0 < -.5 or box.x1 > page.rect.width+.5 or box.y1 > page.rect.height+.5:
                        out_of_bounds.append(dict(page=pno,text=span['text'],bbox=list(box)))
        for font in page.get_fonts():
            if not pdf.extract_font(font[0])[3]: unembedded.append(dict(page=pno,font=font[3]))
    for aid,target in enumerate(doc.placements):
        rp,ref=refs[aid]
        ap,asset,float_only=placed[aid]
        needle=('趋势见图' if aid==0 else '明细见表') if doc.language=='zh' else ('The trend is shown' if aid==0 else 'Details are reported')
        cap=('模拟产出与成本趋势' if aid==0 else '统一口径的分期数据') if doc.language=='zh' else ('Simulated output and cost' if aid==0 else 'Canonical period ledger')
        actual_refs=pdf[rp-1].search_for(needle)
        actual_caps=pdf[ap-1].search_for(cap)
        if not actual_refs or not actual_caps: missing_text.append(aid)
        if ap != rp:
            order='later_page' if ap>rp else 'earlier_page'
        else:
            mid=pdf[ap-1].rect.width/2
            def key(box): return (int(doc.kind=='paper' and box[0]>=mid),box[1])
            order='same_page_after' if key(asset['bbox'])>key(ref['bbox']) else 'same_page_before'
        assets.append(dict(id=aid,target=target,reference_page=rp,asset_page=ap,page_delta=ap-rp,actual_order=order,
                           actual_location='float_page' if float_only else ('top' if target=='top' else 'bottom' if target=='bottom' else 'in_flow'),
                           reference_bbox=list(actual_refs[0]) if actual_refs else None,asset_bbox=asset['bbox'],
                           caption_bbox=list(actual_caps[0]) if actual_caps else None))
    result=dict(renderer='python-v0.2',pages=len(pdf),assets=assets,missing_reference_or_caption=missing_text,
                out_of_bounds_text=out_of_bounds,unembedded_fonts=unembedded,invalid_text_spans=invalid_text,
                position_measurement='Full float boxes recorded by paginator; reference/caption text and font embedding checked in saved PDF.')
    pdf.close()
    if missing_text or out_of_bounds or unembedded or invalid_text:
        raise RuntimeError('Rendered PDF audit failed: '+json.dumps(result,ensure_ascii=False))
    return result
