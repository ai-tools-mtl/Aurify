/**
 * The patent project overview's view model: raw workspace listings and the
 * patent.yml first page become the sections the dashboard tab draws. Pure
 * and synchronous — the body performs the reads, this derives the display.
 * @module
 */

import type { DirectoryListing } from './patent-face.ts'

/** One file entry as the overview lists it. */
export interface ProjectFile {
  readonly name: string
  readonly size?: number
}

/**
 * The pipeline stage the disk facts point at. Presence-based coarse read for
 * the dashboard only — freshness/fingerprint gates stay the patent_loop
 * tool's authority, so `ready` means "nothing pends on presence", not the
 * 成稿 verdict.
 */
export type LoopStageGuess = 'align' | 'chapters' | 'experiments' | 'figures' | 'review' | 'export' | 'ready'

/** One review report's parsed verdict, as the dashboard shows it. */
export interface ReviewReportView {
  readonly name: string
  /** The parsed `总分`, or null when the first page carries none. */
  readonly score: number | null
  /** The report stamps itself as a partial-target review. */
  readonly partial: boolean
  /** A whole-project report whose score clears the effective threshold. */
  readonly passing: boolean
}

/** The dashboard's coarse pipeline summary. */
export interface LoopSummary {
  readonly stage: LoopStageGuess
  /** The effective score bar (reviewThreshold override, minus the degraded relaxation). */
  readonly threshold: number
  /** reference/prior-art.md carries the 查新不可用 marker. */
  readonly degraded: boolean
  readonly reports: readonly ReviewReportView[]
}

/** The whole dashboard's display state. */
export interface ProjectView {
  /** The workspace holds a patent project (patent.yml or the chapter layout present). */
  readonly isProject: boolean
  /** patent.yml's `name` field, best-effort. */
  readonly projectName: string | null
  /** patent.yml's `status` field, best-effort. */
  readonly projectStatus: string | null
  /** brief.md exists at the root. */
  readonly brief: boolean
  /** The chapter files in chapter order: the fixed eight, plus 09-verification.md while the project carries experiment work. */
  readonly chapters: readonly ProjectFile[]
  /** draftedCount: present chapters with content; total: the fixed eight, plus one while the verification chapter is required. */
  readonly drafted: number
  readonly total: number
  /** Application documents present under application/. */
  readonly application: { readonly claims: boolean; readonly description: boolean; readonly abstract: boolean }
  /** Review reports (.md) under review/, by name. */
  readonly review: readonly string[]
  /** Final figure images (.png) at the figures/ root, in name order, each with its 08-drawings caption when one matches. */
  readonly figures: readonly { readonly name: string; readonly caption: string | null }[]
  /** The coarse pipeline summary derived from the second-phase reads. */
  readonly loop: LoopSummary
}

/**
 * Second-phase reads the loop summary consumes. Every field is optional —
 * the panel degrades to presence-only facts when a read failed or was
 * skipped, never blocking the dashboard on one missing file.
 */
export interface ProjectExtras {
  readonly briefText?: string | null
  readonly effectText?: string | null
  readonly priorArtText?: string | null
  readonly experimentsReadmeText?: string | null
  /** Whether each experiments/ subdirectory carries results/run-log.md (body-resolved, capped). */
  readonly experimentRunLogs?: readonly boolean[]
  readonly exportsListing?: DirectoryListing | null
  /** First-page texts of the newest *.review.md reports (body-resolved, capped). */
  readonly reportTexts?: readonly { readonly name: string; readonly text: string | null }[]
}

const CHAPTER_TOTAL = 8

/** The verification chapter, shown and counted only while experiment work requires it (mirror of loop.ts). */
const VERIFICATION_FILE = '09-verification.md'

/** One 附图说明 caption line: `图1 为本发明所述方法的流程总览图；` */
const FIGURE_CAPTION = /图(\d+)\s*[为是][:：]?\s*([^；。\n]+)/gu

/**
 * Pair each final figure png with its caption from the 08-drawings chapter.
 * @param figures - the figures/ listing; null when absent.
 * @param drawingsText - chapters/08-drawings.md's first page; null when unread.
 * @returns png entries in name order with captions where one matches.
 */
function buildFigures(figures: DirectoryListing | null, drawingsText: string | null): { name: string; caption: string | null }[] {
  const captions = new Map<string, string>()
  if (drawingsText !== null) {
    for (const match of drawingsText.matchAll(FIGURE_CAPTION)) {
      const name = `图${match[1]}.png`
      if (!captions.has(name)) captions.set(name, (match[2] ?? '').trim())
    }
  }
  return fileNames(figures, '.png').map(name => ({ name, caption: captions.get(name) ?? null }))
}

/** Entries of one listing: files only, by name. */
function fileNames(listing: DirectoryListing | null, suffix = ''): string[] {
  if (listing === null) return []
  return listing.entries
    .filter(entry => entry.type === 'file' && entry.name.toLowerCase().endsWith(suffix))
    .map(entry => entry.name)
}

/**
 * The loop assessor's rules re-derived for the dashboard. These mirrors of
 * `@mtl-academic/dsh-tool-patent/loop` stay presence-based (the client has no
 * file bytes, only first pages) and never claim the 成稿 verdict — the
 * patent_loop tool remains the authority. Keep the two in step by comment.
 */

/** The five core brief dimensions and their headings (mirror of loop.ts). */
const BRIEF_HEADINGS: readonly (readonly string[])[] = [
  ['技术领域'], ['背景技术', '现有技术'], ['技术问题'], ['发明内容', '技术方案', '整体方案'], ['有益效果'],
]

/** A chapter body counts as quantitative when it carries a number+unit claim (mirror of loop.ts). */
const QUANTITATIVE = /[0-9]+(?:\.[0-9]+)?\s*(%|倍|个|次|条|毫秒|ms|s|KB|MB|GB)/

/** A final figure file at the figures root: `图N.png` or `图N-名称.png` (mirror of loop.ts). */
const FIGURE_FILE = /^图(\d+)(?:-.+)?\.png$/i

/** The degradation marker in reference/prior-art.md (mirror of loop.ts). */
const PRIOR_ART_UNAVAILABLE = /查新不可用/

/** The default review score bar (mirror of loop.ts; patent.yml reviewThreshold overrides). */
const DEFAULT_THRESHOLD = 80

/** How far the bar drops while the prior-art search is marked unreachable (mirror of loop.ts). */
const DEGRADED_DELTA = 10

/**
 * Derive the coarse pipeline summary from the listings and the second-phase
 * texts: the first stage whose presence-based gate fails, the effective
 * threshold, and the parsed review verdicts.
 * @param view inputs - the listings already gathered, plus the optional extras.
 * @returns the loop summary.
 */
function buildLoopSummary(
  draftedCount: number,
  chapterTotal: number,
  briefText: string | null | undefined,
  effectText: string | null | undefined,
  drawingsText: string | null,
  figuresListing: DirectoryListing | null,
  experimentsReadmeText: string | null | undefined,
  experimentRunLogs: readonly boolean[] | undefined,
  exportsListing: DirectoryListing | null,
  patentYml: string | null,
  priorArtText: string | null | undefined,
  reportTexts: readonly { readonly name: string; readonly text: string | null }[] | undefined,
): LoopSummary {
  const thresholdMatch = patentYml === null ? null : /^reviewThreshold:\s*(\d+)\s*$/mu.exec(patentYml)
  const configured = thresholdMatch === null || thresholdMatch[1] === undefined
    ? DEFAULT_THRESHOLD
    : Math.min(100, Math.max(0, Number(thresholdMatch[1])))
  const degraded = priorArtText !== undefined && priorArtText !== null && PRIOR_ART_UNAVAILABLE.test(priorArtText)
  const threshold = degraded ? Math.max(0, configured - DEGRADED_DELTA) : configured

  const declared = new Set<string>()
  if (drawingsText !== null) {
    for (const match of drawingsText.matchAll(FIGURE_CAPTION)) {
      const number = match[1]
      if (number !== undefined) declared.add(number)
    }
  }
  const present = new Set<string>()
  for (const name of fileNames(figuresListing, '.png')) {
    const match = FIGURE_FILE.exec(name)
    const number = match?.[1]
    if (number !== undefined) present.add(number)
  }
  const noFigures = drawingsText !== null && drawingsText.includes('无附图')

  const reports = (reportTexts ?? []).map(({ name, text }) => {
    const scoreMatch = text === null ? undefined : /总分\s*(\d+)/.exec(text)
    const score = scoreMatch?.[1] === undefined ? null : Number(scoreMatch[1])
    const partial = text !== null && text.includes('审查范围：部分')
    return { name, score, partial, passing: !partial && score !== null && score >= threshold }
  })

  const briefAligned = briefText === null || briefText === undefined
    ? false
    : BRIEF_HEADINGS.every(headings => headings.some(heading => briefText.includes(heading)))
  const quantitative = effectText !== null && effectText !== undefined && QUANTITATIVE.test(effectText)
  const experimentsOff = experimentsReadmeText !== null && experimentsReadmeText !== undefined
    && /无需实验|不适用/.test(experimentsReadmeText)
  const experimentsDone = !quantitative
    || experimentsOff
    || (experimentRunLogs !== undefined && experimentRunLogs.some(Boolean))
  const figuresDone = (declared.size > 0 || noFigures)
    && [...declared].every(number => present.has(number))
    && [...present].every(number => declared.has(number))
  const reviewDone = reports.some(report => report.passing)
  const exportDone = fileNames(exportsListing, '.docx').some(name => name.endsWith('-交底书.docx'))

  const stage: LoopStageGuess = !briefAligned
    ? 'align'
    : draftedCount < chapterTotal
      ? 'chapters'
      : !experimentsDone
        ? 'experiments'
        : !figuresDone
          ? 'figures'
          : !reviewDone
            ? 'review'
            : !exportDone
              ? 'export'
              : 'ready'
  return { stage, threshold, degraded, reports }
}

/**
 * Derive the dashboard sections from the workspace listings and patent.yml's first page.
 * @param root - the workspace root listing; null when it could not be read.
 * @param chapters - the chapters/ listing; null when the directory is absent.
 * @param review - the review/ listing; null when absent.
 * @param figures - the figures/ listing; null when absent.
 * @param application - the application/ listing; null when absent.
 * @param patentYml - patent.yml's first page text; null when the file is absent.
 * @param drawingsText - chapters/08-drawings.md's first page, for figure captions; null when absent.
 * @param extras - second-phase reads for the loop summary; every field optional.
 * @returns the display state.
 */
export function buildProjectView(
  root: DirectoryListing | null,
  chapters: DirectoryListing | null,
  review: DirectoryListing | null,
  figures: DirectoryListing | null,
  application: DirectoryListing | null,
  patentYml: string | null,
  drawingsText: string | null = null,
  extras: ProjectExtras = {},
): ProjectView {
  const rootNames = new Set((root?.entries ?? []).map(entry => entry.name))
  const isProject = rootNames.has('patent.yml') || rootNames.has('chapters')
  const listed = (chapters?.entries ?? [])
    .filter(entry => entry.type === 'file' && entry.name.toLowerCase().endsWith('.md'))
    .map(entry => (entry.size === undefined ? { name: entry.name } : { name: entry.name, size: entry.size }))
  // The verification chapter is conditional (mirror of loop.ts): it joins the
  // fixed eight only when the project carries experiment work — quantified
  // effects, or the chapter itself already present.
  const verification = listed.find(file => file.name === VERIFICATION_FILE)
  const chapterFiles = verification === undefined
    ? listed.slice(0, CHAPTER_TOTAL)
    : [...listed.filter(file => file.name !== VERIFICATION_FILE).slice(0, CHAPTER_TOTAL), verification]
  const quantitative = extras.effectText !== undefined && extras.effectText !== null && QUANTITATIVE.test(extras.effectText)
  const total = quantitative || verification !== undefined ? CHAPTER_TOTAL + 1 : CHAPTER_TOTAL
  const drafted = chapterFiles.filter(file => (file.size ?? 0) > 0).length
  const applicationNames = new Set(fileNames(application, '.md'))
  const statusMatch = patentYml === null ? null : /^status:\s*["']?([\w-]+)["']?\s*$/mu.exec(patentYml)
  const nameMatch = patentYml === null ? null : /^name:\s*["']?(.+?)["']?\s*$/mu.exec(patentYml)
  return {
    isProject,
    projectName: nameMatch?.[1] ?? null,
    projectStatus: statusMatch?.[1] ?? null,
    brief: rootNames.has('brief.md'),
    chapters: chapterFiles,
    drafted,
    total,
    application: {
      claims: applicationNames.has('claims.md'),
      description: applicationNames.has('description.md'),
      abstract: applicationNames.has('abstract.md'),
    },
    review: fileNames(review, '.md'),
    figures: buildFigures(figures, drawingsText),
    loop: buildLoopSummary(
      drafted,
      total,
      extras.briefText,
      extras.effectText,
      drawingsText,
      figures,
      extras.experimentsReadmeText,
      extras.experimentRunLogs,
      extras.exportsListing ?? null,
      patentYml,
      extras.priorArtText,
      extras.reportTexts,
    ),
  }
}
