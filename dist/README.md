# 点金 Aurify · dsh 专利撰写插件 · 离线分发包

**0.1.6-alpha.2** · 2026-09-24 打包 · tarball=@mtl-academic 改名后 alpha.2 态 TS / wheel=d04f14094d 态 python(不变)

**本版要点**：MCP 装载前校验（相对路径、缺 `pyproject.toml` 直接拒绝）、env 模式补绝对路径校验、wheel 模式探测 uv 工具、安装器 overrides 原位刷新，且 `-DistDir` 自动锚定为绝对路径。更早的变更见 `git log` 与本仓库的 Release 说明。

这是 DeepSeek Harness（dsh）的专利交底书撰写插件「点金」——不是每块石头都值得点，先验金，再点金。丢一个技术点子，它先检索中国专利给出「值不值得写」的评估（可以反驳它），确认方向后走完五方对齐访谈、八章交底书撰写、附图与仿真实验、确定性审查、docx/PDF 导出，以及可选的 Python 导出/渲染/检索/查新服务。

---

## 一、装插件（必选，约 5 分钟）

前提：已安装 [DeepSeek Harness 桌面版](https://github.com/hairyf/deepseek-harness-desktop)（或任意 dsh ≥0.1.5 安装），并能正常打开其 Web 界面。

> **先约定两件事**：① `<DIST>` 指**解压本包的目录**（绝对路径），本文示例统一用 `G:\dsh-patent-dist`；② 命令里的文件名/版本号（`...-0.1.6-alpha.2.tgz`、`schemastery-3.18.2` 等）按**本版分发物**写死，换版后以 `<DIST>` 目录内实际文件名为准——英文指南 [INSTALL-NEW-PROFILE.md](INSTALL-NEW-PROFILE.md) 用 `<version>` 占位符表达同一件事，两者等价。

### 方式 A：一键安装器（推荐）

先在本目录（tarball 所在目录）把插件解包成**目录**——安装器要求 `<DIST>\bundle\` 与那几个 `.tgz` 同级（桌面端必须目录形态安装：指向 .tgz 文件的依赖会被桌面壳启动自愈判为死链卸载）：

```sh
mkdir bundle
tar -xzf mtl-academic-dsh-patent-0.1.6-alpha.2.tgz -C bundle --strip-components=1
```

然后运行自带的安装器（`-DistDir` 就是 `<DIST>`：**绝对路径、正斜杠**；下同，示例用 `G:/dsh-patent-dist`）：

```powershell
powershell -ExecutionPolicy Bypass -File install-patent-profile.ps1 -Name patent-demo -DistDir "G:/dsh-patent-dist"
```

安装器一次性完成手动方式的全部步骤：校验分发物 → 建/刷新档案 → 写依赖与 overrides → 装包 → 装 persona（取自 `persona.patch.yml`）→ dump-config 验证。幂等可重跑；打印 `DONE` 即成功。参数说明与故障排查见 [`INSTALL-NEW-PROFILE.md`](INSTALL-NEW-PROFILE.md)（英文）。

> **`-DistDir` 必须写绝对路径**（相对路径安装器会自动锚定成当前目录的绝对路径）。这个值会原样写进档案清单的 `file:` 依赖，而 dsh 按**档案目录**解析 `file:`（不是按你运行命令时所在的目录）：写成相对路径装出来的档案，`dsh --profile <名>` 会报 `cannot resolve profile bundle`，桌面版直接打不开该档案。手工改清单时同理——`file:./bundle` 是错的，只有绝对路径对。
>
> **解包出来的 `bundle\` 目录是运行期依赖，装完别删也别移动。** 档案清单用绝对路径引用它，桌面壳每次启动都会解析一遍清单里的 `file:` 依赖，指向不存在目录的会被判为死链卸掉。
>
> Windows 上如果 `tar` 命中 Git 自带的那份（`C:\Program Files\Git\usr\bin\tar.exe`），在受限 shell / 沙箱环境里会以 `couldn't create signal pipe, Win32 error 5` 直接崩掉；改用系统自带的 `C:\Windows\System32\tar.exe`（Win10 1803+ 起随系统提供）即可。

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
- **装进已有档案**：把下面命令里的 `patent-demo` 换成你的档案名；如果这个档案是**桌面版自己建/自己在用**的（里面有 `dsh-tauri*`、`dshmarket` 等条目），先读一遍下面的[「装进已有档案」](#装进已有档案含桌面版自建档案)小节再动手。

#### 3. 解包插件并写入安装配置

先在本目录（tarball 所在目录）把插件解包成**目录**，让 `bundle\` 与那几个 `.tgz` 同级：

```sh
mkdir bundle
tar -xzf mtl-academic-dsh-patent-0.1.6-alpha.2.tgz -C bundle --strip-components=1
```

用记事本打开：

```text
C:\Users\<你的用户名>\.dsh\profiles\patent-demo\pnpm-workspace.yaml
```

这个文件通常已由档案模板创建，里面已有基础设置（`packages: - .`、`nodeLinker: hoisted`、`autoInstallPeers: false`）——**这种情况只把下面的 `overrides:` 段追加到文件末尾**（直接复制，注意缩进；值外面那层引号别省，路径里带空格时会用到）：

```yaml
overrides:
  '@mtl-academic/dsh-tool-patent': 'file:<DIST>/mtl-academic-dsh-tool-patent-0.1.6-alpha.2.tgz'
  '@mtl-academic/dsh-command-patent-review': 'file:<DIST>/mtl-academic-dsh-command-patent-review-0.1.6-alpha.2.tgz'
  '@deepseek-ai/schemastery': 'file:<DIST>/deepseek-ai-schemastery-3.18.2.tgz'
  '@deepseek-ai/cosmokit': 'file:<DIST>/deepseek-ai-cosmokit-1.8.3.tgz'
```

文件不存在、要从头新建时（少见），**基础设置不能省**：少了 `nodeLinker: hoisted`，pnpm 会用默认的 `isolated` 布局，装出来的结构与本文验证过的不同。完整内容就是基础设置加上面那段：

```yaml
packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false

overrides:
  '@mtl-academic/dsh-tool-patent': 'file:<DIST>/mtl-academic-dsh-tool-patent-0.1.6-alpha.2.tgz'
  '@mtl-academic/dsh-command-patent-review': 'file:<DIST>/mtl-academic-dsh-command-patent-review-0.1.6-alpha.2.tgz'
  '@deepseek-ai/schemastery': 'file:<DIST>/deepseek-ai-schemastery-3.18.2.tgz'
  '@deepseek-ai/cosmokit': 'file:<DIST>/deepseek-ai-cosmokit-1.8.3.tgz'
```

把其中 4 处 `<DIST>` 全部替换为解压本包的目录，例如 `G:/dsh-patent-dist`（**正斜杠**）。**必须是绝对路径**——这些 `file:` 值由 dsh 按档案目录解析，相对路径会让档案启动时报 `cannot resolve profile bundle`。

#### 4. 安装、装 persona、验收

安装（目录形态，自动写入依赖与 bundles 声明）：

```sh
dsh plugin --profile patent-demo add "file:<DIST>/bundle"
```

同样的绝对路径要求：`file:<DIST>/bundle` 里的 `<DIST>` 写绝对路径。若这一步的 pnpm 段报 `ERR_PNPM_WORKSPACE_PKG_NOT_FOUND`（`workspace:^`），说明第 3 步的 4 行 overrides 没写对或路径不对——它们是必需项，回去核对。

装 persona（**强烈建议**——没有这一步插件能跑，但模型没有专利把关人的行为纪律：不会先查新评估、不会反驳你）。两种取法任选：

- 直接拷贝现成补丁：把本目录的 `persona.patch.yml` 复制为 `C:\Users\<你的用户名>\.dsh\profiles\patent-demo\cordis.patch.yml`（注意：这会**整个覆盖**该档案原有的 `cordis.patch.yml`，档案里已有别的补丁条目时会一并丢失——按方式 A 的安装器不会覆盖已有 persona，手改时请改成把 persona 条目**追加**进现有文件）；
- 或新建 `cordis.patch.yml`，把 `<DIST>/bundle/README.md` 里「The persona lives in the profile」一节的 yaml 块原样拷入。

看到 `Done` 即成功。

**重启前先验收清单能不能解析**（这一步不能省）：

```sh
dsh --profile patent-demo --dump-config
```

命令**退出码为 0**、输出里能看到 `tool-patent`、`patent-assets`、`command-patent-review`、`mcp-patent-services` 四行与 `persona:` 键，才算装好。若报 `cannot resolve profile bundle "@mtl-academic/dsh-patent"` 或 `ERR_PNPM_*`，**先把档案修好再重启桌面版**：损坏的清单会让桌面版连该档案都打不开（不是「插件不生效」，而是整个档案起不来）。`DANGLING` / `UNINSTALLING` 行说明 bundle 是以 tarball 形态（而非目录形态）装进去的。

然后重启 DeepSeek Harness 桌面版，切换到 `patent-demo` 档案开始会话。

**验收**：新会话直接丢一个技术点子（比如"一种校园快递取件码防泄漏的方法"），它应该先检索再给「建议写/收窄后写/不建议写」的评估；或输入「请调用 patent_brief_coverage 打分：field=测试」，展开“1 次工具调用”看到“五方对齐”结构化卡片即插件完整生效。

#### 装进已有档案（含桌面版自建档案）

桌面版会在**它自己建、自己在用**的档案里放一批它自己的依赖与 bundles 层：`dsh-tauri`、`dsh-tauri-connection`、`dsh-tauri-model-config`、`dsh-tauri-panel-extension`、`dsh-tauri-panel-scheduler`、`dsh-tauri-pet`、`dsh-tauri-rightclick`、`dsh-tauri-session`、`dsh-tauri-turnrewind`、`dsh-tauri-ui`、`dsh-tauri-worktree`（`link:` 形态）与 `dshmarket`、`dsh-better-sidebar`、`dsh-rewind-plugin`、`@xmanrui/dsh-im`。**这些条目必须留在清单里**：

- 方式 A 的安装器是**合并**写入——只确保 `@mtl-academic/dsh-patent` 依赖与 `dsh-base`/`dsh-web-app`/`@mtl-academic/dsh-patent` 三个层，其它条目原样保留，重跑不会抹掉它们；
- **手改时只加不删**。用编辑器整个覆盖 `package.json`（或早期版本安装器那种整体重写）会丢掉上面这些声明，接着 `dsh plugin install` 的 pnpm 段会把它们当**多余包删掉**——档案就丢了桌面版插件（市场、侧边栏、IM、rewind、Tauri 桥全没了）；
- 已经丢了的恢复：安装器每次刷新**已有**档案前，会自动把 `package.json`、`pnpm-workspace.yaml`、`pnpm-lock.yaml`、`cordis.patch.yml` 备份到 `~/.dsh/.plugin-backups/<档案名>-<时间戳>/`，先看那里；没有备份就按该档案自己的 `pnpm-lock.yaml` 顶部 `importers:` 段把依赖键值抄回 `package.json` 的 `dependencies`，并把对应名字补回 `dsh.profile.bundles`，然后重跑安装器。

装完**别急着重启**：先按上面第 4 步的验收命令确认 `--dump-config` 退出码为 0。

---

## 二、模型配置（必选）

插件本身不带模型。桌面版界面 **Settings → Models** 里选择并配置你的模型与 API Key（任意 dsh 支持的 provider 均可）。

审查链路（`/patent-review`、`patent_review`）要真跑评分子代理，所以模型必须是**你所用网关确实支持**的那个：经 GLM 网关调用默认 deepseek 线会报 `model not found`。本发行包的推荐组合是 GLM 网关 + 该网关下的 GLM 模型组，组名以你 `Settings → Models` 里的实际配置为准（文档中的 `zai-coding-cn` 只是本机配置示例）。

---

## 三、可选功能

### 导出/检索/实验/查新服务（9 个 MCP 工具）

需要 [uv](https://docs.astral.sh/uv/)（安装：`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`），然后：

```sh
uv tool install "<DIST>/deepseek_harness_patent_services-0.1.0-py3-none-any.whl"
```

wheel 模式的前提就是这一步（该包未发布 PyPI，`uvx` 只能解析 `uv tool install` 装过的工具）；换了 wheel 版本要重装一次，装了源码目录则不需要。

> 若 `irm` 在受限 shell / 沙箱里报「基础连接已经关闭」或 `SEC_E_NO_CREDENTIALS`（.NET schannel 取不到凭证），改用系统自带的 curl 下载再执行：
> ```powershell
> curl.exe -LsSf -o "$env:TEMP\uv-install.ps1" https://astral.sh/uv/install.ps1
> powershell -ExecutionPolicy Bypass -File "$env:TEMP\uv-install.ps1"
> ```
> 安装脚本把 `uv`/`uvx` 放到 `%USERPROFILE%\.local\bin` 并写进用户 PATH；**PATH 变更对已运行的进程无效**，所以 uv 装完后要重启桌面版才会被 MCP 行找到（正好和「MCP 行在进程启动时装载」是同一次重启）。安装脚本与 `uv tool install` 都会打印一句 `warning: ...\.local\bin is not on your PATH`——那是**当前这个 shell** 的 PATH 还没刷新（用户级 PATH 已经写好），重启终端/桌面版即消失，不用处理。

启用方式（首选，单文件）：在 `~/.dsh/patent-services.yaml` 写——

```yaml
mcp_enabled: true          # 总开关，两种模式都必须写；只写下面那行不会生效
mcp_wheel: true            # 装了 wheel 的机器（uv tool install 过本包的 wheel）
```

用源码的机器则写 `mcp_enabled: true` 加 `mcp_project_dir: <patent-services 源码目录的绝对路径>`（相对路径会被拒绝；目录里必须有 `pyproject.toml`）。布尔值 `true`/`1`/`yes`/`on` 均可，注释用 `#`。

保存后**完整重启桌面版**：MCP 行在进程启动时装载，仅新开会话不生效；会话内可用 `patent_setup_check` 自检（区分「已装载/待重启」）。脚本化场景也可改用用户环境变量 `DSH_PATENT_SERVICES=1`（系统设置→环境变量）。

### 附图渲染（drawio → PNG/PDF）与仿真实验

装了上面的 Python 服务后可用。需本机有 Docker Desktop（渲染与实验镜像 `q771103517/dsh-patent`、`q771103517/dsh-patent-experiment` 首次使用自动从 Docker Hub 拉取，无需手动构建）；本机装有 [draw.io Desktop](https://github.com/jgraph/drawio-desktop/releases) 则附图渲染无需 Docker。

### 从源码使用（面向开发者）

本仓库本身就是源码仓（`packages/` 三个 TS 包 + `python/patent-services`，见仓库根 README 的「仓库结构」）；技能与 Python 服务可直接改源码——Python 服务经 `DSH_PATENT_SERVICES_DIR` 指源码运行，改动即生效。TS 三包的构建接线（tsdown preset、workspace 依赖）在 deepseek-harness monorepo 内：仓库 Release 附带的 `dsh-patent-full.bundle` 是整条分支的 git bundle，`git clone dsh-patent-full.bundle dsh-patent` 即克隆出完整 monorepo 源码仓（构建：`pnpm install && pnpm run build`）。Python 测试：`uv run --project python/patent-services --group test pytest python/patent-services/tests`。

---

## 文件清单

| 文件 | 说明 |
|---|---|
| `mtl-academic-dsh-patent-*.tgz` | 插件本体（含 14 个技能 + Web UI 卡片/面板），解包为 `bundle/` 目录安装 |
| `bundle/` | 上一条解包出来的**目录**（安装源的真正形态，与 tarball 同级由安装器校验；装完别删别移动——档案清单用绝对路径引用它） |
| `mtl-academic-dsh-tool-patent-*.tgz` | 依赖：就绪度打分、权利要求/正文检查、全流程推进工具 |
| `mtl-academic-dsh-command-patent-review-*.tgz` | 依赖：/patent-review 审查命令 + patent_review 直通工具 |
| `deepseek-ai-schemastery-*.tgz` / `deepseek-ai-cosmokit-*.tgz` | 依赖：配置校验库（vendored 构建版） |
| `deepseek_harness_patent_services-*.whl` / `.tar.gz` | 可选 Python 服务（9 个 MCP 工具：导出/渲染/检索/实验/查新） |
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

## 常见故障

| 现象 | 原因与处理 |
|---|---|
| `dsh --profile <名> --dump-config` 报 `cannot resolve profile bundle "@mtl-academic/dsh-patent"`；桌面版重启后打不开该档案 | 档案清单里的 `file:` 指向了解析不到的位置。dsh 按**档案目录**解析 `file:`，所以 `file:./bundle` 这类相对值、或已被删除/移动的 release 目录都会命中：把 `package.json` 的 `@mtl-academic/dsh-patent` 改成 `file:<DIST的绝对路径>/bundle`，`pnpm-workspace.yaml` 的 4 行 overrides 同样改成绝对路径，再跑一次 `dsh plugin --profile <名> install`（或直接重跑方式 A 安装器，它会原位刷新这 4 行） |
| 重启后市场/侧边栏/IM/rewind/Tauri 桥全没了，或安装日志出现 `Packages: +N -M` 把桌面版插件删掉 | 装插件时把档案 `package.json` 整个覆盖了，桌面版自己那批依赖（`dsh-tauri*`、`dshmarket`、`dsh-better-sidebar`、`dsh-rewind-plugin`、`@xmanrui/dsh-im`）掉出清单，pnpm 当多余包清掉。见[「装进已有档案」](#装进已有档案含桌面版自建档案)的恢复步骤 |
| `ERR_PNPM_WORKSPACE_PKG_NOT_FOUND`（`workspace:^`） | `pnpm-workspace.yaml` 的 overrides 块缺失或路径不对；对照 `<DIST>` 里实际存在的 4 个 tarball 名字逐行核对。注意 overrides 只能写在 `pnpm-workspace.yaml`（pnpm 11 忽略 `package.json` 里的 `pnpm` 字段） |
| 日志出现 `DANGLING_LINK_UNINSTALLING`，插件重启后消失 | bundle 是以 `.tgz` 文件形态装进去的。桌面壳启动自愈会把指向非目录的 `file:` 依赖卸掉；删掉该档案重装，`add`/依赖必须指向解包出来的 `bundle` **目录** |
| 装完测试 `dsh ... --dump-config` 报 `EPERM: operation not permitted, open '...\cordis.yml'` | 不是档案坏了：`--dump-config` 会重写档案根部的 `cordis.yml`，只读/受限 shell（或 AI 沙箱）里跑就会这样。用有写权限的普通终端重跑即可 |
| Windows 上 `tar -xzf` 报 `couldn't create signal pipe, Win32 error 5` | `tar` 命中了 Git 自带的 MSYS 版，在受限 shell / 沙箱里起不来。改用 `C:\Windows\System32\tar.exe -xzf ... -C ... --strip-components=1` |
| 模型看不到导出/渲染/检索工具 | Python 服务门没开：`~/.dsh/patent-services.yaml` 缺 `mcp_enabled: true`（总开关，只有 `mcp_wheel`/`mcp_project_dir` 不生效），或配置写得晚于进程启动——MCP 行在进程启动时装载，**完整重启桌面壳**才对（新开会话不够）。会话内 `patent_setup_check` 区分「已装载/待重启」 |
| wheel 模式自检说「未检出已安装的 patent-services 包」 | 该包未发布 PyPI，`uvx` 只能解析 `uv tool install` 装过的工具：先在 `<DIST>` 跑 `uv tool install deepseek_harness_patent_services-0.1.0-py3-none-any.whl`，再重启 |
| 审查报 "model not found" / 鉴权错误 | 会话里换一个你所用网关**确实支持**的模型（审查要真跑评分子代理）。经 GLM 网关调用默认 deepseek 线会报 model not found；本发行包推荐 GLM 网关下的 GLM 模型组，组名以你 `Settings → Models` 实际配置为准（文档里的 `zai-coding-cn` 只是示例） |
| 某个审查维度报全部评分失败 | 网关限流。脚本化审查会分批退避重试，再跑一次 `patent_review` 通常就恢复 |

## 已知边界

- 面向 dsh 0.1.5-rc 至 0.1.6-alpha 线核心（桌面版当前 rc 线实测可用）；旧核心缺 Web 卡片时工具显示为文本行，功能不受影响。
- 中国专利查新（search_cn_patents）需要本机能访问 patents.google.com（通常走代理）；检索不可达时工具会明确报错提示，不会返回编造的结果。
- npm 路线：三个 `@mtl-academic` 包发布后，一条 `dsh plugin add @mtl-academic/dsh-patent` 即完成安装。npm/PyPI 尚未就绪或需离线安装时，走方式 A/B 的本地路径配置。
