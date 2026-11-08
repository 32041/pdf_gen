"""Validated LLM content on a fixed semantic graph, with hash-addressed offline replay."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib,json,re,copy,unicodedata
from content.llm_topics import brief
from content.deepseek_client import DeepSeekClient,ContentAPIError
from core.benchmark_schema import validate_graph
from core.object_numbering import set_visible_number

SCHEMA_VERSION='llm-content-v1'
FACT_PATTERN=re.compile(r'\[\[F:([a-z0-9_]+)\]\]')


def fact_values(doc):
    f=doc.facts;values={}
    for key in ['output','cost','balance']:
        values.update({f'{key}_{i+1}':f'{v:.2f}' for i,v in enumerate(f[key])})
    values.update({f'year_{i+1}':str(v) for i,v in enumerate(f['periods'])})
    values.update(year_last=str(f['periods'][-1]),duration_weeks='12',sessions='24',teaching_hours='48',
                  response_days='2',review_days='5',agreement_months='12',sample_count='240',sites_count='4')
    values['output_growth_percent']=f"{(f['output'][-1]/f['output'][0]-1)*100:.1f}"
    return values


def make_request(doc,options):
    return dict(schema=SCHEMA_VERSION,kind=doc.kind,language=doc.language,subject=brief(doc),seed=doc.seed,
                has_title=doc.has_title,nodes=[dict(id=h.id,parent_id=h.parent_id,level=h.level,is_document_title=h.is_document_title) for h in doc.headings],
                objects=[dict(id=o.id,owner_id=o.owner_id,cell_width=((doc.page_width-2*doc.margin_pt) if o.plate_group else (doc.page_width-2*doc.margin_pt-20*(doc.columns-1))/doc.columns)/4,row_height=(26 if o.row_height>=19 else o.row_height)) for o in doc.objects],
                facts=fact_values(doc),table_mode=options.get('table_mode','llm'),continuation_count=options.get('continuation_count',32))


def request_hash(request,model):
    return hashlib.sha256(json.dumps({'request':request,'model':model},sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()


def messages_for(request):
    instructions='''Write ONE coherent fictional document in the requested genre and language, as a JSON object. This is synthetic document research, not real financial, legal or official disclosure.
The node IDs, parent edges, levels and object owner IDs are immutable. Invent a meaningful, non-repetitive outline that fits that exact tree; do not use unrelated generic headings. Every section develops the SAME subject and its parent section. Real institutions, citations, legal statute identifiers and real financial claims are prohibited.
Return: {"document_title":str,"sections":[{"id":str,"title":str,"paragraph":str}],"continuations":[str,...],"tables":[{"id":str,"caption":str,"reference":str,"rows":[[str,str,str,str],...]}]}.
Include EVERY requested node exactly once and EVERY object exactly once. Document-title nodes must use document_title as their title. Heading titles contain no numbering, no Markdown, no raw IDs, and are unique (at most eight English words / eighteen Chinese characters). Write one substantial paragraph per node, approximately sixty to ninety English words or one hundred to one hundred sixty Chinese characters. Explain concrete decisions, evidence, methods, duties or questions appropriate to that section; do not repeat a boilerplate paragraph. Contracts must have coherent scope and obligations; syllabus must cover teaching and assessment; exam paper must contain actual scenario questions rather than a report. Papers must distinguish simulated observations from causal claims.
All numeric claims in visible text MUST use [[F:fact_key]] tokens from the supplied facts map. No raw digits in titles, prose, captions or table cells; no invented numeric measurements. Facts output/cost/balance are simulated canonical indicators (revenue/cost/operating surplus only for an annual report); teaching/schedule facts are available when appropriate. You need not mention every fact. Arithmetic is already computed by Python. output_growth_percent is cumulative from the first period to the last, NOT year-on-year growth. Use plain text, no formulas, links or bullet markup.
Tables belong to their owner node's subject. Captions are natural descriptions WITHOUT a table number. Do not simply copy the owner's exact heading title. reference must contain exactly one {number}, as 'Table {number}' for English or '表 {number}' for Chinese. No other table numbers or table references in body paragraphs. Python adds the final references and numbers after pagination. Each table has three to six rows including a header, and exactly four columns; cells must be short (<=18 English characters or <=8 Chinese characters), meaningful, and may use fact tokens. Prefer qualitative checklists, schedules, criteria or comparison matrices where numeric indicators are irrelevant; do not put the same revenue table under every topic. If table_mode=derived, rows may be omitted; use canonical output/cost/balance records in that case.
Generate approximately the requested continuation_count DISTINCT short paragraphs (at least sixteen), around thirty-five to fifty-five English words or seventy to one hundred Chinese characters each. These are coherent supporting observations, limitations, record checks and implementation considerations for this same document. They must be broadly applicable within this document, without claiming to be a new section, without heading IDs and without references. They are used only if pagination requires extra context. Do not repeat any primary paragraph or another continuation. Do not add 'synthetic example' boilerplate to each section; the renderer labels the document separately.
Output valid JSON only.'''
    return [{'role':'system','content':instructions},{'role':'user','content':json.dumps(request,ensure_ascii=False)}]


def validate_bundle(bundle,request):
    if not isinstance(bundle,dict):raise ValueError('Response must be a JSON object')
    facts=request['facts'];lang=request['language']
    def text(value,label,max_length=1500,reference=False,context=''):
        if not isinstance(value,str) or not value.strip() or len(value)>max_length:raise ValueError(f'{label}: missing or excessive text')
        value=value.strip().replace('\u200b','').replace('\ufeff','')
        if '\ufffd' in value or '\x00' in value:raise ValueError(f'{label}: invalid Unicode replacement/control character')
        if label in ('paragraph','continuation'):
            value=re.sub(r'Table\s*\d+','the supporting table',value,flags=re.I)
            value=re.sub(r'表\s*\d+','配套记录表',value)
        if label=='caption':value=re.sub(r'^(?:Table|表)\s*\d+\s*[:：.-]?\s*','',value,flags=re.I)
        if reference:
            value=re.sub(r'Table\s*\d+','Table {number}',value,flags=re.I)
            value=re.sub(r'表\s*\d+','表 {number}',value)
        keys=FACT_PATTERN.findall(value)
        if any(k not in facts for k in keys):raise ValueError(f'{label}: unknown fact tokens {[k for k in keys if k not in facts]}; use only the supplied fact keys')
        if '[[F:output_growth_percent]]' in value:
            value=re.sub(r'year[ -]on[ -]year', 'cumulative', value, flags=re.I).replace('同比','累计')
        stripped=FACT_PATTERN.sub('',value)
        if reference:stripped=stripped.replace('{number}','')
        def schedule(match):
            values=[int(n) for n in re.findall(r'\d+',match[0])]
            return '' if values and all(0<=v<=12 for v in values) else match[0]
        stripped=re.sub(r'\b\d+(?:\s*[-–]\s*\d+)?\s*(?:months?|weeks?)\b',schedule,stripped,flags=re.I)
        if re.search(r'month|week|月|周',context,re.I) and re.fullmatch(r'\d+\s*[-–]\s*\d+',stripped) and all(int(v)<=12 for v in re.findall(r'\d+',stripped)):
            stripped=''
        if re.search(r'target|threshold|requirement|标准|阈值|目标|要求',context,re.I) and re.fullmatch(r'[≥≤<>]?\s*\d+(?:\.\d+)?%',stripped) and float(re.search(r'\d+(?:\.\d+)?',stripped)[0])<=100:
            stripped=''
        numeric_text=re.sub(r'\b(?:[A-Z]{1,6}-?\d+(?:\.\d+)?|[A-Za-z]{1,8}-\d+)\b','',stripped)
        if re.search(r'\d',numeric_text):
            allowed=set(facts.values())
            numerals=re.findall(r'(?<![\d.])-?\d+(?:\.\d+)?',numeric_text)
            if any(n not in allowed for n in numerals):raise ValueError(f'{label}: unregistered values {[n for n in numerals if n not in allowed]} in {stripped[:90]!r}; use fact tokens or qualitative labels')
        if '[[' in stripped or ']]' in stripped or re.search(r'\bh\d{4}\b|\bo\d{4}\b',stripped):raise ValueError(f'{label}: unresolved ID/token')
        if not reference and re.search(r'(?:Table|Figure|表|图)\s*\{?number|\{number\}',value,re.I):raise ValueError(f'{label}: manual object reference')
        return FACT_PATTERN.sub(lambda m:facts[m[1]],value)
    document_title=text(bundle.get('document_title'),'document_title',160)
    sections=bundle.get('sections',[])
    expected={n['id'] for n in request['nodes']}
    if not isinstance(sections,list) or {s.get('id') for s in sections}!=expected or len(sections)!=len(expected):raise ValueError('Section ID set changed')
    normalized={'document_title':document_title,'sections':{},'continuations':[],'tables':{}}
    for section in sections:
        title=text(section.get('title'),'section title',160)
        body=text(section.get('paragraph'),'paragraph',1800)
        if len(body)<(90 if lang=='en' else 45):raise ValueError('Paragraph is too short')
        normalized['sections'][section['id']]={'title':title,'paragraph':body}
    names=[s['title'] for s in normalized['sections'].values()]
    if len(set(names))!=len(names):raise ValueError('Duplicate heading titles')
    for node in request['nodes']:
        if node['is_document_title'] and normalized['sections'][node['id']]['title']!=document_title:raise ValueError('Document-title node differs from document_title')
    notes=bundle.get('continuations',[])
    if not isinstance(notes,list) or not 16<=len(notes)<=192:raise ValueError('Need a usable pool of distinct continuation paragraphs (16..192)')
    normalized['continuations']=[text(n,'continuation',1400) for n in notes]
    prose=[s['paragraph'] for s in normalized['sections'].values()]+normalized['continuations']
    if len(set(prose))!=len(prose):raise ValueError('Repeated paragraph')
    tables=bundle.get('tables',[]);expected_objects={o['id'] for o in request['objects']}
    if not isinstance(tables,list) or {t.get('id') for t in tables}!=expected_objects or len(tables)!=len(expected_objects):raise ValueError('Table ID set changed')
    for table in tables:
        caption=text(table.get('caption'),'caption',160)
        ref=text(table.get('reference'),'reference',260,True)
        if ref.count('{number}')!=1 or not re.search(r'(?:Table|表)\s*\{number\}',ref):raise ValueError('Reference needs Table {number} / 表 {number}')
        rows=table.get('rows')
        if request['table_mode']=='llm':
            if not isinstance(rows,list) or not 3<=len(rows)<=6 or any(not isinstance(r,list) or len(r)!=4 for r in rows):raise ValueError('Tables need three to six rows and four columns')
            corrected=[]
            for row in rows:
                if any('[[F:output_growth_percent]]' in str(c) for c in row):row=[re.sub(r'year[ -]on[ -]year','Cumulative',str(c),flags=re.I).replace('同比','累计') for c in row]
                context=' '.join(str(c) for c in rows[0]+row)
                corrected.append([text(c,'table cell',120,context=context) for c in row])
            rows=corrected
            from render.table_cells import cell_layout
            geometry=next(o for o in request['objects'] if o['id']==table['id'])
            for row in rows:
                for value in row:cell_layout(value,geometry['cell_width'],geometry['row_height'])
        else:rows=None
        normalized['tables'][table['id']]={'caption':caption,'reference':ref,'rows':rows}
    return normalized


def apply_bundle(doc,validated,provenance):
    old={h.id:h.title for h in doc.headings}
    doc.title=validated['document_title']
    for h in doc.headings:
        prefix=h.text[:-len(h.title)] if h.text.endswith(h.title) else ''
        h.title=validated['sections'][h.id]['title'];h.text=prefix+h.title
    by_id={h.id:h for h in doc.headings}
    for obj in doc.objects:
        data=validated['tables'][obj.id];obj.topic=by_id[obj.owner_id].title
        obj.content_provenance={'table_content_provider':provenance.get('provider'),'model':provenance.get('model'),'request_hash':provenance.get('request_hash')}
        obj.caption_text=data['caption'];obj.reference_template=data['reference'];obj.owner_locked=True
        if data['reference'].strip() in ('表 {number}','Table {number}'):
            obj.reference_template='相关记录与要求见表 {number}。' if doc.language=='zh' else 'Supporting records are presented in Table {number}.'
        if data['rows'] is not None:
            obj.rows=data['rows']
            if obj.row_height>=19:obj.row_height=max(obj.row_height,26)
        set_visible_number(obj,doc.language,obj.display_number or int(obj.id[1:]))
    doc.content={'sections':validated['sections'],'continuations':validated['continuations'],'provenance':provenance}
    validate_graph(doc)


def prepare_documents(documents,cfg):
    mode=cfg.get('content_provider','template')
    if mode=='template':return
    options=cfg['llm'];model=options['model']
    root=Path(__file__).resolve().parents[1]
    directory=Path(options.get('library_dir','content_library'))
    if not directory.is_absolute():directory=root/directory
    directory.mkdir(parents=True,exist_ok=True)
    client=DeepSeekClient(model,options.get('timeout_seconds',180),options=options)
    def prepare(doc):
        request=make_request(doc,options);digest=request_hash(request,model);path=directory/(digest+'.json')
        if path.exists():
            saved=json.loads(path.read_text(encoding='utf-8'))
            if cfg.get('content_provider')=='llm' and ('\ufffd' in json.dumps(saved['response'],ensure_ascii=False) or '\x00' in json.dumps(saved['response'],ensure_ascii=False)):
                saved['response'],repair_meta=repair_unicode_response(saved['response'],request,client)
                saved['provenance']['unicode_repair_usage']=repair_meta
                path.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
            if saved.get('request')!=request:raise ValueError('Content library hash/request mismatch')
            raw=saved['response']
            if saved.get('extra_continuations'):
                raw={**raw,'continuations':raw['continuations']+saved['extra_continuations']}
                validation_request={**request,'continuation_count':len(raw['continuations'])}
            else:validation_request=request
            validated=validate_bundle(raw,validation_request)
            provenance={**saved['provenance'],'cache_hit':True}
        else:
            if mode=='library':raise ContentAPIError(f'No offline content for {doc.kind}/{doc.doc_id}, seed {doc.seed}. Use the supplied llm_demo config or generate with --content llm.')
            base_request={**request,'nodes':[n for n in request['nodes'] if n['id'] not in doc.augmentation_ids]}
            base_digest=request_hash(base_request,model);base_path=directory/(base_digest+'.json')
            if doc.augmentation_ids and base_path.exists():
                base=json.loads(base_path.read_text(encoding='utf-8'))
                response,meta,addition_response=augment_cached_article(doc,request,base,client,options)
                validated=validate_bundle(response,request)
                provenance={**base['provenance'],'request_hash':digest,'base_request_hash':base_digest,'augmentation_usage':meta,'cache_hit':False}
                temporary=path.with_suffix('.pending');temporary.write_text(json.dumps({'request':request,'response':response,'provenance':provenance,'base_snapshot':base,'augmentation_response':addition_response},ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
                apply_bundle(doc,validated,provenance)
                print(f'Content extended for depth quota: {doc.kind}/{doc.doc_id}',flush=True)
                return
            debug=root/'.cache'/'llm_validation'
            for diagnostic in sorted(debug.glob(digest+'-*.json'),reverse=True) if debug.exists() else []:
                draft=json.loads(diagnostic.read_text(encoding='utf-8'))
                if draft.get('request')!=request:continue
                try:
                    response,table_meta=complete_missing_tables(draft['response'],request,client)
                    validated=validate_bundle(response,request)
                except (ValueError,KeyError,TypeError):continue
                provenance={'provider':'deepseek','model':model,'requested_model':model,'request_hash':digest,'schema':SCHEMA_VERSION,'usage':None,
                            'recovered_draft':True,'table_supplement_usage':table_meta,'cache_hit':False,'validation_retries':0}
                path.write_text(json.dumps({'request':request,'response':response,'provenance':provenance,'original_draft':draft['response']},ensure_ascii=False,indent=2),encoding='utf-8')
                apply_bundle(doc,validated,provenance)
                print(f'Content recovered with completed tables: {doc.kind}/{doc.doc_id}',flush=True)
                return
            messages=messages_for(request);errors=[]
            for retry in range(options.get('validation_retries',2)+1):
                response,meta=client.complete_json(messages,options.get('max_tokens',14000))
                try:
                    response,repair_meta=repair_unicode_response(response,request,client)
                    if repair_meta:meta['unicode_repair_usage']=repair_meta
                    response,table_meta=complete_missing_tables(response,request,client)
                    if table_meta:meta['table_supplement_usage']=table_meta
                    validated=validate_bundle(response,request);break
                except (ValueError,TypeError,KeyError) as exc:
                    errors.append(str(exc))
                    debug=root/'.cache'/'llm_validation';debug.mkdir(parents=True,exist_ok=True)
                    (debug/(digest+f'-{retry}.json')).write_text(json.dumps({'request':request,'response':response,'error':str(exc)},ensure_ascii=False,indent=2),encoding='utf-8')
                    if retry>=options.get('validation_retries',2):raise ContentAPIError('Generated content failed validation: '+'; '.join(errors))
                    messages=messages_for(request)+[{'role':'assistant','content':json.dumps(response,ensure_ascii=False)},{'role':'user','content':'Repair the complete JSON above. Keep valid content, and fix this validation error: '+str(exc)+'. Preserve ALL exact node and object IDs from the original request. Return the complete JSON, never omit tables or sections.'}]
            provenance={'provider':'deepseek','requested_model':model,**meta,'request_hash':digest,'schema':SCHEMA_VERSION,'validation_retries':len(errors),'cache_hit':False}
            temporary=path.with_suffix('.pending');temporary.write_text(json.dumps({'request':request,'response':response,'provenance':provenance},ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
        apply_bundle(doc,validated,provenance)
        from render.table_cells import cell_layout
        width=(doc.page_width-2*doc.margin_pt-20*(doc.columns-1))/doc.columns
        for obj in doc.objects:
            table_width=doc.page_width-2*doc.margin_pt if obj.plate_group else width
            for row in obj.rows:
                for value in row:cell_layout(str(value),table_width/4,obj.row_height)
        print(f'Content ready: {doc.kind}/{doc.doc_id} ({doc.language}, {len(doc.headings)} headings)',flush=True)
    with ThreadPoolExecutor(max_workers=options.get('workers',2)) as executor:
        futures=[executor.submit(prepare,doc) for doc in documents]
        try:
            for future in as_completed(futures):future.result()
        except BaseException:
            for future in futures:future.cancel()
            raise


def extend_continuations(doc,cfg):
    """Generate extra unique context only when actual pagination exhausts its pool."""
    if cfg.get('content_provider')!='llm':raise ContentAPIError('Offline continuation pool exhausted; use llm mode to extend the cached article')
    options=cfg['llm'];root=Path(__file__).resolve().parents[1];directory=Path(options['library_dir'])
    if not directory.is_absolute():directory=root/directory
    path=directory/(doc.content['provenance']['request_hash']+'.json')
    saved=json.loads(path.read_text(encoding='utf-8'))
    extras=saved.get('extra_continuations',[])
    if len(extras)>=64:raise ContentAPIError('Continuation extension budget reached; reduce object count or page-distance demands')
    request=saved['request'];client=DeepSeekClient(options['model'],options.get('timeout_seconds',180),options=options)
    prompt={'subject':request['subject'],'language':request['language'],'facts':request['facts'],
            'existing_continuations':saved['response']['continuations']+extras,'new_count':32}
    messages=[{'role':'system','content':'Return JSON {"continuations":[str,...]}. Write exactly thirty-two NEW, distinct short supporting paragraphs for this same synthetic document. Each is thirty-five to fifty-five English words or seventy to one hundred Chinese characters. No headings, raw IDs, table references, raw digits, or repeated paragraphs. Every numeric claim uses [[F:fact_key]] from the facts map. These paragraphs must add coherent implementation details, evidence limitations, record checks or practical qualifications; avoid padding language. Do not repeat the supplied paragraphs.'},
              {'role':'user','content':json.dumps(prompt,ensure_ascii=False)}]
    for attempt in range(3):
        response,meta=client.complete_json(messages,6500)
        try:
            new=response['continuations']
            if not isinstance(new,list) or not 16<=len(new)<=64:raise ValueError('Need 16..64 distinct extra paragraphs')
            combined={**saved['response'],'continuations':saved['response']['continuations']+extras+new}
            validated=validate_bundle(combined,{**request,'continuation_count':len(combined['continuations'])})
            break
        except (ValueError,KeyError,TypeError) as exc:
            if attempt==2:raise ContentAPIError('Extra context failed validation') from None
            messages.append({'role':'user','content':'Validation error: '+str(exc)+'. Return all thirty-two new paragraphs again.'})
    saved['extra_continuations']=extras+new;saved['provenance'].setdefault('supplement_usage',[]).append(meta)
    pending=path.with_suffix('.pending');pending.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8');pending.replace(path)
    doc.content['continuations']=validated['continuations'];doc.content['provenance']=saved['provenance']
    print(f'Context extended: {doc.kind}/{doc.doc_id}, {len(validated["continuations"])} paragraphs available',flush=True)


def augment_cached_article(doc,request,base,client,options):
    """Only generate newly planned sibling sections; retain the original article and owners."""
    additions=set(doc.augmentation_ids);existing={s['id']:s for s in base['response']['sections']}
    prompt={'subject':request['subject'],'language':request['language'],'facts':request['facts'],
            'document_title':base['response']['document_title'],
            'existing_titles':[s['title'] for s in existing.values()],
            'new_sections':[{'id':n['id'],'parent_id':n['parent_id'],'level':n['level'],
                             'parent_title':existing.get(n['parent_id'],{'title':'New planned parent'})['title'],
                             'parent_paragraph':existing.get(n['parent_id'],{'paragraph':'Develop together with the other new subsections.'})['paragraph']} for n in request['nodes'] if n['id'] in additions]}
    messages=[{'role':'system','content':'Return JSON {"sections":[{"id":str,"title":str,"paragraph":str},...]}. Write only the requested new sibling subsections as coherent details of their supplied parent. Do not change existing article content or introduce a different subject. Titles must be unique, unnumbered, at most eight English words/eighteen Chinese characters. Paragraphs: sixty to ninety English words or one hundred to one hundred sixty Chinese characters. All numeric claims use [[F:fact_key]] tokens from supplied facts; no raw IDs, headings, table references or Markdown in prose. Do not repeat existing titles.'},
              {'role':'user','content':json.dumps(prompt,ensure_ascii=False)}]
    for attempt in range(3):
        response,meta=client.complete_json(messages,3000)
        try:
            added=response['sections']
            if {s['id'] for s in added}!=additions or len(added)!=len(additions):raise ValueError('Missing added section IDs')
            combined=copy.deepcopy(base['response'])
            by_id={s['id']:s for s in combined['sections']};by_id.update({s['id']:s for s in added})
            combined['sections']=[by_id[n['id']] for n in request['nodes']]
            combined['continuations']+=base.get('extra_continuations',[])
            validate_bundle(combined,request)
            return combined,meta,response
        except (ValueError,KeyError,TypeError) as exc:
            if attempt==2:raise ContentAPIError('Added subsections failed validation: '+str(exc)) from None
            messages.append({'role':'user','content':'Repair only the requested new sections: '+str(exc)})


def complete_missing_tables(response,request,client):
    expected={o['id']:o for o in request['objects']}
    if not isinstance(response,dict) or not isinstance(response.get('tables',[]),list) or any(not isinstance(t,dict) for t in response.get('tables',[])):return response,[]
    present={t.get('id'):t for t in response.get('tables',[])}
    missing=set(expected)-set(present)
    if not missing:return response,[]
    if set(present)-set(expected) or len(present)!=len(response.get('tables',[])):return response,[]
    reduced={**request,'objects':[o for o in request['objects'] if o['id'] in present]}
    validate_bundle(response,reduced)  # Do not spend another call on an invalid article body.
    sections={s['id']:s for s in response['sections']}
    prompt={'language':request['language'],'subject':request['subject'],'facts':request['facts'],
            'tables':[dict(**o,owner_title=sections[o['owner_id']]['title'],owner_paragraph=sections[o['owner_id']]['paragraph']) for o in request['objects'] if o['id'] in missing]}
    messages=[{'role':'system','content':'Return JSON {"tables":[{"id":str,"caption":str,"reference":str,"rows":[[str,...],...]}]}. Generate ONLY the requested missing tables, each tied to its owner section. Include EVERY requested ID exactly once. Captions have no numbers. References contain exactly one Table {number} / 表 {number}. Each table has three to six rows including header, exactly four columns; cells short, preferably qualitative, <=18 English characters / <=8 Chinese characters. All numeric observations use supplied [[F:fact_key]] tokens. Do not invent values. Use natural captions rather than copying heading titles.'},
              {'role':'user','content':json.dumps(prompt,ensure_ascii=False)}]
    for attempt in range(3):
        added,meta=client.complete_json(messages,4500)
        try:
            tables=added['tables']
            if {t['id'] for t in tables}!=missing or len(tables)!=len(missing):raise ValueError('Missing table ID set changed')
            combined=copy.deepcopy(response);combined['tables']+=tables
            validate_bundle(combined,request)
            return combined,[meta]
        except (ValueError,KeyError,TypeError) as exc:
            if attempt==2:raise ContentAPIError('Missing table completion failed: '+str(exc)) from None
            messages.append({'role':'user','content':'Repair only these missing tables: '+str(exc)})


def repair_unicode_response(response,request,client):
    broken=[]
    def walk(value,path):
        if isinstance(value,str) and ('\ufffd' in value or '\x00' in value):broken.append({'path':path,'text':value})
        elif isinstance(value,dict):
            for key,child in value.items():walk(child,path+'/'+key)
        elif isinstance(value,list):
            for index,child in enumerate(value):walk(child,path+'/'+str(index))
    walk(response,'')
    if not broken:return response,[]
    prompt={'language':request['language'],'subject':request['subject'],'facts':request['facts'],'broken_fields':broken}
    messages=[{'role':'system','content':'Return JSON {"repairs":[{"path":str,"text":str},...]}. Repair ONLY the supplied corrupted text fields, replacing replacement characters with coherent wording. Preserve meaning and all fact placeholders. Do not introduce new facts, digits, table numbers, sections or IDs. Use clean plain Unicode text without U+FFFD or NUL. Preserve the supplied paths exactly.'},
              {'role':'user','content':json.dumps(prompt,ensure_ascii=False)}]
    expected={b['path'] for b in broken}
    for attempt in range(3):
        answer,meta=client.complete_json(messages,3000)
        try:
            repairs=answer['repairs']
            if {r['path'] for r in repairs}!=expected or len(repairs)!=len(expected):raise ValueError('Repair paths changed')
            corrected=copy.deepcopy(response)
            for r in repairs:
                if not isinstance(r['text'],str) or '\ufffd' in r['text'] or '\x00' in r['text']:raise ValueError('Invalid repaired text')
                parts=r['path'].strip('/').split('/');target=corrected
                for part in parts[:-1]:target=target[int(part)] if isinstance(target,list) else target[part]
                if isinstance(target,list):target[int(parts[-1])]=r['text']
                else:target[parts[-1]]=r['text']
            validate_bundle(corrected,request)
            return corrected,[meta]
        except (ValueError,KeyError,TypeError) as exc:
            if attempt==2:raise ContentAPIError('Unicode text repair failed: '+str(exc)) from None
            messages.append({'role':'user','content':'Fix the requested fields only: '+str(exc)})
