# 开发指南

Aurify 是从 DeepSeek Harness monorepo 提取的插件源码仓。三个 TypeScript 包依赖宿主运行时；Python MCP 服务可独立测试和打包。组件接口见[文档索引](README.md)。

## 目录与配置正本

| 路径 | 内容 |
|---|---|
| `packages/bundle-patent` | 14 个技能、Web 卡片、项目面板与组合 patch |
| `packages/tool-patent` | 五个原生工具、`/patent-loop` 与环境检查 |
| `packages/command-patent-review` | 审查命令/工具、固定 workflow 与七维 rubric |
| `python/patent-services` | 十个 MCP 工具、Word 模板、Dockerfile 与 Python 测试 |
| `docs/install` | 双语安装指南，同时作为 Release 附件源 |
| `scripts` | 独立构建、校验、Windows 安装器、persona 正本及宿主版本映射 |
| `dist` | Git 忽略的本地生成目录 |

用户 persona 只维护 `scripts/persona.patch.yml`，不要在 README 复制全文。技能、示例、模板和第三方许可证是运行资产；diagram-design 按其 [VENDORED.md](../packages/bundle-patent/skills/diagram-design/VENDORED.md) 更新，专利规范放在本地专利技能中。

## 构建发布包

要求 Node.js 20+、npm、Python 3.10+、[uv](https://docs.astral.sh/uv/) 和 `tar`。从仓库根目录执行，发布前确保 `dist/` 为空；需保留的旧产物先移到仓库外：

```sh
npm --prefix scripts ci
npm --prefix scripts run build
uv build --out-dir dist python/patent-services
python3 scripts/prepare-release.py
python3 scripts/verify-dist.py --write-checksums
python3 scripts/verify-dist.py
```

`build-dist.mjs` 使用 `scripts/workspace-versions.json` 替换宿主 workspace 依赖；内部三个包引用当前版本，宿主运行时依赖外置。`prepare-release.py` 从 npm 官方 registry 获取安装器使用的两个配置库归档，复制安装器、persona 和双语指南，再生成版本化 ZIP。`verify-dist.py` 核对入口、技能数、rubric、Python 资产、ZIP 内容和 SHA-256，并拒绝混入旧附件。

安装指南在源码中使用相对链接；复制到 Release 时将仓库文档链接转换为 GitHub 地址，保留发行包内双语互链与 persona 链接。不要手改 `dist/` 中的生成副本。

## 验证范围

Python 测试：

```sh
uv run --locked --project python/patent-services --group test pytest python/patent-services/tests -q
```

独立 TS 构建生成 JS、Web 客户端和 `.d.ts`。**声明生成使用 `noCheck`，构建通过不代表完整类型检查通过。** TS 的 vitest、完整类型检查和宿主 UI 集成需兼容的 DeepSeek Harness monorepo，本仓库不附带该 monorepo。

CI 执行 Python 测试、独立构建及产物完整性校验，不执行宿主 UI、Windows 安装器或 Docker 全链路。记录验证结果时写清执行范围，兼容代码分支不作为实测结论。

开发时可在 `~/.dsh/patent-services.yaml` 合并以下配置，替换实际绝对路径：

```yaml
mcp_enabled: true
mcp_project_dir: /absolute/path/to/Aurify/python/patent-services
```

完整重启宿主后运行 `patent_setup_check`。wheel 模式不锁定本地版本，不能用它证明当前源码已加载。

## 文档维护规则

- 首页只保留简介、快速开始与导航；详细配置放安装指南，接口语义放组件 README，构建与发布各归对应指南。
- 中英文组件说明及安装指南同步修改；更新同目录 `README.i18n.yaml` 中的 `git hash-object <文件>` 值。
- 删除重复、失效或与实现冲突的说明。只有仍具追溯价值的版本专用记录进入 `docs/archive/`，标明日期和现行入口；功能历史统一写入 `CHANGELOG.md`。
- 检查 Markdown 本地路径、标题锚点、版本、工具数量和文档命令的工作目录。修改发行指南时检查复制后的链接。
- 纯文案修改不要求宿主全量测试；修改技能指令需对照工具行为；修改打包流程需从空 `dist/` 构建并校验。
