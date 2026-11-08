# PDF 合成 v0.5：配置化 LLM、图像占位与层级编号

当前保留 **八类各五篇，共40篇真实 DeepSeek 生成文章**。文字和160个表格来自经过校验的 DeepSeek 内容缓存；另80个对象作为未来图片，当前显示白底+边框，并有对应题注、引用和语义归属。**这80幅图片还没有由图片模型生成**。

本轮重点修改：

- 按用户要求，把提供的文字 API key 放入 `configs/providers.local.yaml`；主项目私有下载包包含此文件。图片 key 是独立配置，目前为空。
- 主标题/第一个标题默认居中。28/40篇所有章节使用数字或字母点分的显式层级编号；其余保留参考包确实包含的无编号/部分编号/平面编号。
- 图、表分别从1开始按最终阅读序递增，引用同步；不改变语义归属以迁就几何位置。
- 八个明确体裁全部支持。新增按参考表已归类952篇的权重采样配置。
- 根据参考图片整理了 [待确认视觉参数清单](docs/VISUAL_PARAMETERS_TO_CONFIRM.md)，逐项说明影响、已实现/待实现状态，并留有填写栏。

## 先看结果

打开 `samples_index.html`。主项目含全部40份 PDF、源结构、L1 gold、字体许可证和内容缓存。每类独立的 L3 包含5篇 PDF、页图、块图及标准标注；这些是同一个全局配额批次的子集，单类比例不必等于全局比例。

## 只需 Python 的运行方法

Python 3.10+，依赖只有 PyMuPDF、PyYAML；无需 TeX、Office 或系统字体。

```bat
python -m pip install -r requirements.txt
python check_environment.py

REM 重用随包的40篇内容，不联网，不扣API费用；图片保持白框
python generate.py --type all --count 5 --config configs/llm_demo.yaml --content library --output replay
python verify_dataset.py replay/all/joint/docanno

REM 150 dpi 导出完整 L3 页图和块图，PDF文字仍为矢量
python generate.py --type all --count 5 --config configs/llm_fullres.yaml --content library --output replay_150
```

演示图像为96 dpi。`--type all --count 5` 指八类各5篇；`mixed --count 40` 指总共40篇按权重采样。只有同样的文档图结构/种子/事实计划才会命中现有缓存；其他请求在 library 模式明确报错，不联网、不使用模板冒充 LLM。

## 文字模型与 API key 配置

打开 `configs/providers.local.yaml`：

```yaml
llm:
  api_key: '你的DeepSeek key（本次私有项目已填入）'
images:
  api_key: ''
  api_base: ''
  model: ''
```

文字模型、超时等参数在 `configs/base.yaml` 的 `llm` 段；当前文章模型是 deepseek-flash。文字供应商使用 DeepSeek 官方 HTTPS 接口。可在运行配置的 `llm.api_key` 直接填写，或者使用上述独立本地配置文件；同名本地配置优先，环境变量 DEEPSEEK_API_KEY 最后覆盖。API key 不会写入数据集 config.json 或失败报告中。提交源码时 providers.local.yaml 被 gitignore 排除；本次给你的私有项目 ZIP 按要求保留该文件。

生成新文章（需要联网，可能产生费用）：

```bat
python generate.py --type all --count 5 --config configs/llm_demo.yaml --content llm --seed 123 --output new_articles
```

表格是否来自 LLM 可查：`documents/<id>/document.json` 的 `objects[].content_provenance`，以及 `content_library/<request_hash>.json` 的原始 `response.tables`。`llm.table_mode: llm` 使用模型生成行列内容；`derived` 才是程序派生数值表。章节树、对象 ID、所属标题由程序固定，LLM 命名标题、写正文/题注/引用并填表。

## 图像：现在占位，以后接图像生成模型

```yaml
figures:
  ratio: 0.3333333333333333   # 对象中图的比例，其余为表
  mode: placeholder         # placeholder / api / library
  height_pt: null           # 沿用原对象高度；也可指定30–450pt
  protocol: openai_images
  size: 1024x1024
  response_format: b64_json
  on_error: fail            # 失败时中断；也可选择明确标记的placeholder
```

1. 当前 `mode: placeholder`，仅画白底框和真实题注，不调用图片或文字 API。图片描述保存在 `objects[].figure_prompt`，实际状态为 `figure_status: placeholder`。
2. 选好模型后，填写 `providers.local.yaml` 的 **images** 段，使用它自己的 key、api_base、model，再将运行配置中的 `figures.mode` 改为 `api`。
3. 本版实现的是 OpenAI-compatible `POST /images/generations`（api_base通常带 `/v1`）。支持 `data[0].b64_json` 或 HTTPS 图片 URL；从图片URL下载时不附带 API key。缓存存入 image_library。
4. 单纯能“看图”的 VLM 不一定能“生成图”；供应商协议不兼容时需要新增适配器，不能只填一个模型名。模型图片中的文字/数值正确性也仍需检查。
5. `mode: library` 只读取已有图片缓存；未命中时默认报错。`on_error: placeholder` 才允许以明确记录的白框继续。`figures.ratio: 0` 可生成纯表格对象样例。

图片提示词由文章所属节、题注和已有记录填入；不改变既定归属。当前图片占位描述复用同一节的 LLM 表格/内容语义，不声称已得到真正的模型图片。

## 整篇显式编号比例

```yaml
heading_numbering:
  explicit_document_ratio: 0.7
  explicit_families:
    arabic_dotted: 0.8
    alpha_dotted: 0.2
  remaining_modes:
    none: 0.4
    mixed: 0.4
    misleading: 0.2
```

整篇显式是“所有章节”都按树显示1/1.1/1.1.1或A/A.1/A.1.1，篇名不编号。设为1生成100%这类文档；设为0仍可有部分带编号章节，但没有整篇全显式文档。null恢复旧 numbering_modes；专门测试旧深度×编号格子的 level_grid 配置使用 null。

参考规格明确包含无编号与部分编号标题，不应全删。语义层级始终以 level/parent_id 为准；字体/缩进是视觉线索。该比例按篇统计，level_share_constraints 按标题统计，不应混用。

## 体裁比例

现有八类：论文、年报、公文/标准、一般报告、手册/指南、课程大纲、合同/法律、试卷。语言是另一个维度。参考表全部原始计数与归一化比例见 [REFERENCE_GENRES.md](docs/REFERENCE_GENRES.md)。

```bat
python generate.py --type mixed --count 40 --config configs/reference_mix.yaml --content llm --output reference_mix
```

此命令按参考表**已归类部分**的文档数分配，不保证每类等量。原文指出 other 是未归类的扫描件、无标题页等，不能直接当体裁，因此不虚构“other”类别。

## 验收与边界

- 全局对象冲突率50%，after_section/far_float/before_heading/plate均保留；a(o)是语义所属、g(o)是最终阅读序最近标题。
- 深层标题比例通过实际结构检查；没有孤立子标题，导出 inputs 删除目标标签。
- 逐行测量边界、字体嵌入、字符映射、题注耦合、图表重叠和最终表/图编号。
- 当前版面仅部分对齐参考图片；扫描、复杂侧栏、混合栏数、字体家族、脚注等候选项见待确认清单。没有宣称完成像素/分布全面对齐。
- 原始文章为虚构；结构、数值和几何校验不能证明每句话、每幅生成图的语义都正确。需要人工抽查。

规格复核记录：[TAR_REQUIREMENTS_REVIEW.md](docs/TAR_REQUIREMENTS_REVIEW.md)。
