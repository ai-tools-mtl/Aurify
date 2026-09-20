---
name: patent-services
description: 交底书与申请文件的导出、交付物更新、Word 解析与归档检索的路由。当用户要求导出交底书/申请文件为 docx 或 pdf、用"完成/写完/交付"等措辞要最终文档、更新或修订已交付的导出文档、把附图插入导出文档、解析 Word 版交底书或参考文献、检索历史项目找先例时启用——这些一律走 patent-services 的 MCP 工具；交底书是默认交付物，申请文件只在用户明确点名时导出，禁止用临时脚本拼改 docx。
---

# 交付物纪律：工具导出，禁手拼

导出物（`exports/` 下的 docx/pdf）是源的投影：交底书由 patent.yml + brief + chapters/ 经模板生成，申请文件由 application/ 生成。手改导出物或用临时脚本拼 docx，都会制造源与交付物的漂移——导出物上看到的任何内容都必须能从源重新导出得到。

## 程序

1. **导出主次：交底书是默认交付物**。用户要求"完成/写完/交付"或未点名要哪种文档时，一律指交底书：调 `export_disclosure(project_dir, fmt)`（docx 默认；pdf 需系统 GTK，缺失会报错并给指引）。`export_application_docs(project_dir, fmt)`（申请文件三件套）只在用户明确要求推进申请文件/准备提交时调用——"完成交底书"不等于"交申请文件"，不要替用户把流程推进到 application。
2. **导出后核对附图数**：导出工具返回"内嵌附图 N 张"——N 必须等于 chapters/08-drawings.md 声明的"图N 为…"条数；返回带警告或 N 为 0 而章节声明了附图时，是命名不合规（成品须 `图N.png` 或 `图N-名称.png`）或渲染缺图，修正后重导。**不许把零附图或缺图的导出物当"完成"交付**。
3. **更新已交付内容**（章节修订、附图变更、错字修正）：一律改源（chapters/、figures/、application/）后重新导出覆盖——不要在旧 docx 上打补丁。
4. **就地向已交付 docx 插图或补内容**（用户明确要求且不接受重新导出时）：先说明将修改用户文件并自动留 `.bak`，插图遵守 patent-figure-design 的插图纪律（图N 在图下方居中、编号对应 08 章附图说明、图注轻改写）。
5. **解析 Word 材料**：代理机构模板、已授权交底书、参考文献用 `parse_disclosure_docx(path, output_path?)` 转三层编号 Markdown，存项目 `reference/` 后再引用。
6. **写背景技术找先例**：用 `search_patent_archive(query, archive_dir)` 检索历史项目工作区或 `reference/`（中文分词 + BM25），命中结果给出处再融入正文。
7. **工具不可用时**（本会话未启用 MCP 服务）：明说"当前会话没有启用专利导出服务"，并**直接代写配置**——用写文件工具在 `~/.dsh/patent-services.yaml` 写 `mcp_enabled: true` 加 `mcp_project_dir: <patent-services 源码目录的绝对路径>`（路径原样直写，不要经 shell echo/转义——`G:\02-…` 里的 `\02` 会被某层折叠成控制字符，python 侧会拒读整个文件），然后请用户完整重启桌面壳（插件在进程启动时装载 MCP，仅新开会话无效）；走已安装 wheel 的机器改写 `mcp_wheel: true`——它的前提是先 `uv tool install <分发目录>/deepseek_harness_patent_services-*.whl`（该包未发布 PyPI，uvx 只能运行 uv 已装的工具，自检的 wheel 行会点名）。**不要**退回临时脚本拼改。配置变更后调 `patent_setup_check`（宿主侧工具）复验各通道——它区分「已装载」与「待重启」，显示「已装载」前不要当作工具可用；报告「配置文件损坏」行时按其指名的行号用编辑器重写该行。面向用户的回复一律简体中文。

## 工具清单（MCP 前缀 mcp__patent__）

- `export_disclosure(project_dir, fmt)` — 模板驱动交底书导出。
- `export_application_docs(project_dir, fmt)` — 申请文件三件套单 docx 多分节。
- `parse_disclosure_docx(path, output_path?)` — Word → 三层编号 Markdown。
- `search_patent_archive(query, archive_dir, limit?)` — 中文全文检索（jieba + BM25）。
