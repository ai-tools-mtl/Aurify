---
description: "Aurify 能力 bundle：技能、Web 卡片、项目面板与工具组合；persona 在档案层配置。"
kind: "package-bundle"
---

# @mtl-academic/dsh-patent

[English](README.md) | 中文

Aurify 的能力组合包。通过 [`cordis.patch.yml`](cordis.patch.yml) 加载[原生工具](../tool-patent/README.zh.md)、[审查命令](../command-patent-review/README.zh.md)、技能资产和可选 [Python MCP 服务](../../python/patent-services/README.zh.md)，在 dsh 的 base + web 组合上提供专利工作流。

## 安装与 persona

推荐使用[安装指南](../../docs/install/README.md)中的插件市场安装和自然语言初始化。手动替代命令：

```sh
dsh plugin --profile patent add @mtl-academic/dsh-patent
```

Bundle 不携带 persona，可以装入通用档案。专用 persona 的唯一维护源是 [`scripts/persona.patch.yml`](../../scripts/persona.patch.yml)；将其中条目合并到档案的 `cordis.patch.yml`，保留已有补丁。安装器从同目录读取该文件；无需从 README 复制另一份配置。

## 技能与界面

`src/skills.ts` 读取 `skills/<name>/SKILL.md`，按 frontmatter 注册 runtime skill，并以技能目录为相对资源基准。`name` 和 `description` 必填，损坏资产在加载时报错。无需配置 `customSkillDirs`；修改技能后需重载插件。

| 任务 | 技能 |
|---|---|
| 评估、访谈与循环推进 | [patent-init](skills/patent-init/SKILL.md)、[patent-loop](skills/patent-loop/SKILL.md) |
| 查新与实验 | [patent-research](skills/patent-research/SKILL.md)、[patent-experiment](skills/patent-experiment/SKILL.md) |
| 章节与写作质量 | [patent-chapters](skills/patent-chapters/SKILL.md)、[patent-writing-quality](skills/patent-writing-quality/SKILL.md)、[patent-de-ai](skills/patent-de-ai/SKILL.md)、[patent-effect-contrast](skills/patent-effect-contrast/SKILL.md) |
| 附图 | [patent-figure-design](skills/patent-figure-design/SKILL.md)、[diagram-design](skills/diagram-design/SKILL.md) |
| 申请文件 | [patent-claims](skills/patent-claims/SKILL.md)、[patent-application](skills/patent-application/SKILL.md) |
| 审查与交付 | [patent-review](skills/patent-review/SKILL.md)、[patent-services](skills/patent-services/SKILL.md) |

Web 客户端将就绪度、权利要求检查和审查结果渲染为卡片；右侧项目面板展示章节、报告和附图对照。卡片读取持久化的 presentation meta，旧日志缺数据时回退到文本；界面不向模型历史增加内容。

## 运行约定

- 项目以 `patent.yml`、`brief.md`、`chapters/`、`figures/`、`review/` 和 `exports/` 落盘；模型与用户维护同一批源文件。
- `src/index.ts` 将顶层会话温度设为 0.7；带 `subagent` origin 的子会话不受影响。旧核心若未注入会话主体，则不覆盖温度。
- MCP 默认关闭；settings 文件或环境变量在进程启动时启用。配置和重启要求统一见[安装指南](../../docs/install/README.md#服务与运行依赖)。
- 能力组合依赖兼容宿主；完整 TS 检查和 UI 集成范围见[开发指南](../../docs/DEVELOPMENT.md)。

## 维护边界

技能、模板与示例是随包运行资产，不按历史文档清理。第三方 diagram-design 的来源和更新约束见 [VENDORED.md](skills/diagram-design/VENDORED.md)，专利黑白规范由 `patent-figure-design` 叠加。

当前面向单用户档案组合，不提供多用户界面或每会话 preset。HTML 渲染的固定 1600×2400 视口可能裁切过高画布，交付前需要读图核对。
