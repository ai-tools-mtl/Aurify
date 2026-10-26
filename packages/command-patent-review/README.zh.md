---
description: "固定七维审查流程：/patent-review 命令与 patent_review 工具共用执行链路和报告。"
kind: "package-reference"
---

# @mtl-academic/dsh-command-patent-review

[English](README.md) | 中文

`/patent-review`（用户命令）和 `patent_review`（模型工具）共用固定 workflow 脚本与随包评分标准。调用方只提供目标路径，报告写入 `review/`。固定的是编排和报告聚合；模型评分本身仍有采样波动。

## 输入与报告

- 文件：审查一个 Markdown 文件。
- 普通目录：按文件名排序拼接顶层 `*.md`。
- 含 `patent.yml` 的项目根：收集 `brief.md` 及 `chapters/`、`application/` 顶层 Markdown，两个目录各按名排序；不把旧报告、导出物、参考资料或实验产物混入评分。

报告写入最近的含 `patent.yml` 祖先目录下的 `review/<label>.review.md`；没有项目祖先时，写入解析基准下的 `review/`。只有项目根目标带整项目审查指纹；单文件和其他目录是部分审查，不能替代整项目门禁。

报告总分形如 `**总分**：85 / 100`，流程门和面板兼容旧版 `总分 85`。缺失或非数字分数不视为通过。工具返回摘要和路径，完整报告需另读文件；命令结果仅进 UI，不进入模型历史。

## 评分与一致性

[`rubric/default.json`](rubric/default.json) 包含七维及权重：完整性 0.15、技术方案清晰度 0.20、新颖性表述 0.15、撰写规范性 0.15、权利要求质量 0.15、说明书支持度 0.15、摘要合规 0.05。评分标准加载时校验，并通过 `package.json` 的 `files` 随包分发。

`src/script.ts` 为各维度执行独立评分，取多次评分的四舍五入均值，并在有有效分数的维度间重新归一化权重。失败子任务不直接终止整次审查，报告保留失败及有效次数；总分需结合缺失维度判断。

项目根或申请文件目标同时存在 `claims.md` 与 `description.md` 时，另做权利要求—说明书支持度和术语一致性检查。相同输入与相同收集分数生成相同报告；这不保证重复调用得到相同模型分数。

## 配置

| 键 | 默认值与含义 |
|---|---|
| `scoringPasses` | 2，整数 1–5；每维评分次数。项目 `patent.yml` 的 `reviewPasses` 可覆盖 |
| `reviewTemperature` | 0.2，范围 0–2；旧引擎不支持子任务温度时回退提供方默认值 |
| `projectRoot` | 未设置；相对目标按当前 agent 会话 cwd 解析。两者都不存在时报错 |

报告归属在路径解析后按项目祖先判定，不依赖用户恰好从项目根启动会话。`reviewThreshold` 是[流程评估器](../tool-patent/README.zh.md#流程门禁)的项目门槛，不是本包评分次数配置。

## 开发与限制

保留 `name`、`inject`、`Config`、`apply` 命名导出，不增加 default export。审查依赖宿主 `workflowEngine`，Bundle 通过兼容行启用它。完整宿主验证见[开发指南](../../docs/DEVELOPMENT.md)。

每次调用仅一个目标，不提供保存的评分标准变体或多目标批处理。模型与网关故障会影响评分完整性；在 shell 中打开报告时需正确引用含空格的路径。
