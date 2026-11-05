# deepseek-harness-patent-services

[English](README.md) | 中文

Aurify 的 Python MCP stdio 服务。Bundle 启用后，十五个工具以 `mcp__patent__` 前缀出现在模型工具表中。安装与启用统一见[安装指南](../../docs/install/README.md#服务与运行依赖)。

## 工具接口

`?` 表示可选参数，实际默认值见 `src/patent_services/server.py`。

| 工具及参数 | 行为 |
|---|---|
| `import_patent_document(project_dir, document_path, name?, overwrite?)` | 将 docx 节标题映射到八章，生成 brief 骨架和缺失的 manifest；额外一级节追加章节，权利要求与摘要不原文导入。已有内容默认拒绝覆盖 |
| `parse_disclosure_docx(path, output_path?)` | 按显式样式和编号解析三层 Markdown，可写出文件；跳过表格和嵌入图片 |
| `export_disclosure(project_dir, fmt?)` | 基于随包代理机构模板生成交底书，嵌入图N成品，返回路径、附图数和审查/标题警告 |
| `export_application_docs(project_dir, fmt?)` | 将 `application/{claims,description,abstract}.md` 导出为单文件多分节；有附图时加入摘要附图和说明书附图 |
| `render_drawio_figure(source, fmt?)` | drawio → png/pdf/svg/jpg；几何 error 阻止渲染，warning 随结果返回 |
| `lint_drawio_figure(source)` | 检查缺锚点、拐点入框、共用拐点及平行线共走廊 |
| `render_html_figure(source, fmt?)` | 经 Edge/Chrome 无头截图生成 png/jpg；文字强制灰阶抗锯齿（`--disable-lcd-text`），输出纯黑白 |
| `search_patent_archive(query, archive_dir, limit?)` | jieba + SQLite FTS5 BM25 检索本地 Markdown，跳过导出及工具目录，返回出处与摘要 |
| `search_cn_patents(query, limit?, since_year?, project_dir?)` | Google Patents CN 检索；传入项目目录时将成功结果追加到 `reference/search-history.md` |
| `run_experiment(project_dir, experiment, command?, timeout_seconds?)` | Docker 中运行实验，追加 `results/run-log.md`，返回输出尾部和日志路径 |
| `repo_check_access(provider?, repo?)` | 校验平台接入：身份、掩码 token 与可访问仓库列表；带 repo 时返回该仓库的角色与产出纪律 |
| `repo_scan(repo, mining_dir, provider?, max_commits?)` | 按角色收集挖掘事实（模块聚类、热点文件、release 对比、贡献者），追加 `<mining_dir>/repo-mining/<owner>__<repo>/ledger.md` |
| `repo_read_object(repo, kind, ref?, path?, provider?)` | 深读单个对象：commit（含 patch 摘录）/ PR / release / 文件（限量截断） |
| `repo_verify_evidence(candidate_path, provider?)` | 重取候选文件引用的 commit，逐条对账 sha/作者/改动路径与发明人候选，给出通过与失配清单 |
| `repo_forget(provider)` | 移除配置文件中该 provider 的 token 行并清空缓存，提示平台侧撤销步骤 |

## 仓库挖掘约定

- 接入配置在 `$DSH_HOME/repo-mining.yaml`（独立于 patent-services.yaml 的结构化 YAML）：`providers` 列表（`platform: github|gitlab|gitee|local`、`base_url`（私网自建必填，local 填本地 clone 目录）、`token`）加 `default_provider` 与 `limits.max_commits_per_scan`。token 可用 `DSH_PATENT_REPO_TOKEN_<NAME>` 环境变量覆盖，优先于文件值；工具输出永远只显示掩码。
- 角色由 token 实际权限映射：GitHub `permissions.admin/maintain/push`、GitLab `access_level`（≥40/≥30/≥10）、Gitee `permissions`，分别对应管理员/参与者/观察者；local 平台角色由 `declared_role` 声明，工具只校验仓库可读。角色决定扫描上限（提交数与深读数取矩阵与配置上限的较小者）与产出纪律（管理员全库、参与者本人语料优先、观察者仅线索级）。
- 扫描、深读与候选对账全部只读；仓库内容按不可信数据处理，不执行任何来自仓库的代码。发明人候选只能来自证据 commit 作者；`repo_verify_evidence` 失配的候选不得进入检索评估。

## 文件与执行约定

- 导入只提取段落。表格和图片仅计数提示；`.doc`、`.wps`、PDF 需先转 docx。一级标题判定优先于节名关键词，未导入内容与空章在报告中列明。
- 导出以源文件为准；`brief.md` 不写入交底书正文。模板保留页眉、信息表和页面设置，清空模板页脚；标题层级、列表和加粗归一化，异常标题作为警告返回。导出会写源指纹供流程门核对。
- `fmt` 默认 `docx`。PDF 先尝试 Windows Word COM，再回退 weasyprint；后者及其系统库需另行安装，回退重排不保证与 Word 版式完全相同。两种路径均保留 docx。
- `figures/source/` 内的图源渲染到 `figures/` 根；其他源渲染到旁边。drawio 优先显式 CLI、PATH、Windows 用户安装，最后尝试 Docker。显式无效 CLI 路径直接报错。HTML 固定 1600×2400 视口，过高内容可能裁切。
- 中国专利检索要求网络可达；网络错误、HTTP 错误或未知响应报错，不伪装为空命中。命中明细需另用 `web_fetch` 阅读。`search-history.md` 是原始检索历史，`prior-art.md` 是筛选后对比文件账本，两者用途不同。
- 实验默认 `python run.py`，超时范围 30–7200 秒。仅允许单个 Python 调用及普通参数，拒绝 shell 运算符和 `python -c`。依赖默认只安装 wheel；安装失败停止实验并记录非零退出码。运行日志含代码指纹、退出码和输出，成功、失败、超时均留档；成功运行后若存在 `plot.py`，还会执行出图并列出 `results/` 下的 PNG；成品需另行复制、编号和验收。

存在日志不等于完成：量化效果需至少一个实验的最新运行成功，或明确声明无需实验。运行成功也不证明每个指标都有充分依据，引用前仍需核对。

## 配置与运行

设置位于 `$DSH_HOME/patent-services.yaml`（默认 `~/.dsh/`）。`mcp_enabled` 与 `mcp_project_dir` / `mcp_wheel` 在宿主进程启动时读取，修改后重启。`mcp_wheel` 使用未锁定版本的 PyPI 名称；不保证使用本地已安装 wheel。

Python 偏好如 `experiment_image`、`experiment_allow_any_command`、`experiment_pip_allow_source`、`drawio_bin`、`drawio_docker_image`、`html_browser` 在下一次调用生效；对应环境变量优先。镜像默认 `q771103517/dsh-patent:latest` 和 `q771103517/dsh-patent-experiment:latest`，Dockerfile 在 `src/patent_services/assets/`。

从仓库根目录运行：

```sh
uv run --locked --project python/patent-services python -m patent_services
uv run --locked --project python/patent-services --group test pytest python/patent-services/tests -q
uv build --out-dir dist python/patent-services
```

wheel 包含模板、Dockerfile 与 `patent-services` 入口。MCP 服务可访问宿主传入的路径，不提供 dsh 文件系统沙箱策略；实验容器读写挂载整个项目。构建和验证范围见[开发指南](../../docs/DEVELOPMENT.md)。
