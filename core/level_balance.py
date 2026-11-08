"""Balance rendered heading populations without changing old semantic ownership edges."""
from collections import Counter
from core.benchmark_schema import Heading,validate_graph
from content.benchmark_content import number


def balance_levels(documents,cfg):
    if not cfg.get('auto_balance_levels'):return []
    constraints=cfg.get('level_share_constraints',{})
    lower=constraints.get('4,5',[0,1])[0]
    changes=[];used_domains=Counter()
    def share():
        headings=[h for d in documents for h in d.headings]
        return sum(h.level in (4,5) for h in headings)/len(headings)
    while share()+1e-12<lower:
        candidates=[]
        for doc in documents:
            children={h.parent_id for h in doc.headings}
            positions={h.id:i for i,h in enumerate(doc.headings)}
            prohibited={doc.headings[-1].id}
            prohibited.update(o.target_previous_id for o in doc.objects if o.target_subtype=='before_heading')
            for obj in doc.objects:
                if obj.target_subtype=='after_section':
                    start,end=positions[obj.owner_id],positions[obj.target_previous_id]
                    prohibited.update(h.id for h in doc.headings[start:end])
            for h in doc.headings:
                if h.id not in children and h.id not in prohibited and h.level in (3,4) and h.level<doc.target_depth:
                    candidates.append((used_domains[doc.kind],len(doc.augmentation_ids),doc.doc_id,-h.level,doc,h))
        if not candidates:raise ValueError('Cannot reach deep-level share without violating structural/ownership constraints')
        _,_,_,_,doc,parent=min(candidates,key=lambda x:x[:4])
        next_id=max(int(h.id[1:]) for h in doc.headings)+1
        new=[]
        for index in (1,2):
            title=parent.title+('实施细则' if index==1 else '复核细则') if doc.language=='zh' else parent.title+(' implementation detail' if index==1 else ' review detail')
            h=Heading(f'h{next_id+index-1:04d}',title,parent.level+1,parent.id,parent.path+(index,))
            numbered=doc.numbering_mode in ('numbered','misleading') or (doc.numbering_mode=='mixed' and parent.text!=parent.title)
            h.text=(number(h.path,doc.numbering_family)+' ' if numbered else '')+h.title
            new.append(h);doc.augmentation_ids.append(h.id)
        pos=doc.headings.index(parent)+1;doc.headings[pos:pos]=new
        if doc.numbering_mode=='misleading':
            n=0
            for h in doc.headings:
                if h.is_document_title:h.text=h.title
                else:n+=1;h.text=f'{n}. '+h.title
        used_domains[doc.kind]+=1;validate_graph(doc)
        changes.append({'doc_id':doc.doc_id,'parent_id':parent.id,'added_ids':[h.id for h in new],'level':parent.level+1})
    return changes
