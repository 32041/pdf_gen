"""Five distinct synthetic subject briefs per supported document genre."""
TOPICS={
'paper':[
 ('Warehouse robot charging and task allocation','仓储机器人的充电与任务分配'),('Urban heat sensing with sparse monitoring sites','稀疏监测点条件下的城市热环境观测'),('Acoustic fault screening for small industrial fans','小型工业风机的声学故障初筛'),('Adaptive sampling for river water quality','河流水质的自适应采样'),('Demand forecasting for public library services','公共图书馆服务需求预测')],
'annual_report':[
 ('Fictional cold-chain logistics operator','虚构冷链物流企业'),('Fictional regional water services company','虚构区域供水服务企业'),('Fictional industrial software vendor','虚构工业软件企业'),('Fictional community service provider','虚构社区服务企业'),('Fictional efficient lighting manufacturer','虚构节能照明制造企业')],
'official':[
 ('Pilot inspection programme for public facilities','公共设施巡检试点工作通知'),('Vocational skills training implementation notice','职业技能培训实施通知'),('Public service data quality procedures','公共服务数据质量管理办法'),('Community emergency drill arrangements','社区应急演练工作安排'),('Recycling service pilot implementation','再生资源回收服务试点方案')],
'report':[
 ('Neighbourhood mobility and transfer access study','社区出行与换乘可达性调研'),('Public library capacity and service assessment','公共图书馆容量与服务评估'),('Energy performance assessment of office buildings','办公建筑能源绩效评估'),('Municipal water supply resilience assessment','市政供水韧性评估'),('Accessibility audit of local service centres','基层服务中心无障碍审查')],
'manual_guide':[
 ('Soil moisture monitoring controller operations','土壤水分监测控制器操作手册'),('Service ticket triage and handover guide','服务工单分派与交接指南'),('Warehouse shift handover and inventory guide','仓储交班与盘点操作指南'),('Indoor air quality station maintenance','室内空气质量监测站维护指南'),('Small solar generation logger operations','小型光伏发电记录仪操作手册')],
'course_syllabus':[
 ('Discrete event simulation course syllabus','离散事件仿真课程教学大纲'),('Environmental monitoring methods course','环境监测方法课程教学大纲'),('Technical writing and evidence course','技术写作与证据表达课程大纲'),('Data quality engineering course','数据质量工程课程教学大纲'),('Public service evaluation course','公共服务评价课程教学大纲')],
'legal_contract':[
 ('Fictional equipment maintenance services agreement','虚构设备维护服务协议'),('Fictional document annotation services agreement','虚构文档标注服务协议'),('Fictional warehouse storage services agreement','虚构仓储保管服务协议'),('Fictional software acceptance and support agreement','虚构软件验收与支持协议'),('Fictional professional training delivery agreement','虚构专业培训服务协议')],
'exam_paper':[
 ('Scenario-based service operations assessment','服务运营情境考核试卷'),('Environmental monitoring scenario assessment','环境监测情境考核试卷'),('Data quality reasoning assessment','数据质量推理考核试卷'),('Warehouse coordination assessment','仓储协同考核试卷'),('Technical evidence interpretation assessment','技术证据解读考核试卷')]}


def brief(doc):
    index=(doc.variant_index-1)%5
    return TOPICS[doc.kind][index][doc.language=='zh']
