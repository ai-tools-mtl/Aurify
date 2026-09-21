# deepseek-harness-patent-services

[English](README.md) | 中文

> 本文的相对链接按 deepseek-harness monorepo 布局书写；本仓库是提取态分发仓（完整 monorepo 见 Release 附带的 `dsh-patent-full.bundle`），所以指向本目录之外的链接要在 monorepo 中才可达。

把专利交底书领域服务经 MCP stdio 暴露给 dsh `patent` profile：模板/参考文献解析、整项目导出、申请文件导出、drawio 附图渲染、归档检索、docker 仿真实验与中国专利发现。经 [`@deepseek-ai/dsh-mcp-client`](../../packages/mcp/mcp-client/README.zh.md) 挂载后，工具以 `mcp__patent__parse_disclosure_docx`、`mcp__patent__export_disclosure`、`mcp__patent__export_application_docs`、`mcp__patent__render_drawio_figure`、`mcp__patent__render_html_figure`、`mcp__patent__lint_drawio_figure`、`mcp__patent__search_patent_archive`、`mcp__patent__run_experiment` 与 `mcp__patent__search_cn_patents` 出现在模型工具表。

## 工具

- `parse_disclosure_docx(path, output_path?)` — 按三层编号策略把 Word 文档解析为 Markdown（显式标题样式，`第一章/一、/1.` 为一级，`1.1/（一）` 为二级，`1.1.1` 为三级）；可选同时写出 Markdown 文件。表格与内嵌图片跳过。
- `export_disclosure(project_dir, fmt)` — 以随包附带的代理机构交底书模板（`assets/disclosure-template.docx`）为底版导出：页眉「专利申请技术交底书」、发明人信息表与页面规格随模板保留，模板页脚（页码、事务所名与 logo）导出时清空，章节按模板条款（一、名称 ~ 八、附图）以模板自身排版（楷体_GB2312 四号、1.5 倍行距、首行两字符缩进）填入，并叠加阅读层级——条款标题加粗、`##` 子标题加粗不缩进、`- ` 分点渲染为 `●` 悬挂缩进圆点、`**加粗**` 保留为真加粗；未匹配模板条款的章节追加为后续条款，`brief.md` 不进入交底书；figures/图N.png 按序嵌入附图节（图N 标注与 08 章图题在图下方）；`docx`（默认，python-docx）或 `pdf`（Windows 上优先经隐藏窗口 Word COM 转换——docx 仍保留在 exports/，无 Word 时回退 weasyprint）。
- `export_application_docs(project_dir, fmt)` — 把申请文件三件套（`application/{claims,description,abstract}.md`）按已提交申请文件的版式导出：单文档多分节——说明书摘要、权利要求书（每条编号权项一段，Markdown 续行并段）、说明书（居中发明名称 + 加粗不缩进节标题）——文档类型标签置于居中带下框线的页眉（黑体四号，字间空格照录），正文宋体四号（西文 Times New Roman、1.5 倍行距、首行两字符缩进、`●` 圆点与 `**加粗**` 层级同交底书），权利要求书与说明书各自重排页码但不显示页码；`docx`/`pdf` 行为与交底书导出一致。
- `render_drawio_figure(source, fmt)` — 把一个 `.drawio` 源渲染为 `png`/`pdf`/`svg`/`jpg`：源在 `figures/source/` 下时成品落到 `figures/` 根（最外层只放最终插入文档的 PNG——源在 `figures/source/`、中间产物在 `figures/tmp/`），其余情况渲染到源旁。CLI 依次从 `DSH_DRAWIO_BIN`、PATH（`draw.io`/`drawio`）、用户级 Windows 安装位置解析（显式 `DSH_DRAWIO_BIN` 是严格模式——路径无效直接报错，不落入兜底）；docker 兜底运行 `DSH_DRAWIO_DOCKER_IMAGE`（默认 `q771103517/dsh-patent:latest`，即由 `assets/Dockerfile.drawio` 构建并发布到 Docker Hub 的中文字体叠加镜像——缺失时自动拉取；插件更新改动 Dockerfile 时以同一 tag 重建并推送）；后端全部不可用时报错并给出安装/构建指引。任何后端动手前先跑几何自查：error 级毛病（拐点入框、多边共用拐点）直接拒绝渲染并退回修改清单，warning（缺锚点、共走廊）附在成功返回里。
- `lint_drawio_figure(source)` — 在渲染前对 `.drawio` 源做几何自查（figure-design 技能绘制纪律的机器化）：缺显式 exit/entry 锚点的连线（自动布线拐点不受控的根源）、拐点落入所绕行框内、多边共用同一拐点（线段搭接重叠之源）、平行线段共走廊。逐条给出修法；error 级发现正是 render_drawio_figure 拒绝渲染的那几类——画完先 lint，把几何修在源头。
- `render_html_figure(source, fmt)` — 经 Edge/Chrome 无头截图把自包含 HTML 附图（diagram-design 产物）栅格化为 png/jpg 到源旁（`DSH_HTML_BROWSER` 可指定浏览器可执行文件）；源在 `figures/source/` 下时成品落 `figures/` 根。
- `search_patent_archive(query, archive_dir, limit)` — 归档根目录（历史项目工作区或单个项目的 `reference/`）下 Markdown 语料的中文全文检索（jieba 分词 + SQLite FTS5 BM25）；跳过 `exports/` 与工具目录。命中返回路径、标题与居中摘要。
- `search_cn_patents(query, limit?, since_year?)` — 在 Google Patents 上发现中国专利，供查新与背景技术检索：检索词用中文核心特征词，命中限定 CN 公开范围逐行返回（公开号、标题、申请人、优先权日），某篇的摘要与权利要求 1 用 web_fetch 抓静态渲染的明细页（`patents.google.com/patent/<公开号>/zh`）阅读。底层是无鉴权的 `/xhr/query` 接口，需要本机能访问 patents.google.com（通常走系统代理——Windows 上 urllib 自动识别）；网络不可达、HTTP 错误与无法识别的响应都报错并给出补救指引，绝不静默返回空结果——编造的命中比失败的检索更糟。
- `run_experiment(project_dir, experiment, command?, timeout_seconds?)` — 在 docker 运行镜像里执行一个仿真实验：项目目录挂载到 `/workspace`，工作目录是 `experiments/<experiment>/`，该目录有 `requirements.txt` 时先装依赖再执行命令，运行的合并输出尾部返回给模型。`command` 只接受带普通参数的单个 `python`/`python3` 调用（默认 `python run.py`）——不得携带 shell 运算符：它经 `sh -c` 在整个项目的读写挂载上执行，自由字符串等于任意代码执行面；确需放宽由用户设置 `DSH_EXPERIMENT_ALLOW_ANY_COMMAND=1`。每次调用——成功、失败或超时——都向 `experiments/<experiment>/results/run-log.md` 追加一条出处记录（时间、镜像、命令、退出码、输出尾部）；交底书里引用的每个数字都指向其中一条记录。镜像（`DSH_PATENT_EXPERIMENT_IMAGE`，默认 `q771103517/dsh-patent-experiment:latest`，由 `assets/Dockerfile.experiment` 构建并发布到 Docker Hub——缺失时自动拉取；预装栈变化时以同一 tag 重建并推送）自带 numpy/scipy/pandas/matplotlib/openpyxl 与中文字体，matplotlib 无需逐脚本设置字体即可渲染中文标注；没有 docker 命令时报错并给出 Docker Desktop 指引。

## 可选设置

用户偏好放在 `$DSH_HOME/patent-services.yaml`（默认 `~/.dsh/`），不用 `setx` 环境变量：`experiment_allow_any_command`、`experiment_image`、`drawio_bin`、`drawio_docker_image`、`html_browser`。改完下一次工具调用即生效，无需重启；同名环境变量仍然优先，文件缺失或损坏只是回落代码默认值。

## 运行

```sh
uv run --project python/patent-services python -m patent_services   # stdio server
uv run --project python/patent-services pytest                      # tests
uv build                                                            # wheel + sdist into dist/
```

wheel 是可安装形态：自带模板与 Dockerfile 资产和 `patent-services` console script。`patent` bundle 挂载的客户端行藏在若干 opt-in 门之后，默认全关（disabled——在 `dsh --profile patent --dump-config` 中可见，但不出现在工具表）：

- **单文件方式（首选）**：`~/.dsh/patent-services.yaml` 写 `mcp_enabled: true`——**总开关，两种模式都必须写**——再加 `mcp_project_dir: <本检出的绝对路径>`（源码模式；相对路径、或缺 `pyproject.toml` 的目录会被拒绝并给出可读原因）或 `mcp_wheel: true`（wheel 模式）。wheel 模式要求先把 wheel 装成 uv 工具：`uv tool install <dist-dir>/deepseek_harness_patent_services-<version>-py3-none-any.whl`——本包未发布 PyPI，`uvx` 只解析 `uv tool install` 装过的东西。tool-patent 插件在加载时读该文件并自行装载客户端。
- **环境变量方式（脚本化场景）**：设 `DSH_PATENT_SERVICES` 经 `uvx --from deepseek-harness-patent-services patent-services` 运行已安装的包；或设 `DSH_PATENT_SERVICES_DIR`（本检出的绝对路径）直接从源码运行模块。

两种方式下该行都在**进程启动时**装载：新写的文件要到下一个 dsh 进程才生效，仅新开会话不够；`patent_setup_check` 区分「已装载/待重启」。

## Known Limitations and Deferred Work

- **表格与图片不解析**——解析器只遍历段落；含表格内容的模板会在 Markdown 投影中丢失。
- **PDF 导出在 Windows 上优先走 Word COM**——weasyprint（需系统 GTK）保留为非 Windows 回退；两条路径都会把 docx 保留在 `exports/`。
- **无文件系统策略**——MCP stdio 服务运行在宿主进程的信任域内，在 dsh fs 沙箱之外；它能看到模型传入的路径。
