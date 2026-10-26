---
description: "Aurify capability bundle: skills, Web cards, project panel and tool composition; persona belongs to the profile."
kind: "package-bundle"
---

# @mtl-academic/dsh-patent

English | [中文](README.zh.md)

The Aurify capability bundle. [`cordis.patch.yml`](cordis.patch.yml) composes the [native tools](../tool-patent/README.md), [review command](../command-patent-review/README.md), skill assets and optional [Python MCP services](../../python/patent-services/README.md) over the dsh base + web stack.

## Installation and persona

Use marketplace installation and natural-language initialization in the [installation guide](../../docs/install/INSTALL-NEW-PROFILE.md). Manual alternative:

```sh
dsh plugin --profile patent add @mtl-academic/dsh-patent
```

The bundle is persona-free and can join a general-purpose profile. The single maintained source for the dedicated persona is [`scripts/persona.patch.yml`](../../scripts/persona.patch.yml). Merge its entries into the profile's `cordis.patch.yml`, preserving existing patches. The installer reads this file beside itself; no separate README configuration copy is needed.

## Skills and interface

`src/skills.ts` reads `skills/<name>/SKILL.md`, registers runtime skills from frontmatter, and resolves resources relative to each skill directory. `name` and `description` are required; malformed assets fail at load. No `customSkillDirs` setting is needed. Reload the plugin after editing skills.

| Task | Skills |
|---|---|
| Evaluation, interview and progression | [patent-init](skills/patent-init/SKILL.md), [patent-loop](skills/patent-loop/SKILL.md) |
| Research and experiments | [patent-research](skills/patent-research/SKILL.md), [patent-experiment](skills/patent-experiment/SKILL.md) |
| Chapters and writing quality | [patent-chapters](skills/patent-chapters/SKILL.md), [patent-writing-quality](skills/patent-writing-quality/SKILL.md), [patent-de-ai](skills/patent-de-ai/SKILL.md), [patent-effect-contrast](skills/patent-effect-contrast/SKILL.md) |
| Figures | [patent-figure-design](skills/patent-figure-design/SKILL.md), [diagram-design](skills/diagram-design/SKILL.md) |
| Application documents | [patent-claims](skills/patent-claims/SKILL.md), [patent-application](skills/patent-application/SKILL.md) |
| Review and delivery | [patent-review](skills/patent-review/SKILL.md), [patent-services](skills/patent-services/SKILL.md) |

The Web client renders readiness, claims lint and review cards. The project panel lists chapters, reports and figures with captions. Cards use persisted presentation metadata, falling back to text for older logs; the interface adds no model-history content.

## Runtime contracts

- Project sources live in `patent.yml`, `brief.md`, `chapters/`, `figures/`, `review/` and `exports/`. Users and the model edit the same files.
- `src/index.ts` sets top-level conversation temperature to 0.7, excluding children with `subagent` origin. Older cores without the session subject skip the override.
- MCP is disabled by default and enabled at process start through settings or environment variables. Configuration and restart requirements live in the [installation guide](../../docs/install/INSTALL-NEW-PROFILE.md#services-and-runtime-dependencies).
- A compatible host is required. See the [development guide](../../docs/DEVELOPMENT.md) for full TS checks and UI integration boundaries.

## Maintenance boundaries

Skills, templates and examples are shipped runtime assets. See [VENDORED.md](skills/diagram-design/VENDORED.md) for third-party diagram-design provenance and update rules; `patent-figure-design` overlays the patent monochrome requirements.

The bundle targets single-user profile composition, without a multi-user UI or per-session presets. HTML rendering uses a fixed 1600×2400 viewport and can crop tall canvases; inspect rendered figures before delivery.
