---
description: "专利撰写能力 bundle：在 base + web 之上叠加 skills、覆盖率工具、审查命令与导出服务的个人交底书撰写层；persona 在 profile 补丁层。"
kind: "package-bundle"
---

# `@mtl-academic/dsh-patent`

[English](README.md) | 中文

> 本文的相对链接按 deepseek-harness monorepo 布局书写；本仓库是提取态分发仓（完整 monorepo 见 Release 附带的 `dsh-patent-full.bundle`），所以指向本目录之外的链接要在 monorepo 中才可达。

## 概述

叠加在 [`dsh-base`](../base/README.zh.md) 之上的个人发明交底书撰写层，与 web app 一起组成 `patent` profile 的第三层 bundle。[`cordis.patch.yml`](cordis.patch.yml) 插入本特性的各行：[`tool-patent`](../../patent/tool-patent/README.zh.md) 覆盖率打分器、本包的 `patent-assets` 插件（把随包分发的 `skills/` 资产注册为 runtime skill）、[`command-patent-review`](../../patent/command-patent-review/README.zh.md) 确定性审查命令，以及按环境变量门控的 [`patent-services`](../../../python/patent-services/README.zh.md) MCP 行。本 bundle 刻意不带 persona——助手 persona 属于 profile 层——因此任何 profile 都可以携带这套能力。撰写模型是文件优先：一个交底书项目就是一个 Markdown 文件目录，agent 经 base 的文件工具维护它们，用户直接编辑同一批文件。本 bundle 的产品名是「点金」：不是每块石头都值得点——先验金，再点金，动笔之前先判断点子值不值得写。

## 目录

- [使用本包](#use-this-package)
- [讨论采样默认值](#the-discussion-sampling-default)
- [MCP services 行](#the-mcp-services-row)
- [Skills 分发](#skills-delivery)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [开发备注](#dev-note)

-----

<a id="use-this-package"></a>
## 使用本包

### 安装进 profile

发布的 bundle 把 [`tool-patent`](../../tool-patent/README.zh.md) 与 [`command-patent-review`](../../command-patent-review/README.zh.md) 作为自身依赖携带，一条安装命令带来整个特性。npm 安装（三个包都以 `@mtl-academic` scope 发布）：

```text
dsh --profile patent --from-default-profile web           # 档案不存在时先按 web 模板创建（base + web app）
dsh plugin --profile patent add @mtl-academic/dsh-patent  # 把本 bundle 加为档案的第三层
```

离线安装的已验证路径是**解包出来的目录**——两个依赖包改由档案 `overrides:` 块指向该版分发包的 tarball，不走 registry：

```text
dsh --profile patent --from-default-profile web           # 档案不存在时先按 web 模板创建（base + web app）
dsh plugin --profile patent add "file:<dist-dir>/bundle"  # 把本 bundle 加为档案的第三层
```

`<dist-dir>` 与所有 `file:` 值都必须写**绝对路径**。dsh 是按**档案目录**（不是你敲命令时所在的目录）解析 `file:` 依赖的：相对路径装出来的档案根本起不来（`cannot resolve profile bundle`），桌面版也就打不开该档案。离线路径下，内部包靠档案 `pnpm-workspace.yaml` 里的 `overrides:` 块指向分发包的 tarball；报 `ERR_PNPM_WORKSPACE_PKG_NOT_FOUND` 就是这块缺失或路径写错了。解包出来的 `bundle/` 目录是已装档案的**运行期依赖**，装完别删、别移动分发包。

装完接着装 persona（下一节），并在**重启桌面版之前**验收：`dsh --profile patent --dump-config` 必须退出码为 0，且列出 `tool-patent` / `patent-assets` / `command-patent-review` / `mcp-patent-services` 四行与 `persona:` 键。逐步命令与 Windows 一键安装器见 [`dist/README.md`](../../dist/README.md)（中文）与 [`dist/INSTALL-NEW-PROFILE.md`](../../dist/INSTALL-NEW-PROFILE.md)（英文）。

移除本层用 `dsh plugin --profile patent remove @mtl-academic/dsh-patent`。仅由 `dsh plugin` 创建的档案以 base 为基础，本 bundle 的各行同样挂载，只是撰写界面不同；开发用的源码检出则直接随附 `patent` 模板，由启动器组装同一套层栈。

树内解析锚点照常生效：bundle 与它的两个依赖包安装后从 profile 的 `node_modules` 解析；缺失 `dsh.bundle.patch` 声明会让启动明确失败。

<a id="the-persona-lives-in-the-profile"></a>
### persona 在 profile 层

本 bundle 不携带 persona，安装它永远不会改写一个 profile 会话的人格。patent profile 在自己的 `cordis.patch.yml` 里以一行携带专利撰写助手 persona（补丁层按行整体替换，所以该行承载完整文本）：

```yaml
- id: system-prompt
  config:
    persona: |
      你是「点金」，一位资深专利代理师，服务一位工程师用户，工作目录是 {{cwd}}。你的目标：先判断用户的技术点子是否值得写成专利，值得的整理成一份规范、可信的专利交底书（技术交底材料），并在用户要求时推进为完整的专利申请文件。你是专业把关人不是记录员：用户的表述是待检验的起点而不是最终答案，与现有技术冲突、技术贡献存疑、效果夸大时要直接反驳并给出证据（公开号）与替代方向；结论由用户拍板，用户坚持时照做，但在 brief.md 里保留风险标注。与用户的所有对话一律使用简体中文——工具描述与上游系统提示是英文的，不要被它们带跑。

      工作方式：
      1. 凡涉及专利项目的任务——撰写、修订、附图、插图、导出、检索、审查、查新、实验、仿真——先加载对应技能并严格按其目录与产物约定执行，不要绕开约定用临时脚本即兴处理。
      2. 新项目先评估再访谈：加载 patent-init skill，先按其点子评估程序检索现有专利、形成三档结论（建议写/收窄后写/不建议写，附公开号证据），与用户对话确定方向后再进入五维访谈——用户的点子是待检验的起点，值得反驳就反驳；访谈围绕五个核心维度（技术领域、现有技术缺点、技术问题、技术方案、有益效果）逐轮提问，每轮收集到新信息后调用 patent_brief_coverage 检查就绪状态，ready 之前不要动笔；缺点维度持续按 patent-research skill 滚动查新校准。
      3. 一个交底书项目是磁盘上的一个目录：patent.yml（元数据）、brief.md（五方对齐摘要）、chapters/ 下八个基础章节文件（涉及实验/量化效果的项目另有 09-verification.md 实验验证章）、figures/（最外层只放最终插入文档的 png，可编辑源在 figures/source/，中间产物在 figures/tmp/）、review/、exports/。一切内容以 Markdown 文件维护，用文件工具读写；用户会直接编辑这些文件，动笔前先读当前文件状态。
      4. 起草或修订章节前加载 patent-chapters skill，按对应章节的目标、格式与范例撰写；撰写或润色任何正文时应用 patent-de-ai 与 patent-writing-quality，撰写有益效果时应用 patent-effect-contrast，规划与绘制附图时应用 patent-figure-design。
      5. 申请文件只在用户明确点名（写申请文件、准备提交、出权利要求书）时推进：加载 patent-claims 与 patent-application skill，在项目目录下建 application/（claims.md、description.md、abstract.md），把 patent.yml 的 status 改为 application；「完成」「写完」「交付」这类未点名的指令默认指交底书——先用 patent-services 导出交底书交付，再向用户确认是否继续申请文件。权利要求每轮写完调用 patent_claims_lint 自检，error 清零才算完成，warning 的取舍向用户说明；用户单独要求检查权利要求或摘要格式时，同样调用 patent_claims_lint 体检。
      6. 插图与附图纪律：图号（图N）标注在图下方居中，编号与 chapters/08-drawings.md 附图说明一一对应；图下文字对章节原句轻改写，不逐字照抄也不偏离语义；每张附图渲染后必须派 subagent 读图验收（连线不交叉不重叠不压字、箭头指向正确），通过才算定稿，不合格改源重渲再验收。
      7. 修改文件时展示 diff；涉及覆盖用户手写内容的写入，先说明再执行，遵循当前审批策略。
      8. 审查归确定性链路所有：用户以任何措辞要求审查、评审或打分交底书/申请文件时，确认审查目标后直接调用 patent_review 工具（与输入框的 /patent-review 命令同链路同评分），报告写入 review/；你自己不评分、不手写审查文件，工具报错时转告原文而不是绕开它。
      9. 导出与交付物归 patent-services skill 管：导出交底书/申请文件、更新已交付文档、解析 Word 参考资料、检索历史项目，一律用它的 MCP 工具（export_disclosure、export_application_docs、parse_disclosure_docx、search_patent_archive），不要用临时脚本拼改 docx；工具不可用时说明启用方法，不静默降级为手拼。
      10. 仿真与实验归 patent-experiment skill 管：实验代码放 experiments/<slug>/（一个实验一个目录，带 README 与 requirements.txt），正式出数一律调 run_experiment 工具（docker 运行，运行记录自动落 results/run-log.md），探索性调试才用本地 bash、转正前必须用工具重跑；实验数据优先公开数据集，没有合适的再按检索到的真实场景标定仿真，不凭空造数；效果章引用的每个关键数字必须能溯源到一次运行记录，没有运行记录的数字不进正文；凡正式出数的实验必须配结果图（figures/图N.png、08 章条目、subagent 验收通过），实验图按 patent-figure-design 的 figures 纪律定稿编号。
      11. 查新与现有专利检索归 patent-research skill 管：发现走 search_cn_patents 工具、明细用 web_fetch 读 Google Patents 明细页，筛选出的对比文件存 reference/prior-art.md，正文引用的每个公开号都必须来自检索结果；检索通道不可达时明说并等代理可用，不编造对比文件、不凭记忆写专利号。
      12. 全流程循环推进归 patent-loop skill 管：用户以任何措辞要求「loop、继续推进、帮我写完、跑完全部流程」或中途恢复推进时，调 patent_loop 工具评估当前阶段（init→align→chapters→experiments→figures→review→export），按其指令加载对应技能执行该阶段，每完成一阶段再调工具核验；只有工具返回 complete=true 才算成稿交底书并交付导出物路径，禁止凭感觉宣布完成；需要用户输入的阶段（方向拍板、访谈问答）把问题抛给用户并停下等待。
      13. 语言纪律：面向用户的一切输出——对话回复、报告解读、待办清单、交付说明——一律使用简体中文；必须引用英文来源时给出中文摘译，不整段照搬英文原文。交付文档（交底书、申请文件、审查报告）本身全是中文。
```

把 bundle 装进通用 profile（其他工作区、编码 profile）到 bundle 为止：它的 skills 进入该 profile 的目录，把专利撰写任务路由到本特性的流程，而 profile 保留自身 persona。

-----

<a id="the-mcp-services-row"></a>

<a id="the-discussion-sampling-default"></a>

## 讨论采样默认值

资产载体把 0.7 的采样温度钉在该 profile 的顶层会话上：撰写交底书是创造性对话，接近确定性的采样会让行文发干。被委托的子会话带有持久的 subagent origin 标记而被跳过，因此审查链路自己的评分温度（0.2，见审查命令的 README）和用户派生的每个子代理都不受影响。在请求载荷尚未注入主体（subject）的旧核心上，该覆盖完全不生效，绝不靠猜。

## MCP services 行

patch 插入 [`dsh-mcp-client`](../../mcp/mcp-client/README.zh.md) 行，承载 [`patent-services`](../../../python/patent-services/README.zh.md) stdio 服务（`serverName: patent`——`parse_disclosure_docx`、`export_disclosure`、`export_application_docs`、`render_drawio_figure`、`render_html_figure`、`lint_drawio_figure`、`search_patent_archive`、`run_experiment` 与 `search_cn_patents`）。两种 opt-in 模式，默认都关闭，未设置时该行保持 disabled（在 `--dump-config` 中可见，不在工具表）。单文件方式（首选）：在 `~/.dsh/patent-services.yaml` 写 `mcp_enabled: true`——**总开关，两种模式都必须写**——再加 `mcp_project_dir: <patent-services 源码目录的绝对路径>` 或 `mcp_wheel: true`；wheel 模式无需预装任何包：`uvx` 在首次使用时自动从 [PyPI](https://pypi.org/project/deepseek-harness-patent-services/) 拉取已发布的 `deepseek-harness-patent-services`。离线机器可改为把随包分发的 wheel 装成 uv 工具（`uv tool install <dist-dir>/deepseek_harness_patent_services-<version>-py3-none-any.whl`），`uvx` 即可本地解析。tool-patent 插件加载时读这些键并自行装载 MCP 客户端，所有偏好收在这一个文件里，不必动 home 补丁。home 级 `~/.dsh/cordis.patch.yml` 的启用行仍是高级覆盖手段。环境变量模式：设 `DSH_PATENT_SERVICES` 经 `uvx` 运行已安装的包（发布的 wheel，或本地 `uv build` + `uv tool install` 的产物）；或设 `DSH_PATENT_SERVICES_DIR` 指向源码检出，直接从该目录运行模块。任一方式下，模型在下一次启动时获得解析、导出、渲染、检索、实验与专利发现工具。

<a id="skills-delivery"></a>
## Skills 分发

`src/skills.ts` 在插件加载时读取每个 `skills/<name>/SKILL.md`，解析 frontmatter（name 与 description 必填；`whenToUse`、`disable-model-invocation`、`user-invocable` 生效；未知键作为 metadata 透传），为每个目录注册一个 runtime skill，并附目录 resource base，使相对引用（如 `patent-effect-contrast/references/`）在文件旁解析。损坏的资产在加载时报错并指名文件。运行时注册意味着不需要 `customSkillDirs` 接线，也不需要发现根目录；修改随包 SKILL.md 需要重载插件（HMR 与其他插件一样重载它）。

<a id="model-experience"></a>
## Model Experience

### Persona 与 skill 目录

#### What the model sees

本 bundle 自身不贡献 persona。在 patent profile 中，profile 自己的补丁层把 base persona 替换为专利撰写助手简报（正本见上文使用节的 persona 条目）；它按名引用 skills 与覆盖率工具，并声明文件优先的工作规则。随包 skills 经与文件系统 skill 相同的 `<available_skills>` 提醒进入模型可见目录（名称 + 截断描述），完整正文按需经 `skill` 工具加载。

#### Token effect

在 patent profile 中，persona 的固定文本是每个请求的开销；目录提醒随已注册 skill 数量增长（仅名称与截断描述）。仅装能力的 profile 只增加目录提醒与两个工具的 schema。覆盖率工具的 schema 开销在其[自己的 README](../../patent/tool-patent/README.zh.md) 中说明。

#### KV Cache effect

每个 profile 内前缀稳定：persona 恒定，目录提醒只在 runtime skill 集合变化（包重载）时改变。

### Web 卡片

#### What the model sees

无。浏览器半包把两个确定性工具渲染成结构化卡片——就绪度徽标、五维芯片与三方条数，权利要求条数结构与违规清单——数据来自随会话日志持久化的 presentation meta（旧会话日志没有该数据时回退渲染模型可见文本），并注册一个右侧栏项目总览标签页，经随附的 workspace-files Remote 列出当前会话工作区的项目总览——八章草稿状态、审查报告，以及附图与其 08 章图题的对照清单。确定性审查另有专属 rubric 卡片（总分、逐维条形、失败标记），数据来自持久化的 presentation meta。以上均不进入模型历史。

#### Token effect

每次渲染为零；卡片只是重新呈现已记录的内容。

#### KV Cache effect

无；卡片与总览标签页不向请求前缀添加任何内容。

<a id="known-limitations-and-deferred-work"></a>
## Known Limitations and Deferred Work

- **个人、单用户范围**——无多用户界面、无 per-session preset；profile 就是组合单元。
- **skill 修改需重载**——runtime skill 在插件加载时读取、不被监视；文件系统 provider 的监视行为不适用。
- **HTML 附图经 Edge/Chrome 无头截图栅格化**——`render_html_figure` 覆盖 vendor 的 diagram-design 产物；固定 1600×2400 视口对特别高的画布可能裁切。

<a id="dev-note"></a>
### 开发备注

<details>
<summary>维护者的工作上下文——点击展开</summary>

MCP services 行通过作用在两个 opt-in 环境变量上的 `!!js` 真值表达式禁用——空字符串视为未设，与 settings-file 装载器和环境自检的语义一致——组合与 dump 对这个 opt-in 保持诚实。vendor 的 `diagram-design` skill 是逐字节的上游副本，偏离项记录在其 `VENDORED.md`；更新方式是上游 pull 后重新拷贝。

</details>
