---
description: "Aurify native tools: readiness, claims and prose linting, pipeline assessment and environment checks."
kind: "package-reference"
---

# @mtl-academic/dsh-tool-patent

English | [中文](README.zh.md)

Registers five native tools and `/patent-loop`. The separate `patent_review` tool belongs to the [review package](../command-patent-review/README.md). See the [installation guide](../../docs/install/INSTALL-NEW-PROFILE.md) for setup.

## Tools

| Tool | Input and result |
|---|---|
| `patent_brief_coverage` | Five core and three auxiliary text dimensions; missing dimensions, alignment counts and `ready` |
| `patent_claims_lint` | Claims and optional abstract text; claim structure and C1–C6 / A1–A2 findings |
| `patent_prose_lint` | Prose text; filler, long sentences, parallelisms, summaries and definitions |
| `patent_loop` | Project directory; first incomplete stage, all gaps and a directive |
| `patent_setup_check` | Host-side checks of MCP loading, uv/uvx, Docker/images, draw.io and search connectivity, with remedies |

The first three inspect supplied text. `patent_loop` reads disk state; `patent_setup_check` remains available while MCP is disabled. The Bundle Web client renders coverage, claims and review cards.

## Readiness and static rules

Readiness requires nonblank `field`, `background`, `problem`, `solution` and `effect`. Estimated point counts for `background`, `problem` and `effect` must differ by at most 1. Alignment passes provisionally while any of those three is absent, but missing core dimensions still block readiness. `name`, `drawings` and `key_points` are informational. The counting semantics come from TianGong's `brief_dimensions.py`; tolerance is not configurable.

| Rule | Current implementation |
|---|---|
| C1 | Consecutive numbering from 1; referenced claims must exist |
| C2 | Dependent claims cite earlier claims only |
| C3 | Multiple citations require alternative-reference form |
| C4 | A multiple-dependent claim cannot depend on another multiple-dependent claim |
| C5 (warning) | Independent claim lacks the two-part phrase 其特征在于 |
| C6 | Drawing references such as 如图N所示 are errors |
| A1 | Supplied abstract exceeds 300 non-whitespace characters |
| A2 (warning) | Supplied abstract includes promotional wording |

These are code heuristics, not substantive examination. Prose lint treats filler, apologetic wording and sentences over 150 characters as errors; triple parallelisms, paragraph summaries and textbook definitions are warnings.

## Pipeline gates

`patent_loop` and `/patent-loop` share `src/loop.ts` and return the first incomplete stage in order:

| Stage | Main gate |
|---|---|
| init | Root `patent.yml` exists |
| align | Five core dimensions in `brief.md` have content |
| chapters | Eight chapters drafted; name chapter contains only the final name; quantified effects or an experiments tree require `09-verification.md`; cited publication numbers appear in `reference/prior-art.md` |
| experiments | Quantified effects need at least one experiment whose latest run exits 0, or an explicit 无需实验 / 不适用 declaration in `experiments/README.md` |
| figures | Figure declarations in `08-drawings.md` match final files at the `figures/` root in both directions, or explicitly state 无附图 |
| review | Newest report is parseable, meets `reviewThreshold` (default 80), matches current sources and covers the whole project |
| export | A disclosure docx exists and matches current sources |

Review and export gates prefer source fingerprints, falling back to mtimes for legacy files. Changed source bytes require a new review/export; timestamps alone do not invalidate stamped files.

A 查新不可用 marker in `reference/prior-art.md` temporarily lowers the review threshold by 10 and keeps a research-debt reminder active. Once connectivity returns, complete research, remove the marker and review again. This does not waive source verification. `complete=true` means file gates passed; it does not prove content sufficiency or evidence for every metric. Coverage trusts the submitted text, and brief/effect detection is heuristic.

The review gate also reads `review/attempts.md`: repeated below-threshold attempts can stop automatic review and require a user decision. Do not silently lower the threshold or reset the ledger.

`/patent-loop` injects loop instructions through `agent.followup()`; its UI summary stays out of model history. Reassess after each stage. Direction approval and interview answers still require user input.

## Loading and development

The tool plugin uses named `name`, `inject` and `apply` exports; do not add a default export. MCP configuration loads at process start. `patent_setup_check` distinguishes loaded from restart-pending state; saved settings alone do not establish availability.

Full type checks and host tests require a compatible monorepo; see the [development guide](../../docs/DEVELOPMENT.md).
