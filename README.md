# 点金 Aurify

DeepSeek Harness（dsh）的第三方专利撰写插件。先检索中国专利，给出「建议写 / 收窄后写 / 不建议写」的评估及公开号证据；方向确认后，再推进访谈、交底书、附图、实验、审查和导出。

## 安装与开始使用

1. 在 DeepSeek Harness 桌面版 **设置 → 插件市场**中搜索 **Aurify** 或 **点金**，安装到当前活动档案。
2. 在该档案中发送：

   > 帮我初始化点金插件的运行环境，检查并配置所需依赖和服务。

3. 按 `patent_setup_check` 报告完成配置。MCP 配置变更后，**完整退出并重启桌面版**，再发送：

   > 帮我复检点金插件的环境，确认所需服务已就绪。

复检通过后，描述技术点子开始评估，或提供已有 Word 文档继续完善。无需先克隆仓库或下载发行包。npm、Windows 安装器、本地包安装及手动配置见[安装指南](docs/install/README.md)（[English](docs/install/INSTALL-NEW-PROFILE.md)）。

## 能力与边界

| 阶段 | 能力 |
|---|---|
| 评估与访谈 | 中国专利检索、三档评估、五维信息收集及缺点—问题—效果对齐检查 |
| 撰写 | 八章交底书、正文检查、效果对比；涉及实验时补充验证章 |
| 附图与实验 | drawio / HTML 渲染、几何检查、Docker 仿真与运行日志 |
| 审查 | `/patent-review` 与 `patent_review` 共用七维评分流程，报告保存到 `review/` |
| 导入与导出 | Word 导入为项目章节；交底书及申请文件导出为 docx/PDF |

交底书是默认交付物；权利要求书、说明书和摘要仅在用户明确要求时推进。审查流程固定，模型评分仍有波动；通过检查不等于专利可授权。导入只提取段落，表格与嵌入图片需另行核对。

插件由 14 个技能、5 个原生工具、10 个 Python MCP 工具和独立审查命令/工具组成，包含 Web 卡片和项目面板。Bundle 不携带 persona；专用 persona 可在档案层选装。

运行需要兼容的 dsh 宿主和可用模型。中国专利检索需要访问 `patents.google.com`；仿真实验需要 Docker；drawio 渲染可用本机 CLI 或 Docker，HTML 渲染需要 Edge/Chrome。PDF 优先使用 Windows Word COM，否则依赖另行配置的 weasyprint 环境。

## 文档与源码

[文档索引](docs/README.md)按使用、开发、发布和历史记录组织全部入口。

| 路径 | 职责 |
|---|---|
| [`packages/bundle-patent`](packages/bundle-patent/README.zh.md) | 技能、Web 界面与组合配置 |
| [`packages/tool-patent`](packages/tool-patent/README.zh.md) | 就绪度、权利要求/正文检查、流程推进与环境自检 |
| [`packages/command-patent-review`](packages/command-patent-review/README.zh.md) | 审查流程、评分标准与报告 |
| [`python/patent-services`](python/patent-services/README.zh.md) | 文档、附图、检索与实验服务 |
| [`scripts`](scripts/) | 构建、校验、Windows 安装器与 persona 正本 |

## 版本与分发

当前源码：npm 三包 **0.1.6-alpha.7**，Python 服务 **0.1.2**，处于 alpha 阶段。安装包入口为 [GitHub Releases](https://github.com/ai-tools-mtl/Aurify/releases)；`dist/` 是本地生成目录，不受 Git 追踪。

GitHub Release、npm/PyPI 和插件市场各自发布，版本不一定同步。`mcp_wheel: true` 使用未锁定版本的 PyPI 包；精确运行本版 Python 服务请使用源码模式。开发、构建与验证范围见[开发指南](docs/DEVELOPMENT.md)，变更见[更新记录](CHANGELOG.md)。

Aurify 与 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 无隶属关系。
