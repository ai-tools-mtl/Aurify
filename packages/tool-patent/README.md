---
description: "Deterministic patent surfaces: five-party alignment readiness scoring, CNIPA claims linting, de-AI prose linting, and the patent-loop state assessor that drives a project from any stage to the exported disclosure."
kind: "package-reference"
---

# @mtl-academic/dsh-tool-patent

English | [中文](README.zh.md)

> Relative links in this document follow the deepseek-harness monorepo layout. This repository is the extracted distribution — the full monorepo ships as the release's `dsh-patent-full.bundle` — so links that leave this directory resolve in the monorepo, not here.

## Summary

Model-facing deterministic patent surfaces. `patent_brief_coverage` scores a disclosure brief against the five-party alignment (五方对齐) readiness criteria so the Init dialogue has a deterministic stop signal; `patent_claims_lint` lints a drafted application's claims (and optional abstract) against the CNIPA format minimums; `patent_loop` assesses a project directory from any pipeline stage and names the one next stage, and the `/patent-loop` command injects that assessment into the session as a full-pipeline push. Choose them inside the patent profile; the two pure tools carry no configuration, and the loop pair reads project state from disk.

## Table of Contents

- [What it does](#what-it-does)
- [Scoring semantics](#scoring-semantics)
- [Claims lint semantics](#claims-lint-semantics)
- [Setup check](#setup-check)
- [Loop semantics](#loop-semantics)
- [Rendering](#rendering)
- [Export shape](#export-shape)
- [Model Experience](#model-experience)
- [Known Limitations and Deferred Work](#known-limitations-and-deferred-work)
- [Dev Note](#dev-note)

## What it does

Registers five tools on `ctx.tools` and one command on `ctx.commands`. `patent_setup_check` is the host-plane environment self-check (see [Setup check](#setup-check)). For `patent_brief_coverage` the model sends the draft content collected so far per dimension — `field`, `background`, `problem`, `solution`, `effect`, plus the edge dimensions `name`, `drawings`, `key_points` (omitted keys mean uncollected) — and receives the collected/missing split, the three-way alignment verdict, and the readiness signal. For `patent_claims_lint` the model sends the drafted claims text (and the optional abstract) and receives the claim count split and the rule violations. The coverage and lint tools are pure functions of their arguments; calls and results ride the loop's `tool/call` and `tool/result` session events, and nothing else is appended. `patent_prose_lint` is the machine half of the patent-de-ai skill: filler phrases, over-150-character sentences, triple parallelisms (errors to clear), plus paragraph summaries and textbook definitions (warnings). `patent_loop` and `/patent-loop` share one disk-reading assessor (see [Loop semantics](#loop-semantics)).

## Scoring semantics

The scorer is a port of TianGong's `brief_dimensions.py` (the Init readiness authority of the reference implementation):

- **Core dimensions** — `field`, `background`, `problem`, `solution`, `effect`. A brief is ready only when every one has non-blank content.
- **Alignment check** — the point counts of `background`, `problem`, and `effect` (estimated by splitting on enumeration markers such as ①②/`1.`/`(1)`/`一、`, and on semicolons and newlines, taking the larger count) must stay within tolerance 1 of each other. The verdict passes vacuously while any of the three is uncollected: a missing dimension is "not yet collected", not "misaligned".
- **Edge dimensions** — `name`, `drawings`, `key_points` are accepted and displayed but never gate readiness; they are typically completed during drafting.

The tolerance and the heuristic count are ported asset semantics (init-stage information is coarse), not deployment tunables, so there is no configuration.

## Claims lint semantics

`patent_claims_lint` parses the numbered claims ("1." through "N.", claims may span lines) and checks statutory-format minimums, not substantive examination:

- **C1** numbering: claims must run consecutively from 1; citations of nonexistent claims are the same rule.
- **C2** dependent claims cite only earlier claims (a self or forward reference is an error).
- **C3** citation form: citing several claims requires the 择一 reference form "根据权利要求N至M中任一项所述的".
- **C4** a multiple-dependent claim must not take another multiple-dependent claim as its base.
- **C5** (warning) an independent claim without "其特征在于" lacks the two-part form expected of improvement-type inventions.
- **A1** the abstract must not exceed 300 non-whitespace characters; the rule runs only when the abstract is supplied.

The parsed claims are deliberately excluded from the model-visible result: the model just supplied the text, so echoing every claim back spends tokens for nothing.

## Setup check

`patent_setup_check` probes every optional channel — the MCP services row (its `~/.dsh/patent-services.yaml` mcp keys, home-patch row, or enabling env vars; the one check an MCP-served tool could never run), docker and its two images, the native draw.io CLI, the patents.google.com reachability, the experiment command policy, the proxy variables — and returns one Chinese verdict line per channel with the fix for whatever is missing. Host-plane on purpose: the tool stays available while the MCP row is disabled, so it is what names that missing row; a broken channel is a report row, never an exception. The same settings keys also drive the plugin's own MCP load: when nothing else enabled the static row, `apply` reads `mcp_enabled`/`mcp_project_dir`/`mcp_wheel` and loads the mcp client with `ctx.plugin` — one file carries every preference. `mcp_enabled` is the master switch, required in both modes: a file carrying only `mcp_wheel` or `mcp_project_dir` stays off, and the check says so. The load refuses a relative project dir or a directory without a pyproject.toml before spawning (the cause lands in the load-failure report row), and wheel mode requires the wheel installed as a uv tool — the package is not on PyPI, so `uvx` only resolves what `uv tool install` put there; the check reports both. The patent-init skill runs the check as step zero of every new project.

## Loop semantics

`patent_loop` reads only disk facts and returns the first incomplete pipeline stage — init (no `patent.yml`) → align (brief.md missing or a core dimension section absent) → chapters (any of the eight files missing or a placeholder; a project carrying experiment work — a quantified effect chapter or an experiments/ tree — also needs the verification chapter chapters/09-verification.md, drafted like any other chapter; a publication number cited in brief.md or chapters/ that the prior-art ledger `reference/prior-art.md` never recorded also stays a chapters gap — every cited 公开号 must trace to a recorded search result, never memory) → experiments (a quantified effect chapter with no run log and no "not applicable" declaration) → figures (the 08-drawings declarations versus the figure files at the figures root, both directions) → review (the NEWEST `*.review.md` must parse to a total score at or above the threshold — default 80, overridable per project via `reviewThreshold` in patent.yml, relaxed by 10 while a 查新不可用 marker sits in `reference/prior-art.md` — and must be fresh against the sources it reviewed: the report's stamped 源指纹 digest over the source set decides, with the mtime comparison kept only for legacy stamp-less reports) → export (no disclosure docx in exports/, or one whose stamped `.fingerprint` sidecar — written by the exporter — no longer matches the live sources; mtime stays the fallback for sidecar-less exports) — plus a per-stage directive naming the skills to load and the disciplines that stage's skills enforce. Digests beat mtimes because git checkouts and directory syncs rewrite mtimes without touching bytes; a review or export is stale exactly when the bytes changed. The below-threshold gap also quotes the report's revision list top items as priorities, so the model knows what to fix without opening the report. `complete=true` requires every gate to pass; it is the authority on 成稿, and the tool description and the `patent-loop` skill tell the model to re-check after every stage instead of declaring the project final itself. Three disk escape hatches keep a legitimate project from deadlocking the loop: `experiments/README.md` declaring 无需实验, 无附图 noted in 08-drawings.md, and the search-unreachable marker — which trades ten score points for a recorded debt the model must repay by searching and re-reviewing once the channel returns; while the marker sits, every directive (the done verdict included) carries a standing debt note, and the tool probes whether the channel came back so a recovered connection turns the next call's roadmap into the repayment step. The `/patent-loop` command assesses, injects the loop contract into the session as a durable user-plane input through `agent.followup()`, and returns a UI-only summary — the command result never enters model history, and stages needing the user (direction sign-off, interview answers) end the turn with questions on the table.

## Rendering

The canonical result is `{ covered, missing, ready, coreFilled: { done, total }, aligned, alignmentCounts }`; its Native renderer returns one text block naming the missing dimensions with their Chinese chapter titles, the alignment counts with the tolerance verdict, and the ready/not-ready verdict with the next action.

## Export shape

A function plugin: it exports `name` / `inject` / `apply` and NO default. A stray `export default` would collapse the module via the Loader's `unwrapExports` and drop `inject` (see [docs/postmortem/0001](../../../docs/postmortem/0001-acp-default-export-drops-inject.md)). `inject` is `['tools', 'commands']` — the command registration rides the same plugin as the tools.

## Model Experience

### Tool schema

#### What the model sees

The model sees the generated [`patent_brief_coverage` schema](../../../docs/tool-catalog.md#deepseek-aidsh-tool-patent).

#### Token effect

Fixed schema cost on every request where the tool is visible.

#### KV Cache effect

Prefix-stable while the definition and visibility are unchanged.

### Tool-call history and result

#### What the model sees

Each call carries the draft dimension contents as arguments. Success returns one text block of fixed shape (coverage progress, named gaps, alignment verdict, next action). No stable failure modes: blank arguments are a valid "nothing collected yet" input, and every schema violation is rejected by the registry with the standard `INVALID_ARGS` result.

#### Token effect

Scales with the draft text the model submits per call; results are small and fixed-shape.

#### KV Cache effect

Append-only; newly visible content follows the reusable request prefix.

## Known Limitations and Deferred Work

- **The tool scores what it is given** — the model supplies the dimension contents from its context; it could submit a trimmed brief and receive a misleading `ready`. The `patent-init` skill procedure constrains this, and the review engine re-checks the written files.
- **No path-based input** — the coverage and lint tools take text, not a `brief.md` path; reading the file first through the `fs` tools is the model's job, keeping this package free of filesystem policy (the loop pair is the deliberate exception: it reads project state itself so its verdict cannot be gamed by what the model submits).
- **The loop's brief and effect heuristics are presence checks** — a heading with a non-empty body passes align, and any number-plus-unit in the effect chapter triggers the experiments gate; thin content and unbacked numbers are the skills' and the review engine's job, not the assessor's.

<a id="dev-note"></a>
### Dev Note

<details>
<summary>Working context for maintainers — click to expand</summary>

The scorer is a port of TianGong's `brief_dimensions.py`; the tolerance and the heuristic enumeration count are ported asset semantics, not deployment tunables. The lint rules track CNIPA statutory format minimums (C1-C6, A1-A2), not substantive examination. The loop assessor deliberately trusts only disk artifacts — a stage whose artifacts are missing stays pending no matter what the conversation claims — and every escape hatch is itself a disk file.

</details>
