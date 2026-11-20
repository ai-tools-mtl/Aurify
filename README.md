# 点金 Aurify

DeepSeek Harness（dsh）的第三方专利撰写插件。先检索中国专利，给出「建议写 / 收窄后写 / 不建议写」的评估及公开号证据；方向确认后，再推进访谈、交底书、附图、实验、审查和导出。

## 安装与开始使用

1. 在 DeepSeek Harness 桌面版 **设置 → 插件市场**中搜索 **Aurify** 或 **点金**，安装到当前活动档案。

   也可走社区市场：本插件已被社区插件市场 [DSH Market](https://dsh.market/)（[源码](https://github.com/2BingLing/dsh-market)）收录。推荐桌面端 [DeepSeek Harness Desktop](https://github.com/dsh-tauri/deepseek-harness-desktop) 可在启动引导中按需安装「DSH Market」预设插件，之后在其侧边栏「插件市场」中文搜索 **Aurify** 一键安装；不装插件时也可直接在 Web 版搜索并复制安装命令。
2. 在该档案中发送：

   > 帮我初始化点金插件的运行环境，检查并配置所需依赖和服务。

3. 按 `patent_setup_check` 报告完成配置。MCP 配置变更后，**完整退出并重启桌面版**，再发送：

   > 帮我复检点金插件的环境，确认所需服务已就绪。

复检通过后，描述技术点子开始评估，或提供已有 Word 文档继续完善。无需先克隆仓库或下载发行包。npm、Windows 安装器、本地包安装及手动配置见[安装指南](docs/install/README.md)（[English](docs/install/INSTALL-NEW-PROFILE.md)）。

## 能力与边界

| 阶段 | 能力 |
|---|---|
| 仓库挖掘 | 接入 GitHub/GitLab（含自建）/Gitee/本地 clone，按 token 实际权限映射管理员/参与者/观察者三档角色；角色化扫描（commit 聚类、热点文件、release 对比）、候选点子经问询确认后落盘证据链并对账 |
| 评估与访谈 | 中国专利检索、三档建议与暂缓评估、评估状态恢复、五维信息收集及缺点—问题—效果对齐检查 |
| 撰写 | 八章交底书、正文检查、效果对比；涉及实验时补充验证章 |
| 附图与实验 | drawio / HTML 双路线渲染流程、架构与结构类附图（含剖视、爆炸图），几何检查与图文一致性验收；Docker 仿真与运行日志 |
| 审查 | `/patent-review` 与 `patent_review` 共用七维评分流程，报告保存到 `review/` |
| 导入与导出 | Word 导入为项目章节；交底书及申请文件导出为 docx/PDF |

交底书是默认交付物；权利要求书、说明书和摘要仅在用户明确要求时推进。交付终点是申请文件（说明书、权利要求书、摘要及附图）——审查意见答复（OA）、驳回复审、分案等申请后程序不在本套件范围内（patent-claims 的缩圈预案仅为撰写期退守准备，不含答复程序）。审查流程固定，模型评分仍有波动；通过检查不等于专利可授权。导入只提取段落，表格与嵌入图片需另行核对。仓库挖掘只读不改仓库，token 仅需只读权限且永不回显；挖掘候选须过证据对账门后才进入评估。

插件由 15 个技能、5 个原生工具、15 个 Python MCP 工具和独立审查命令/工具组成，包含 Web 卡片和项目面板。Bundle 不携带 persona；专用 persona 可在档案层选装。

运行需要兼容的 dsh 宿主和可用模型。中国专利检索需要访问 `patents.google.com`；仿真实验需要 Docker；drawio 渲染可用本机 CLI 或 Docker，HTML 渲染需要 Edge/Chrome。PDF 优先使用 Windows Word COM，否则依赖另行配置的 weasyprint 环境。仓库挖掘需能访问对应平台（私网自建平台需在 `~/.dsh/repo-mining.yaml` 配置 base_url）。

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

当前源码：npm 三包 **0.2.0**，Python 服务 **0.2.0**。安装包入口为 [GitHub Releases](https://github.com/ai-tools-mtl/Aurify/releases)；`dist/` 是本地生成目录，不受 Git 追踪。

GitHub Release、npm/PyPI 和插件市场各自发布，版本不一定同步。`mcp_wheel: true` 使用未锁定版本的 PyPI 包；精确运行本版 Python 服务请使用源码模式。开发、构建与验证范围见[开发指南](docs/DEVELOPMENT.md)，变更见[更新记录](CHANGELOG.md)。

Aurify 与 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 无隶属关系。

## 友链

- [DeepSeek Harness Desktop](https://github.com/dsh-tauri/deepseek-harness-desktop)：推荐使用的 dsh 桌面端，启动引导中可安装 DSH Market 社区插件市场。
- [DSH Market](https://dsh.market/)：社区插件市场（[2BingLing/dsh-market](https://github.com/2BingLing/dsh-market)），已收录本插件。
