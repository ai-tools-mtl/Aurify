# 点金 Aurify · 安装与环境指南

[English](INSTALL-NEW-PROFILE.md) · [文档索引](../README.md)

适用于已安装 DeepSeek Harness 桌面版或兼容 dsh 宿主的用户。先配置宿主可用的模型与 API Key；插件不附带模型。宿主兼容代码面向 0.1.5-rc 至 0.1.6-alpha 线，本次文档整理未重新实测版本矩阵。

源码版本见[仓库首页](../../README.md)。GitHub Release、npm/PyPI 和插件市场分别发布；选用哪条安装路线，就核对该渠道实际版本。

## 插件市场与自然语言初始化（推荐）

1. 桌面版 **设置 → 插件市场**搜索 **Aurify** 或 **点金**，安装到当前活动档案。
2. 在该档案会话中输入：

   > 帮我初始化点金插件的运行环境，检查并配置所需依赖和服务。

3. 按 `patent_setup_check` 报告处理依赖与配置。MCP 配置变更后**完整退出并重启桌面版**，再输入：

   > 帮我复检点金插件的环境，确认所需服务已就绪。

服务是否可用以复检为准，保存配置或新开会话不能代替重启。就绪后可描述点子，或提供已有 docx 导入。以下章节用于手动安装和排障。

## npm 与 Windows 安装器

跨平台手动安装：

```sh
dsh plugin --profile patent-demo add @mtl-academic/dsh-patent
dsh --profile patent-demo --dump-config
```

若找不到命令，检查桌面版 dsh 垫片：Windows 为 `%LOCALAPPDATA%\deepseek-harness\bin\dsh.cmd`，macOS/Linux 通常为 `~/.local/bin/dsh`。配置目录默认 `~/.dsh/`（Windows 为 `%USERPROFILE%\.dsh`）。

Windows 用户可从仓库根目录运行安装器；使用 Release 时去掉 `scripts/` 前缀：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-patent-profile.ps1 -Name patent-demo
```

安装器合并档案依赖、从同目录 `persona.patch.yml` 安装专用 persona，并执行 `--dump-config`。参数：`-Name` 指定档案；`-PersonaFrom` 指定已有档案（默认 `auto` 使用随附 persona，空字符串跳过）；`-NoVerify` 跳过验证。安装器仅支持 Windows，macOS/Linux 使用手动命令。

通用档案可保留原 persona。需要专用 persona 时，将 [`persona.patch.yml`](../../scripts/persona.patch.yml) 条目合并到 `~/.dsh/profiles/<档案>/cordis.patch.yml`，不要覆盖已有补丁。Bundle 本身不携带 persona。

装过旧本地包版本时，换回 npm 前移除 `pnpm-workspace.yaml` 中 Aurify 的四个 `file:` overrides；保留不相关配置。安装器的 npm 路径会清理这组旧条目。

## 本地包安装

从 [GitHub Releases](https://github.com/ai-tools-mtl/Aurify/releases) 下载同一版本 ZIP 并核对 `SHA256SUMS`。源码检出不自带 `dist/`。ZIP 含三个插件 tarball、两个配置库 tarball、Python wheel/sdist、安装器、persona 与双语指南；`bundle/` 需手动解包生成。

本地包只替代部分下载，完全断网仍需预备宿主、npm/Python 传递依赖和 Docker 镜像。

在发行目录中解包（将 `<版本>` 替换为实际文件名中的版本）：

```sh
mkdir bundle
tar -xzf mtl-academic-dsh-patent-<版本>.tgz -C bundle --strip-components=1
```

Windows 优先使用 `C:\Windows\System32\tar.exe`，避免 Git MSYS tar 在受限 shell 中报 signal pipe 错误。解包后，`bundle/` 与五个 `.tgz` 应位于同一目录。

Windows 安装：

```powershell
powershell -ExecutionPolicy Bypass -File install-patent-profile.ps1 -Name patent-demo -Offline -DistDir "C:/aurify-release"
```

`-DistDir` 使用正斜杠绝对路径。安装完成后保留发行目录：档案运行时引用其中的 `bundle/`，移动或删除会使档案无法解析。

跨平台手动替代步骤：

1. 为新档案先执行 `dsh plugin --profile patent-demo add "file:<DIST>/bundle"` 建立清单。依赖未配置齐时可能失败；确认清单已建立后继续。
2. 合并档案 `package.json` 的依赖 `"@mtl-academic/dsh-patent": "file:<DIST>/bundle"`，并确保 `dsh.profile.bundles` 包含该包。保留原有宿主层和其他依赖。
3. 在档案 `pnpm-workspace.yaml` 合并以下四项。替换 `<DIST>` 与 `<版本>`，配置库版本以实际附件名为准：

   ```yaml
   overrides:
     '@mtl-academic/dsh-tool-patent': 'file:<DIST>/mtl-academic-dsh-tool-patent-<版本>.tgz'
     '@mtl-academic/dsh-command-patent-review': 'file:<DIST>/mtl-academic-dsh-command-patent-review-<版本>.tgz'
     '@deepseek-ai/schemastery': 'file:<DIST>/deepseek-ai-schemastery-3.18.2.tgz'
     '@deepseek-ai/cosmokit': 'file:<DIST>/deepseek-ai-cosmokit-1.8.3.tgz'
   ```

4. 执行 `dsh plugin --profile patent-demo install`，选装 persona，再执行 `dsh --profile patent-demo --dump-config`。

所有 `file:` 值均使用绝对路径。Bundle 指向解包目录，不指向 `.tgz`。升级时使用新版本附件并重跑安装器，勿混放多个版本或覆盖同版本已发布文件。

## 服务与运行依赖

需要 [uv/uvx](https://docs.astral.sh/uv/) 才能启动 Python MCP 服务。合并配置到 `$DSH_HOME/patent-services.yaml`（默认 `~/.dsh/patent-services.yaml`），选择一种模式：

```yaml
mcp_enabled: true
mcp_wheel: true  # uvx 从 PyPI 解析，未锁定为本仓库版本
```

精确使用本版或预缓存依赖后离线运行时，使用源码模式：

```yaml
mcp_enabled: true
mcp_project_dir: /absolute/path/to/Aurify/python/patent-services
```

源码目录须为含 `pyproject.toml` 的绝对路径。wheel 模式执行 `uvx --from deepseek-harness-patent-services patent-services`，无需先 `uv tool install`，也不保证使用已安装的本地 wheel。两种模式均需 `mcp_enabled: true`。

脚本化场景可改用 `DSH_PATENT_SERVICES=1` 或 `DSH_PATENT_SERVICES_DIR`。变更启用方式、源码路径或 PATH 后，完整重启桌面版并复检；图形应用不一定继承 shell 配置中的变量。

| 能力 | 额外依赖 |
|---|---|
| docx 导入/导出、归档检索 | Python MCP 服务 |
| PDF | Windows Word COM，或另行配置 weasyprint 及系统库；回退版式可能不同 |
| drawio 渲染 | draw.io CLI 或 Docker；默认镜像 `q771103517/dsh-patent:latest` |
| HTML 渲染 | Edge/Chrome；固定视口可能裁切过高画布 |
| 仿真实验 | 运行中的 Docker；默认镜像 `q771103517/dsh-patent-experiment:latest` |
| 中国专利检索 | 可访问 `patents.google.com` 的网络 |

镜像首次使用可能需要拉取。自检会报告各通道状态，项目起步按技能要求处理受限项；检索通道跳过须由用户明确选择并保留待补查标记。服务接口和设置项见 [Python 服务说明](../../python/patent-services/README.zh.md)。

## 验收、恢复与排障

手动安装后，先确认 `--dump-config` 退出码为 0，再重启桌面版。应出现 `tool-patent`、`patent-assets`、`command-patent-review`、`mcp-patent-services` 行；MCP 行存在不等于服务已启用，仍需会话内自检。可请求 `patent_brief_coverage` 检查 `field=测试`，核对工具结果；旧宿主可能仅显示文本卡片。

已有档案的 `package.json`、bundle 层与补丁只合并修改。安装器刷新已有档案前备份到 `~/.dsh/.plugin-backups/<档案>-<时间戳>/`；误删宿主插件声明时优先从备份恢复，或按该档案 lockfile 的 `importers` 重建依赖与 bundle 层后重装。

| 现象 | 处理 |
|---|---|
| `cannot resolve profile bundle` / 插件重启后消失 | 核对 `file:` 绝对路径和 `bundle/` 是否保留；修复目录依赖后重装，无需删除整个档案 |
| `ERR_PNPM_WORKSPACE_PKG_NOT_FOUND` | 检查本地包路径及 overrides；确认使用本版构建产物，不是未转换的源码 manifest |
| `--dump-config` 报 `EPERM` | 命令需写入档案 `cordis.yml`，从有写权限的终端重跑 |
| 看不到 MCP 工具 / 显示待重启 | 检查总开关、模式、uv/uvx 的 PATH；完整退出桌面版再启动 |
| wheel 拉取失败 | 检查 PyPI 连通性及 uv/uvx；精确版本或受限网络使用已缓存依赖的源码模式 |
| 审查鉴权失败 / `model not found` | 在宿主模型设置中选择网关实际支持且已配置密钥的模型 |
| 某审查维度全部失败 | 查看报告中的失败原因，排除限流、网络或模型错误后重试；不只看总分 |
| 检索不可达 | 检查网络和代理，保留失败原因；不要用编造命中替代 |

旧核心的评分温度、讨论温度和 Web 卡片依能力检测回退。升级宿主后仍需复检，不把兼容分支视为全版本实测证明。

开发、测试和打包见[开发指南](../DEVELOPMENT.md)与[发布流程](../RELEASING.md)。
