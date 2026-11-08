"""Visible numbers follow final reading order; internal object IDs remain stable."""


def set_visible_number(obj,language,number):
    obj.display_number=number
    figure=getattr(obj,'object_type','table')=='figure'
    label=('图' if figure else '表') if language=='zh' else ('Figure' if figure else 'Table')
    topic=obj.topic
    suffix=obj.caption_text or (f'{topic}的分期记录' if language=='zh' else f'Period records for {topic.lower()}')
    obj.caption=f'{label} {number}'+('：' if language=='zh' else ': ')+suffix
    if obj.reference_template:obj.reference_text=obj.reference_template.replace('{number}',str(number))
    else:obj.reference_text=f'{topic}见{label} {number}。' if language=='zh' else f'See {label} {number} for {topic.lower()}.'


def stabilize_numbering(doc,paginator_factory,max_passes=12):
    from core.benchmark_audit import collect_blocks
    by_id={o.id:o for o in doc.objects}
    for iteration in range(1,max_passes+1):
        pages=paginator_factory(doc).build()
        layout=[dict(page=i+1,operations=p['operations']) for i,p in enumerate(pages)]
        tables=[b for b in collect_blocks(layout) if b['type'] in ('table','figure')]
        changed=False
        from collections import Counter
        counters=Counter()
        for block in tables:
            counters[block['type']]+=1;number=counters[block['type']]
            obj=by_id[block['id']];old=(obj.caption,obj.reference_text)
            set_visible_number(obj,doc.language,number)
            changed|=old!=(obj.caption,obj.reference_text)
        if not changed:return pages,iteration
    raise ValueError('Visible object numbering did not stabilize; batch rejected')
