/**
 * Human-facing `/patent-review` command: a deterministic rubric review over
 * one project file or a directory of Markdown files. The handler reads the
 * target from disk, starts the fixed workflow script (host data — the model
 * cannot skip or reshape the review), writes `review/<label>.review.md`, and
 * returns a UI-only summary. `CommandResult` never enters model history; the
 * report reaches the model only when it later reads the file through the fs
 * tools, so "model-visible ⟺ logged" stays intact.
 * @module @deepseek-ai/dsh-command-patent-review
 */

import { readFile, readdir, writeFile, mkdir, access } from 'node:fs/promises'
import { readFileSync } from 'node:fs'
import { join, relative, resolve, dirname, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
import type { Agent } from '@deepseek-ai/dsh-agent'
import z from '@deepseek-ai/schemastery'
import type { CommandInvocation, CommandResult } from '@deepseek-ai/dsh-commands'
import { defineTool } from '@deepseek-ai/dsh-tools'
// Type-only: resolves ctx.workflowEngine for the run start.
import type {} from '@deepseek-ai/dsh-workflow'
import { isReviewOutcome, renderReport, summarize, type ReviewOutcome } from './review.ts'
import { REVIEW_SCRIPT } from './script.ts'
import { sourceFingerprint } from '@deepseek-ai/dsh-tool-patent/fingerprint'
import { readManifest } from '@deepseek-ai/dsh-tool-patent'

export { isReviewOutcome, renderReport, summarize } from './review.ts'
export { REVIEW_SCRIPT } from './script.ts'

export const name = 'command-patent-review'
export const inject = ['commands', 'tools', 'workflowEngine']

/** One rubric scoring dimension with its banded scoring guide. */
export interface RubricDimension {
  key: string
  title: string
  weight: number
  guide: Record<string, string>
}

/** The versioned rubric document the review engine scores against. */
export interface RubricDocument {
  name: string
  dimensions: RubricDimension[]
}

/** Absolute path of the shipped versioned rubric, resolved beside the package. */
export const RUBRIC_PATH = fileURLToPath(new URL('../rubric/default.json', import.meta.url))

// Fails loud at load: a broken rubric is a deployment error, not a per-call one.
const rubric = loadRubric()

/**
 * Load and validate the versioned rubric (a durable file boundary — parsed,
 * not trusted). Misconfiguration fails loud at load.
 * @param path - absolute rubric JSON path.
 * @returns the rubric document.
 */
export function loadRubric(path: string = RUBRIC_PATH): RubricDocument {
  const document = JSON.parse(readFileSync(path, 'utf8')) as unknown
  if (typeof document !== 'object' || document === null) {
    throw new Error(`patent review rubric ${path}: expected an object`)
  }
  const { name, dimensions } = document as Record<string, unknown>
  if (typeof name !== 'string' || name.length === 0) throw new Error(`patent review rubric ${path}: missing name`)
  if (!Array.isArray(dimensions) || dimensions.length === 0) throw new Error(`patent review rubric ${path}: missing dimensions`)
  for (const dimension of dimensions) {
    const record = dimension as Record<string, unknown>
    if (typeof record.key !== 'string' || typeof record.title !== 'string' || typeof record.weight !== 'number'
      || typeof record.guide !== 'object' || record.guide === null || Array.isArray(record.guide)
      || !Object.entries(record.guide).every(([band, text]) => typeof band === 'string' && typeof text === 'string')) {
      throw new Error(`patent review rubric ${path}: malformed dimension ${JSON.stringify(record.key ?? dimension)}`)
    }
  }
  return document as RubricDocument
}

/** Model-facing `/patent-review` command configuration. */
export interface Config {
  /**
   * How many independent scoring passes run per rubric dimension. Two gives a
   * self-consistency signal (spread is visible in the report) at twice the
   * child count; one is the cheap mode. Validated to 1-5.
   */
  scoringPasses: number
  /**
   * Sampling temperature pinned on every scoring child's requests. Scoring is
   * a mechanical rubric application, so the default sits near deterministic;
   * raise it only when the rubric should reward wording variety (it should
   * not). Validated to the provider-agnostic 0-2 range.
   */
  reviewTemperature: number
  /**
   * The patent project root: the base for relative review targets. Unset
   * resolves each invocation against the receiving agent's session cwd (the
   * workspace a web composition created the session in); set it explicitly
   * only when the fs world differs from that session workspace (e.g. a
   * composed `fs-local` cwd). The report folder anchors to the nearest
   * enclosing patent.yml project regardless.
   */
  projectRoot?: string
}

/** Schemastery configuration for the review command. */
export const Config: z<Config> = z.object({
  // `natural()` is schemastery's integer primitive (number().step(1).min(0)).
  scoringPasses: z.natural().min(1).max(5).default(2),
  reviewTemperature: z.number().min(0).max(2).default(0.2),
  projectRoot: z.string(),
})

const USAGE = '用法：/patent-review <文件或目录>（相对工作目录，如 duofenqu-zhiwudeng/chapters/03-background.md 或整个项目目录）'

/** Whether the path exists. */
async function exists(path: string): Promise<boolean> {
  try {
    await access(path)
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    return false
  }
  return true
}

/**
 * Locate the enclosing patent project: the nearest ancestor directory of the
 * resolved target that holds `patent.yml` (the file-first project marker), so
 * the report lands in the project's own `review/` even when the session cwd is
 * the workspace above it.
 * @param targetPath - the resolved review target (file or directory).
 * @returns the project root, or undefined when no ancestor holds `patent.yml`.
 */
async function findEnclosingProject(targetPath: string): Promise<string | undefined> {
  let dir = resolve(dirname(targetPath))
  while (true) {
    if (await exists(join(dir, 'patent.yml'))) return dir
    const parent = dirname(dir)
    if (parent === dir) return undefined
    dir = parent
  }
}

/** Markdown files reviewed for a directory target, in name order. */
async function collectMarkdownFiles(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true })
  return entries.filter(entry => entry.isFile() && entry.name.endsWith('.md'))
    .map(entry => entry.name)
    .sort()
}

/** Read the target's content; a directory target concatenates its Markdown files in name order. */
async function readTarget(projectRoot: string, rawPath: string): Promise<{ label: string; content: string } | undefined> {
  const absolute = resolve(projectRoot, rawPath)
  let content: string
  try {
    content = await readFile(absolute, 'utf8')
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code !== 'EISDIR') return undefined
    const names = await collectMarkdownFiles(absolute)
    if (names.length === 0) return undefined
    const parts = await Promise.all(names.map(async (name) => {
      const body = await readFile(join(absolute, name), 'utf8')
      return `<!-- ${name} -->\n\n${body.trim()}`
    }))
    content = parts.join('\n\n---\n\n')
  }
  return { label: relative(projectRoot, absolute).replaceAll('\\', '/'), content }
}

/**
 * Read the claims↔description consistency inputs when the review target sits
 * inside the application document set. Both files must exist; any missing
 * file skips the phase (a partial set has nothing consistent to check).
 * @param reportRoot - the project root anchoring `application/`.
 * @param targetPath - the resolved review target.
 * @returns the two texts, or undefined when the target is elsewhere or the
 * set is incomplete.
 */
async function readConsistencyInputs(reportRoot: string, targetPath: string): Promise<{ claims: string; description: string } | undefined> {
  const applicationDir = join(reportRoot, 'application')
  const inside = targetPath === applicationDir || targetPath.startsWith(applicationDir + sep)
  if (!inside) return undefined
  const read = async (name: string): Promise<string | undefined> => {
    try {
      return await readFile(join(applicationDir, name), 'utf8')
    } catch (error: unknown) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
      return undefined
    }
  }
  const claims = await read('claims.md')
  const description = await read('description.md')
  return claims === undefined || description === undefined ? undefined : { claims, description }
}

/**
 * The invocation surface executeReview actually reads — the human command and
 * the model-facing tool both supply it, so the fixed script, the rubric, and
 * the report path stay identical regardless of which surface fired.
 */
interface ReviewInvocation {
  /** The review target text: a file or directory path relative to the cwd. */
  readonly rawInput: string
  /** The agent on whose behalf the review runs (cwd and engine parent). */
  readonly agent: Agent
  /** Cancellation for the run. */
  readonly signal: AbortSignal
}

/** The per-dimension fold the tool's structured card consumes (no per-pass detail). */
interface ReviewDimensionFold {
  key: string
  title: string
  weight: number
  average: number | null
  failedPasses: number
}

/** Execute one review run and persist its report; the outcome's per-dimension fold rides along for the tool's structured card. */
async function executeReview(
  ctx: Context,
  config: Config,
  invocation: ReviewInvocation,
): Promise<{ result: CommandResult; dimensions?: ReviewDimensionFold[] }> {
  const target = invocation.rawInput.trim()
  if (target.length === 0) return { result: { kind: 'error', text: USAGE } }
  const projectRoot = config.projectRoot ?? invocation.agent.session.header.cwd
  if (projectRoot === undefined) {
    return { result: { kind: 'error', text: '无法确定项目根目录：未配置 projectRoot，且会话未携带工作目录。' } }
  }
  const file = await readTarget(projectRoot, target)
  if (file === undefined) return { result: { kind: 'error', text: `未找到可审查的 Markdown 文件：${target}` } }
  const reportRoot = (await findEnclosingProject(resolve(projectRoot, target))) ?? projectRoot
  const resolvedTarget = resolve(projectRoot, target)
  const consistency = await readConsistencyInputs(reportRoot, resolvedTarget)
  // A per-project pass count overrides the profile-wide default: interview
  // heavy projects can drop to one pass, contested ones raise it — the same
  // override relationship patent.yml's reviewThreshold has with the default bar.
  const manifest = await readManifest(reportRoot)
  const passes = manifest?.reviewPasses ?? config.scoringPasses
  // Whole-project scope: the resolved target IS the project root. The loop's
  // score gate only accepts reports stamped with this scope.
  const scope: 'project' | 'partial' = resolvedTarget === resolve(reportRoot) ? 'project' : 'partial'

  const run = ctx.workflowEngine.start({
    meta: { name: 'patent-review', description: `Rubric review of ${file.label}` },
    script: REVIEW_SCRIPT,
    args: {
      fileLabel: file.label,
      fileContent: file.content,
      dimensions: rubric.dimensions,
      passes,
      reviewerTemperature: config.reviewTemperature,
      ...consistency === undefined ? {} : { consistency },
    },
    parent: invocation.agent,
    signal: invocation.signal,
  })
  let outcome: ReviewOutcome
  try {
    const result = await run.result
    if (result.stopReason !== 'completed') {
      return { result: { kind: 'error', text: `审查未完成（${result.stopReason}）：${result.error ?? '未知原因'}` } }
    }
    if (!isReviewOutcome(result.value)) {
      return { result: { kind: 'error', text: '审查脚本的返回值不是预期的评分结构。' } }
    }
    outcome = result.value
  } finally {
    await run.dispose()
  }

  // A target that resolves to the project root itself (".", the bare project
  // name) yields an empty label; collapse to the project directory's name so
  // the report never hides as review/.review.md.
  const rawLabel = file.label.trim().length === 0
    ? (reportRoot.split(sep).pop() ?? 'project')
    : file.label
  const safeName = rawLabel.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').replace(/\.md$/i, '') || 'project'
  await mkdir(join(reportRoot, 'review'), { recursive: true })
  const reportPath = relative(projectRoot, join(reportRoot, 'review', `${safeName}.review.md`)).replaceAll('\\', '/')
  // The digest is taken after the run completes, over the report root's
  // source set — the loop's freshness gate compares it against the live
  // bytes, so a post-review source edit voids the report even when mtimes lie.
  const fingerprint = await sourceFingerprint(reportRoot)
  await writeFile(join(reportRoot, 'review', `${safeName}.review.md`), `${renderReport(outcome, file.label, scope, fingerprint)}\n`, 'utf8')
  // The attempt ledger is the loop's convergence memory: below-threshold
  // re-reviews accumulate here, and the loop's gate escalates to the user
  // instead of re-reviewing forever once they stop paying off.
  const overallText = outcome.overall === null ? '无' : String(outcome.overall)
  await writeFile(
    join(reportRoot, 'review', 'attempts.md'),
    `- ${new Date().toISOString()} 总分 ${overallText} 范围 ${scope} 目标 ${file.label || '(项目根)'}\n`,
    { encoding: 'utf8', flag: 'a' },
  )
  return {
    result: { kind: 'success', text: summarize(outcome, reportPath) },
    dimensions: outcome.dimensions.map(({ key, title, weight, average, failedPasses }) => ({ key, title, weight, average, failedPasses })),
  }
}

/**
 * Register `/patent-review` for every composed human-command adapter.
 * @param ctx - context carrying the command registry and the workflow engine.
 * @param config - deployment's scoring-pass count.
 */
export function apply(ctx: Context, config: Config): void {
  const active = new Set<Promise<unknown>>()
  const runFull = (invocation: ReviewInvocation): Promise<{ result: CommandResult; dimensions?: ReviewDimensionFold[] }> => {
    const operation = executeReview(ctx, config, invocation)
    active.add(operation)
    const retire = (): void => { active.delete(operation) }
    void operation.then(retire, retire)
    return operation
  }
  const run = (invocation: ReviewInvocation): Promise<CommandResult> => runFull(invocation).then(executed => executed.result)
  const handler = (invocation: CommandInvocation): Promise<CommandResult> => run(invocation)
  ctx.effect(function* () {
    // Yield drain before registration: composite teardown is LIFO, so no new
    // invocation can enter while already-started handler promises quiesce.
    yield async () => { await Promise.allSettled(active) }
    yield ctx.commands.register({
      name: 'patent-review',
      description: '按评分标准（rubric）审查交底书文件或目录，报告写入 review/',
      handler,
    })
    yield ctx.tools.register(defineTool({
      name: 'patent_review',
      description: 'Run the deterministic patent review for one disclosure/application file or a directory: '
        + 'the fixed rubric workflow scores every dimension with independent passes (plus the claims↔description '
        + 'consistency phase inside application/) and writes review/<label>.review.md. Use this for any '
        + 'conversational review request — confirm the target, then call it; do not score documents yourself '
        + 'and do not ask the user to dispatch /patent-review for this.',
      parameters: {
        target: {
          type: 'string',
          required: true,
          description: 'The review target relative to the working directory: "." for the current project '
            + 'directory, a Markdown file like "chapters/03-background.md", or a project subdirectory like '
            + '"application".',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            kind: { type: 'string', required: true, enum: ['success', 'error'] },
            summary: { type: 'string', required: true },
            report: { type: 'string', required: true },
            overall: { type: 'integer' },
            dimensions: {
              type: 'array',
              items: {
                type: 'object',
                additionalProperties: false,
                properties: {
                  key: { type: 'string', required: true },
                  title: { type: 'string', required: true },
                  weight: { type: 'number', required: true },
                  average: { type: 'integer' },
                  failedPasses: { type: 'integer', required: true },
                },
              },
            },
          },
        },
        render: (_args, value) => [{ type: 'text', text: value.summary }],
        presentationMeta: (_args, value) => value,
      },
      async execute(args, exec) {
        if (exec.agent === undefined) {
          return { kind: 'error' as const, report: '', summary: '无法确定审查所属的会话（工具调用缺少 agent 上下文）。' }
        }
        const executed = await runFull({ rawInput: args.target, agent: exec.agent, signal: exec.signal })
        const result = executed.result
        if (result.kind === 'error') return { kind: 'error' as const, report: '', summary: result.text.length > 0 ? result.text : '审查失败。' }
        const overall = /总分\s*(\d+)/.exec(result.text ?? '')?.[1]
        return {
          kind: 'success' as const,
          report: /(\S+\.review\.md)/.exec(result.text ?? '')?.[1] ?? '',
          ...(overall === undefined ? {} : { overall: Number(overall) }),
          ...(executed.dimensions === undefined ? {} : {
            dimensions: executed.dimensions.map(({ key, title, weight, average, failedPasses }) => ({
              key, title, weight, failedPasses,
              ...(average === null ? {} : { average }),
            })),
          }),
          summary: result.text ?? '',
        }
      },
      presentCall: args => ({ card: 'generic', title: '审查交底书', kind: 'other', rawInput: args }),
    }))
  }, 'command-patent-review lifecycle')
}
