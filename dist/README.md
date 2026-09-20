# 点金 Aurify · dsh 专利撰写插件 · 离线分发包

版本：0.1.6-alpha.1（2026-09-20 打包，对应源码仓提交 feb50a15c3；tarball=38ea41e8d9 态 TS + wheel=feb50a15c3 态 python）。本版新增：drawio 几何自查（渲染硬门）、实验验证章 09-verification、中文优先回复纪律、宿主面环境自检工具 patent_setup_check、配置文件化偏好（~/.dsh/patent-services.yaml + home patch 启用 MCP 行）。

这是 DeepSeek Harness（dsh）的专利交底书撰写插件「点金」——不是每块石头都值得点，先验金，再点金。丢一个技术点子，它先检索中国专利给出「值不值得写」的评估（可以反驳它），确认方向后走完五方对齐访谈、八章交底书撰写、附图与仿真实验、确定性审查、docx/PDF 导出，以及可选的 Python 导出/渲染/检索/查新服务。

---

## 一、装插件（必选，约 5 分钟）

前提：已安装 [DeepSeek Harness 桌面版](https://github.com/hairyf/deepseek-harness-desktop)（或任意 dsh ≥0.1.5 安装），并能正常打开其 Web 界面。

### 方式 A：一键安装器（推荐）

先用 Windows 终端把插件解包成**目录**（桌面端必须目录形态安装——指向 .tgz 文件的依赖会被桌面壳启动自愈判为死链卸载）：

```sh
mkdir bundle
tar -xzf mtl-academic-dsh-patent-0.1.6-alpha.1.tgz -C bundle --strip-components=1
```

然后运行自带的安装器（把 `<DIST>` 换成解压目录，**正斜杠**）：

```powershell
powershell -ExecutionPolicy Bypass -File install-patent-profile.ps1 -Name patent-demo -DistDir <DIST>
```

安装器一次性完成手动方式的全部步骤：校验分发物 → 建/刷新档案 → 写依赖与 overrides → 装包 → 装 persona（取自 `persona.patch.yml`）→ dump-config 验证。幂等可重跑；打印 `DONE` 即成功。参数说明与故障排查见 [`INSTALL-NEW-PROFILE.md`](INSTALL-NEW-PROFILE.md)（英文）。

安装器仅面向 **Windows**（系统自带 PowerShell）。macOS/Linux 用户直接走方式 B：把 `%USERPROFILE%\.dsh` 换成 `~/.dsh`、桌面版 dsh 垫片在 `~/.local/bin/dsh`（而非 `%LOCALAPPDATA%\deepseek-harness\bin\dsh.cmd`）、用户环境变量写入 shell profile，其余步骤完全一致。

### 方式 B：手动安装

以下以 Windows 路径书写；macOS/Linux 的路径换算见方式 A 末尾的说明。

#### 1. 找到 dsh 命令

桌面版用户：dsh 命令行在桌面版安装时已配置，打开 **Windows 终端（PowerShell）** 直接输入 `dsh` 能看到帮助即可。若提示找不到命令，用桌面版自带的：

```text
%LOCALAPPDATA%\deepseek-harness\bin\dsh
```

（`%LOCALAPPDATA%` 即 `C:\Users\<你的用户名>\AppData\Local`。）

#### 2. 选一个要安装的档案（profile）

- **全新试用**（推荐，不影响现有档案）：
  ```sh
  dsh --profile patent-demo --from-default-profile web --no-open
  ```
  这会创建一个名为 `patent-demo` 的新档案（出错就先 `dsh --profile patent-demo --from-default-profile web` 跑一次不带 --no-open 的，Ctrl+C 退出即可）。
- **装进已有档案**：把下面命令里的 `patent-demo` 换成你的档案名。

#### 3. 解包插件并写入安装配置

先在本目录把插件解包成**目录**：

```sh
mkdir bundle
tar -xzf mtl-academic-dsh-patent-0.1.6-alpha.1.tgz -C bundle --strip-components=1
```

用记事本打开（没有就新建）：

```text
C:\Users\<你的用户名>\.dsh\profiles\patent-demo\pnpm-workspace.yaml
```

在文件**末尾**追加（直接复制，注意缩进）：

```yaml
overrides:
  '@deepseek-ai/dsh-tool-patent': file:<DIST>/deepseek-ai-dsh-tool-patent-0.1.6-alpha.1.tgz
  '@deepseek-ai/dsh-command-patent-review': file:<DIST>/deepseek-ai-dsh-command-patent-review-0.1.6-alpha.1.tgz
  '@deepseek-ai/schemastery': file:<DIST>/deepseek-ai-schemastery-3.18.2.tgz
  '@deepseek-ai/cosmokit': file:<DIST>/deepseek-ai-cosmokit-1.8.3.tgz
```

把其中 4 处 `<DIST>` 全部替换为你解压本包的目录，例如 `G:/dsh-patent-dist`（**正斜杠**）。

#### 4. 安装、装 persona、验收

安装（目录形态，自动写入依赖与 bundles 声明）：

```sh
dsh plugin --profile patent-demo add "file:<DIST>/bundle"
```

装 persona（**强烈建议**——没有这一步插件能跑，但模型没有专利把关人的行为纪律：不会先查新评估、不会反驳你）。两种取法任选：

- 直接拷贝现成补丁：把本目录的 `persona.patch.yml` 复制为 `C:\Users\<你的用户名>\.dsh\profiles\patent-demo\cordis.patch.yml`；
- 或新建 `cordis.patch.yml`，把 `<DIST>/bundle/README.md` 里「The persona lives in the profile」一节的 yaml 块原样拷入。

看到 `Done` 即成功。然后重启 DeepSeek Harness 桌面版，切换到 `patent-demo` 档案开始会话。

**验收**：新会话直接丢一个技术点子（比如"一种校园快递取件码防泄漏的方法"），它应该先检索再给「建议写/收窄后写/不建议写」的评估；或输入「请调用 patent_brief_coverage 打分：field=测试」，展开“1 次工具调用”看到“五方对齐”结构化卡片即插件完整生效。

---

## 二、模型配置（必选）

插件本身不带模型。桌面版界面 **Settings → Models** 里选择并配置你的模型与 API Key（任意 dsh 支持的 provider 均可）。

---

## 三、可选功能

### 导出/检索/实验/查新服务（8 个 MCP 工具）

需要 [uv](https://docs.astral.sh/uv/)（安装：`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`），然后：

```sh
uv tool install "<DIST>/deepseek_harness_patent_services-0.1.0-py3-none-any.whl"
```

再给系统加一个用户环境变量 `DSH_PATENT_SERVICES=1`（系统设置→环境变量），重启桌面版。

### 附图渲染（drawio → PNG/PDF）与仿真实验

装了上面的 Python 服务后可用。需本机有 Docker Desktop（渲染与实验镜像 `q771103517/dsh-patent`、`q771103517/dsh-patent-experiment` 首次使用自动从 Docker Hub 拉取，无需手动构建）；本机装有 [draw.io Desktop](https://github.com/jgraph/drawio-desktop/releases) 则附图渲染无需 Docker。

### 从源码使用（面向开发者）

本仓库本身就是源码仓（`packages/` 三个 TS 包 + `python/patent-services`，见仓库根 README 的「仓库结构」）；技能与 Python 服务可直接改源码——Python 服务经 `DSH_PATENT_SERVICES_DIR` 指源码运行，改动即生效。TS 三包的构建接线（tsdown preset、workspace 依赖）在 deepseek-harness monorepo 内：仓库 Release 附带的 `dsh-patent-full.bundle` 是整条分支的 git bundle，`git clone dsh-patent-full.bundle dsh-patent` 即克隆出完整 monorepo 源码仓（构建：`pnpm install && pnpm run build`）。Python 测试：`uv run --project python/patent-services --group test pytest python/patent-services/tests`。

---

## 文件清单

| 文件 | 说明 |
|---|---|
| `mtl-academic-dsh-patent-*.tgz` | 插件本体（含 14 个技能 + Web UI 卡片/面板），解包为 `bundle/` 目录安装 |
| `deepseek-ai-dsh-tool-patent-*.tgz` | 依赖：就绪度打分、权利要求/正文检查、全流程推进工具 |
| `deepseek-ai-dsh-command-patent-review-*.tgz` | 依赖：/patent-review 审查命令 + patent_review 直通工具 |
| `deepseek-ai-schemastery-*.tgz` / `deepseek-ai-cosmokit-*.tgz` | 依赖：配置校验库（vendored 构建版） |
| `deepseek_harness_patent_services-*.whl` / `.tar.gz` | 可选 Python 服务（8 个 MCP 工具：导出/渲染/检索/实验/查新） |
| `install-patent-profile.ps1` | 一键安装器（方式 A） |
| `persona.patch.yml` | persona 档案补丁正本（装 persona 用） |
| `INSTALL-NEW-PROFILE.md` | 安装器配套的英文分步指南与故障排查 |
| `README.md` | 本文件——中文接收方指南 |

## 核心版本兼容表

插件跨 dsh 核心版本可用（旧核心自动降级，不会失败），但部分能力需要较新的核心才完整生效：

| 能力 | 旧核心（0.1.5-rc 线） | 新核心（0.1.6-alpha 线） |
|---|---|---|
| patent_loop 全流程推进 / 分数门 / 查新债放宽 | ✅ 完整可用 | ✅ 完整可用 |
| 纯函数工具（patent_brief_coverage / patent_claims_lint / patent_prose_lint） | ✅ 完整可用 | ✅ 完整可用 |
| 审查温度（reviewTemperature=0.2） | ⚠️ 自动降级：旧引擎不识别该选项，评分子代理用模型默认温度，审查照常运行 | ✅ 完整生效 |
| 讨论温度（顶层会话 0.7） | ⚠️ 视核心是否在请求载荷注入会话主体而定，未注入则自动关闭 | ✅ 完整生效 |
| 实验自动出图 + 代码指纹入 run-log | ✅ 完整可用（随 Python 服务生效，与核心版本无关） | ✅ 完整可用 |

升级核心后无需重装插件，重启桌面版即带全新行为。

## 已知边界

- 面向 dsh 0.1.5-rc 至 0.1.6-alpha 线核心（桌面版当前 rc 线实测可用）；旧核心缺 Web 卡片时工具显示为文本行，功能不受影响。
- 中国专利查新（search_cn_patents）需要本机能访问 patents.google.com（通常走代理）；检索不可达时工具会明确报错提示，不会返回编造的结果。
- 插件未发布到 npm/PyPI，故需要方式 A/B 的本地路径配置；正式发布后此步骤将退化为一条 `dsh plugin add @mtl-academic/dsh-patent`。
