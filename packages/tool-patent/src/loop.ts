/**
 * The patent-loop state assessor: one deterministic pass over a project
 * directory that names the first incomplete pipeline stage and the directive
 * for finishing it. The loop itself runs in the model's hands — call the
 * tool, execute the stage per its skills, call again — but the completion
 * verdict ("成稿交底书") belongs to this assessor, which reads only disk
 * facts (manifest, brief, chapters, experiment run log, figure files, review
 * reports, the prior-art ledger, the exported docx), never the model's own
 * claim of being done.
 * @module dsh-tool-patent/loop
 */

import { readdir, readFile, stat, access } from 'node:fs/promises'
import { join, resolve, basename } from 'node:path'
import { sourceFingerprint } from './fingerprint.ts'

/** Pipeline stages in execution order; `done` is the completed verdict. */
export const LOOP_STAGES = ['init', 'align', 'chapters', 'experiments', 'figures', 'review', 'export'] as const

/** One pipeline stage, or `done` when the disclosure is final. */
export type LoopStage = (typeof LOOP_STAGES)[number] | 'done'

/** The eight disclosure chapter files in their canonical order. */
const CHAPTER_FILES = [
  '01-name.md', '02-field.md', '03-background.md', '04-problem.md',
  '05-solution.md', '06-effect.md', '07-key-points.md', '08-drawings.md',
] as const

/**
 * The verification chapter, required only while the project carries real
 * experiment work (a quantified effect chapter or an experiments/ tree): the
 * five-part evidence story — what it targets, the common approach, where it
 * falls short, how this invention solves it, the measured outcome.
 */
const VERIFICATION_FILE = '09-verification.md'

/** A chapter counts as drafted once its trimmed body reaches this length. */
const CHAPTER_MIN_CHARS = 20

/** The default total score a review report must reach before the loop may finish. */
const DEFAULT_REVIEW_THRESHOLD = 80

/** How far the score bar drops while the prior-art search is unreachable. */
const DEGRADED_REVIEW_DELTA = 10

/** The overall score line a review report carries: `总分 81`. */
const REPORT_SCORE = /总分\s*(\d+)/

/** The source-digest stamp a report carries: `> 源指纹：<16 hex chars>`. */
const REPORT_FINGERPRINT = /^> 源指纹：([0-9a-f]{16})/m

/** One revision-list entry: `- **维度**（均分 N，影响 X.Y）：建议`. */
const REVISION_ITEM = /^[-*] \*\*(.+?)\*\*（均分 \d+，影响 [\d.]+）：(.+)$/gm

/** How many revision-list items the review gap names as priorities. */
const REVISION_PRIORITY_COUNT = 3

/**
 * Extract the report's revision list (top items first — the renderer orders
 * by weighted impact) so the gap can name what to fix before the model opens
 * the report.
 * @param report - the report text.
 * @returns up to {@link REVISION_PRIORITY_COUNT} `维度：建议` strings, empty when the section is absent.
 */
function revisionPriorities(report: string | undefined): string[] {
  if (report === undefined) return []
  const section = report.split(/^## 修订清单（按影响排序）\s*$/m)[1]
  if (section === undefined) return []
  const items: string[] = []
  for (const match of section.matchAll(REVISION_ITEM)) {
    items.push(`${match[1]}：${match[2]}`)
    if (items.length >= REVISION_PRIORITY_COUNT) break
  }
  return items
}

/** The degradation marker the research skill writes when the search is unreachable. */
const PRIOR_ART_UNAVAILABLE = /查新不可用/

/** A Chinese publication number in prose or the ledger: `CN117891234A`, `CN 212345678 U`. */
const PUBLICATION_NUMBER = /\bCN\s?\d{7,9}\s?[ABUYS][0-9]?\b/g

/** Normalize a matched number (`CN 117891234 A` → `CN117891234A`) for comparison. */
function normalizePublicationNumber(match: string): string {
  return match.replace(/\s+/g, '').toUpperCase()
}

/** The standing note every directive carries while the prior-art debt is open. */
const PRIOR_ART_DEBT_NOTE = '注意：本项目带着未清偿的查新降级债（审查达标线临时放宽 10 分）——检索通道恢复后按 patent-research 补检索 reference/prior-art.md、删除「查新不可用」标记，并把审查分数审回未放宽的达标线。'

/** One pending requirement found by the assessment pass. */
export interface LoopGap {
  /** The stage whose completion this gap belongs to. */
  stage: LoopStage
  /** Human-readable description of what is missing. */
  detail: string
}

/** The assessor's verdict for one project directory. */
export interface LoopState {
  /** Absolute project directory the assessment ran against. */
  projectRoot: string
  /** Project display name: the manifest `name`, else the directory's basename. */
  projectName: string
  /** Whether a patent project (patent.yml) exists at the root. */
  hasProject: boolean
  /** First incomplete stage in pipeline order; `done` when nothing pends. */
  stage: LoopStage
  /** True only when every pipeline gate passes — the 成稿 verdict. */
  complete: boolean
  /** Every pending requirement in pipeline order (the roadmap, not just the stage). */
  gaps: LoopGap[]
  /** The directive for the current stage: what to do, which skills, which disciplines. */
  directive: string
  /** Skill names to load before executing the current stage. */
  skills: string[]
  /** Whether the current stage may pause for user input (evaluation, interview). */
  mayNeedUser: boolean
  /** Whether the prior-art search is marked unreachable in reference/prior-art.md. */
  priorArtDegraded: boolean
}

/** Whether a path exists. */
async function exists(path: string): Promise<boolean> {
  try {
    await access(path)
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    return false
  }
  return true
}

/** Read a text file, or undefined when missing. */
async function readText(path: string): Promise<string | undefined> {
  try {
    return await readFile(path, 'utf8')
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    return undefined
  }
}

/** Last modification time, or the epoch when the path is missing. */
async function mtimeOf(path: string): Promise<number> {
  try {
    return (await stat(path)).mtimeMs
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    return 0
  }
}

/** The manifest fields other packages key on; the loop itself reads only the threshold. */
export interface PatentManifest {
  name?: string
  status?: string
  reviewThreshold?: number
  reviewPasses?: number
}

/**
 * Parse the manifest fields the plugin keys on (`name`, `status`, the
 * optional `reviewThreshold` score bar, and the optional `reviewPasses`
 * per-dimension scoring-pass count) without pulling in a YAML dependency —
 * patent.yml is model-generated with a flat, known shape.
 * @param root - the project directory.
 * @returns the manifest fields, or undefined when the file is missing.
 */
export async function readManifest(root: string): Promise<PatentManifest | undefined> {
  const text = await readText(join(root, 'patent.yml'))
  if (text === undefined) return undefined
  const fields: PatentManifest = {}
  for (const line of text.split(/\r?\n/)) {
    const match = /^(name|status|reviewThreshold|reviewPasses):\s*(.+?)\s*$/.exec(line)
    const key = match?.[1]
    const value = match?.[2]
    if (key === undefined || value === undefined) continue
    if (key === 'reviewThreshold') {
      const threshold = Number(value)
      if (Number.isFinite(threshold) && threshold >= 0 && threshold <= 100) fields.reviewThreshold = threshold
    } else if (key === 'reviewPasses') {
      const passes = Number(value)
      if (Number.isInteger(passes) && passes >= 1 && passes <= 5) fields.reviewPasses = passes
    } else {
      fields[key as 'name' | 'status'] = value
    }
  }
  return fields
}

/** The five core brief dimensions, their section headings, and Chinese labels. */
const BRIEF_SECTIONS: ReadonlyArray<{ key: string; label: string; headings: string[] }> = [
  { key: 'field', label: '技术领域', headings: ['技术领域'] },
  { key: 'background', label: '背景技术', headings: ['背景技术', '现有技术'] },
  { key: 'problem', label: '技术问题', headings: ['技术问题'] },
  { key: 'solution', label: '发明内容', headings: ['发明内容', '技术方案', '整体方案'] },
  { key: 'effect', label: '有益效果', headings: ['有益效果'] },
]

/**
 * Whether brief.md carries a non-empty section for every core dimension. The
 * brief is free prose, so this is a presence heuristic — an empty heading
 * counts as missing, a thin one still counts (thickness is the interview's
 * job, judged by `patent_brief_coverage`).
 * @param brief - the brief.md text.
 * @returns one gap detail per core dimension missing a non-empty section.
 */
function missingBriefSections(brief: string): string[] {
  return BRIEF_SECTIONS.filter(({ headings }) => {
    const pattern = new RegExp(`^#{1,4}.*(?:${headings.join('|')})`, 'm')
    const index = brief.search(pattern)
    if (index < 0) return true
    const rest = brief.slice(index).replace(pattern, '')
    const nextHeading = rest.search(/^#{1,4}\s/m)
    return (nextHeading < 0 ? rest : rest.slice(0, nextHeading)).trim().length === 0
  }).map(({ label }) => `brief.md 缺少核心维度章节：${label}`)
}

/**
 * Collect the chapter gaps: any of the eight files missing or thinner than
 * the drafted threshold.
 * @param root - the project directory.
 * @returns gap details for the chapter stage, empty when all eight drafted.
 */
async function chapterGaps(root: string): Promise<string[]> {
  const details: string[] = []
  for (const name of CHAPTER_FILES) {
    const body = await readText(join(root, 'chapters', name))
    if (body === undefined) {
      details.push(`缺章节文件 chapters/${name}`)
    } else if (body.trim().length < CHAPTER_MIN_CHARS) {
      details.push(`chapters/${name} 为占位/空白`)
    }
  }
  return details
}

/** A figure declaration line in 08-drawings.md: `图N 为……`. */
const FIGURE_DECLARATION = /图(\d+)\s*[为是]/g

/** A final figure file name at the figures root: `图N.png` or `图N-名称.png`. */
const FIGURE_FILE = /^图(\d+)(?:-.+)?\.png$/i

/** A chapter body counts as quantitative when it carries a number+unit claim. */
const QUANTITATIVE = /[0-9]+(?:\.[0-9]+)?\s*(%|倍|个|次|条|毫秒|ms|s|KB|MB|GB)/

/**
 * Compare the 08-drawings declarations against the figure files that actually
 * sit at the figures root (same naming contract the exporter collects by).
 * @param root - the project directory.
 * @returns missing figure numbers, surplus figure numbers, and whether the
 * drawings chapter plans any figure at all.
 */
async function figureGaps(root: string): Promise<{ missing: number[]; surplus: number[]; planned: boolean }> {
  const drawings = await readText(join(root, 'chapters', '08-drawings.md'))
  const declared = new Set<number>()
  if (drawings !== undefined) {
    for (const match of drawings.matchAll(FIGURE_DECLARATION)) declared.add(Number(match[1]))
  }
  const present = new Set<number>()
  const figuresDir = join(root, 'figures')
  if (await exists(figuresDir)) {
    for (const entry of await readdir(figuresDir, { withFileTypes: true })) {
      const match = FIGURE_FILE.exec(entry.name)
      if (entry.isFile() && match !== null) present.add(Number(match[1]))
    }
  }
  // The documented escape hatch: a project declaring 无附图 in the drawings
  // chapter plans zero figures on purpose — the declaration itself satisfies
  // the planning gate (surplus files on disk still count as mismatches).
  const noFigures = drawings !== undefined && drawings.includes('无附图')
  const missing = [...declared].filter(number => !present.has(number)).sort((a, b) => a - b)
  const surplus = [...present].filter(number => !declared.has(number)).sort((a, b) => a - b)
  return { missing, surplus, planned: declared.size > 0 || noFigures }
}

/** A figure reference in prose: `见图5` / `如图3所示` — the digits must be declared. */
const FIGURE_REFERENCE = /图(\d+)/g

/**
 * Collect figure numbers the prose references outside the drawings chapter.
 * A reference to a number 08-drawings never declares means the prose and the
 * figure plan have drifted (typically after renumbering).
 * @param root - the project directory.
 * @param declared - the figure numbers 08-drawings.md declares.
 * @returns referenced-but-undeclared figure numbers, in first-seen order.
 */
async function undeclaredReferences(root: string, declared: Set<number>): Promise<number[]> {
  const chaptersDir = join(root, 'chapters')
  if (!await exists(chaptersDir)) return []
  const unseen: number[] = []
  for (const entry of (await readdir(chaptersDir)).sort()) {
    if (!entry.endsWith('.md') || entry === '08-drawings.md') continue
    const body = await readText(join(chaptersDir, entry))
    if (body === undefined) continue
    for (const match of body.matchAll(FIGURE_REFERENCE)) {
      const number = Number(match[1])
      if (!declared.has(number) && !unseen.includes(number)) unseen.push(number)
    }
  }
  return unseen
}

/**
 * Compare the publication numbers the prose cites against the prior-art
 * ledger. Every 公开号 in brief.md or chapters/ must trace to an entry in
 * reference/prior-art.md — the recorded search results — so a cited number
 * the ledger never saw (typically written from memory) stays a chapters-stage
 * gap instead of reaching the review with an untraceable citation.
 * @param root - the project directory.
 * @returns the prior-art gap details, empty when every citation is ledgered
 * (or nothing cites a publication number at all).
 */
async function priorArtGaps(root: string): Promise<string[]> {
  const cited = new Set<string>()
  const files = [join(root, 'brief.md')]
  const chaptersDir = join(root, 'chapters')
  if (await exists(chaptersDir)) {
    for (const entry of (await readdir(chaptersDir)).sort()) {
      if (entry.endsWith('.md')) files.push(join(chaptersDir, entry))
    }
  }
  for (const path of files) {
    const body = await readText(path)
    if (body === undefined) continue
    for (const match of body.matchAll(PUBLICATION_NUMBER)) cited.add(normalizePublicationNumber(match[0]))
  }
  if (cited.size === 0) return []
  const ledger = await readText(join(root, 'reference', 'prior-art.md'))
  if (ledger === undefined) {
    return ['正文引用了公开号，但 reference/prior-art.md（出处账本）不存在——按 patent-research 技能把检索到的对比文件逐条记入账本']
  }
  const recorded = new Set([...ledger.matchAll(PUBLICATION_NUMBER)].map(match => normalizePublicationNumber(match[0])))
  const missing = [...cited].filter(number => !recorded.has(number))
  if (missing.length > 0) {
    return [`正文引用的公开号未见于 reference/prior-art.md：${missing.join('、')}——按 patent-research 技能检索核实后记入账本；检索不到佐证的引用从正文删除，禁止凭记忆写号`]
  }
  return []
}

/**
 * Whether the experiments stage is satisfied: a run log exists under any
 * experiment directory (official numbers recorded), or the project declared
 * experiments not applicable via `experiments/README.md`.
 * @param root - the project directory.
 * @returns the unmet experiments requirement, or undefined when satisfied.
 */
async function experimentsGap(root: string): Promise<string | undefined> {
  const experimentsDir = join(root, 'experiments')
  if (await exists(experimentsDir)) {
    for (const entry of await readdir(experimentsDir, { withFileTypes: true })) {
      if (entry.isDirectory() && await exists(join(experimentsDir, entry.name, 'results', 'run-log.md'))) return undefined
    }
  }
  const readme = await readText(join(experimentsDir, 'README.md'))
  if (readme !== undefined && /无需实验|不适用/.test(readme)) return undefined
  return 'experiments/ 下既无任何 results/run-log.md（正式运行记录）也无"无需实验"声明'
}

/** Whether the experiments tree exists with anything in it. */
async function experimentsPresent(root: string): Promise<boolean> {
  const experimentsDir = join(root, 'experiments')
  if (!await exists(experimentsDir)) return false
  return (await readdir(experimentsDir)).length > 0
}

/**
 * The verification chapter's own gate: a project with real experiment work
 * (quantified effects or an experiments/ tree) must carry
 * chapters/09-verification.md — the disclosure's evidence story. Drafted
 * like any other chapter: present and beyond the placeholder threshold.
 * @param root - the project directory.
 * @param required - whether the project carries experiment work at all.
 * @returns the verification gap details, empty when satisfied or N/A.
 */
async function verificationGaps(root: string, required: boolean): Promise<string[]> {
  if (!required) return []
  const body = await readText(join(root, 'chapters', VERIFICATION_FILE))
  if (body === undefined) {
    return [`缺章节文件 chapters/${VERIFICATION_FILE}（实验验证章）——按 patent-chapters 的五要素结构撰写：针对什么事情、普遍的解决方式、遇到的问题、本专利如何解决、解决效果`]
  }
  if (body.trim().length < CHAPTER_MIN_CHARS) return [`chapters/${VERIFICATION_FILE} 为占位/空白`]
  return []
}

/**
 * Whether the review stage is satisfied: at least one rubric report file in
 * review/.
 * @param root - the project directory.
 * @returns the unmet review requirement, or undefined when satisfied.
 */
/** The newest source mtime the review and export gates measure freshness against. */
async function newestSourceTime(root: string): Promise<number> {
  let newest = 0
  for (const dir of ['chapters', 'figures']) {
    const dirPath = join(root, dir)
    if (!await exists(dirPath)) continue
    for (const entry of await readdir(dirPath, { withFileTypes: true })) {
      if (!entry.isFile()) continue
      newest = Math.max(newest, await mtimeOf(join(dirPath, entry.name)))
    }
  }
  return Math.max(newest, await mtimeOf(join(root, 'brief.md')))
}

/**
 * Whether the review stage is satisfied: the NEWEST rubric report is a
 * whole-project review (stamped `审查范围：整项`; older reports without the
 * stamp pass permissively) whose parsed total score reaches the effective
 * threshold, and which is not older than the sources it reviewed. On top of
 * that, the attempt ledger escalates: after repeated below-threshold
 * re-reviews with stalling gains, the gate stops asking for another
 * re-review and tells the model to put the decision in the user's hands.
 * @param root - the project directory.
 * @param effectiveThreshold - the score bar after any degradation relaxation.
 * @param degraded - whether the prior-art marker relaxed the threshold.
 * @returns the unmet review requirement, or undefined when satisfied.
 */
async function reviewGap(root: string, effectiveThreshold: number, degraded: boolean): Promise<string | undefined> {
  const reviewDir = join(root, 'review')
  if (!await exists(reviewDir)) return 'review/ 不存在——还没跑过确定性审查'
  const reports = (await readdir(reviewDir)).filter(name => name.endsWith('.review.md'))
  if (reports.length === 0) return 'review/ 下没有任何 *.review.md 审查报告'
  const timed = await Promise.all(reports.map(async name => ({ name, time: await mtimeOf(join(reviewDir, name)) })))
  timed.sort((a, b) => b.time - a.time)
  const latest = timed[0]
  if (latest === undefined) return 'review/ 下没有任何 *.review.md 审查报告'
  const content = await readText(join(reviewDir, latest.name))
  const score = parseReportScore(content)
  if (score === undefined) return `最新审查报告 ${latest.name} 缺少可解析的总分——重跑审查`
  if (/审查范围：部分/.test(content ?? '')) {
    return `最新审查报告只覆盖了局部目标（${latest.name}）——审查整个项目（目标用 "."）后重审，局部报告不作为整项达标的依据`
  }
  // Freshness prefers the stamped source digest — it survives git checkouts
  // and syncs that rewrite mtimes; reports without a stamp (legacy) fall back
  // to the mtime comparison.
  const stamped = REPORT_FINGERPRINT.exec(content ?? '')?.[1]
  if (stamped !== undefined) {
    if (await sourceFingerprint(root) !== stamped) {
      return `最新审查报告（总分 ${score}）的源指纹与当前源文件不符——审查之后源文件已变动，需要重审`
    }
  } else {
    const sourceTime = await newestSourceTime(root)
    if (latest.time < sourceTime) return `最新审查报告（总分 ${score}）早于源文件的最新修改（旧报告无源指纹，按修改时间判定）——内容已变，需要重审`
  }
  const stall = await stalledReview(reviewDir, effectiveThreshold)
  if (stall !== undefined) return stall
  if (score < effectiveThreshold) {
    const priorities = revisionPriorities(content)
    const priority = priorities.length > 0 ? `；优先修订：${priorities.join('；')}` : ''
    return `最新审查总分 ${score} 低于达标线 ${effectiveThreshold}${degraded ? '（查新不可用，已放宽 10 分）' : ''}——对照报告修订清单逐维度修订后重审${priority}`
  }
  return undefined
}

/**
 * Detect convergence stall in the attempt ledger: a trailing run of
 * below-threshold whole-project attempts long enough (three, or two with a
 * gain under three points) that another automatic re-review would just burn
 * tokens. The escape is the user's decision — lowering `reviewThreshold`
 * below the latest score, or resetting the ledger — both machine-visible.
 * @param reviewDir - the review directory holding attempts.md.
 * @param threshold - the effective score bar the attempts are judged against.
 * @returns the escalation message, or undefined while attempts are still converging.
 */
async function stalledReview(reviewDir: string, threshold: number): Promise<string | undefined> {
  const ledger = await readText(join(reviewDir, 'attempts.md'))
  if (ledger === undefined) return undefined
  const scores = [...ledger.matchAll(/总分 (\d+)/g)]
    .map(match => Number(match[1]))
    .slice(-6)
  // Only the trailing run of below-threshold attempts matters; a passing
  // attempt resets the count by definition.
  const below: number[] = []
  for (const score of reversed(scores)) {
    if (score >= threshold) break
    below.unshift(score)
  }
  const latestScore = below.at(-1)
  const firstScore = below[0]
  const gained = latestScore !== undefined && firstScore !== undefined && latestScore - firstScore >= 3
  const stalled = below.length >= 3 || (below.length === 2 && !gained)
  if (!stalled) return undefined
  return `已连续 ${below.length} 次重审未达线（${below.join(' → ')}，达标线 ${threshold}）且分数增益停滞——停止自动重审，向用户汇报并请求决策：调低 patent.yml 的 reviewThreshold（低于最新分 ${latestScore ?? 0} 即放行），或删除 review/attempts.md 重置计数后继续修订`
}

/** Iterate an array last-to-first without mutating it. */
function* reversed<T>(items: T[]): Iterable<T> {
  for (let index = items.length - 1; index >= 0; index--) yield items[index] as T
}

/**
 * Parse the report's overall score line.
 * @param report - the report text.
 * @returns the parsed score, or undefined when the line is absent.
 */
function parseReportScore(report: string | undefined): number | undefined {
  if (report === undefined) return undefined
  const match = REPORT_SCORE.exec(report)
  const score = match?.[1]
  return score === undefined ? undefined : Number(score)
}

/**
 * Whether the export stage is satisfied: a disclosure docx exists in exports/
 * and is not older than any source it projects (brief, chapters, figures).
 * @param root - the project directory.
 * @returns the unmet export requirement, or undefined when satisfied.
 */
async function exportGap(root: string): Promise<string | undefined> {
  const exportsDir = join(root, 'exports')
  if (!await exists(exportsDir)) return 'exports/ 不存在——交底书从未导出'
  const exported = (await readdir(exportsDir)).filter(name => name.endsWith('-交底书.docx'))
  if (exported.length === 0) return 'exports/ 下没有 *-交底书.docx'
  const latest = exported[exported.length - 1]
  if (latest === undefined) return 'exports/ 下没有 *-交底书.docx'
  // The exporter stamps a source digest beside each docx; when present it is
  // the freshness verdict (mtime stays the fallback for legacy exports).
  const sidecar = await readText(join(exportsDir, latest.replace(/\.docx$/, '.fingerprint')))
  if (sidecar !== undefined) {
    if (await sourceFingerprint(root) !== sidecar.trim()) {
      return `导出物 ${latest} 的源指纹与当前源文件不符——导出之后源文件已变动，改源后调 export_disclosure 重新导出`
    }
    return undefined
  }
  const exportTime = await mtimeOf(join(exportsDir, latest))
  if (exportTime < await newestSourceTime(root)) return `导出物 ${latest} 早于源文件的最新修改（需要重新导出）`
  return undefined
}

/** Per-stage directive: what to do, which skills, and the hard disciplines. */
const STAGE_DIRECTIVES: Readonly<Record<Exclude<LoopStage, 'done'>, { directive: string; skills: string[]; mayNeedUser: boolean }>> = {
  init: {
    directive: '这是一个新项目起点。加载 patent-init 技能：先按其点子评估程序拆 2~3 个核心技术特征，用 search_cn_patents 检索现有专利并用 web_fetch 读最接近几篇的明细，形成三档结论（建议写/收窄后写/不建议写，附公开号证据）与用户对话定方向；用户确认后按建档约定建立 patent.yml + brief.md（开头是评估节）。'
      + '评估结论需要用户拍板——把判断和证据摆到桌面并直接提问，不要替用户决定。',
    skills: ['patent-init', 'patent-research'],
    mayNeedUser: true,
  },
  align: {
    directive: '五方对齐摘要未就绪。加载 patent-init 技能的访谈程序：一次聚焦一两个维度、用具体封闭的问题逐轮向用户提问；每轮把已收集内容传 patent_brief_coverage 检查，缺点维度按 patent-research 滚动查新校准。'
      + '访谈答案必须来自用户——把问题抛给用户并等待回答，禁止编造；ready=true 后向用户复述五方内容确认，再写定 brief.md。',
    skills: ['patent-init', 'patent-research'],
    mayNeedUser: true,
  },
  chapters: {
    directive: '章节未齐。加载 patent-chapters 技能，按 brief.md 撰写缺失章节；正文应用 patent-de-ai 与 patent-writing-quality，有益效果章应用 patent-effect-contrast；章节只保留正文，起草注释进会话或 review/。'
      + '涉及实验或量化效果的项目同时撰写 chapters/09-verification.md 实验验证章（五要素：针对什么事情、普遍的解决方式、遇到的问题、本专利如何解决、解决效果——效果数据待实验转正后回填，先成章）。',
    skills: ['patent-chapters', 'patent-de-ai', 'patent-writing-quality', 'patent-effect-contrast'],
    mayNeedUser: false,
  },
  experiments: {
    directive: '有益效果章含量化数据，但 experiments/ 缺少正式运行记录。加载 patent-experiment 技能：公开数据集优先、无公开集按真实场景标定仿真；正式出数一律 run_experiment 工具（docker），进正文的结果数据必须配结果图（出图脚本入实验目录，黑白、中文标注、subagent 验收）。'
      + '实验转正后把结果与关键数字回填 chapters/09-verification.md 实验验证章——章里引用的每个数字都能溯源到一条运行记录。'
      + '确认本项目无需实验时，在 experiments/README.md 写明「无需实验：<理由>」后继续。',
    skills: ['patent-experiment'],
    mayNeedUser: false,
  },
  figures: {
    directive: '附图未齐。加载 patent-figure-design 技能：黑白极简、总图先行、图类形态互不混淆、图内无图号；源文件进 figures/source/，渲染后成品落 figures/ 根。'
      + '每张图渲染后必须派 subagent 用 read_image 按检查单验收（线不交叉不重叠不贴框、箭头正确、不压字），不合格改源重渲，通过才保留——自查不算验收。实验结果图经 patent-experiment 出图后定稿复制进 figures/ 根。',
    skills: ['patent-figure-design'],
    mayNeedUser: false,
  },
  review: {
    directive: '审查未达标（最新报告总分低于达标线，或还没有报告）。确认审查目标（项目目录用 "."）后直接调用 patent_review 工具跑确定性七维审查，报告写入 review/；自己不评分、不手写审查文件。对照报告把失分维度逐条修订到源文件，再重审到达标线为止；查新通道不可用导致阈值放宽时，按 patent-research 在 reference/prior-art.md 留「查新不可用：原因，待补查」标记，网络恢复后补查、删除标记并把分数审回原达标线。',
    skills: ['patent-review'],
    mayNeedUser: false,
  },
  export: {
    directive: '交底书导出物缺失或已落后于源文件。加载 patent-services 技能：调 export_disclosure 重新导出（更新内容一律改源后重导，不手改 docx），核对返回的「内嵌附图 N 张」与 08 章声明条数一致；顺带把 patent.yml 的 status 推进到对应阶段（review）。',
    skills: ['patent-services'],
    mayNeedUser: false,
  },
}

/** The completed-stage directive: deliver, and stop looping. */
const DONE_DIRECTIVE = '项目已成稿：交底书导出物存在且不落后于源文件、附图齐全、审查报告在 review/。向用户交付导出物路径与要点摘要，结束循环；用户明确要求推进申请文件时才走 patent-claims 与 patent-application。'

/**
 * Run one assessment pass over a project directory and produce the loop
 * state: the first incomplete stage, the full pending roadmap, and the
 * current stage's directive. Every verdict is a disk fact — a stage the
 * model believes finished but whose artifacts are missing stays pending.
 * @param projectDir - the project directory (resolved against the caller).
 * @returns the loop state; `complete` is true only when every gate passes.
 */
export async function assessLoopState(projectDir: string): Promise<LoopState> {
  const root = resolve(projectDir)
  const manifest = await readManifest(root)
  const gaps: LoopGap[] = []
  const projectName = manifest?.name ?? basename(root)
  const priorArt = await readText(join(root, 'reference', 'prior-art.md'))
  const degraded = priorArt !== undefined && PRIOR_ART_UNAVAILABLE.test(priorArt)
  const configuredThreshold = manifest?.reviewThreshold ?? DEFAULT_REVIEW_THRESHOLD
  const effectiveThreshold = degraded
    ? Math.max(0, configuredThreshold - DEGRADED_REVIEW_DELTA)
    : configuredThreshold

  if (manifest === undefined) {
    gaps.push({ stage: 'init', detail: '无 patent.yml——项目未建档' })
  } else {
    const brief = await readText(join(root, 'brief.md'))
    if (brief === undefined) {
      gaps.push({ stage: 'align', detail: '缺 brief.md——五方对齐摘要未建档' })
    } else {
      for (const detail of missingBriefSections(brief)) gaps.push({ stage: 'align', detail })
    }
    for (const detail of await chapterGaps(root)) gaps.push({ stage: 'chapters', detail })
    for (const detail of await priorArtGaps(root)) gaps.push({ stage: 'chapters', detail })
    const effect = await readText(join(root, 'chapters', '06-effect.md'))
    const quantified = effect !== undefined && QUANTITATIVE.test(effect)
    // The verification chapter is a chapters-stage gate and precedes the
    // experiments stage in pipeline order, so it slots in before the run-log
    // requirement: the evidence story gets drafted with the chapters, then
    // the experiment numbers fill it in.
    for (const detail of await verificationGaps(root, quantified || await experimentsPresent(root))) {
      gaps.push({ stage: 'chapters', detail })
    }
    if (quantified) {
      const experiments = await experimentsGap(root)
      if (experiments !== undefined) gaps.push({ stage: 'experiments', detail: experiments })
    }
    const figures = await figureGaps(root)
    if (!figures.planned) {
      gaps.push({ stage: 'figures', detail: '08-drawings.md 未声明任何「图N 为…」——附图尚未规划' })
    }
    if (figures.missing.length > 0) {
      gaps.push({ stage: 'figures', detail: `声明了附图但 figures/ 根缺成品：图${figures.missing.join('、图')}（文件须命名 图N.png 或 图N-名称.png）` })
    }
    if (figures.surplus.length > 0) {
      gaps.push({ stage: 'figures', detail: `figures/ 根有未在 08 章声明的成品：图${figures.surplus.join('、图')}（补声明或移除）` })
    }
    const declared = new Set<number>()
    const drawings = await readText(join(root, 'chapters', '08-drawings.md'))
    if (drawings !== undefined) {
      for (const match of drawings.matchAll(FIGURE_DECLARATION)) declared.add(Number(match[1]))
    }
    for (const number of await undeclaredReferences(root, declared)) {
      gaps.push({ stage: 'figures', detail: `正文引用了图${number}，但 08 章未声明——补声明或修正正文引用` })
    }
    const review = await reviewGap(root, effectiveThreshold, degraded)
    if (review !== undefined) gaps.push({ stage: 'review', detail: review })
    const disclosure = await exportGap(root)
    if (disclosure !== undefined) gaps.push({ stage: 'export', detail: disclosure })
  }

  const stage: LoopStage = gaps[0]?.stage ?? 'done'
  const current = stage === 'done'
    ? { directive: DONE_DIRECTIVE, skills: [] as string[], mayNeedUser: false }
    : STAGE_DIRECTIVES[stage]
  // The relaxed-threshold debt follows the project through every stage —
  // including done, where a delivered disclosure would otherwise present
  // itself as fully clean while the prior-art search never actually ran.
  const directive = degraded ? `${current.directive}\n${PRIOR_ART_DEBT_NOTE}` : current.directive
  return {
    projectRoot: root,
    projectName,
    hasProject: manifest !== undefined,
    stage,
    complete: stage === 'done',
    gaps,
    directive,
    skills: current.skills,
    mayNeedUser: current.mayNeedUser,
    priorArtDegraded: degraded,
  }
}
