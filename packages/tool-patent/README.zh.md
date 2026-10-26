---
description: "Aurify 原生工具：就绪度、权利要求与正文检查、流程推进、环境自检。"
kind: "package-reference"
---

# @mtl-academic/dsh-tool-patent

[English](README.md) | 中文

注册五个原生工具与 `/patent-loop` 命令；独立审查工具 `patent_review` 由[审查包](../command-patent-review/README.zh.md)提供。安装和环境配置见[安装指南](../../docs/install/README.md)。

## 工具

| 工具 | 输入与判定 |
|---|---|
| `patent_brief_coverage` | 接受五个核心维度和三个辅助维度的文本；返回缺失维度、条数对齐和 `ready` |
| `patent_claims_lint` | 接受权利要求文本及可选摘要，返回权项结构和 C1–C6 / A1–A2 违规 |
| `patent_prose_lint` | 接受正文，检查套话、长句、排比、总结和定义式表述 |
| `patent_loop` | 读取项目目录，返回首个未完成阶段、全部缺口和执行指令 |
| `patent_setup_check` | 检查 MCP 装载、uv/uvx、Docker/镜像、draw.io 和检索通道，逐项报告修法 |

前三项按传入文本检查。`patent_loop` 读取磁盘状态，`patent_setup_check` 在宿主侧运行，因此 MCP 关闭时仍可用。覆盖率、权利要求和审查卡片由 Bundle 的 Web 客户端渲染。

## 就绪度与静态规则

就绪度要求 `field`、`background`、`problem`、`solution`、`effect` 全部非空；`background`、`problem`、`effect` 的估算条数最大偏差不超过 1。三者有未收集项时，对齐检查暂放行，但缺维度仍阻止就绪。`name`、`drawings`、`key_points` 仅展示，不参与门禁。计数语义移植自 TianGong 的 `brief_dimensions.py`，无可调容差。

| 规则 | 当前实现 |
|---|---|
| C1 | 从 1 连续编号，引用权项必须存在 |
| C2 | 从属权项只引用更早权项 |
| C3 | 多项引用须采用择一引用形式 |
| C4 | 多项从属权项不得以另一多项从属权项为基础 |
| C5（warning） | 独立权项缺少「其特征在于」提示 |
| C6 | 权项中出现「如图N所示」等附图引用报错 |
| A1 | 提供摘要时，非空白字符数不得超过 300 |
| A2（warning） | 提供摘要时，提示商业宣传措辞 |

以上描述代码启发式检查，不替代实质审查。正文检查将套话、道歉措辞和超过 150 字的句子列为 error；三连排比、段末总结和教科书定义列为 warning。

## 流程门禁

`patent_loop` 与 `/patent-loop` 共用 `src/loop.ts`，按以下顺序返回首个未完成阶段：

| 阶段 | 主要门禁 |
|---|---|
| init | 根目录存在 `patent.yml` |
| align | `brief.md` 五个核心维度有内容 |
| chapters | 八章完成；名称章仅含最终名称；量化效果或已有实验目录时补 `09-verification.md`；正文公开号须记入 `reference/prior-art.md` |
| experiments | 量化效果须有至少一个实验的最新记录退出码为 0，或在 `experiments/README.md` 声明「无需实验 / 不适用」 |
| figures | `08-drawings.md` 的图号与 `figures/` 根目录成品双向对应，或明确声明「无附图」 |
| review | 最新报告可解析、达到 `reviewThreshold`（默认 80）并与当前源一致；需整项目审查 |
| export | 存在与当前源一致的交底书 docx |

审查和导出优先比较源指纹，旧文件缺指纹时回退 mtime。源内容改变需重新审查/导出；仅改时间戳不使带指纹的文件过期。

`reference/prior-art.md` 中的「查新不可用」使审查线临时降低 10 分，并持续提示待补查；通道恢复后补检索、移除标记并重审。它不免除来源核对。`complete=true` 只表示文件门禁通过，不能证明内容充分或每项指标都有证据。覆盖率依赖模型传入文本，流程中的 brief/量化效果识别也只是启发式检查。

审查门还读取 `review/attempts.md`：连续低分触发停止自动重审并请求用户决策，不应静默降低门槛或重置账本。

`/patent-loop` 经 `agent.followup()` 注入循环指令，UI 摘要不进模型历史。每完成一阶段需再次调用工具；方向确认和访谈仍需等待用户输入。

## 装载与开发

工具包导出 `name`、`inject` 和 `apply`，保留命名导出结构，不添加 default export。MCP 配置在进程启动时装载；`patent_setup_check` 区分「已装载」和「待重启」，已保存配置不代表服务可用。

完整类型检查和宿主测试需要兼容的 monorepo，见[开发指南](../../docs/DEVELOPMENT.md)。
