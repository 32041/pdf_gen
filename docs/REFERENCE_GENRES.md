# tar.zip 体裁表与当前支持范围

来源：`conflict_bench/conflict_bench/spec.md` §3。表中是该来源文件统计的文档数，不是 DocHieNet 官方全量类别分布，也不是生成时应该使用的冲突率。

| 来源体裁 | 来源文档数 | 占已归类952篇 | 生成入口 | 当前样例 |
| --- | ---: | ---: | --- | ---: |
| course_syllabus 课程大纲/培养方案 | 41 | 4.31% | course_syllabus | 5 |
| annual_report 年报 | 18 | 1.89% | annual_report | 5 |
| academic_paper 学术论文 | 280 | 29.41% | paper | 5 |
| manual_guide 手册/指南 | 102 | 10.71% | manual_guide | 5 |
| report 报告 | 85 | 8.93% | report | 5 |
| gov_standard 政府/标准 | 245 | 25.74% | official | 5 |
| legal_contract 合同/法律 | 156 | 16.39% | legal_contract | 5 |
| exam_paper 试卷 | 25 | 2.63% | exam_paper | 5 |
| other 未归类 | 560 | 不计入上述分母 | 未作为生成体裁 | 0 |

来源合计1512篇，其中952篇归入上面八类。原文明确说 other 包含无标题页、扫描件、拼版等分类失败项，**不要当体裁用**，所以没有凭空增加一个“other模板”。中文/英文属于语言维度，和这八个体裁交叉采样。

两种模式：

```bat
REM 小批次覆盖：每类5篇，40篇，忽略体裁权重
python generate.py --type all --count 5 --config configs/llm_demo.yaml --content library --output examples

REM 来源比例：按已归类952篇的原始文档数作为权重，总共40篇（新计划，需LLM生成）
python generate.py --type mixed --count 40 --config configs/reference_mix.yaml --content llm --output source_mix
```

按来源比例的小批次不保证每个体裁恰好五篇，整数配额使用最大余数取整。来源表的“冲突/篇”不是对象级冲突率，不能直接用作 conflict_ratio。当前联合任务的全局对象冲突率仍单独配置为50%。
