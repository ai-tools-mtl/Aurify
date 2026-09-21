---
description: "确定性 rubric 审查：人类命令 /patent-review 与模型工具 patent_review 共用同一条 host 侧链路，报告写入 review/ 目录。"
kind: "package-reference"
---

# @deepseek-ai/dsh-command-patent-review

[English](README.md) | 中文

> 本文的相对链接按 deepseek-harness monorepo 布局书写；本仓库是提取态分发仓（完整 monorepo 见 Release 附带的 `dsh-patent-full.bundle`），所以指向本目录之外的链接要在 monorepo 中才可达。

## 概述

确定性专利审查，两个入口：人类命令 `/patent-review` 与模型工具 `patent_review`。两者都审查一个交底书文件或一个 Markdown 文件目录，报告写入 `review/`。模型不能跳过、改形或稀释审查——编排是 host 数据，模型侧入口只提供目标路径。

## 目录

- [做什么](#what-it-does)
- [固定脚本与 rubric](#the-fixed-script-and-the-rubric)
- [配置](#configuration)
- [导出形态](#export-shape)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

<a id="what-it-does"></a>
## 做什么

两个入口都从工作目录读取目标（单个文件，或一个目录——其中 `*.md` 按名排序拼接），经 `ctx.workflowEngine` 启动固定 workflow 脚本，完成后写 `review/<label>.review.md`。命令结果仅进 UI（`CommandResult` 永不进入模型历史）；工具把 UI 摘要文本作为工具结果返回给模型。完整报告只在模型之后经 fs 工具读取时才变为模型可见，那会被记录为普通工具流量，"model-visible ⟺ logged" 因此保持完整，无需新的 session 事件。

文件目标产出 `review/<安全名>.review.md`；目录目标以 `<!-- 名称 -->` 标记拼接各 Markdown 文件，为整份文档产出一份报告。

<a id="the-fixed-script-and-the-rubric"></a>
## 固定脚本与 rubric

脚本（`src/script.ts`，由 workflow 引擎 worker 执行的纯 JS 字符串）按 rubric 维度 × 配置的评分次数各启动一个携带 schema 的子代理，把每个维度的各次评分折叠为四舍五入均值，并在收集到评分的维度上重归一化权重。失败的子代理解析为 `null`，降低该维度的有效次数，而不是让整个运行失败。评分提示词只针对文档本身评判：合理不覆盖某维度的章节按其对维度的铺垫打分，而不是因它不是完整申请而受罚。当审查目标位于申请文件集内（且 `claims.md` 与 `description.md` 齐备）时，运行加入 NLI 式一致性阶段——每遍一个 claims→说明书支持度子代理与一个术语一致性子代理，聚合为一致性分与未支持权项并集，渲染为报告的「一致性检查」小节。rubric（`rubric/default.json`，在天工系统审查 rubric 基础上扩展到申请阶段：内容完整性 0.15 / 技术方案清晰度 0.20 / 新颖性表述 0.15 / 撰写规范性 0.15 / 权利要求质量 0.15 / 说明书支持度 0.15 / 摘要合规 0.05，各带分段评分指南）在 git 中版本化——git 历史取代天工存于数据库的 rubric，成为防漂移锚点。rubric 在加载时解析并校验（持久文件边界）；损坏的 rubric 报错失败。

确定性声明：同一输入文件与同一组收集到的评分，逐字节渲染出同一报告；模型打分本身当然是采样方差，报告中的各次评分与离散度把它显式呈现。

<a id="configuration"></a>
## 配置

`scoringPasses`（整数 1-5，默认 2）：每个维度的独立评分次数。两次带来自一致性信号（报告可见离散度），代价是双倍子代理数；一次是廉价模式。项目可在自己的 patent.yml 写 `reviewPasses: 1-5` 覆盖档案级默认（与 reviewThreshold 对默认达标线的"项目压档案"关系同款）。

`reviewTemperature`（数字 0-2，默认 0.2）：经 workflow 的子代理温度覆盖，钉在每个评分子代理请求上的采样温度。评分是对评分标准的机械套用，默认值接近确定性；`agent()` 尚不支持温度选项的旧引擎会在调用时被识别，子代理降级为提供方默认值而不是失败。

`projectRoot`（可选字符串）：相对审查目标的基准。未设置时按每次调用的 agent 会话 cwd 解析——即 web 组合创建会话时的工作区。只有当 fs 世界与该会话工作区不同（例如组合了独立 `fs-local` cwd）时才需要显式设置；既无配置根目录也无会话 cwd 的调用会报错失败，而不是审查错目录。

报告落点锚定 file-first 项目模型：目标解析后，向上最近的持有 `patent.yml` 的目录拥有 `review/`——形如 `<项目>/chapters/03-background.md` 的目标会把报告写进 `<项目>/review/`，即使工作目录是项目上方的工作区；没有找到 `patent.yml` 祖先时，报告照旧落在 `projectRoot/review/`。

<a id="export-shape"></a>
## 导出形态

函数插件：只导出 `name` / `inject` / `Config` / `apply`，禁止 default export。多余的 `export default` 会被 Loader 的 `unwrapExports` 折叠模块并丢掉 `inject`（见 [docs/postmortem/0001](../../../docs/postmortem/0001-acp-default-export-drops-inject.zh.md)）。

<a id="model-experience"></a>
## Model Experience

### patent_review 工具

#### What the model sees

工具表中的 `patent_review` 工具：单个 `target` 参数（文件或目录路径）。口语审查请求（"审查一下这份交底书"）落为调用这个工具——模型确认目标后调用；固定脚本、rubric 与报告路径都是模型永不提供的 host 数据。工具结果携带与命令相同的 UI 摘要（总分、注意事项、报告路径）；完整报告经之后的 fs 读取变为模型可见。

#### Token effect

组合了本包的 profile 中工具 schema 随每个请求存在；每次运行增加一条工具结果（短摘要）。

#### KV Cache effect

前缀稳定：schema 恒定；摘要在前缀之后追加。

### Command surface

#### What the model sees

无。`/patent-review` 是人类命令：分发不经过模型轮次，`CommandResult` 仅进 UI，只有 log-only 的 `command/run`/`command/done` 事件记录这次尝试。

#### Token effect

每次调用为零。

#### KV Cache effect

无；命令不向请求前缀添加任何内容。

<a id="known-limitations-and-deferred-work"></a>
## Known Limitations and Deferred Work

- **npm 发布会丢掉 rubric 资产**——workspace 约束门禁把 `files` 钉在不含 `rubric/` 条目的统一清单上；发布本包需要放宽该清单（包保持 workspace 内部使用时无影响）。
- **每次调用一个目标**——没有保存的 rubric 变体，也没有多目标批量；审查永远使用随包版本化的这份 rubric。
- **Windows shell 引用**——摘要中的报告路径是普通相对路径；需要用 shell 打开它的消费方自行加引号。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

rubric 在天工系统审查 rubric 之上扩展出申请阶段维度，并以 git 版本化——git 历史就是防漂移锚点。脚本经 `ctx.workflowEngine` 运行，该引擎由 patent bundle 在 host 平面重新启用（`workflow-ptc`），因此在 preset 拥有引擎的 web 组合上命令照样可用。

</details>
