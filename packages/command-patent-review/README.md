---
description: "The deterministic rubric review: the human /patent-review command and the model-facing patent_review tool share one host-plane pipeline with the report written under review/."
kind: "package-reference"
---

# @deepseek-ai/dsh-command-patent-review

English | [中文](README.zh.md)

> Relative links in this document follow the deepseek-harness monorepo layout. This repository is the extracted distribution — the full monorepo ships as the release's `dsh-patent-full.bundle` — so links that leave this directory resolve in the monorepo, not here.

## Summary

The deterministic patent review, reachable from two surfaces: the human-facing `/patent-review` command and the model-facing `patent_review` tool. Both review one disclosure file or a directory of Markdown files and write the report to `review/`. The model cannot skip, reshape, or dilute the review — the orchestration is host data, and the model-facing surface only supplies the target path.

## Table of Contents

- [What it does](#what-it-does)
- [The fixed script and the rubric](#the-fixed-script-and-the-rubric)
- [Configuration](#configuration)
- [Export shape](#export-shape)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

## What it does

Both surfaces read the target from the working directory (a file, or a directory whose `*.md` files are concatenated in name order), start the fixed workflow script through `ctx.workflowEngine`, and on completion write `review/<label>.review.md`. The command result is UI-only (`CommandResult` never enters model history); the tool returns the summary text to the model as its tool result. The report reaches the model in full only when it later reads the file through the fs tools, which keeps "model-visible ⟺ logged" intact with no new session event.

A file target produces `review/<safe-name>.review.md`; a directory target concatenates its Markdown files with `<!-- name -->` markers and produces one report for the whole document.

## The fixed script and the rubric

The script (`src/script.ts`, a plain-JS string executed by the workflow engine's worker) spawns one schema-carrying child per rubric dimension per configured pass, folds each dimension's pass scores into a rounded mean, and renormalizes the dimension weights over the dimensions that collected scores. A failed child resolves to `null` and lowers that dimension's pass count instead of failing the run. The scoring prompt judges the document alone: a chapter that legitimately does not cover a dimension is scored on the groundwork it provides, not punished for the complete application it is not. When the review target sits inside the application document set (and both `claims.md` and `description.md` exist), an NLI-style consistency phase joins the run — per pass one claims→description support child and one terminology child, aggregated into a consistency score with the union of unsupported-claim findings, rendered as the report's 一致性检查 section. The rubric (`rubric/default.json`, extending TianGong's system review rubric to the application stage: 内容完整性 0.15 / 技术方案清晰度 0.20 / 新颖性表述 0.15 / 撰写规范性 0.15 / 权利要求质量 0.15 / 说明书支持度 0.15 / 摘要合规 0.05, each with a banded scoring guide) is versioned in git — git history is the anti-drift anchor, replacing TianGong's database-stored rubric. The rubric is parsed and validated at load (a durable file boundary); a malformed rubric fails loud.

Determinism claim: the same input file and the same collected scores render the same report byte for byte; model scoring itself is of course sampling variance, which the per-pass scores and the spread in the report make visible.

## Configuration

`scoringPasses` (integer 1-5, default 2): independent scoring passes per dimension. Two gives a self-consistency signal at twice the child count; one is the cheap mode. A project overrides the profile-wide value with `reviewPasses: 1-5` in its patent.yml (the same project-beats-profile relationship `reviewThreshold` has with the default bar).

`reviewTemperature` (number 0-2, default 0.2): the sampling temperature pinned on every scoring child's requests through the workflow's per-child temperature override. Scoring is a mechanical rubric application, so the default sits near deterministic; engines whose `agent()` predates the temperature option are detected at call time and the child degrades to the provider default instead of failing.

`projectRoot` (optional string): the base for relative review targets. Unset resolves each invocation against the receiving agent's session cwd — the workspace a web composition created the session in. Set it explicitly only when the fs world differs from that session workspace (e.g. a composed `fs-local` cwd); an invocation with neither a configured root nor a session cwd fails loud instead of reviewing against the wrong directory.

Report placement anchors to the file-first project model: after the target resolves, the nearest ancestor directory holding `patent.yml` owns the `review/` folder, so a target like `<project>/chapters/03-background.md` reports into `<project>/review/` even when the working directory is the workspace above it; without an enclosing `patent.yml` the report lands under `projectRoot/review/` as before.

## Export shape

A function plugin: it exports `name` / `inject` / `Config` / `apply` and NO default. A stray `export default` would collapse the module via the Loader's `unwrapExports` and drop `inject` (see [docs/postmortem/0001](../../../docs/postmortem/0001-acp-default-export-drops-inject.md)).

## Model Experience

### The patent_review tool

#### What the model sees

The `patent_review` tool in the tool table: one `target` parameter (file or directory path). A conversational review request ("审查一下这份交底书") resolves to calling this tool — the model confirms the target and invokes it; the fixed script, the rubric, and the report path are host data the model never supplies. The tool result carries the same UI summary the command shows (overall score, notes, report path); the full report becomes model-visible through a later fs read.

#### Token effect

The tool schema rides every request in profiles composing this package; each run adds one tool result (the short summary).

#### KV Cache effect

Prefix-stable: the schema is constant; summaries append after the prefix.

### Command surface

#### What the model sees

Nothing. `/patent-review` is a human command: dispatch bypasses the model turn, `CommandResult` is UI-only, and only the log-only `command/run`/`command/done` events record the attempt.

#### Token effect

Zero per invocation.

#### KV Cache effect

None; the command adds nothing to the request prefix.

## Known Limitations and Deferred Work

- **npm publishing would drop the rubric asset** — the workspace-constraints gate pins `files` to the uniform list without a `rubric/` entry; publishing this package would need that list widened (moot while the package stays workspace-internal).
- **One target per invocation** — no saved rubric variants and no multi-target batch; the review is always the shipped versioned rubric.
- **Windows shell quoting** — the report path in the summary is a plain relative path; consumers that shell out to open it must quote it themselves.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

The rubric extends TianGong's system review rubric to the application stage and is versioned in git — git history is the anti-drift anchor. The script runs through `ctx.workflowEngine`, which the patent bundle re-enables on the host plane (`workflow-ptc`), so the command works on the web composition where presets otherwise own the engine.

</details>
