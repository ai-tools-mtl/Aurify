---
description: "The patent-writing capability bundle: skills, coverage tool, review command, and export services a personal disclosure-drafting profile adds over base + web; the persona lives in the profile layer."
kind: "package-bundle"
---

# `@mtl-academic/dsh-patent`

English | [中文](README.zh.md)

## Summary

A personal invention-disclosure drafting layer over [`dsh-base`](../base/README.md) — the `patent` profile's third bundle layer. [`cordis.patch.yml`](cordis.patch.yml) inserts the feature rows: the [`tool-patent`](../../patent/tool-patent/README.md) scorer, the `patent-assets` plugin (registers the shipped `skills/` as runtime skills), the [`command-patent-review`](../../patent/command-patent-review/README.md) deterministic review, and the environment-gated [`patent-services`](../../../python/patent-services/README.md) MCP row. The bundle is persona-free; the persona belongs to the profile layer. Drafting is file-first: a project is a Markdown directory the agent maintains through the base tools while the user edits the same files. Product name Aurify (点金, touch of gold): appraise the idea against prior art before drafting it.



## Table of Contents

- [Use this package](#use-this-package)
- [The discussion sampling default](#the-discussion-sampling-default)
- [The MCP services row](#the-mcp-services-row)
- [Skills delivery](#skills-delivery)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

-----

<a id="use-this-package"></a>
## Use this package

### Install into a profile

The verified install path — the published bundle pulls the [`tool-patent`](../../patent/tool-patent/README.md) and [`command-patent-review`](../../patent/command-patent-review/README.md) packages as its own dependencies, so one install brings the whole feature:

```text
dsh --profile patent --from-default-profile web
dsh plugin --profile patent add @mtl-academic/dsh-patent
```

The first command creates the profile from the web template (base + web app) and starts it; the second adds this bundle as the profile's third layer and manages it through later `add`/`remove` runs. A profile created by `dsh plugin` alone is base-backed — the bundle's rows mount there too, but the drafting surface is the web app. Removing the layer is `dsh plugin --profile patent remove @mtl-academic/dsh-patent`; the source checkout used for development instead ships the `patent` template directly, where the same layer stack is assembled by the launcher.

The in-box resolution anchors apply: the bundle and its two dependency packages resolve from the profile's `node_modules` once installed, and a missing `dsh.bundle.patch` declaration fails startup loudly.

### The persona lives in the profile

The bundle ships no persona, so installing it never rewrites what a profile's sessions are. A patent profile carries the patent-assistant persona in its own `cordis.patch.yml` as one row (patch layers replace rows wholesale, so the row holds the full text):

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

Installing the bundle into a general profile (another workspace, a coding profile) stops at the bundle: its skills enter that profile's catalog and route patent-writing tasks to this feature's procedures, while the profile keeps its own persona.

-----

<a id="the-mcp-services-row"></a>
## The discussion sampling default

The asset carrier pins a 0.7 sampling temperature on the profile's top-level sessions: drafting a disclosure is creative conversation, and near-deterministic sampling reads flatter than it should. Delegated children carry the durable subagent origin and are skipped, so the review chain's own scoring temperature (0.2 — see the review command's README) and every user-spawned subagent stay untouched. On cores whose request payloads predate the subject injection the override stays off entirely rather than guessing.

## The MCP services row

The patch inserts the [`dsh-mcp-client`](../../mcp/mcp-client/README.md) row for the [`patent-services`](../../../python/patent-services/README.md) stdio server (`serverName: patent` — `parse_disclosure_docx`, `export_disclosure`, `export_application_docs`, `render_drawio_figure`, `render_html_figure`, `lint_drawio_figure`, `search_patent_archive`, `run_experiment`, and `search_cn_patents`). Two opt-in modes, both off by default so the row stays disabled (visible in `--dump-config`, absent from the tool table). The single-file way (preferred): write `mcp_enabled: true` plus `mcp_project_dir: <absolute path to the patent-services checkout>` (or `mcp_wheel: true`) into `~/.dsh/patent-services.yaml` — the tool-patent plugin reads those keys at load and loads the MCP client itself, so every preference lives in that one file and the home patch stays untouched. A home-level `~/.dsh/cordis.patch.yml` row with `disabled: false` and a static `command`/`args` remains the advanced override. The env modes: set `DSH_PATENT_SERVICES` to run the installed package through `uvx` (the published wheel, or a locally built one via `uv build` + `uv tool install`); or set `DSH_PATENT_SERVICES_DIR` to a source checkout, which runs the module straight from that directory. Either way the model gains the parsing, export, rendering, search, experiment, and patent-discovery tools at the next boot.

## Skills delivery

`src/skills.ts` reads each `skills/<name>/SKILL.md` at plugin load, parses the frontmatter (name and description required; `whenToUse`, `disable-model-invocation`, and `user-invocable` honored; unknown keys pass through as metadata), and registers one runtime skill per directory with a directory resource base so relative references (such as `patent-effect-contrast/references/`) resolve beside the file. Malformed assets fail loud at load and name the file. Runtime registration means no `customSkillDirs` wiring and no discovery root; editing a shipped SKILL.md takes a reload of the package (HMR reloads it like any plugin).

## Model Experience

### Persona and skill catalog

#### What the model sees

The bundle itself contributes no persona. In a patent profile, the profile's own patch layer replaces the base persona with the patent-assistant brief (the canonical row lives in the Use-this-package section above); it names the skills and the coverage tool and states the file-first working rules. The shipped skills enter the model-facing catalog through the same `<available_skills>` reminder as filesystem skills (name plus truncated description), with full bodies loading on demand through the `skill` tool.

#### Token effect

In a patent profile, the persona's fixed text costs on every request; the catalog reminder scales with the number of registered skills (names and truncated descriptions only). A capability-only profile adds only the catalog reminder and the two tools' schemas. The coverage tool's schema cost is documented in its [own README](../../patent/tool-patent/README.md).

#### KV Cache effect

Prefix-stable per profile: the persona is constant, and the catalog reminder changes only when the runtime skill set changes (a package reload).

### Web cards

#### What the model sees

Nothing. The browser half renders the two deterministic tools as structured cards — the readiness chips with the three-way point counts, and the claims count split with the violation list — from the presentation meta persisted with the session log (falling back to the rendered text on sessions logged without it), and registers a right-sidebar dashboard tab that lists the open session workspace's project overview — the eight chapters' draft state, the review reports, and the figure images paired with their 08-drawings captions — through the shipped workspace-files Remote. The deterministic review renders as its own rubric card (overall score, per-dimension bars, failed-pass markers) from the persisted presentation meta. None of it enters model history.

#### Token effect

Zero per render; the cards re-present logged content only.

#### KV Cache effect

None; the cards and the overview tab add nothing to the request prefix.

## Known Limitations and Deferred Work

- **Personal, single-user scope** — no multi-user surfaces, no per-session preset; the profile is the unit of composition.
- **Skill edits need a reload** — runtime skills are read at plugin load, not watched; the filesystem provider's watch behavior does not apply.
- **HTML figures rasterize through the Edge/Chrome headless screenshot** — `render_html_figure` covers the vendored diagram-design outputs; exotic viewport assumptions (fixed 1600×2400) may clip very tall canvases.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

The MCP services row is disabled via a `!!js` expression over `DSH_PATENT_SERVICES_DIR`, so composition and dumps stay honest about the opt-in. The vendored `diagram-design` skill is a byte-for-byte upstream copy with documented deviations in its `VENDORED.md`; update it by re-copying after an upstream pull.

</details>
