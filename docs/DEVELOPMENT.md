# 开发指南

Aurify 是从 deepseek-harness monorepo 提取的插件源码仓。三个 TypeScript 包使用宿主提供的运行时；Python MCP 服务可独立测试和打包。

## 目录职责

| 路径 | 内容 |
|---|---|
| `packages/bundle-patent` | 14 个技能、Web 卡片和项目面板、bundle patch |
| `packages/tool-patent` | 五个原生工具、`/patent-loop` 与环境检查 |
| `packages/command-patent-review` | `/patent-review`、`patent_review` 与七维 rubric |
| `python/patent-services` | 十个 MCP 工具、Word 模板与 Python 测试 |
| `docs/install` | 中英文安装参考 |
| `scripts` | 独立构建、校验、安装器、persona 与 workspace 发布版本映射 |
| `dist` | 本地生成的 Release 资产，不受 Git 追踪 |

Word 模板和技能示例属于运行所需的源码资产，应保留在仓库。

## 构建发布包

要求 Node.js 20+、npm、Python 3.10+、[uv](https://docs.astral.sh/uv/) 和 `tar`。从仓库根目录执行：

```sh
npm --prefix scripts ci
npm --prefix scripts run build
uv build --out-dir dist python/patent-services
python3 scripts/prepare-release.py
python3 scripts/verify-dist.py --write-checksums
python3 scripts/verify-dist.py
```

`build-dist.mjs` 使用 `scripts/workspace-versions.json` 解析宿主 workspace 依赖，不读取旧安装包。内部三个包按当前版本互相引用；宿主运行时依赖保持外置。`prepare-release.py` 从 npm 官方 registry 获取安装器需要的两个配置库归档，将安装脚本、persona 和指南复制到 `dist/`，生成版本化的 ZIP。`SHA256SUMS` 覆盖所有独立发布文件及 ZIP。

此独立构建生成 JS、Web 客户端和 `.d.ts`，**声明生成使用 `noCheck`，不代表完整 TypeScript 类型检查通过**。TypeScript 的 vitest、类型检查和实际宿主 UI 集成需放回兼容的 deepseek-harness monorepo 执行，本仓库不附带该 monorepo，也不承诺存在额外 git bundle。

## Python 测试与源码模式

```sh
uv run --locked --project python/patent-services --group test pytest python/patent-services/tests -q
```

在 `~/.dsh/patent-services.yaml` 合并以下配置，可直接运行本版 Python 源码（替换为实际绝对路径）：

```yaml
mcp_enabled: true
mcp_project_dir: /absolute/path/to/Aurify/python/patent-services
```

完整退出并重启桌面版，再让助手调用 `patent_setup_check` 复检。`mcp_wheel: true` 使用未指定版本的 PyPI 名称，不能据此断言加载了本地构建的 wheel。

## 文档维护

根 README 负责快速上手和导航；安装指南负责详细配置；包 README 保留各组件实现约定。修改双语 README 后同步两种语言，并用 `git hash-object` 更新同目录 `README.i18n.yaml`。只改文档不需要运行宿主全量测试；改变打包流程时必须从空 `dist/` 构建并校验。
