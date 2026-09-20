---
description: "确定性专利工具面：交底书 brief 的五方对齐就绪度打分、权利要求书的 CNIPA 格式静态检查、去 AI 味正文检查，以及把项目从任意阶段推进到导出成稿的 patent-loop 状态评估。"
kind: "package-reference"
---

# @deepseek-ai/dsh-tool-patent

[English](README.md) | 中文

## 概述

模型可见的确定性专利工具面。`patent_brief_coverage` 按五方对齐就绪判据为交底书 brief 打分，给 Init 对话一个确定性的「何时停止提问、开始动笔」信号；`patent_claims_lint` 按中国专利申请（CNIPA）格式最低要求对起草的权利要求书（及可选的摘要）做静态检查；`patent_loop` 从任意流水线阶段评估项目目录并指认下一个阶段，配套的 `/patent-loop` 命令把评估结果注入会话做全流程推进。在 patent profile 内使用；两个纯函数工具不带任何配置，loop 工具对读盘项目状态做判定。

## 目录

- [做什么](#what-it-does)
- [打分语义](#scoring-semantics)
- [权利要求检查语义](#claims-lint-semantics)
- [环境自检](#setup-check)
- [循环语义](#loop-semantics)
- [渲染](#rendering)
- [导出形态](#export-shape)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

<a id="what-it-does"></a>
## 做什么

在 `ctx.tools` 上注册五个工具、在 `ctx.commands` 上注册一个命令。`patent_setup_check` 是宿主面环境自检（见[环境自检](#setup-check)）。`patent_brief_coverage`：模型按维度传入已收集的草稿内容——`field`、`background`、`problem`、`solution`、`effect` 五个核心维度，外加 `name`、`drawings`、`key_points` 三个边缘维度（省略即未收集）——返回已收集/缺失清单、三方对齐判定与就绪信号。`patent_claims_lint`：模型传入起草的权利要求书文本（及可选摘要），返回权项数量结构与规则违例。两个纯函数工具的调用与结果经 loop 的 `tool/call` 与 `tool/result` session 事件记录，不追加任何其他事件。`patent_prose_lint` 是 patent-de-ai 技能的机器半边：套话转折词、超 150 字长句、三连排比为必须清除的 error，段末总结与教科书定义为 warning 提示。`patent_loop` 与 `/patent-loop` 共用一个读盘评估器（见[循环语义](#loop-semantics)）。

<a id="scoring-semantics"></a>
## 打分语义

打分器移植自天工的 `brief_dimensions.py`（参照实现的 Init 就绪唯一权威）：

- **核心维度**——`field`、`background`、`problem`、`solution`、`effect`。全部非空才就绪。
- **对齐检查**——`background`、`problem`、`effect` 三方的条数（按 ①②/`1.`/`(1)`/`一、` 等序号与分号、换行切分取较大者估算）最大偏差不得超过容差 1。三方任一未收集时对齐判定空放通过：缺维度是「还没收集到」，不是「未对齐」。
- **边缘维度**——`name`、`drawings`、`key_points` 接受并展示，但不参与就绪判定；它们通常在生成期补全。

容差与启发式计数是移植资产语义（init 阶段信息粒度粗），不是部署可调项，因此没有配置。

<a id="claims-lint-semantics"></a>
## 权利要求检查语义

`patent_claims_lint` 解析带编号的权利要求（"1." 至 "N."，一条权项可跨行），检查的是法定格式最低要求，不是实质审查：

- **C1** 编号：必须从 1 连续编号；引用不存在的权项同属本规则。
- **C2** 从属权利要求只能引用在前的权利要求（引用自身或更晚为错误）。
- **C3** 引用形式：引用多项必须用「根据权利要求N至M中任一项所述的」择一引用形式。
- **C4** 多项从属权利要求不得以另一多项从属权利要求为基础。
- **C5**（警告）独立权利要求未出现「其特征在于」，缺少改进型发明应采用的两部分式写法。
- **A1** 摘要非空白字符不得超过 300 字；仅在传入摘要时运行。

解析出的权项刻意不进入模型可见结果：模型刚提交过全文，回显每条权项只是白白消耗 token。

<a id="setup-check"></a>
## 环境自检

`patent_setup_check` 逐通道探测——MCP 服务行（~/.dsh/patent-services.yaml 的 mcp 键、home 补丁行、或启用环境变量——这是 MCP 工具永远做不到的那项检查）、docker 与两个镜像、draw.io 原生 CLI、patents.google.com 可达性、实验命令策略、代理变量——逐项返回中文结论行，缺什么附修法。刻意在宿主面：MCP 行未启用时本工具依然可用，所以点名「缺 MCP 行」的正是它；通道坏了是报告行，绝不抛异常。同一组 settings 键也驱动插件自己的 MCP 装载：静态行未被其他方式启用时，`apply` 读 `mcp_enabled`/`mcp_project_dir`/`mcp_wheel` 并经 `ctx.plugin` 装载 mcp 客户端——一个文件承载全部偏好。patent-init 技能把它作为每个新项目的第 0 步。

<a id="loop-semantics"></a>
## 循环语义

`patent_loop` 只读磁盘事实，返回第一个未完成的流水线阶段——init（无 `patent.yml`）→ align（brief.md 缺失或核心维度章节缺失）→ chapters（八章任一缺失或占位；携带实验工作——效果章含量化数据或 experiments/ 非空——的项目还必须有实验验证章 chapters/09-verification.md，占位空白同样算缺；brief.md 或 chapters/ 里引用的公开号若未见于查新出处账本 `reference/prior-art.md`，同样停在 chapters 阶段——每个被引用的公开号都必须能溯源到一条检索记录，绝不凭记忆写号）→ experiments（效果章含量化数据但无运行记录、也无「无需实验」声明）→ figures（08 章声明与 figures/ 根成品双向对账）→ review（最新一份 `*.review.md` 必须解析出达到达标线的总分——默认 80，项目可在 patent.yml 写 `reviewThreshold` 覆盖；`reference/prior-art.md` 存在查新不可用标记时放宽 10 分——且对所审源文件保持新鲜：以报告内盖的「源指纹」摘要为准，无戳的旧报告退回按修改时间判定）→ export（exports/ 无交底书 docx，或其随附的 `.fingerprint` sidecar（导出器写入）与当前源文件不符；无 sidecar 的旧导出物退回按修改时间判定）——并给出当前阶段的 directive：加载哪些技能、遵守哪些纪律。指纹优于 mtime：git 检出与目录同步会改写 mtime 而不动字节，审查或导出物恰在字节变化时才算过期。低于达标线的 gap 还会引用报告修订清单的前几条作为优先项，模型不必打开报告就知道先修什么。`complete=true` 要求全部关卡通过；它是「成稿」的唯一权威，工具描述与 patent-loop skill 要求模型每完成一阶段就回来复检，而不是自行宣布项目完成。三个磁盘逃生口防止合法项目卡死循环：`experiments/README.md` 声明无需实验、08-drawings.md 标注无附图、查新不可用标记——第三个用 10 分换一笔记录在案的债，通道恢复后必须补检索并重审偿还；标记存续期间每条 directive（含成稿结论）都携带常驻债务提示，工具还会探测通道是否恢复，连接一回来，下一次调用的待办清单就变成偿债步骤。`/patent-loop` 命令先评估，再经 `agent.followup()` 把循环契约作为持久用户面输入注入会话，返回仅 UI 可见的摘要——命令结果不进模型历史；需要用户的阶段（方向拍板、访谈问答）以问题收尾等用户回答。

<a id="rendering"></a>
## 渲染

规范结果为 `{ covered, missing, ready, coreFilled: { done, total }, aligned, alignmentCounts }`；Native 渲染返回一个文本块，具名缺失维度（带中文章节名）、对齐计数与容差判定、就绪判定与下一步动作。

<a id="export-shape"></a>
## 导出形态

函数插件：只导出 `name` / `inject` / `apply`，禁止 default export。多余的 `export default` 会被 Loader 的 `unwrapExports` 折叠模块并丢掉 `inject`（见 [docs/postmortem/0001](../../../docs/postmortem/0001-acp-default-export-drops-inject.zh.md)）。`inject` 为 `['tools', 'commands']`——命令注册与工具同插件。

<a id="model-experience"></a>
## Model Experience

### Tool schema

#### What the model sees

模型看到生成的 [`patent_brief_coverage` schema](../../../docs/tool-catalog.zh.md#deepseek-aidsh-tool-patent)。

#### Token effect

工具可见的每个请求上都是固定 schema 开销。

#### KV Cache effect

定义与可见性不变时前缀稳定。

### Tool-call history and result

#### What the model sees

每次调用携带草稿维度内容作为参数。成功返回一个定形文本块（覆盖进度、具名缺口、对齐判定、下一步动作）。无稳定失败模式：空白参数是合法的「尚未收集」输入，schema 违规由 registry 以标准 `INVALID_ARGS` 结果拒绝。

#### Token effect

随模型每次提交的草稿文本量增长；结果小而定形。

#### KV Cache effect

只追加；新出现的内容跟在可复用的请求前缀之后。

<a id="known-limitations-and-deferred-work"></a>
## Known Limitations and Deferred Work

- **工具只对传入内容打分**——维度内容由模型从其上下文提供；模型可能提交删减版 brief 而得到误导性 `ready`。`patent-init` skill 的程序约束这一点，审查引擎会对落盘文件复查。
- **不支持路径输入**——两个纯函数工具接收文本而非 `brief.md` 路径；读文件先经 `fs` 工具完成，本包因此不沾文件系统策略（loop 工具对是刻意的例外：它自己读项目状态，判定才不会被模型提交的内容左右）。
- **循环的 brief 与效果章启发式只判存在性**——标题下有非空正文即过 align，效果章出现任一「数字+单位」即触发 experiments 关卡；内容单薄与数字无据是各技能与审查引擎的职责，不是评估器的。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

打分器移植自天工的 `brief_dimensions.py`；容差与启发式计数是移植资产语义，不是部署可调项。检查规则对齐 CNIPA 法定格式最低要求（C1-C6、A1-A2），不是实质审查。循环评估器刻意只信磁盘产物——对话里怎么说都不算，产物缺失的阶段保持未完成；所有逃生口本身也是磁盘文件。

</details>
