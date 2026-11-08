"""Small deterministic placeholder provider; content expansion is intentionally deferred."""
import random
from core.benchmark_schema import Heading, BenchmarkDocument

DOMAINS={'paper':'academic_paper','official':'gov_standard','annual_report':'annual_report',
         'report':'report','manual_guide':'manual_guide','course_syllabus':'course_syllabus',
         'legal_contract':'legal_contract','exam_paper':'exam_paper'}
TITLES={
 'paper':('Resource Allocation in a Simulated Service System','模拟服务系统的资源配置研究'),
 'annual_report':('Northbridge Systems Annual Report','澄川系统有限公司年度报告'),
 'official':('Notice on the Service Capacity Pilot','关于开展服务能力提升试点的通知'),
 'report':('Service Capacity Assessment Report','服务能力评估报告'),
 'manual_guide':('Service Platform Operations Guide','服务平台操作指南'),
 'course_syllabus':('Service Operations Course Syllabus','服务运营课程教学大纲'),
 'legal_contract':('Service Programme Agreement','服务项目协议'),
 'exam_paper':('Service Management Assessment','服务管理考核试卷')}
NOUNS_EN=['Resource planning','Service delivery','Data collection','Quality review','Capacity assessment','Cost controls','Staff allocation','Process design','Risk monitoring','Operating results','Performance checks','Implementation scope','Record management','System maintenance','Demand analysis','Reporting rules','Review procedure','Support arrangements','Schedule management','Acceptance criteria','Evidence review','Training requirements','Audit preparation','Technical scope']
NOUNS_ZH=['资源规划','服务交付','数据采集','质量复核','能力评估','成本控制','人员配置','流程设计','风险监测','经营表现','绩效检查','实施范围','记录管理','系统维护','需求分析','报告要求','审查程序','保障安排','进度管理','验收标准','证据核查','培训要求','检查准备','技术范围']


def roman(n):
    values=[(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]
    result=''
    for v,s in values:
        while n>=v: result+=s; n-=v
    return result


def number(path,family):
    if family=='arabic_dotted': return '.'.join(map(str,path))
    if family=='alpha_dotted': return chr(64+path[0])+(''.join('.'+str(i) for i in path[1:]))
    if family=='roman_outline':
        parts=[roman(path[0])]+[str(i) for i in path[1:]]
        return '.'.join(parts)
    if family=='cn_outline':
        n=path[-1]; cn='一二三四五六七八九'[n-1]
        return [cn+'、','（'+cn+'）',str(n)+'.','（'+str(n)+'）',chr(64+n)+'.','（'+chr(96+n)+'）'][min(len(path)-1,5)]
    raise ValueError('Unknown numbering family')


def build_document(doc_id,kind,language,seed,depth,has_title,numbering,family,style,template,columns,margin,size):
    rng=random.Random(seed)
    title=TITLES[kind][language=='zh']
    nouns=list(NOUNS_ZH if language=='zh' else NOUNS_EN)
    rng.shuffle(nouns)
    headings=[]
    def add(title_,level,parent,path,is_title=False):
        h=Heading(f'h{len(headings)+1:04d}',title_,level,parent,path,is_document_title=is_title)
        headings.append(h)
        return h
    parent='root';start_level=1
    if has_title:
        h=add(title,1,'root',(),True);parent=h.id;start_level=2
    word_index=0
    def subtree(parent_id,level,prefix,expand):
        nonlocal word_index
        for index in [1,2]:
            base=nouns[word_index%len(nouns)]
            cycle=word_index//len(nouns)
            name=base if not cycle else base+('补充说明' if language=='zh' else ' supplement')+str(cycle)
            word_index+=1
            node=add(name,level,parent_id,prefix+(index,))
            if level<depth and (expand or index==1):
                subtree(node.id,level+1,node.path,False)
    if start_level<=depth: subtree(parent,start_level,(),True)
    groups={}
    for h in headings:
        if not h.is_document_title: groups.setdefault(h.parent_id,rng.random()<.5)
    if numbering=='mixed' and len(groups)>1:
        keys=list(groups);groups[keys[0]]=True;groups[keys[-1]]=False
    counter=0
    for h in headings:
        if not h.is_document_title:counter+=1
        if h.is_document_title or numbering=='none' or (numbering=='mixed' and not groups[h.parent_id]):
            h.text=h.title
        elif numbering=='misleading':
            # A flat list is deliberately unrelated to semantic depth; no isolated dotted labels.
            h.text=f'{counter}. '+h.title
        else: h.text=number(h.path,family)+' '+h.title
    output=[round(80+i*13+rng.uniform(-4,4),2) for i in range(4)]
    cost=[round(v*.65,2) for v in output]
    facts={'periods':[2022,2023,2024,2025],'output':output,'cost':cost,
           'balance':[round(a-b,2) for a,b in zip(output,cost)],'synthetic':True}
    return BenchmarkDocument(doc_id,kind,DOMAINS[kind],language,title,seed,depth,has_title,numbering,family,
                             style,template,columns,margin,size,headings,facts)


def paragraph(doc,heading,continuation=False,continuation_index=0):
    if doc.content:
        if continuation:
            notes=doc.content['continuations']
            if continuation_index>=len(notes):raise ValueError('Generated continuation pool exhausted; increase llm.continuation_count and regenerate content')
            return notes[continuation_index]
        return doc.content['sections'][heading.id]['paragraph']
    f=doc.facts
    if doc.language=='zh':
        intro=('后续记录采用相同的统计口径。' if continuation else f'本节围绕{heading.title}说明实施范围、数据口径和复核安排。')
        return intro+f"模拟记录覆盖 {f['periods'][0]} 至 {f['periods'][-1]} 年。末期产出为 {f['output'][-1]:.2f}，成本为 {f['cost'][-1]:.2f}，差额为 {f['balance'][-1]:.2f}。"+'各项记录应结合服务规模和实施条件解释，不将总量变化直接等同于效率提升。异常情况在复核时单独说明，所有数值仅用于本合成示例。'
    intro=('Subsequent records use the same measurement procedure. ' if continuation else f'This section sets out the scope, measurement procedure and review arrangements for {heading.title.lower()}. ')
    return intro+f"The simulation covers {f['periods'][0]} to {f['periods'][-1]}. Final output is {f['output'][-1]:.2f}, cost is {f['cost'][-1]:.2f}, and the balance is {f['balance'][-1]:.2f}. "+'Records should be interpreted alongside service scale and implementation conditions. Aggregate change alone does not establish improved efficiency. Exceptions are documented during review; all observations are synthetic.'
