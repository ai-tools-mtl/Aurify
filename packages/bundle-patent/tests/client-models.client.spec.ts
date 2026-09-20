/** Tests for the patent client card models: meta path, text fallback, running preview. */

import { describe, expect, it } from 'vitest'
import { buildProjectView } from '../src/client/project-model.ts'
import { coverageView, lintView, parseCoverageText, type ToolBlockLike } from '../src/client/models.ts'

function listing(entries: { name: string; type: 'file' | 'directory'; size?: number }[]) {
  return { entries }
}

const READY_TEXT = 'Brief coverage 5/5 (all five core dimensions covered). '
  + 'Alignment counts background/problem/effect = 2/2/2, aligned within tolerance 1. '
  + 'READY: write brief.md and the chapter files, then start drafting.'

const MISSING_TEXT = 'Brief coverage 3/5 (missing: 背景技术 (background), 技术问题 (problem)). '
  + 'Alignment counts background/problem/effect = 2/0/1, NOT aligned (spread 2 exceeds tolerance 1). '
  + 'NOT ready: keep asking for the missing dimensions before drafting.'

const LINT_TEXT = 'Claims 5 (2 independent, 3 dependent), 2 errors, 1 warnings. '
  + '[C1] claim 3 编号不连续 | [C5] claim 1 缺少其特征在于 | [A1] 摘要超出 300 字上限 FAIL: fix the C/A-rule errors before export.'

function settled(content: string, meta?: unknown): ToolBlockLike {
  return {
    callId: 'call-1',
    kind: 'tool-result',
    call: { name: 'x', argsRaw: '{}' },
    content: [{ type: 'text', text: content }],
    isError: false,
    meta,
  }
}

describe('coverageView', () => {
  it('prefers the persisted presentation meta when present', () => {
    const meta = {
      covered: ['field', 'background', 'problem', 'solution', 'effect'],
      missing: [],
      ready: true,
      coreFilled: { done: 5, total: 5 },
      aligned: true,
      alignmentCounts: { background: 2, problem: 2, effect: 2 },
    }
    const view = coverageView(settled(READY_TEXT, meta))
    expect(view.state).toBe('ok')
    expect(view.meta).toEqual(meta)
  })

  it('parses the rendered text when the session carries no meta', () => {
    const view = coverageView(settled(MISSING_TEXT))
    expect(view.meta).not.toBeNull()
    expect(view.meta?.coreFilled).toEqual({ done: 3, total: 5 })
    expect(view.meta?.missing).toEqual(['background', 'problem'])
    expect(view.meta?.ready).toBe(false)
    expect(view.meta?.aligned).toBe(false)
    expect(view.meta?.alignmentCounts).toEqual({ background: 2, problem: 0, effect: 1 })
  })

  it('parses the ready render text', () => {
    const view = coverageView(settled(READY_TEXT))
    expect(view.meta?.ready).toBe(true)
    expect(view.meta?.missing).toEqual([])
    expect(view.meta?.aligned).toBe(true)
  })

  it('keeps the raw text reachable when the render text drifts', () => {
    const view = coverageView(settled('a completely different shape'))
    expect(view.meta).toBeNull()
    expect(view.text).toBe('a completely different shape')
  })

  it('previews submitted core dimensions while running', () => {
    const view = coverageView({
      callId: 'call-1',
      argsRaw: JSON.stringify({ field: '机械', background: '现有技术', effect: '' }),
    })
    expect(view.state).toBe('running')
    expect(view.submitted).toEqual(['field', 'background'])
  })
})

describe('lintView', () => {
  it('prefers the persisted presentation meta when present', () => {
    const meta = {
      summary: { total: 5, independent: 2, dependent: 3, errors: 0, warnings: 1 },
      violations: [{ rule: 'C5', claim: 1, severity: 'warning', message: 'two-part form' }],
    }
    const view = lintView(settled('Claims 5 ...', meta))
    expect(view.meta).toEqual(meta)
    expect(view.meta?.violations[0]?.severity).toBe('warning')
  })

  it('parses the rendered text with the violation list', () => {
    const view = lintView(settled(LINT_TEXT))
    expect(view.meta?.summary).toEqual({ total: 5, independent: 2, dependent: 3, errors: 2, warnings: 1 })
    expect(view.meta?.violations.map(violation => violation.rule)).toEqual(['C1', 'C5', 'A1'])
    expect(view.meta?.violations[0]?.claim).toBe(3)
  })

  it('parses the all-pass render text without findings', () => {
    const view = lintView(settled('Claims 4 (1 independent, 3 dependent), 0 errors, 0 warnings. all format rules pass PASS: no format errors (warnings are drafting hints, not blockers).'))
    expect(view.meta?.violations).toEqual([])
    expect(view.meta?.summary.errors).toBe(0)
  })

  it('exposes the running state before the result lands', () => {
    expect(lintView({ callId: 'c', argsRaw: '{"claims":"1..."}' }).state).toBe('running')
  })
})

describe('parseCoverageText', () => {
  it('returns null for foreign text', () => {
    expect(parseCoverageText('')).toBeNull()
    expect(parseCoverageText('Claims 5 (2 independent, 3 dependent), 0 errors.')).toBeNull()
  })
})


describe('buildProjectView', () => {
  const root = listing([
    { name: 'patent.yml', type: 'file', size: 120 },
    { name: 'brief.md', type: 'file', size: 800 },
    { name: 'chapters', type: 'directory' },
    { name: 'review', type: 'directory' },
    { name: 'figures', type: 'directory' },
    { name: 'application', type: 'directory' },
  ])

  it('derives the full overview from the workspace listings', () => {
    const view = buildProjectView(
      root,
      listing([
        { name: '01-name.md', type: 'file', size: 300 },
        { name: '02-field.md', type: 'file', size: 0 },
      ]),
      listing([{ name: 'draft-review.md', type: 'file', size: 900 }]),
      listing([{ name: '图1.png', type: 'file', size: 2000 }, { name: '图1.drawio', type: 'file', size: 2000 }, { name: 'source', type: 'directory' }, { name: 'tmp', type: 'directory' }]),
      listing([{ name: 'claims.md', type: 'file', size: 4000 }]),
      'name: 一种缓存方法\nstatus: application\n',
      '图1 为本发明所述方法的流程总览图；\n',
    )
    expect(view.isProject).toBe(true)
    expect(view.projectName).toBe('一种缓存方法')
    expect(view.projectStatus).toBe('application')
    expect(view.brief).toBe(true)
    expect(view.chapters).toHaveLength(2)
    expect(view.drafted).toBe(1)
    expect(view.total).toBe(8)
    expect(view.application.claims).toBe(true)
    expect(view.application.description).toBe(false)
    expect(view.review).toEqual(['draft-review.md'])
    expect(view.figures).toEqual([{ name: '图1.png', caption: '本发明所述方法的流程总览图' }])
  })

  it('reports a non-project workspace', () => {
    const view = buildProjectView(listing([{ name: 'README.md', type: 'file', size: 10 }]), null, null, null, null, null)
    expect(view.isProject).toBe(false)
    expect(view.drafted).toBe(0)
  })

  it('derives the coarse loop stage from the second-phase reads', () => {
    // The quantified effect text below requires the verification chapter, so
    // the listing carries all nine.
    const eightChapters = listing([
      ...Array.from({ length: 8 }, (_, index) => ({
        name: `0${index + 1}-name.md`, type: 'file' as const, size: 300,
      })),
      { name: '09-verification.md', type: 'file' as const, size: 300 },
    ])
    const projectRoot = listing([
      { name: 'patent.yml', type: 'file', size: 120 },
      { name: 'brief.md', type: 'file', size: 800 },
      { name: 'chapters', type: 'directory' },
      { name: 'review', type: 'directory' },
      { name: 'figures', type: 'directory' },
      { name: 'experiments', type: 'directory' },
      { name: 'exports', type: 'directory' },
    ])
    const base = {
      briefText: '## 技术领域\n\n存储。\n\n## 背景技术\n\n慢。\n\n## 技术问题\n\n提速。\n\n## 发明内容\n\n新结构。\n\n## 有益效果\n\n省空间。\n',
      effectText: '命中率达到 95%。',
      drawingsText: '无附图\n',
      experimentsReadmeText: '无需实验：纯界面方法。\n',
      experimentRunLogs: [],
      exportsListing: listing([]),
      reportTexts: [],
      patentYml: 'name: 测试\nstatus: drafting\nreviewThreshold: 85\n',
      priorArtText: null,
    }
    // All presence gates green except review: no passing report.
    const atReview = buildProjectView(projectRoot, eightChapters, listing([{ name: 'p.review.md', type: 'file', size: 900 }]), null, null, base.patentYml, base.drawingsText, base)
    expect(atReview.loop.stage).toBe('review')
    expect(atReview.loop.threshold).toBe(85)

    // A passing whole-project report flips the stage to export, a partial one does not.
    const passing = buildProjectView(projectRoot, eightChapters, listing([{ name: 'p.review.md', type: 'file', size: 900 }]), null, null, base.patentYml, base.drawingsText, {
      ...base,
      exportsListing: listing([{ name: '测试-交底书.docx', type: 'file', size: 900 }]),
      reportTexts: [{ name: 'p.review.md', text: '总分 88\n\n> 审查范围：整项（项目根）\n' }],
    })
    expect(passing.loop.stage).toBe('ready')

    const partialOnly = buildProjectView(projectRoot, eightChapters, listing([{ name: 'p.review.md', type: 'file', size: 900 }]), null, null, base.patentYml, base.drawingsText, {
      ...base,
      reportTexts: [{ name: 'p.review.md', text: '总分 96\n\n> 审查范围：部分（chapters）\n' }],
    })
    expect(partialOnly.loop.stage).toBe('review')
    expect(partialOnly.loop.reports[0]?.passing).toBe(false)

    // The degraded marker relaxes the bar by ten.
    const degraded = buildProjectView(projectRoot, eightChapters, listing([{ name: 'p.review.md', type: 'file', size: 900 }]), null, null, base.patentYml, base.drawingsText, {
      ...base,
      priorArtText: '查新不可用：网络不可达，待补查\n',
      reportTexts: [{ name: 'p.review.md', text: '总分 78\n' }],
    })
    expect(degraded.loop.threshold).toBe(75)
    expect(degraded.loop.reports[0]?.passing).toBe(true)

    // A quantitative effect without a run log or the marker pins experiments.
    const atExperiments = buildProjectView(projectRoot, eightChapters, null, null, null, base.patentYml, base.drawingsText, {
      ...base,
      experimentsReadmeText: null,
      experimentRunLogs: [false],
    })
    expect(atExperiments.loop.stage).toBe('experiments')
  })
})
