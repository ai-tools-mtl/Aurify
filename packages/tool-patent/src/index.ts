/**
 * Model-facing deterministic patent tools: the five-party alignment coverage
 * scorer that gates the Init dialogue, the claims-and-abstract linter for
 * application drafting, and the patent-loop state assessor that drives a
 * project from any stage to the exported disclosure. The coverage and lint
 * tools are pure functions of their arguments; the loop tool and the
 * `/patent-loop` command read project state from disk and share one
 * assessor, so the completion verdict never depends on the model's own
 * claim of being done. Named exports preserve loader injection metadata.
 * @module @mtl-academic/dsh-tool-patent
 */

import { resolve } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import type { CommandInvocation, CommandResult } from '@deepseek-ai/dsh-commands'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { ALL_DIMENSIONS, ALIGN_TOLERANCE, computeCoverage, DIMENSION_TITLES, type DimensionOutline } from './coverage.ts'
import { ABSTRACT_MAX_CHARS, lintClaims } from './claims-lint.ts'
import { lintProse } from './prose-lint.ts'
import * as McpClient from '@deepseek-ai/dsh-mcp-client'
import { assessLoopState, type LoopState } from './loop.ts'
import { checkSetupChannels, formatSetupReport, homePatchEnablesMcp, launchBlockage, markSettingsMcpLoaded, mcpFromSettings, noteSettingsMcpLoadError } from './setup-check.ts'

export { computeCoverage } from './coverage.ts'
export type { Coverage, DimensionOutline } from './coverage.ts'
export { lintClaims, parseClaims, countAbstractChars, ABSTRACT_MAX_CHARS } from './claims-lint.ts'
export type { ClaimsLintResult, ParsedClaim, ClaimViolation } from './claims-lint.ts'
export { lintProse } from './prose-lint.ts'
export type { ProseLintResult, ProseViolation } from './prose-lint.ts'
export { assessLoopState } from './loop.ts'
export type { LoopGap, LoopStage, LoopState } from './loop.ts'
export { readManifest } from './loop.ts'
export type { PatentManifest } from './loop.ts'
export { checkSetupChannels, formatSetupReport } from './setup-check.ts'
export type { SetupChannel } from './setup-check.ts'

export const name = 'tool-patent'
export const inject = ['tools', 'commands']

const DIMENSION_DESCRIPTIONS: Readonly<Record<(typeof ALL_DIMENSIONS)[number], string>> = {
  name: 'Proposed invention name (invention name).',
  field: 'Technical field (technical field).',
  background: 'Prior-art shortcomings (shortcomings of the prior art); enumeration improves the alignment estimate.',
  problem: 'Technical problems to solve (technical problems), one per prior-art shortcoming.',
  solution: 'Technical solution (technical solution): architecture, components, and how each solves a stated problem.',
  effect: 'Beneficial effects (beneficial effects), ideally quantified and tied to solution components.',
  key_points: 'Key points and protection scope (key points and protection scope).',
  drawings: 'Figures (figures).',
}

/**
 * Compose the model-facing result text: coverage progress, the named gaps with
 * their Chinese chapter titles, and the alignment verdict.
 * @param value - the canonical coverage result.
 * @returns the render text blocks.
 */
function renderCoverage(value: ReturnType<typeof computeCoverage>): { type: 'text'; text: string }[] {
  const gapText = value.missing.length === 0
    ? 'all five core dimensions covered'
    : `missing: ${value.missing.map(key => `${DIMENSION_TITLES[key as keyof typeof DIMENSION_TITLES]} (${key})`).join(', ')}`
  const counts = value.alignmentCounts
  const alignText = value.aligned
    ? `aligned within tolerance ${ALIGN_TOLERANCE}`
    : `NOT aligned (spread ${Math.max(...Object.values(counts)) - Math.min(...Object.values(counts))} exceeds tolerance ${ALIGN_TOLERANCE})`
  const verdict = value.ready
    ? 'READY: write brief.md and the chapter files, then start drafting.'
    : 'NOT ready: keep asking for the missing dimensions before drafting.'
  return [{
    type: 'text',
    text: `Brief coverage ${value.coreFilled.done}/${value.coreFilled.total} (${gapText}). `
      + `Alignment counts background/problem/effect = ${counts.background}/${counts.problem}/${counts.effect}, ${alignText}. ${verdict}`,
  }]
}

/**
 * Compose the model-facing result text for the claims lint: the claim count
 * split, the violation list, and the verdict.
 * @param value - the canonical lint projection (summary + violations).
 * @returns the render text blocks.
 */
function renderClaimsLint(value: { summary: ReturnType<typeof lintClaims>['summary']; violations: ReturnType<typeof lintClaims>['violations'] }): { type: 'text'; text: string }[] {
  const { summary } = value
  const head = `Claims ${summary.total} (${summary.independent} independent, ${summary.dependent} dependent), `
    + `${summary.errors} errors, ${summary.warnings} warnings.`
  const list = value.violations.length === 0
    ? 'all format rules pass'
    : value.violations.map(violation => `[${violation.rule}]${violation.claim === undefined ? '' : ` claim ${violation.claim}`} ${violation.message}`).join(' | ')
  const verdict = summary.errors === 0
    ? 'PASS: no format errors (warnings are drafting hints, not blockers).'
    : 'FAIL: fix the C/A-rule errors before export.'
  return [{ type: 'text', text: `${head} ${list} ${verdict}` }]
}

/**
 * Compose the loop prompt the `/patent-loop` command injects into the
 * session: the assessor's stage verdict plus the loop contract — execute the
 * stage per its skills, re-check with the tool after every stage, and never
 * declare the project final without the assessor's `complete` verdict.
 * @param state - the current assessment.
 * @returns the user-plane prompt text.
 */
function loopPrompt(state: LoopState): string {
  const gapLines = state.gaps.map(gap => `- [${gap.stage}] ${gap.detail}`).join('\n')
  return `【patent-loop 全流程推进】项目：${state.projectName}（${state.projectRoot}）\n`
    + `当前阶段：${state.stage}${state.mayNeedUser ? '（本阶段需要用户输入）' : ''}\n`
    + `待办清单：\n${gapLines.length > 0 ? gapLines : '- 无——项目已成稿'}\n\n`
    + `本阶段指令：${state.directive}\n\n`
    + '循环契约（必须遵守）：\n'
    + `1. 先加载本阶段指定的技能（${state.skills.length > 0 ? state.skills.join('、') : '无需技能'}）再动手，严格按技能的目录与纪律执行：附图渲染后必须派 subagent 验收合格才保留；正式实验数据必须出自 run_experiment 工具；导出一律走 patent-services 的 MCP 工具，禁止手拼 docx。\n`
    + '2. 每完成一个阶段就再次调用 patent_loop 工具核验；只有它返回 complete=true 才算完成，禁止凭感觉宣布成稿。\n'
    + '3. 需要用户输入时（方向拍板、访谈问答、复述确认），把问题抛给用户并结束本轮；用户回答后继续推进，用户也可随时再发 /patent-loop 恢复。\n'
    + '4. 工具或网络不可用时如实说明并给启用方法，不静默降级、不编造。'
}

/**
 * Compose the loop tool's model-facing render text: the stage verdict plus
 * the directive, with the re-check contract spelled out once. The input is
 * the tool's own projection (gap strings), not the full LoopState.
 * @param value - the execute projection returned by the tool.
 * @returns the render text block.
 */
function renderLoop(value: { complete: boolean; projectName: string; stage: string; directive: string; gaps: string[] }): { type: 'text'; text: string }[] {
  const head = value.complete
    ? `LOOP COMPLETE: ${value.projectName} 已成稿（导出物、附图、审查报告全部就位）。`
    : `LOOP STAGE [${value.stage}]: ${value.gaps[0] ?? ''}`
  const tail = value.complete
    ? '交付导出物路径与要点摘要即可，不要再循环。'
    : '按指令完成后再次调用 patent_loop 核验，直到返回 LOOP COMPLETE。'
  return [{ type: 'text', text: `${head}\n${value.directive}\n${tail}` }]
}

/**
 * Probe whether the prior-art search channel is reachable again. Best effort
 * with a short timeout — a failure keeps the degraded (relaxed) state without
 * any error surfacing to the caller.
 * @returns whether patents.google.com answered within the timeout.
 */
async function searchChannelReachable(): Promise<boolean> {
  try {
    const response = await fetch('https://patents.google.com/', { signal: AbortSignal.timeout(3000) })
    return response.ok
  } catch {
    return false
  }
}

/**
 * Register the `patent_brief_coverage` and `patent_claims_lint` tools, the
 * `patent_loop` assessor tool, and the `/patent-loop` command on `ctx`.
 * @param ctx - registrant context carrying the tool and command registries.
 */
export async function apply(ctx: Context): Promise<void> {
  ctx.tools.register(defineTool({
    name: 'patent_brief_coverage',
    description: 'Score a patent disclosure brief against the five-party alignment readiness criteria '
      + '(technical field, prior-art shortcomings, technical problems, solution, beneficial effects). '
      + 'Send the draft content collected so far for each dimension (omit uncollected ones) and use the '
      + 'readiness verdict to decide whether to keep asking questions or to start drafting. Core dimensions: '
      + 'field, background, problem, solution, effect; the background/problem/effect point counts must stay '
      + `within tolerance ${ALIGN_TOLERANCE} of each other.`,
    parameters: Object.fromEntries(ALL_DIMENSIONS.map(key => [
      key,
      { type: 'string' as const, description: DIMENSION_DESCRIPTIONS[key] },
    ])),
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          covered: { type: 'array', required: true, items: { type: 'string' } },
          missing: { type: 'array', required: true, items: { type: 'string' } },
          ready: { type: 'boolean', required: true },
          coreFilled: {
            type: 'object',
            required: true,
            additionalProperties: false,
            properties: {
              done: { type: 'integer', required: true },
              total: { type: 'integer', required: true },
            },
          },
          aligned: { type: 'boolean', required: true },
          alignmentCounts: {
            type: 'object',
            required: true,
            additionalProperties: false,
            properties: {
              background: { type: 'integer', required: true },
              problem: { type: 'integer', required: true },
              effect: { type: 'integer', required: true },
            },
          },
        },
      },
      render: (_args, value) => renderCoverage(value),
      // The canonical value IS the UI payload: the shipped web card renders
      // it directly and falls back to the rendered text on cores that predate
      // the presentation channel.
      presentationMeta: (_args, value) => value,
    },
    execute(args) {
      const outline: DimensionOutline = args
      return Promise.resolve(computeCoverage(outline))
    },
    presentCall: args => ({ card: 'generic', title: 'Score brief coverage', kind: 'other', rawInput: args }),
  }))

  ctx.tools.register(defineTool({
    name: 'patent_claims_lint',
    description: 'Lint a drafted Chinese patent application claims section (and optional abstract) '
      + 'against the CNIPA format minimums: consecutive numbering (C1), dependent claims citing only '
      + 'earlier claims (C2), citation form (C3), the multiple-dependent base restriction (C4), the '
      + 'two-part form hint for independent claims (C5), the ban on drawing references inside claims '
      + '(C6), the abstract length cap (A1, '
      + `${ABSTRACT_MAX_CHARS} characters), and the abstract promotional-wording hint (A2). `
      + 'Send the claims text (and the abstract when drafting it); '
      + 'use the error/warning split to decide what must be fixed before export.',
    parameters: {
      claims: {
        type: 'string',
        required: true,
        description: 'The claims section text (权利要求书), numbered claims "1." through "N.".',
      },
      abstract: {
        type: 'string',
        description: 'The abstract text (说明书摘要); the A1 length rule runs only when supplied.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          summary: {
            type: 'object',
            required: true,
            additionalProperties: false,
            properties: {
              total: { type: 'integer', required: true },
              independent: { type: 'integer', required: true },
              dependent: { type: 'integer', required: true },
              errors: { type: 'integer', required: true },
              warnings: { type: 'integer', required: true },
            },
          },
          // The two lint tools' violations schemas are structurally alike by
          // design (same wire shape, different fields); the type inference on
          // defineTool schemas needs these inline, so the clone is exempted.
          /* jscpd:ignore-start */
          violations: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                claim: { type: 'integer' },
                rule: { type: 'string', required: true },
                severity: { type: 'string', required: true, enum: ['error', 'warning'] },
                message: { type: 'string', required: true },
              },
            },
          },
          /* jscpd:ignore-end */
        },
      },
      render: (_args, value) => renderClaimsLint(value),
      presentationMeta: (_args, value) => value,
    },
    execute(args) {
      // The parsed claims stay out of the model-visible value: the model just
      // supplied them, so echoing every claim back spends tokens for nothing.
      const { summary, violations } = lintClaims(args.claims, args.abstract)
      return Promise.resolve({ summary, violations })
    },
    presentCall: args => ({ card: 'generic', title: 'Lint claims', kind: 'other', rawInput: { claims: '…', abstract: args.abstract } }),
  }))

  ctx.tools.register(defineTool({
    name: 'patent_prose_lint',
    description: 'Deterministic de-AI prose lint for disclosure chapter text, the machine half of the '
      + 'patent-de-ai skill: filler and apologetic phrases (值得注意的是/换言之/综上所述/遗憾的是…), sentences over 150 '
      + 'characters, triple parallelisms, paragraph-ending summary sentences, and textbook definitions. '
      + 'Errors must be cleared before a chapter counts as drafted; warnings are drafting hints. '
      + 'Run it on every drafted or revised chapter before presenting it.',
    parameters: {
      text: {
        type: 'string',
        required: true,
        description: 'The chapter prose to check (one chapter or a span; markdown structure is fine).',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          summary: {
            type: 'object',
            additionalProperties: false,
            required: true,
            properties: {
              cliches: { type: 'integer', required: true },
              longSentences: { type: 'integer', required: true },
              parallelisms: { type: 'integer', required: true },
              paragraphSummaries: { type: 'integer', required: true },
              definitions: { type: 'integer', required: true },
              errors: { type: 'integer', required: true },
              warnings: { type: 'integer', required: true },
            },
          },
          /* jscpd:ignore-start */
          violations: {
            type: 'array',
            required: true,
            items: {
              type: 'object',
              additionalProperties: false,
              properties: {
                rule: { type: 'string', required: true },
                severity: { type: 'string', required: true },
                message: { type: 'string', required: true },
                excerpt: { type: 'string', required: true },
              },
            },
          },
          /* jscpd:ignore-end */
        },
      },
      render: (_args, value) => [{
        type: 'text',
        text: `Prose lint: ${value.summary.errors} errors, ${value.summary.warnings} warnings `
          + `(cliches ${value.summary.cliches}, long sentences ${value.summary.longSentences}, `
          + `parallelisms ${value.summary.parallelisms}). `
          + (value.summary.errors === 0 ? 'PASS.' : 'Fix the errors before the chapter counts as drafted.'),
      }],
      presentationMeta: (_args, value) => value,
    },
    execute(args) {
      // Pure function of the submitted text, like the claims lint.
      return Promise.resolve(lintProse(args.text))
    },
    presentCall: () => ({ card: 'generic', title: 'Lint prose', kind: 'other', rawInput: { text: '…' } }),
  }))

  ctx.tools.register(defineTool({
    name: 'patent_loop',
    description: 'Assess a patent project from any stage and name the one next pipeline stage '
      + '(init → align → chapters → experiments → figures → review → export) with its directive. '
      + 'Every verdict is read from disk facts — manifest, brief, chapters (a project carrying '
      + 'experiments or quantified effects also needs the verification chapter 09-verification.md), '
      + 'the experiment run log, figure files against the drawings chapter, publication numbers in '
      + 'the prose against the prior-art ledger (reference/prior-art.md), the NEWEST review report '
      + 'total score against the threshold (default 80; reviewThreshold in patent.yml overrides; a '
      + '查新不可用 marker in reference/prior-art.md relaxes it by 10) with report freshness against '
      + 'the sources, and the exported disclosure docx — never from the conversation, so this is the '
      + 'only authority on whether the project is 成稿. '
      + 'Use it to start or resume a full-pipeline push ("loop", "继续推进", "帮我完成"), and call it '
      + 'again after finishing each stage; only its complete=true verdict ends the loop.',
    parameters: {
      project_dir: {
        type: 'string',
        description: 'The patent project directory. Defaults to the working directory; pass the '
          + 'project folder when the session sits above it.',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          stage: { type: 'string', required: true },
          complete: { type: 'boolean', required: true },
          projectName: { type: 'string', required: true },
          projectRoot: { type: 'string', required: true },
          mayNeedUser: { type: 'boolean', required: true },
          priorArtDegraded: { type: 'boolean', required: true },
          skills: { type: 'array', required: true, items: { type: 'string' } },
          directive: { type: 'string', required: true },
          gaps: { type: 'array', required: true, items: { type: 'string' } },
        },
      },
      render: (_args, value) => renderLoop(value),
      presentationMeta: (_args, value) => value,
    },
    async execute(args, exec) {
      const root = args.project_dir ?? exec.agent?.session.header.cwd
      if (root === undefined) {
        return {
          stage: 'init',
          complete: false,
          projectName: '',
          projectRoot: '',
          mayNeedUser: false,
          priorArtDegraded: false,
          skills: [],
          directive: '无法定位项目目录：会话未携带工作目录，请用 project_dir 参数显式指定。',
          gaps: ['无法定位项目目录'],
        }
      }
      const state = await assessLoopState(resolve(root))
      const gaps = state.gaps.map(gap => `[${gap.stage}] ${gap.detail}`)
      if (state.priorArtDegraded && await searchChannelReachable()) {
        gaps.push('[查新债] 检索通道已恢复：按 patent-research 补检索 reference/prior-art.md，然后删除「查新不可用」标记，并把审查分数审回未放宽的达标线')
      }
      return {
        stage: state.stage,
        complete: state.complete,
        projectName: state.projectName,
        projectRoot: state.projectRoot,
        mayNeedUser: state.mayNeedUser,
        priorArtDegraded: state.priorArtDegraded,
        skills: state.skills,
        directive: state.directive,
        gaps,
      }
    },
    presentCall: args => ({ card: 'generic', title: 'Patent loop', kind: 'other', rawInput: args }),
  }))

  // Host-plane on purpose: an MCP-served self-check cannot diagnose an MCP
  // row that never loaded, so this tool must not depend on it — it is what
  // names the missing row and hands the model the enabling step.
  ctx.tools.register(defineTool({
    name: 'patent_setup_check',
    description: 'Self-check the patent plugin environment: the MCP services row (the ~/.dsh/patent-services.yaml mcp keys, a home-patch row, or the env opt-in), docker and its '
      + 'two images, the native draw.io CLI, the patents.google.com search channel, the experiment '
      + 'command policy, and the proxy variables — one Chinese verdict line per channel with the '
      + 'configuration step for whatever is missing. Host-side on purpose: it works even while the '
      + 'MCP row is disabled, so it is the tool that names that missing row. Call it at a project\'s '
      + 'start ("检查专利环境/环境自检", before the idea evaluation), after any configuration change, '
      + 'or when a channel behaves oddly; act on the gaps (a pre-warm docker pull, asking the user '
      + 'for one settings-file line) and re-check. The MCP row loads at process start, so a freshly '
      + 'written settings file needs a dsh process restart — the desktop shell as a whole, not just '
      + 'a new conversation; the check reports 已装载 versus 待重启 so you never hand the user a '
      + 'false green light. A broken channel is a report row, never an exception.',
    parameters: {},
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          report: { type: 'string', required: true },
          failed: { type: 'array', required: true, items: { type: 'string' } },
        },
      },
      render: (_args, value) => [{ type: 'text', text: value.report }],
      presentationMeta: (_args, value) => value,
    },
    async execute() {
      const channels = await checkSetupChannels()
      return { report: formatSetupReport(channels), failed: [...new Set(channels.filter(c => c.status === 'fail').map(c => c.gates).filter(g => g.length > 0))] }
    },
    presentCall: () => ({ card: 'generic', title: 'Patent setup check', kind: 'other', rawInput: {} }),
  }))

  // The command is a trigger, not an executor: it assesses the project and
  // injects the loop prompt as a durable user-plane input, so the work runs
  // in the model's hands with full tool access while the assessor keeps the
  // completion verdict. The CommandResult stays UI-only.
  const handler = async (invocation: CommandInvocation): Promise<CommandResult> => {
    const cwd = invocation.agent.session.header.cwd
    if (cwd === undefined) return { kind: 'error', text: '无法确定项目目录：会话未携带工作目录，请先 cd 到项目目录或指定目标。' }
    const raw = invocation.rawInput.trim()
    const root = resolve(cwd, raw.length > 0 ? raw : '.')
    const state = await assessLoopState(root)
    if (!state.complete) {
      invocation.agent.followup(createUserMessage({
        content: [{ type: 'text', text: loopPrompt(state) }],
        source: { kind: 'user' },
      }))
    }
    const head = state.complete
      ? `项目已成稿（${state.projectName}）：交底书导出物、附图、审查报告全部就位，无需循环。`
      : `patent-loop 已启动：${state.projectName} — 当前阶段 ${state.stage}（${state.gaps[0]?.detail ?? ''}）；推进指令已注入会话，模型完成后会自动核验下一阶段。`
    const roadmap = state.gaps.map(gap => `[${gap.stage}] ${gap.detail}`).join('；')
    return { kind: 'success', text: roadmap.length > 0 ? `${head}\n待办：${roadmap}` : head }
  }
  ctx.effect(function* () {
    yield ctx.commands.register({
      name: 'patent-loop',
      description: '从任何阶段把专利项目推进到成稿交底书（评估当前阶段→注入推进指令→循环直到 complete）',
      handler,
    })
  }, 'tool-patent loop command')

  // The patent MCP services, config-file mode: when neither the env opt-in
  // nor a home-patch row enabled the bundle's static row, the settings
  // file's mcp keys load the client here — one file carries every
  // preference, and the home patch stays untouched. Skipped whenever the
  // static row is already live: a duplicate serverName fails loud. Empty
  // strings count as unset, matching what the setup check reports. The boot
  // marker afterwards lets the setup check separate "configured" from
  // "configured and live" — a file written after boot needs a restart.
  const envDir = process.env.DSH_PATENT_SERVICES_DIR
  const envWheel = process.env.DSH_PATENT_SERVICES
  if ((envDir === undefined || envDir.length === 0) && (envWheel === undefined || envWheel.length === 0)
    && !homePatchEnablesMcp()) {
    const launch = mcpFromSettings()
    if (launch !== null) {
      // Config-shape problems are rejected before the spawn: a relative
      // project dir would make uv resolve against the process working
      // directory, and the raw spawn error says nothing a user can act on.
      // The same readable cause then feeds the load-failure report state.
      const blockage = launchBlockage(launch)
      if (blockage !== null) {
        noteSettingsMcpLoadError(new Error(blockage))
      } else {
        try {
          await ctx.plugin(McpClient, {
            transport: 'stdio',
            serverName: 'patent',
            command: launch.command,
            args: [...launch.args],
          })
          markSettingsMcpLoaded()
        } catch (error: unknown) {
          // A failed optional row must never take the host-plane tools down
          // with it: record the cause so the setup check can report it, and
          // let apply() finish registering the loop and setup tools.
          noteSettingsMcpLoadError(error)
        }
      }
    }
  }
}
