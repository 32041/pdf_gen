"""Allocate global integer quotas, then assign feasible semantic ownership scenarios."""
from collections import Counter,defaultdict
import random
from core.planner import allocate
from core.benchmark_schema import TableObject, relation, validate_graph


def _pairs(doc,subtype):
    hs=doc.headings;result=defaultdict(list)
    if subtype=='normal':
        for h in hs: result['same'].append((h.id,h.id))
    elif subtype=='before_heading':
        for i in range(1,len(hs)):
            owner,prev=hs[i],hs[i-1]
            result[relation(owner.id,prev.id,hs)].append((owner.id,prev.id))
    else:
        # Far floats and plates use the final heading, so delayed content does not
        # silently change the predecessor of earlier after-section scenarios.
        candidates=hs[-1:] if subtype in ('far_float','plate') else hs[1:]
        for g in candidates:
            gi=hs.index(g)
            for owner in hs[:gi]:
                result[relation(owner.id,g.id,hs)].append((owner.id,g.id))
        indices={h.id:i for i,h in enumerate(hs)}
        for key in result:
            result[key].sort(key=lambda p:indices[p[1]]-indices[p[0]])
    return result


def assign_objects(documents,cfg,rng):
    per_doc=cfg['objects_per_document']
    total=per_doc*len(documents)
    if not total: return {'objects':0,'subtypes':{},'relations_by_subtype':{}}
    flags=allocate({'conflict':cfg['conflict_ratio'],'normal':1-cfg['conflict_ratio']},total,rng)
    n_conflict=flags.count('conflict')
    subtypes=allocate(cfg['subtype_weights'],n_conflict,rng)
    counts=Counter(subtypes)
    normal=total-n_conflict
    slots=[[] for _ in documents]
    capacities=[per_doc for _ in documents]
    plates=counts['plate'];group_index=0
    while plates:
        size=min(plates,cfg['plate_max_objects'])
        if plates-size==1 and size>2: size-=1
        companion=0
        if size==1:
            if normal<1: raise ValueError('A plate requires >=2 objects; increase count or normal share.')
            companion=1;normal-=1
        eligible=[i for i,cap in enumerate(capacities) if cap>=size+companion]
        if not eligible: raise ValueError('Plate groups do not fit objects_per_document; increase it or lower plate_max_objects.')
        di=max(eligible,key=lambda i:capacities[i])
        group_index+=1;group=f'plate-{group_index}'
        slots[di].extend([{'subtype':'plate','plate_group':group} for _ in range(size)])
        if companion: slots[di].append({'subtype':'normal','plate_group':group})
        capacities[di]-=size+companion;plates-=size
    other=[s for s in subtypes if s!='plate']+['normal']*normal
    rng.shuffle(other)
    for subtype in other:
        available=[i for i,c in enumerate(capacities) if c]
        di=rng.choice(available)
        slots[di].append({'subtype':subtype,'plate_group':None});capacities[di]-=1
    flat=[]
    for di,items in enumerate(slots):
        for item in items:
            item['di']=di;item['pairs']=_pairs(documents[di],item['subtype'])
            if item['subtype']=='normal' and item['plate_group']:
                h=documents[di].headings[-1];item['pairs']={'same':[(h.id,h.id)]}
            flat.append(item)
    relation_targets={}
    for subtype in ['normal','after_section','far_float','before_heading','plate']:
        jobs=[j for j in flat if j['subtype']==subtype]
        weights={'same':1} if subtype=='normal' else cfg['relation_weights'][subtype]
        desired=allocate(weights,len(jobs),rng)
        relation_targets[subtype]=dict(Counter(desired))
        # Capacity matching preserves exact integer relation quotas; impossible
        # combinations fail clearly rather than silently changing distributions.
        matched={}
        def match(ji,seen):
            possible=[i for i,r in enumerate(desired) if jobs[ji]['pairs'].get(r)]
            rng.shuffle(possible)
            for ri in possible:
                if ri in seen: continue
                seen.add(ri)
                if ri not in matched or match(matched[ri],seen):
                    matched[ri]=ji;return True
            return False
        for ji in sorted(range(len(jobs)),key=lambda i:len(jobs[i]['pairs'])):
            if not match(ji,set()):
                raise ValueError(f'Infeasible {subtype} relation quota at these depths. Increase depth/count or adjust relation_weights.')
        for ri,ji in matched.items():jobs[ji]['relation']=desired[ri]
    used=Counter()
    for di,doc in enumerate(documents):
        by_id={h.id:h for h in doc.headings}
        items=slots[di]
        for oi,item in enumerate(items,1):
            pairs=item['pairs'][item['relation']]
            # Spread before-heading objects to prevent a pile too large for a column.
            if item['subtype']=='before_heading':
                best=min(used[(di,p[0])] for p in pairs)
                pairs=[p for p in pairs if used[(di,p[0])]==best]
            elif item['subtype']=='after_section': pairs=pairs[:min(4,len(pairs))]
            owner,prev=rng.choice(pairs)
            used[(di,owner)]+=1
            topic=by_id[owner].title
            caption=(f'表 {oi}：{topic}的分期记录' if doc.language=='zh' else f'Table {oi}: Period records for {topic.lower()}')
            reference=(f'{topic}的分期记录见表 {oi}。' if doc.language=='zh' else f'Period records for {topic.lower()} are shown in Table {oi}.')
            rows=[['Period','Output','Cost','Balance']]+[[str(a),f'{b:.2f}',f'{c:.2f}',f'{d:.2f}'] for a,b,c,d in zip(doc.facts['periods'],doc.facts['output'],doc.facts['cost'],doc.facts['balance'])]
            doc.objects.append(TableObject(f'o{oi:04d}',owner,prev,item['subtype'],item['relation'],topic,caption,rows,reference,item['plate_group']))
        for obj in doc.objects:
            if obj.plate_group and sum(o.plate_group==obj.plate_group for o in doc.objects)>=5:obj.row_height=13
        validate_graph(doc)
    return {'objects':total,'conflicts':n_conflict,'subtypes':dict(counts),'relations_by_subtype':relation_targets}


def replan_bindings(doc,seed,previous_layout):
    """Reject previous rendering; create a NEW semantic plan and fully render again.

    This never relabels an existing PDF. Captions and references are regenerated
    together with ownership before the next rendering attempt.
    """
    rng=random.Random(seed);pages={}
    for p in previous_layout:
        for op in p['operations']:
            if op['type']=='title':pages.setdefault(op['block_id'],p['page'])
    indices={h.id:i for i,h in enumerate(doc.headings)};headings={h.id:h for h in doc.headings};loads=Counter()
    for obj in sorted(doc.objects,key=lambda o:o.target_subtype!='before_heading'):
        if obj.target_subtype not in ('after_section','before_heading') or obj.plate_group:continue
        pairs=list(_pairs(doc,obj.target_subtype)[obj.target_relation])
        if obj.owner_locked:pairs=[pair for pair in pairs if pair[0]==obj.owner_id]
        if not pairs:raise ValueError('No placement repair preserves the locked semantic owner')
        rng.shuffle(pairs)
        if obj.target_subtype=='before_heading':
            owner,prev=min(pairs,key=lambda p:loads[('before',p[0])]);loads[('before',owner)]+=1
        else:
            owner,prev=min(pairs,key=lambda p:(max(0,pages.get(p[1],0)-pages.get(p[0],0)),loads[('after',p[1])],indices[p[1]]-indices[p[0]]))
            loads[('after',prev)]+=1
        obj.owner_id=owner;obj.target_previous_id=prev;obj.topic=headings[owner].title
        from core.object_numbering import set_visible_number
        set_visible_number(obj,doc.language,obj.display_number or int(obj.id[1:]))
    validate_graph(doc)
