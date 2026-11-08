# tar.zip 规格复核与 LLM 接入边界

依据：用户上传的 conflict_bench/spec.md、level_bench/level_spec.md、data_format.txt。参考包不是训练集或评测集，不复用原始标签。只采用机制定义与版式先验。

| 要求 | 执行位置 / 验收 |
| --- | --- |
| 归属由语义父边决定，不能用位置反推 | benchmark_schema / objects.owner_id；LLM 接入后 owner_locked，几何修复不得改挂标题 |
| g(o) 是最终阅读序最近标题 | benchmark_audit.collect_blocks / audit_benchmark，保存 a/g 与两个页差 |
| 四类冲突 | after_section、far_float、before_heading、plate；按渲染结果逐对象验收 |
| after_section 越过其他标题 | 放在目标位置标题后、首段正文前；实际 owner 页差零或一，明确处理规格与原始数据矛盾 |
| far_float 至少两页 | 仍按所属标题页差判定；填充来自 LLM 独立补充段落，容量不足再生成补充，不反复复制模板 |
| plate 无标题且多对象 | 独立页；至少两个对象，支持二至六个；题注与表同页 |
| 标题深度可控 | 二至六级，has_title 明确，编号/字号/缩进独立于语义父边；不允许孤立子标题 |
| 编号与深度解耦 | 程序统一保留 numbered/none/mixed/misleading 标题模式，LLM 只命名，不编号 |
| 标题纯净性 | 每篇唯一语义根，标题文本唯一；页眉页脚独立 page_furniture；当前不生成目录 |
| 归属正常/冲突混合 | 全部四十篇作为一个批次分配配额，避免每类五篇分别取整积累偏差 |
| 每类先五篇 | --type all --count 5：当前八个明确体裁各五篇，共四十篇；other 不作为体裁 |
| 可视表格编号递增 | 最终阅读序重编号、同步正文引用、重新分页直到稳定；内部 ID 不变 |
| PDF 可复制 | 实际字符 CID→规范 UTF-16BE ToUnicode，生成内置校验及跨引擎抽检 |
| L1/L2/L3 导出 | 同一语义真值；docs.jsonl、页图、块图、composition、render、stats；inputs 删除目标标签 |
| 数字与表格一致 | 数值用 Python 的事实占位符替换，核心事实不得改写；另允许明确标识的建议计划时间/比例与技术标识，详见数值校验器 |
| 资源本地化 | 字体和许可证随包；生成不依赖 TeX、Office 或系统字体 |
| 可复现 | 缓存经过校验的 LLM JSON、模型名、请求哈希、可获得的 token 用量和内容版本（部分修复草稿用量未知，不推断总费用）；可离线重渲染 |

## 不偷换口径

- 参考包建议的比例和 data_format 的示意总量不是统一的强制规模。当前发布规模按用户要求为四十篇。
- 最大深度按文档计，层级占比按标题计，冲突率按有归属且有前驱标题的对象计。
- hard_ratio 未定义，保留 null；不等同于 conflict_ratio。
- 题注可解性与文章语义质量需要抽检，结构/字体/数值占位符校验不能替代语义人工审查。
- DocHieNet 版式对齐仍是纸型、栏数、模板与有限标题框先验，不声称已达到完整图文/扫描版面分布。
- 本轮生成文章与结构化表格，不使用 DeepSeek 生成图片，也不将图片生成混入两个当前评测任务。
- 演示图像可使用明确记录的较低 dpi 以便下载，PDF 保持矢量。150 dpi 重渲染不需要重新调用 LLM。

## v0.5 本轮再审核

- level_spec.md §2 明确存在 none/some/most 编号分层；§4.2 指出层级不能仅靠字号推断；§4.3 列出阿拉伯、中文、字母等编号家族。因此保留无编号、部分编号样本，增加 heading_numbering.explicit_document_ratio 控制整篇使用点分层级编号的篇数。
- conflict spec §3 有八个明确体裁，当前八类全部对应；other 是未归类短板，原文要求不要把它当体裁。完整原始计数与归一化配比见 REFERENCE_GENRES.md。
- 图片现在是 figure 对象，不再用表格冒充图片。placeholder 模式严格输出白底+边框；API 模式才调用独立图像供应商。figures.ratio 控制图/表比例，图和表分别按最终阅读序编号。
- 用户指定主标题居中，优先于参考页中居中/左齐并存的现象；没有篇名语义层时，第一节标题同样居中，不额外制造一个语义根。
- 用户指定 API key 放在配置中：本地提供 configs/providers.local.yaml，并在私有项目下载包内保留；导出的 config.json 与失败报告中的 api_key 字段脱敏。图片 key 与文字 key 分开读取。
- 视觉审视范围、未明说的因素、每个参数影响及待确认选项见 VISUAL_PARAMETERS_TO_CONFIRM.md。未实现项明确标为拟议参数，不宣称完整 DocHieNet 视觉对齐。
