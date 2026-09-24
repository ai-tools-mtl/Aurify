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
| 导出 | 代理机构模板交底书 + 申请文件三件套，docx/PDF，插图自动配对 |

组成：**14 个技能**（撰写纪律）+ **5 个原生工具**（就绪度打分、权利要求/正文检查、全流程推进、审查直通、环境自检）+ **9 个 MCP 工具**（导出/解析/渲染与几何自查/检索/实验/查新，Python 服务）+ `/patent-review` 审查命令 + Web 结构化卡片与项目面板。Bundle 不带 persona（人格在档案补丁层，安装时一并装入），可装入任意 dsh 档案。

## 安装

安装细节只维护一份正本（`dist/` 内），根 README 只保留最短路径与跳转：

| 文档 | 管什么 |
|---|---|
| 本节 | 最短路径——能直接复制跑通的最少命令 |
| [dist/README.md](dist/README.md) | **完整接收方指南**（中文）：手动安装逐步命令、验收方法、模型配置、可选功能、核心兼容表、已知边界 |
| [dist/INSTALL-NEW-PROFILE.md](dist/INSTALL-NEW-PROFILE.md) | 安装器参数、手动步骤（英文）、macOS/Linux 路径替换表、故障排查 |

前置：[DeepSeek Harness 桌面版](https://github.com/hairyf/deepseek-harness-desktop)（或 dsh ≥0.1.5）；可选 uv（Python 服务）与 Docker Desktop（附图渲染、仿真实验）。

**方式 A · 一键安装器（Windows，推荐）**——先在本仓库根目录把插件解包成**目录**（安装器要求 `<dist目录>\bundle\` 与 tarball 同级），再跑安装器；建档案、写 overrides、装包、装 persona、验证全自动，幂等可重跑：

```powershell
mkdir dist\bundle
tar -xzf dist\mtl-academic-dsh-patent-0.1.6-alpha.2.tgz -C dist\bundle --strip-components=1
powershell -ExecutionPolicy Bypass -File dist\install-patent-profile.ps1 -Name patent-demo -DistDir "$PWD\dist"
```

`-DistDir` 一律给**绝对路径**（上例的 `$PWD\dist`）；它会原样写进档案清单的 `file:` 依赖，而 dsh 是按**档案目录**（不是按当前目录）解析这些路径的——写成相对路径装出来的档案，下次启动直接报 `cannot resolve profile bundle`，桌面版根本打不开该档案。安装器已把 `-DistDir` 锚定为绝对路径，手改清单时同样必须写绝对路径。

解包出来的 `dist\bundle\` 与 `dist\*.tgz` 是安装源，**装完别删、别移动**：档案清单用绝对路径引用 `bundle\` 目录，桌面版启动自愈会把指向不存在目录的 `file:` 依赖判为死链卸掉。

> Windows 上如果 `tar` 命中 Git 自带的那份（`C:\Program Files\Git\usr\bin\tar.exe`），在受限 shell/沙箱里会以 `couldn't create signal pipe, Win32 error 5` 直接崩；换成系统自带的 `C:\Windows\System32\tar.exe`（Win10 1803+ 自带 bsdtar）即可。

macOS/Linux 无安装器，直接走方式 B——路径替换（`~/.dsh`、桌面版垫片 `~/.local/bin/dsh`、环境变量进 shell profile）见 INSTALL-NEW-PROFILE.md 的替换表。

**方式 B · 手动安装**——五步：解包 tarball 为 `bundle/` 目录（桌面端必须目录形态）→ 建 profile → 写 pnpm overrides → `dsh plugin add "file:<DIST>/bundle"` → 装 persona（`dist/persona.patch.yml` 拷为档案的 `cordis.patch.yml`）；可选追加 Python 服务（`uv tool install` wheel + 用户环境变量 `DSH_PATENT_SERVICES=1`，重启桌面版）。**`<DIST>` 与清单里所有 `file:` 路径都必须是绝对路径**（`file:./bundle` 这类相对值会按档案目录解析，直接让档案不可启动）；逐步命令见 [dist/README.md 的方式 B](dist/README.md)。

**装进已有档案（包括桌面版自建的档案）**——安装器是合并写入：档案清单里既有的依赖与 bundles 层（桌面版自己的 `dsh-tauri*`、`dshmarket`、`dsh-better-sidebar`、`dsh-rewind-plugin`、`@xmanrui/dsh-im`）会保留，只新增本插件需要的条目。**不要用编辑器整个覆盖 `package.json`**：清单外的包会被 pnpm 当多余包删掉，档案就丢了桌面版插件。装完先跑 `dsh --profile <档案名> --dump-config`（退出码必须为 0）再重启桌面版——清单解析不了时桌面版会直接打不开该档案。细节与恢复步骤见 [dist/README.md 的「装进已有档案」](dist/README.md)。

## 仓库结构

```text
packages/bundle-patent/            # 能力 bundle：14 技能 + Web 卡片/面板 + MCP 行（@mtl-academic/dsh-patent）
packages/tool-patent/              # 就绪度打分、权利要求/正文检查、全流程推进工具（@mtl-academic/dsh-tool-patent）
packages/command-patent-review/    # /patent-review 确定性审查命令 + patent_review 直通工具（七维 rubric）
python/patent-services/            # Python MCP 服务：导出/解析/渲染/检索/实验/查新（8 工具）
dist/                              # 可直接安装的 npm tarball + Python wheel + 一键安装器 + persona 补丁 + 接收方指南
```

技术标识：npm 包 `@mtl-academic/dsh-patent`（随两个 `@mtl-academic` 依赖包一同发布，发布后 `dsh plugin add @mtl-academic/dsh-patent` 直装；也可用 `dist/` 内 tarball 离线安装）；Docker 镜像 `q771103517/dsh-patent`（附图渲染）与 `q771103517/dsh-patent-experiment`（仿真实验），首次使用自动拉取。

## 开发

技能/Python 服务可直接改源码（Python 服务经 `DSH_PATENT_SERVICES_DIR` 指源码运行，改动即生效）。TS 包的构建接线在 deepseek-harness monorepo 内（tsdown preset、workspace 依赖），完整 monorepo 历史与构建上下文见本仓库 Release 附带的 `dsh-patent-full.bundle`（`git clone` 即得源码仓，`pnpm install && pnpm run build`）。Python 测试：`uv run --project python/patent-services --group test pytest python/patent-services/tests`。

## 已知边界

- 面向 dsh 0.1.5-rc 至 0.1.6-alpha 线核心；旧核心缺 Web 卡片时工具显示为文本行，功能不受影响。
- 中国专利查新需本机能访问 patents.google.com（通常走代理）；不可达时明确报错，不返回编造结果。
- 附图渲染与仿真实验需要 Docker Desktop 在运行。

## 已知同类

[deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) 是 DeepSeek AI 官方的 agent harness，本项目是其生态的第三方能力插件，与其无隶属关系。
