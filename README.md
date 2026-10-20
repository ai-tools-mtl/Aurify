# 点金 Aurify

> Not every stone is worth gilding — appraise the idea before you gild it.
> 先验金，再点金。[DeepSeek Harness（dsh）](https://github.com/deepseek-ai/deepseek-harness) 的专利撰写把关人 · the patent-writing gatekeeper for dsh。

丢一个技术点子，点金先检索中国专利给出「建议写 / 收窄后写 / 不建议写」的评估（附公开号证据，可以反驳它），确认方向后再带你走完全流程：五方对齐访谈 → 八章交底书 → 附图与仿真实验 → 七维审查 → docx/PDF 导出。

与「帮你起草」类插件的本质区别：**你的表述是待检验的起点，不是最终答案**——它敢反驳、会批评、按证据给方向，结论由你拍板。

## 功能地图

| 阶段 | 能力 |
|------|------|
| 点子评估 | 中国专利查新（Google Patents CN 检索）+ 三档结论 + 对话定向 |
| 访谈 | 五方对齐（现有技术缺点 → 技术问题 → 有益效果），就绪度工具打分，ready 前不动笔 |
| 撰写 | 八章交底书 + 去 AI 味 + 效果对比框架 |
| 实验 | docker 仿真实验（公开数据集优先，真实场景标定仿真），运行记录自动落账 |
| 附图 | drawio / HTML 双通道渲染，黑白中文规范，编号与正文联动 |
| 审查 | `/patent-review` 七维 rubric + NLI 一致性，报告落档 |
| 导出 | 代理机构模板交底书 + 申请文件三件套，docx/PDF，插图自动配对，标题层级归一化 |
| 导入 | 已有 Word 交底书/申请文件按节名切入为八章草稿（缺章点名、已有内容拒覆写） |

组成：**14 个技能**（撰写纪律）+ **5 个原生工具**（就绪度打分、权利要求/正文检查、全流程推进、审查直通、环境自检）+ **10 个 MCP 工具**（文档导入/导出/解析/渲染与几何自查/检索/实验/查新，Python 服务）+ `/patent-review` 审查命令 + Web 结构化卡片与项目面板。Bundle 不带 persona（人格在档案补丁层，安装时一并装入），可装入任意 dsh 档案。

## 安装

推荐直接从 **DeepSeek Harness 桌面版的插件市场**安装，再通过自然语言初始化环境，无需先克隆仓库或下载 `dist/`。

1. 打开桌面版 **设置 → 插件市场**，搜索 **Aurify** 或 **点金**，安装到当前活动档案。
2. 在安装插件的档案中发送：

   > 帮我初始化点金插件的运行环境，检查并配置所需依赖和服务。

3. 助手会调用 `patent_setup_check` 自检，按结果协助配置 Python MCP 服务、检查 uv/uvx、Docker、镜像及检索通道；需要你操作的步骤会明确列出。
4. 如果启用或修改了 MCP 服务配置，按提示**完整退出并重启桌面版**，然后发送：

   > 帮我复检点金插件的环境，确认所需服务已就绪。

复检通过后即可描述技术点子开始评估，或提供已有 Word 文档继续处理。初始化过程中若有依赖缺失或网络受限，按自检提示处理；输入初始化指令本身不代表环境已经就绪。

| 文档 | 用途 |
|---|---|
| [安装与环境指南](dist/README.md) | 自然语言初始化、手动配置参考、模型配置与故障排查 |
| [英文安装指南](dist/INSTALL-NEW-PROFILE.md) | 对应英文说明、安装器参数与跨平台路径替换 |
| [Bundle 说明](packages/bundle-patent/README.zh.md) | 技能、persona 与 MCP 服务的组成及开发细节 |

npm 命令、Windows 安装器与离线安装仍可用，见安装与环境指南的方式 B–E。专用档案的 persona 补丁属于可选配置，见该指南的「装 persona」；通用档案可保留原 persona。附图渲染与仿真实验需要 Docker，检索需要能访问 Google Patents。

## 仓库结构

```text
packages/bundle-patent/            # 能力 bundle：14 技能 + Web 卡片/面板 + MCP 行（@mtl-academic/dsh-patent）
packages/tool-patent/              # 就绪度打分、权利要求/正文检查、全流程推进工具（@mtl-academic/dsh-tool-patent）
packages/command-patent-review/    # /patent-review 确定性审查命令 + patent_review 直通工具（七维 rubric）
python/patent-services/            # Python MCP 服务：文档导入/导出/解析/渲染/检索/实验/查新（10 工具）
dist/                              # 可直接安装的 npm tarball + Python wheel + 一键安装器 + persona 补丁 + 接收方指南
```

技术标识：npm 包 `@mtl-academic/dsh-patent`（随两个 `@mtl-academic` 依赖包一同发布，发布后 `dsh plugin add @mtl-academic/dsh-patent` 直装；也可用 `dist/` 内 tarball 离线安装）；Docker 镜像 `q771103517/dsh-patent`（附图渲染）与 `q771103517/dsh-patent-experiment`（仿真实验），首次使用自动拉取。

## 开发

当前源码修复了整项审查漏读章节与申请文件、报告总分格式解析、失败实验日志误判完成及依赖安装失败仍继续执行的问题。整项审查传项目根目录（当前目录为项目时用 `.`），包含 `brief.md`、`chapters/` 和 `application/` 的顶层 Markdown；实验阶段要求至少一个实验的最新运行记录退出码为 0，或有明确的无需实验声明。本地 `dist/` 已重建为全量并集构建 TS `0.1.6-alpha.7` 与 Python `0.1.2`（上述修复＋已有文档导入、导出标题归一化、名称章单行门三项特性），待发布 registry；注意版本分叉——npm 已发布的 `0.1.6-alpha.6`（latest）与 PyPI 已发布的 `0.1.1` 出自修复线构建，不含那三项特性。

技能/Python 服务可直接改源码（Python 服务经 `DSH_PATENT_SERVICES_DIR` 指源码运行，改动即生效）。TS 包的构建接线在 deepseek-harness monorepo 内（tsdown preset、workspace 依赖），完整 monorepo 历史与构建上下文见本仓库 Release 附带的 `dsh-patent-full.bundle`（`git clone` 即得源码仓，`pnpm install && pnpm run build`）。独立打包：`npm --prefix scripts install && npm --prefix scripts run build`；Python wheel/sdist：`python -m build --outdir dist python/patent-services`（需安装 build 与 hatchling）。产物验证：`python3 scripts/verify-dist.py`；重建后用 `--write-checksums` 更新校验文件。独立 TS 打包生成声明但不代替完整 monorepo 类型检查；运行时依赖保持外置，发布依赖范围沿用已有分发包元数据。Python 测试：`uv run --project python/patent-services --group test pytest python/patent-services/tests`。

## 已知边界

- 面向 dsh 0.1.5-rc 至 0.1.6-alpha 线核心；旧核心缺 Web 卡片时工具显示为文本行，功能不受影响。
- 中国专利查新需本机能访问 patents.google.com（通常走代理）；不可达时明确报错，不返回编造结果。
- 附图渲染与仿真实验需要 Docker Desktop 在运行。

## 已知同类

[deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) 是 DeepSeek AI 官方的 agent harness，本项目是其生态的第三方能力插件，与其无隶属关系。
