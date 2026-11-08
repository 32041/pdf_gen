import random
from core.schema import Section, Document

TOPICS = {
 'paper': {
  'en': ('Resource Allocation in a Simulated Service System', [('Study design','Simulation setting','Evaluation protocol'),('Results and interpretation','Capacity and output','Limits of the simulation')]),
  'zh': ('模拟服务系统的资源配置研究', [('研究设计','模拟场景与假设','评价方法'),('结果与讨论','投入与产出','研究局限')])},
 'annual_report': {
  'en': ('Northbridge Systems — Synthetic Annual Report', [('Business review','Operating performance','Cost management'),('Outlook and risk','Capacity planning','Risk controls')]),
  'zh': ('澄川系统有限公司年度报告（模拟）', [('经营回顾','业务表现','成本管理'),('展望与风险','资源规划','风险控制')])},
 'official': {
  'en': ('Notice on the Pilot Service Capacity Programme', [('Programme arrangements','Scope and objectives','Implementation schedule'),('Implementation requirements','Resource management','Monitoring and review')]),
  'zh': ('关于开展服务能力提升试点工作的通知（模拟）', [('工作安排','试点范围与目标','实施步骤'),('落实要求','资源管理','监测与评估')])}}

def build(kind, language, seed, placements, paragraphs, depth=2):
    rng = random.Random(seed)
    revenue = [round(80 + i*13 + rng.uniform(-4,4), 2) for i in range(4)]
    cost = [round(v * rng.uniform(.61,.72),2) for v in revenue]
    profit = [round(r-c,2) for r,c in zip(revenue,cost)]
    growth = (revenue[-1]/revenue[0]-1)*100
    facts = dict(years=[2022,2023,2024,2025], revenue=revenue, cost=cost, profit=profit, growth_percent=growth,
                 unit='synthetic units', synthetic=True)
    title, outline = TOPICS[kind][language]
    sections=[]
    for i,(parent,*children) in enumerate(outline):
        sub=[]
        for j,name in enumerate(children):
            if language == 'zh':
                context = {'paper':'本研究采用四个连续阶段的模拟数据，考察资源投入、服务产出与结余之间的关系。各阶段采用一致的统计口径，结果用于展示排版和数据处理流程。',
                'annual_report':'本报告以虚构企业的年度经营数据为基础。营业收入、经营成本与经营结余来自同一份事实表，所有金额均为模拟单位。',
                'official':'本次试点以服务能力提升为目标，按准备、实施、评估和复核四个阶段推进。各责任单位应统一台账口径，按阶段报告投入与产出情况。'}[kind]
                evidence=f'记录显示，首期产出为 {revenue[0]:.2f}，末期为 {revenue[-1]:.2f}，累计变化 {growth:.1f}%。末期成本为 {cost[-1]:.2f}，结余为 {profit[-1]:.2f}。'
                notes=['各阶段之间存在投入规模差异，因此不能仅凭总量变化推断效率提升。后续分析应结合服务质量、人员配置与需求变化。', '成本采用统一口径归集，结余由产出减去成本计算。本样例未纳入税费、资产负债或其他财务科目，不能视作完整财务报表。', '实施过程中应保留原始记录，说明异常波动的原因，并在阶段复核时检查图表、正文与台账是否一致。', '这些数据由程序生成，不代表现实企业或真实实验。结果仅支持本模拟场景中的描述，不能用于外部因果推断。']
            else:
                context={'paper':'This study uses four simulated periods to examine resource input, service output and operating balance. Definitions remain constant across periods; the experiment demonstrates the document synthesis pipeline.',
                'annual_report':'This report describes a fictional organisation. Revenue, operating cost and operating balance come from one canonical fact table. All amounts use synthetic units.',
                'official':'The pilot programme improves service capacity through preparation, implementation, evaluation and review. Responsible teams shall maintain consistent records of resources and output.'}[kind]
                evidence=f'Output increases from {revenue[0]:.2f} to {revenue[-1]:.2f}, a cumulative change of {growth:.1f}%. Final-period cost is {cost[-1]:.2f}, leaving an operating balance of {profit[-1]:.2f}.'
                notes=['Scale differs between periods, so aggregate growth alone does not establish improved efficiency. Further assessment should consider demand, staffing and service quality.', 'Operating balance is calculated as output less cost. Taxes, assets and liabilities are outside this example; this is not a complete set of financial statements.', 'Teams should retain source records, explain unusual variation and reconcile figures with the canonical ledger during each review.', 'The data are generated and do not describe real companies or experiments. Findings support descriptive claims within this simulation only.']
            if language == 'zh':
                focus = [
                    '本节明确数据的覆盖范围和业务边界。四个阶段采用相同单位，不将规模变化直接解释为效率变化。',
                    '本节说明执行与核算方法。各阶段先汇总产出和成本，再计算差额；不在文字生成时重新估算这些指标。',
                    '资源规划以观察到的阶段变化为起点。新增投入应先明确用途和责任，再通过后续记录判断是否达到预期。',
                    '复核工作应同时覆盖数值与解释。对于缺少数据支持的结论，应记录为待验证问题，不能作为已证实结果。'][i*2+j]
            else:
                focus = [
                    'This section defines the scope of the records. All four periods share a unit of measurement. Changes in scale are distinguished from changes in efficiency.',
                    'This section specifies the accounting procedure. Output and cost are recorded first; the balance is computed from their difference rather than estimated during writing.',
                    'Resource planning begins with the observed period changes. Additional inputs require a stated purpose and owner before subsequent records can establish progress.',
                    'Review covers both numbers and interpretation. Claims without supporting observations remain questions for future evaluation rather than established results.'][i*2+j]
            candidates = [context+' '+focus, evidence+' '+notes[(i*2+j)%4], notes[(i*2+j+1)%4]+' '+notes[(i*2+j+2)%4]]
            texts = candidates[:paragraphs]
            if paragraphs > len(candidates):
                raise ValueError('Template provider supports 1–3 paragraphs per subsection; extend providers.py for longer content')
            sub.append(Section(name,texts))
        sections.append(Section(parent,children=sub))
    if depth == 1:
        for section in sections:
            section.paragraphs = [p for child in section.children for p in child.paragraphs]
            section.children = []
    elif depth == 3:
        for section in sections:
            for child in section.children:
                texts = child.paragraphs
                child.paragraphs = []
                child.children = [Section('数据与观察' if language=='zh' else 'Data and observations', texts[:max(1,len(texts)//2)]),
                                  Section('解释与边界' if language=='zh' else 'Interpretation and scope', texts[max(1,len(texts)//2):] or [texts[-1]])]
    elif depth != 2:
        raise ValueError('Supported heading depths: 1, 2, 3')
    return Document(kind,language,title,seed,facts,sections,placements)
