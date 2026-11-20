# 开发指南

Aurify 是从 DeepSeek Harness monorepo 提取的插件源码仓。三个 TypeScript 包依赖宿主运行时；Python MCP 服务可独立测试和打包。组件接口见[文档索引](README.md)。

## 目录与配置正本

| 路径 | 内容 |
|---|---|
| `packages/bundle-patent` | 15 个技能、Web 卡片、项目面板与组合 patch |
| `packages/tool-patent` | 五个原生工具、`/patent-loop` 与环境检查 |
| `packages/command-patent-review` | 审查命令/工具、固定 workflow 与七维 rubric |
| `python/patent-services` | 十五个 MCP 工具、Word 模板、Dockerfile 与 Python 测试（`repo_*` 五件为仓库挖掘：接入 GitHub/GitLab/Gitee/本地 clone，配置在 `~/.dsh/repo-mining.yaml`） |
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

已安装 `scripts` 构建依赖时，可独立验证评估恢复的工具／命令入口：

```sh
node --test packages/tool-patent/tests/loop-recovery.standalone.test.mjs
```

审查阈值常量在 `tool-patent/src/loop.ts`（正本）与 `bundle-patent/src/client/project-model.ts`（客户端镜像）各存一份，镜像由同步守卫测试看护，可独立运行：

```sh
node --test packages/tool-patent/tests/threshold-sync.standalone.test.mjs
```

该测试使用真实的注册代码、命令、阶段判定器、源指纹和临时文件，仅替代宿主的工具注册及消息包装，不启动 MCP 或访问网络。覆盖成稿项目仍注入评估核对、证据同步到 brief 后旧产物失效及 review 阶段仍有恢复指令、环境门与用户选择要求保留。它不运行模型，不能证明技能已实际完成语义重评、法律判断或提案全部行为场景；完整宿主和模型验收需另行执行。

CI 执行 Python 测试、独立构建及产物完整性校验，不执行宿主 UI、Windows 安装器或 Docker 全链路。`release` 工作流在 main 上版本号推进时自动发布 npm/PyPI/Release/Docker（触发条件与密钥见[发布流程](RELEASING.md)「自动化发布」节）。记录验证结果时写清执行范围，兼容代码分支不作为实测结论。

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
