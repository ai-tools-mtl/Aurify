import { mkdtemp, mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { basename, join } from 'node:path'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { apply, loadRubric, type Config } from '../src/index.ts'
import type { ReviewOutcome } from '../src/review.ts'

let root: string

/**
 * Build the mount config: explicit-undefined `projectRoot` test overrides must
 * end absent (exactOptionalPropertyTypes), not present-as-undefined.
 */
function buildConfig(overrides: { scoringPasses?: number; reviewTemperature?: number; projectRoot?: string | undefined }): Config {
  const { projectRoot, ...rest } = { scoringPasses: 2, reviewTemperature: 0.2, projectRoot: root, ...overrides }
  return projectRoot === undefined ? rest : { ...rest, projectRoot }
}

const OUTCOME: ReviewOutcome = {
  overall: 81,
  dimensions: [
    {
      key: 'completeness', title: '内容完整性', weight: 0.25, average: 82, failedPasses: 0,
      scores: [80, 84], evidence: ['章节齐全。', '信息充分。'], suggestions: ['补充分级说明。', '补充样例。'],
    },
    {
      key: 'novelty', title: '新颖性表述', weight: 0.2, average: 78, failedPasses: 1,
      scores: [78], evidence: ['区别明确。'], suggestions: ['加强对比。'],
    },
  ],
}

/** Minimal agent stub the project-root resolution path reads. */
type AgentStub = { session: { header: { cwd?: string } } }

function mount(
  engineResult: { stopReason: string; value?: unknown; error?: string },
  overrides: { scoringPasses?: number; reviewTemperature?: number; projectRoot?: string | undefined } = {},
): {
  handler: (rawInput: string, agent?: AgentStub) => Promise<{ kind: string; text?: string }>
  tool: { execute: (args: unknown, exec: unknown) => Promise<{ kind: 'success' | 'error'; summary: string; report: string; overall?: number }> } | undefined
  start: ReturnType<typeof vi.fn>
  startedArgsContainer: { args: Record<string, unknown> }
  steps: unknown[]
} {
  let handler!: (invocation: { rawInput: string; agent?: AgentStub }) => Promise<{ kind: string; text?: string }>
  let tool: { execute: (args: unknown, exec: unknown) => Promise<{ kind: 'success' | 'error'; summary: string; report: string; overall?: number }> } | undefined
  const startedArgsContainer: { args: Record<string, unknown> } = { args: {} }
  const steps: unknown[] = []
  const start = vi.fn((request: { args: Record<string, unknown> }) => {
    startedArgsContainer.args = request.args
    return {
      id: 'run-1',
      meta: {},
      result: Promise.resolve(engineResult),
      cancel: () => {},
      dispose: async () => {},
    }
  })
  const ctx = {
    commands: {
      register: vi.fn((definition: {
        handler: (invocation: { rawInput: string }) => Promise<{ kind: string; text?: string }>
      }) => {
        handler = definition.handler
        return () => {}
      }),
    },
    tools: {
      register: vi.fn((definition: { name: string; execute: (args: unknown, exec: unknown) => Promise<{ kind: 'success' | 'error'; summary: string; report: string; overall?: number }> }) => {
        if (definition.name === 'patent_review') tool = definition
        return () => {}
      }),
    },
    workflowEngine: { start },
    effect: (callback: (() => Generator) | Generator): void => {
      // Cordis accepts a generator factory or an iterable; drain either shape,
      // recording the yielded lifecycle steps (drain function, registration).
      const iterator = typeof callback === 'function' ? (callback as () => Generator)() : callback
      for (const step of iterator) steps.push(step)
    },
  }
  apply(ctx as never, buildConfig(overrides))
  expect(handler).toBeInstanceOf(Function)
  return {
    handler: (rawInput: string, agent?: AgentStub) =>
      handler({ rawInput, ...agent === undefined ? {} : { agent } }),
    tool,
    start,
    startedArgsContainer,
    steps,
  }
}

beforeAll(async () => {
  root = await mkdtemp(join(tmpdir(), 'patent-review-'))
  await mkdir(join(root, 'chapters'), { recursive: true })
  await writeFile(join(root, 'patent.yml'), 'formatVersion: 1\nname: 测试项目\nstatus: drafting\n', 'utf8')
  await writeFile(join(root, 'brief.md'), '五方对齐摘要', 'utf8')
  await writeFile(join(root, 'chapters', '03-background.md'), '背景技术内容', 'utf8')
  await writeFile(join(root, 'chapters', '04-problem.md'), '技术问题内容', 'utf8')
  await writeFile(join(root, 'chapters', '99-draft.txt'), 'ignored', 'utf8')
})

afterAll(async () => {
  await rm(root, { recursive: true, force: true })
})

describe('loadRubric', () => {
  it('loads the shipped versioned rubric with its seven dimensions', () => {
    const rubric = loadRubric()
    expect(rubric.dimensions.map(dimension => dimension.key)).toEqual([
      'completeness', 'solution_clarity', 'novelty', 'writing_quality',
      'claims_quality', 'description_support', 'abstract_compliance',
    ])
    expect(rubric.dimensions.reduce((sum, dimension) => sum + dimension.weight, 0)).toBeCloseTo(1, 10)
  })

  it('fails loud on a malformed rubric file', async () => {
    const path = join(root, 'bad-rubric.json')
    await writeFile(path, '{"name":"x","dimensions":[{"key":1}]}', 'utf8')
    expect(() => loadRubric(path)).toThrow(/malformed dimension/)
  })

  it.each([
    ['non-object document', '42', /expected an object/],
    ['missing name', '{"dimensions":[]}', /missing name/],
    ['missing dimensions', '{"name":"x"}', /missing dimensions/],
    ['empty dimensions', '{"name":"x","dimensions":[]}', /missing dimensions/],
    ['non-numeric weight', '{"name":"x","dimensions":[{"key":"k","title":"t","weight":"heavy","guide":{}}]}', /malformed dimension/],
    ['non-object guide', '{"name":"x","dimensions":[{"key":"k","title":"t","weight":1,"guide":[]}]}', /malformed dimension/],
    ['non-string guide text', '{"name":"x","dimensions":[{"key":"k","title":"t","weight":1,"guide":{"90-100":42}}]}', /malformed dimension/],
    ['missing key', '{"name":"x","dimensions":[{"title":"t","weight":1,"guide":{}}]}', /malformed dimension/],
  ])('fails loud: %s', async (_label, body, message) => {
    const path = join(root, 'bad-rubric.json')
    await writeFile(path, body, 'utf8')
    expect(() => loadRubric(path)).toThrow(message)
  })
})

describe('the /patent-review command', () => {
  it('registers on the command registry with usage description', async () => {
    const { start, steps } = mount({ stopReason: 'completed', value: OUTCOME })
    expect(start).not.toHaveBeenCalled()
    // The yielded lifecycle steps: the teardown drain, the command registration,
    // and the patent_review tool registration.
    expect(steps.length).toBe(3)
    await (steps[0] as () => Promise<unknown>)()
  })

  it('registers the patent_review tool beside the command', () => {
    const { tool } = mount({ stopReason: 'completed', value: OUTCOME })
    expect(tool).toBeDefined()
  })

  it('the patent_review tool runs the same pipeline and returns the summary', async () => {
    const { tool, start } = mount({ stopReason: 'completed', value: OUTCOME })
    const value = await tool!.execute({ target: 'chapters/03-background.md' }, {
      agent: { session: { header: { cwd: root } } },
      signal: new AbortController().signal,
    })
    expect(start).toHaveBeenCalledTimes(1)
    expect(value.kind).toBe('success')
    expect(value.overall).toBe(81)
    expect(value.report).toBe('review/chapters-03-background.review.md')
    expect(value.summary).toContain('总分 81')
    const written = await readFile(join(root, 'review', 'chapters-03-background.review.md'), 'utf8')
    expect(written).toContain('81')
  })

  it('the patent_review tool surfaces the error text as its summary', async () => {
    const { tool } = mount({ stopReason: 'completed', value: OUTCOME })
    const value = await tool!.execute({ target: 'chapters/03-background.md' }, {})
    expect(value.kind).toBe('error')
    expect(value.summary).toContain('agent 上下文')
  })

  it('a whole-project target names the report after the project, not an empty label', async () => {
    const { handler } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('.')
    expect(result.kind).toBe('success')
    const written = await readdir(join(root, 'review'))
    expect(written).toContain(`${basename(root)}.review.md`)
    expect(written.some(name => name.startsWith('.'))).toBe(false)
  })

  it('reviews one file, starts the fixed script, and writes the report', async () => {
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('chapters/03-background.md')
    expect(start).toHaveBeenCalledTimes(1)
    const request = start.mock.calls[0]![0] as Record<string, unknown>
    expect(request.meta).toEqual({ name: 'patent-review', description: 'Rubric review of chapters/03-background.md' })
    expect(request.args).toMatchObject({
      fileLabel: 'chapters/03-background.md',
      fileContent: '背景技术内容',
      passes: 2,
    })
    expect((request.args as Record<string, unknown>).dimensions).toHaveLength(7)
    expect(result.kind).toBe('success')
    expect(result.text).toContain('总分 81 / 100')
    expect(result.text).toContain('新颖性表述 失败 1 次')
    const report = await readFile(join(root, 'review', 'chapters-03-background.review.md'), 'utf8')
    expect(report).toContain('# 交底书审查：chapters/03-background.md')
    expect(report.endsWith('\n')).toBe(true)
  })

  it('reviews a directory target by concatenating its Markdown files in name order', async () => {
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('chapters')
    expect(result.kind).toBe('success')
    const request = start.mock.calls[0]![0] as { args: { fileContent: string; fileLabel: string } }
    expect(request.args.fileLabel).toBe('chapters')
    expect(request.args.fileContent).toContain('<!-- 03-background.md -->')
    expect(request.args.fileContent).toContain('<!-- 04-problem.md -->')
    expect(request.args.fileContent).not.toContain('notes.txt')
  })

  it('returns the usage text for an empty argument without starting a run', async () => {
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('  ')
    expect(result.kind).toBe('error')
    expect(result.text).toContain('用法：/patent-review')
    expect(start).not.toHaveBeenCalled()
  })

  it('reports a missing target without starting a run', async () => {
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('chapters/99-missing.md')
    expect(result.kind).toBe('error')
    expect(result.text).toContain('未找到可审查的 Markdown 文件：chapters/99-missing.md')
    expect(start).not.toHaveBeenCalled()
  })

  it('reports an empty directory target without starting a run', async () => {
    await mkdir(join(root, 'empty-dir'), { recursive: true })
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('empty-dir')
    expect(result.kind).toBe('error')
    expect(start).not.toHaveBeenCalled()
  })

  it('surfaces a failed run with its error message', async () => {
    const { handler } = mount({ stopReason: 'error', error: 'worker crashed' })
    const result = await handler('chapters/03-background.md')
    expect(result.kind).toBe('error')
    expect(result.text).toContain('审查未完成（error）：worker crashed')
  })

  it('rejects a return value that is not the expected score structure', async () => {
    const { handler } = mount({ stopReason: 'completed', value: { nope: true } })
    const result = await handler('chapters/03-background.md')
    expect(result.kind).toBe('error')
    expect(result.text).toContain('不是预期的评分结构')
  })

  it('surfaces a stopped run without an error message', async () => {
    const { handler } = mount({ stopReason: 'cancelled' })
    const result = await handler('chapters/03-background.md')
    expect(result.kind).toBe('error')
    expect(result.text).toContain('审查未完成（cancelled）：未知原因')
  })

  it('resolves the target against the session cwd when projectRoot is unset', async () => {
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME }, { projectRoot: undefined })
    const result = await handler('chapters/03-background.md', { session: { header: { cwd: root } } })
    expect(result.kind).toBe('success')
    expect(start).toHaveBeenCalledTimes(1)
    expect(result.text).toContain('总分 81 / 100')
  })

  it('fails loud when neither projectRoot nor the session cwd is set', async () => {
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME }, { projectRoot: undefined })
    const result = await handler('chapters/03-background.md', { session: { header: {} } })
    expect(result.kind).toBe('error')
    expect(result.text).toContain('无法确定项目根目录')
    expect(start).not.toHaveBeenCalled()
  })

  it('anchors the report to the enclosing patent.yml project', async () => {
    await mkdir(join(root, 'project-a', 'chapters'), { recursive: true })
    await writeFile(join(root, 'project-a', 'patent.yml'), 'formatVersion: 1\n', 'utf8')
    await writeFile(join(root, 'project-a', 'chapters', '03-background.md'), '背景技术内容', 'utf8')
    const { handler } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('project-a/chapters/03-background.md')
    expect(result.kind).toBe('success')
    expect(result.text).toContain('project-a/review/')
    const report = await readFile(join(root, 'project-a', 'review', 'project-a-chapters-03-background.review.md'), 'utf8')
    expect(report).toContain('# 交底书审查：project-a/chapters/03-background.md')
  })

  it('sends the consistency inputs for an application target', async () => {
    await mkdir(join(root, 'project-app', 'application'), { recursive: true })
    await writeFile(join(root, 'project-app', 'patent.yml'), 'formatVersion: 1\n', 'utf8')
    await writeFile(join(root, 'project-app', 'application', 'claims.md'), '1. 独权。\n', 'utf8')
    await writeFile(join(root, 'project-app', 'application', 'description.md'), '# 说明书\n\n支持独权。\n', 'utf8')
    await writeFile(join(root, 'project-app', 'application', 'abstract.md'), '摘要。\n', 'utf8')
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('project-app/application/claims.md')
    expect(result.kind).toBe('success')
    const args = (start.mock.calls[0]![0] as { args: Record<string, unknown> }).args
    expect(args.consistency).toMatchObject({ claims: '1. 独权。\n', description: '# 说明书\n\n支持独权。\n' })
    const report = await readFile(join(root, 'project-app', 'review', 'project-app-application-claims.review.md'), 'utf8')
    expect(report).toContain('# 交底书审查：project-app/application/claims.md')
  })

  it('omits the consistency inputs when the application set is incomplete or the target is elsewhere', async () => {
    await mkdir(join(root, 'project-partial', 'application'), { recursive: true })
    await writeFile(join(root, 'project-partial', 'patent.yml'), 'formatVersion: 1\n', 'utf8')
    await writeFile(join(root, 'project-partial', 'application', 'claims.md'), '1. 独权。\n', 'utf8')
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME })
    // The application set lacks description.md: the phase is skipped.
    await handler('project-partial/application/claims.md').catch(() => {})
    // And a chapter target never carries the phase.
    await mkdir(join(root, 'project-partial', 'chapters'), { recursive: true })
    await writeFile(join(root, 'project-partial', 'chapters', '01-name.md'), '名称\n', 'utf8')
    await handler('project-partial/chapters/01-name.md')
    for (const call of start.mock.calls) {
      expect((call[0] as { args: Record<string, unknown> }).args.consistency).toBeUndefined()
    }
  })

  it('reports the working directory itself as an unreviewable target', async () => {
    const empty = await mkdtemp(join(tmpdir(), 'patent-review-empty-'))
    const { handler, start } = mount({ stopReason: 'completed', value: OUTCOME }, { projectRoot: empty })
    const result = await handler('.')
    expect(result.kind).toBe('error')
    expect(result.text).toContain('未找到可审查的 Markdown 文件：.')
    expect(start).not.toHaveBeenCalled()
    await rm(empty, { recursive: true, force: true })
  })

  it('passes the configured temperature to the workflow script args', async () => {
    const { handler, startedArgsContainer } = mount({ stopReason: 'completed', value: OUTCOME }, { reviewTemperature: 0.3 })
    const result = await handler('chapters/03-background.md')
    expect(result.kind).toBe('success')
    expect(startedArgsContainer.args.reviewerTemperature).toBe(0.3)
  })

  it('overrides the profile pass count with patent.yml reviewPasses for that project', async () => {
    const project = join(root, 'passes-project')
    await mkdir(join(project, 'chapters'), { recursive: true })
    await writeFile(join(project, 'patent.yml'), 'formatVersion: 1\nname: 少轮次\nstatus: drafting\nreviewPasses: 1\n', 'utf8')
    await writeFile(join(project, 'chapters', '03-background.md'), '背景技术内容', 'utf8')
    const { handler, startedArgsContainer } = mount({ stopReason: 'completed', value: OUTCOME })
    const result = await handler('passes-project/chapters')
    expect(result.kind).toBe('success')
    expect(startedArgsContainer.args.passes).toBe(1)
    await rm(project, { recursive: true, force: true })
  })

  it('keeps the profile pass count for projects without a reviewPasses override', async () => {
    const { handler, startedArgsContainer } = mount({ stopReason: 'completed', value: OUTCOME }, { scoringPasses: 3 })
    const result = await handler('chapters/03-background.md')
    expect(result.kind).toBe('success')
    expect(startedArgsContainer.args.passes).toBe(3)
  })
})
