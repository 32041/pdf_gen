"""Document-level explicit hierarchy quota; visual labels never change semantic edges."""
import random
from core.planner import allocate
from content.benchmark_content import number


def apply_heading_policy(documents,cfg,seed):
    options=cfg.get('heading_numbering',{});share=options.get('explicit_document_ratio')
    for doc in documents:doc.title_alignment=cfg.get('title_alignment','center')
    if share is None:return
    rng=random.Random(seed+71413)
    flags=allocate({'yes':share,'no':1-share},len(documents),rng)
    families=allocate(options.get('explicit_families',{'arabic_dotted':.8,'alpha_dotted':.2}),flags.count('yes'),rng)
    rest=allocate(options.get('remaining_modes',{'none':.4,'mixed':.4,'misleading':.2}),flags.count('no'),rng)
    for doc,flag in zip(documents,flags):
        doc.explicit_hierarchy=flag=='yes'
        if doc.explicit_hierarchy:
            doc.numbering_mode='numbered';doc.numbering_family=families.pop()
        else:doc.numbering_mode=rest.pop()
        parents=list(dict.fromkeys(h.parent_id for h in doc.headings if not h.is_document_title))
        groups={p:i%2==0 for i,p in enumerate(parents)}
        count=0
        for h in doc.headings:
            if h.is_document_title:h.text=h.title;continue
            count+=1
            mode=doc.numbering_mode
            if mode=='none' or (mode=='mixed' and not groups[h.parent_id]):h.text=h.title
            elif mode=='misleading':h.text=f'{count}. '+h.title
            else:h.text=number(h.path,doc.numbering_family)+' '+h.title
