---
description: "Fixed seven-dimension review pipeline shared by /patent-review and patent_review."
kind: "package-reference"
---

# @mtl-academic/dsh-command-patent-review

English | [中文](README.zh.md)

`/patent-review` (user command) and `patent_review` (model tool) share a fixed workflow script and shipped rubric. Callers supply only the target path; reports go to `review/`. Orchestration and aggregation are deterministic; model scores still vary with sampling.

## Targets and reports

- File: review one Markdown file.
- Ordinary directory: concatenate top-level `*.md` files in filename order.
- Project root with `patent.yml`: collect `brief.md` and top-level Markdown in `chapters/` and `application/`, sorting each directory by name. Old reports, exports, references and experiment artifacts are excluded.

Reports go to `review/<label>.review.md` under the nearest ancestor containing `patent.yml`, or under the resolution base when no project ancestor exists. Only project-root targets receive a whole-project review fingerprint. File and other directory reviews are partial and cannot satisfy that gate.

Scores render as `**总分**：85 / 100`; the loop and dashboard also accept legacy `总分 85`. Missing or nonnumeric scores do not pass. The tool returns a summary and path; read the report separately for full content. Command results are UI-only and do not enter model history.

## Scoring and consistency

[`rubric/default.json`](rubric/default.json) defines seven dimensions and weights: completeness 0.15, solution clarity 0.20, novelty presentation 0.15, writing conventions 0.15, claims quality 0.15, description support 0.15 and abstract compliance 0.05. It is validated on load and included through the package manifest's `files` list.

`src/script.ts` runs independent scoring passes per dimension, rounds their means and renormalizes weights over dimensions with valid scores. Failed children do not directly abort the run; the report records failures and effective pass counts. Interpret the total alongside any missing dimensions.

Project-root or application targets with both `claims.md` and `description.md` also run claims-to-description support and terminology checks. Equal input and collected scores yield an equal report; repeated model calls need not yield equal scores.

## Configuration

| Key | Default and behavior |
|---|---|
| `scoringPasses` | 2, integer 1–5; passes per dimension. Project `patent.yml` can override with `reviewPasses` |
| `reviewTemperature` | 0.2, range 0–2; older engines without child temperature support use the provider default |
| `projectRoot` | Unset; resolve relative targets against the current agent session cwd. Fail if neither base is available |

Report ownership follows project ancestry after path resolution. Users need not launch the session from the project root. `reviewThreshold` belongs to the [pipeline assessor](../tool-patent/README.md#pipeline-gates), not this package's pass-count configuration.

## Development and limitations

Keep the named `name`, `inject`, `Config` and `apply` exports; do not add a default export. Review needs the host `workflowEngine`, enabled by the Bundle's compatibility rows. See the [development guide](../../docs/DEVELOPMENT.md) for host validation boundaries.

Each call accepts one target; saved rubric variants and multi-target batches are unsupported. Model and gateway failures can leave scores incomplete. Quote paths containing spaces when opening reports through a shell.
