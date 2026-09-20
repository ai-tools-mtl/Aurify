import { mkdtemp, mkdir, rm, utimes, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { assessLoopState, readManifest } from '../src/loop.ts'
import { sourceFingerprint } from '../src/fingerprint.ts'
import * as ToolPatent from '../src/index.ts'

let root: string

beforeAll(async () => {
  root = await mkdtemp(join(tmpdir(), 'patent-loop-'))
})

afterAll(async () => {
  await rm(root, { recursive: true, force: true })
})

/** Create an empty project scratch directory. */
async function scratch(name: string): Promise<string> {
  const dir = join(root, name)
  await mkdir(dir, { recursive: true })
  return dir
}

const MANIFEST = 'formatVersion: 1\nname: 测试存储装置\nstatus: drafting\n'

const FULL_BRIEF = [
  '# 五方对齐摘要',
  '## 点子评估', '建议写，对比文件 CN101 语义无关。', '## 技术领域', '数据存储领域。',
  '## 背景技术', '① 现有方案过慢；② 空间浪费', '## 技术问题', '① 提速；② 省空间',
  '## 发明内容', '新索引结构', '## 有益效果', '① 命中率提升；② 空间减半',
].join('\n\n')

const BODY = '正文内容超过二十个字符的占位段落，用于通过成稿长度门槛的检查逻辑。'

/** Scaffold a project with a manifest, a full brief, and all eight drafted chapters. */
async function fullProject(name: string): Promise<string> {
  const dir = await scratch(name)
  await writeFile(join(dir, 'patent.yml'), MANIFEST, 'utf8')
  await writeFile(join(dir, 'brief.md'), FULL_BRIEF, 'utf8')
  await mkdir(join(dir, 'chapters'), { recursive: true })
  for (const file of ['01-name.md', '02-field.md', '03-background.md', '04-problem.md', '05-solution.md', '06-effect.md', '07-key-points.md', '08-drawings.md']) {
    await writeFile(join(dir, 'chapters', file), `# ${file}\n\n${BODY}`, 'utf8')
  }
  return dir
}

describe('assessLoopState stage machine', () => {
  it('names init for a bare directory with no patent.yml', async () => {
    const dir = await scratch('bare')
    const state = await assessLoopState(dir)
    expect(state.hasProject).toBe(false)
    expect(state.stage).toBe('init')
    expect(state.complete).toBe(false)
    expect(state.mayNeedUser).toBe(true)
    expect(state.skills).toContain('patent-init')
  })

  it('names align while brief.md is missing or lacks a core section', async () => {
    const missing = await scratch('no-brief')
    await writeFile(join(missing, 'patent.yml'), MANIFEST, 'utf8')
    expect((await assessLoopState(missing)).stage).toBe('align')

    const partial = await scratch('thin-brief')
    await writeFile(join(partial, 'patent.yml'), MANIFEST, 'utf8')
    await writeFile(join(partial, 'brief.md'), '## 技术领域\n\n存储。\n', 'utf8')
    const state = await assessLoopState(partial)
    expect(state.stage).toBe('align')
    expect(state.gaps.some(gap => gap.detail.includes('背景技术'))).toBe(true)
  })

  it('passes align once the brief carries all five core sections', async () => {
    const dir = await scratch('brief-only')
    await writeFile(join(dir, 'patent.yml'), MANIFEST, 'utf8')
    await writeFile(join(dir, 'brief.md'), FULL_BRIEF, 'utf8')
    const state = await assessLoopState(dir)
    expect(state.stage).toBe('chapters')
    expect(state.skills).toContain('patent-chapters')
  })

  it('names chapters while any of the eight files is missing or a placeholder', async () => {
    const dir = await fullProject('thin-chapters')
    await rm(join(dir, 'chapters', '05-solution.md'))
    await writeFile(join(dir, 'chapters', '06-effect.md'), '# 有益效果\n\n待补。', 'utf8')
    const state = await assessLoopState(dir)
    expect(state.stage).toBe('chapters')
    expect(state.gaps.some(gap => gap.detail.includes('05-solution.md'))).toBe(true)
    expect(state.gaps.some(gap => gap.detail.includes('06-effect.md 为占位'))).toBe(true)
  })

  it('names experiments for quantified effects with no run log, and accepts the not-applicable marker', async () => {
    const dir = await fullProject('no-experiments')
    await writeFile(join(dir, 'chapters', '06-effect.md'), `# 有益效果\n\n丢失从 226 个降至 0，调用减少 22%。${BODY}`, 'utf8')
    // Quantified effects also require the verification chapter — a chapters gap.
    const verification = await assessLoopState(dir)
    expect(verification.gaps.some(gap => gap.detail.includes('09-verification'))).toBe(true)
    expect(verification.stage).toBe('chapters')

    await mkdir(join(dir, 'experiments'), { recursive: true })
    await writeFile(join(dir, 'experiments', 'README.md'), '无需实验：纯界面布局方法，无量化效果主张。\n', 'utf8')
    // The 无需实验 declaration satisfies the run-log requirement, but the
    // quantified claims still need their evidence story — the verification
    // chapter argues from public data or reasoning instead of run records.
    const state = await assessLoopState(dir)
    expect(state.stage).toBe('chapters')
    expect(state.gaps.some(gap => gap.detail.includes('09-verification'))).toBe(true)
    await writeFile(join(dir, 'chapters', '09-verification.md'), `# 实验验证\n\n${BODY}`, 'utf8')
    expect((await assessLoopState(dir)).stage).toBe('figures')
  })

  it('satisfies experiments with a run log anywhere under experiments/', async () => {
    const dir = await fullProject('with-experiments')
    await writeFile(join(dir, 'chapters', '06-effect.md'), `# 有益效果\n\n丢失从 226 个降至 0。${BODY}`, 'utf8')
    await mkdir(join(dir, 'experiments', 'sim', 'results'), { recursive: true })
    await writeFile(join(dir, 'experiments', 'sim', 'results', 'run-log.md'), '| 时间 | 退出码 |\n', 'utf8')
    // The experiments tree alone (even before the effect chapter quantifies)
    // requires the verification chapter.
    expect((await assessLoopState(dir)).gaps.some(gap => gap.detail.includes('09-verification'))).toBe(true)
    await writeFile(join(dir, 'chapters', '09-verification.md'), `# 实验验证\n\n${BODY}`, 'utf8')
    expect((await assessLoopState(dir)).stage).toBe('figures')
  })

  it('never requires the verification chapter for a project without experiment work', async () => {
    const dir = await fullProject('no-verification-needed')
    const state = await assessLoopState(dir)
    expect(state.gaps.some(gap => gap.detail.includes('09-verification'))).toBe(false)
  })

  it('names figures for undeclared, missing, or surplus figure files', async () => {
    const none = await fullProject('figures-unplanned')
    expect((await assessLoopState(none)).gaps.some(gap => gap.detail.includes('未声明任何'))).toBe(true)

    const missing = await fullProject('figures-missing')
    await writeFile(join(missing, 'chapters', '08-drawings.md'), `# 附图说明\n\n图1 为流程总览图；\n图2 为架构图。\n${BODY}`, 'utf8')
    await mkdir(join(missing, 'figures'), { recursive: true })
    await writeFile(join(missing, 'figures', '图1-流程总览.png'), 'png', 'utf8')
    const state = await assessLoopState(missing)
    expect(state.stage).toBe('figures')
    expect(state.gaps.some(gap => gap.detail.includes('图2'))).toBe(true)

    await writeFile(join(missing, 'figures', '图9-多余.png'), 'png', 'utf8')
    expect((await assessLoopState(missing)).gaps.some(gap => gap.detail.includes('图9'))).toBe(true)
  })

  it('names review until a rubric report exists, then export until a fresh disclosure docx exists', async () => {
    const dir = await fullProject('review-and-export')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n图1 为流程总览图。\n${BODY}`, 'utf8')
    await mkdir(join(dir, 'figures'), { recursive: true })
    await writeFile(join(dir, 'figures', '图1.png'), 'png', 'utf8')
    expect((await assessLoopState(dir)).stage).toBe('review')

    await mkdir(join(dir, 'review'), { recursive: true })
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 81\n', 'utf8')
    expect((await assessLoopState(dir)).stage).toBe('export')

    // The score gate: a fresh report below the default bar of 80 keeps the loop at review.
    await writeFile(join(dir, 'chapters', '07-key-points.md'), `# 关键点\n\n修订后的内容。${BODY}`, 'utf8')
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 79\n', 'utf8')
    const low = await assessLoopState(dir)
    expect(low.stage).toBe('review')
    expect(low.gaps[0]?.detail).toContain('低于达标线 80')

    // The prior-art degradation marker relaxes the bar by ten points.
    await mkdir(join(dir, 'reference'), { recursive: true })
    await writeFile(join(dir, 'reference', 'prior-art.md'), '查新不可用：代理未开启，待补查\n', 'utf8')
    expect((await assessLoopState(dir)).stage).toBe('export')
    await rm(join(dir, 'reference', 'prior-art.md'))

    // A per-project threshold overrides the default bar.
    await writeFile(join(dir, 'patent.yml'), `${MANIFEST}reviewThreshold: 85\n`, 'utf8')
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 81\n', 'utf8')
    const strict = await assessLoopState(dir)
    expect(strict.stage).toBe('review')
    expect(strict.gaps[0]?.detail).toContain('低于达标线 85')

    // A report older than the sources it reviewed is stale no matter its score.
    await writeFile(join(dir, 'patent.yml'), MANIFEST, 'utf8')
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 95\n', 'utf8')
    const stale = new Date(Date.now() - 60_000)
    await utimes(join(dir, 'review', 'project.review.md'), stale, stale)
    await writeFile(join(dir, 'chapters', '06-effect.md'), `# 有益效果\n\n审查之后的源文件修订。${BODY}`, 'utf8')
    const outdated = await assessLoopState(dir)
    expect(outdated.stage).toBe('review')
    expect(outdated.gaps[0]?.detail).toContain('早于源文件')

    // A report without a parseable total score fails loud instead of passing.
    await writeFile(join(dir, 'review', 'project.review.md'), '没有总分行\n', 'utf8')
    const unparseable = await assessLoopState(dir)
    expect(unparseable.stage).toBe('review')
    expect(unparseable.gaps[0]?.detail).toContain('缺少可解析的总分')

    // A fresh passing report reopens the export gate, and done closes the loop.
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 88\n', 'utf8')
    await mkdir(join(dir, 'exports'), { recursive: true })
    await writeFile(join(dir, 'exports', '测试存储装置-交底书.docx'), 'docx', 'utf8')
    const fresh = await assessLoopState(dir)
    expect(fresh.stage).toBe('done')
    expect(fresh.complete).toBe(true)
  })

  it('rejects a partial-scope report as the whole-project verdict', async () => {
    const dir = await fullProject('partial-scope')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n无附图\n${BODY}`, 'utf8')
    await mkdir(join(dir, 'review'), { recursive: true })
    await writeFile(join(dir, 'review', 'chapters.review.md'), '总分 92\n\n> 审查范围：部分（chapters）\n', 'utf8')
    const state = await assessLoopState(dir)
    expect(state.stage).toBe('review')
    expect(state.gaps[0]?.detail).toContain('只覆盖了局部目标')
  })

  it('escalates instead of re-reviewing forever once score gains stall', async () => {
    const dir = await fullProject('stalled')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n无附图\n${BODY}`, 'utf8')
    await mkdir(join(dir, 'review'), { recursive: true })
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 73\n', 'utf8')
    await writeFile(
      join(dir, 'review', 'attempts.md'),
      '- t1 总分 70 范围 project 目标 .\n- t2 总分 72 范围 project 目标 .\n- t3 总分 73 范围 project 目标 .\n',
      'utf8',
    )
    const state = await assessLoopState(dir)
    expect(state.stage).toBe('review')
    expect(state.gaps[0]?.detail).toContain('连续 3 次重审未达线')
    expect(state.gaps[0]?.detail).toContain('reviewThreshold')
  })

  it('flags prose references to undeclared figures', async () => {
    const dir = await fullProject('figure-refs')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n图1 为流程总览图。\n${BODY}`, 'utf8')
    await writeFile(join(dir, 'chapters', '06-effect.md'), `# 有益效果\n\n静默丢失归零（对比见图9）。${BODY}`, 'utf8')
    const state = await assessLoopState(dir)
    expect(state.gaps.some(gap => gap.detail.includes('正文引用了图9，但 08 章未声明'))).toBe(true)
  })

  it('flags prose publication numbers missing from the prior-art ledger', async () => {
    // A citation with no ledger file at all names the ledger itself.
    const noLedger = await fullProject('prior-art-absent')
    await writeFile(join(noLedger, 'brief.md'), FULL_BRIEF.replace('CN101', '见 CN 212345678 U'), 'utf8')
    const absent = await assessLoopState(noLedger)
    expect(absent.stage).toBe('chapters')
    expect(absent.gaps.some(gap => gap.detail.includes('reference/prior-art.md') && gap.detail.includes('不存在'))).toBe(true)

    // A ledger that never saw the cited number names the number itself.
    const dir = await fullProject('prior-art-missing')
    await writeFile(join(dir, 'chapters', '03-background.md'), `# 背景技术\n\n最接近的现有技术：CN117891234A 采用分层缓存。${BODY}`, 'utf8')
    await mkdir(join(dir, 'reference'), { recursive: true })
    await writeFile(join(dir, 'reference', 'prior-art.md'), '| 公开号 | 标题 |\n| --- | --- |\n| CN109876543B | 一种无关装置 |', 'utf8')
    const state = await assessLoopState(dir)
    expect(state.stage).toBe('chapters')
    expect(state.gaps.some(gap => gap.detail.includes('CN117891234A') && gap.detail.includes('prior-art.md'))).toBe(true)
  })

  it('accepts prose publication numbers recorded in the prior-art ledger', async () => {
    const dir = await fullProject('prior-art-ok')
    await writeFile(join(dir, 'chapters', '03-background.md'), `# 背景技术\n\nCN117891234A 采用分层缓存。${BODY}`, 'utf8')
    await mkdir(join(dir, 'reference'), { recursive: true })
    await writeFile(join(dir, 'reference', 'prior-art.md'), '| 公开号 | 标题 |\n| --- | --- |\n| CN 117891234 A | 一种分层缓存系统 |', 'utf8')
    const state = await assessLoopState(dir)
    expect(state.gaps.some(gap => gap.detail.includes('公开号'))).toBe(false)
  })

  it('carries the prior-art debt note on the directive while degraded, including at done', async () => {
    const scaffold = async (name: string): Promise<string> => {
      const dir = await fullProject(name)
      await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n图1 为流程总览图。\n${BODY}`, 'utf8')
      await mkdir(join(dir, 'figures'), { recursive: true })
      await writeFile(join(dir, 'figures', '图1.png'), 'png', 'utf8')
      await mkdir(join(dir, 'review'), { recursive: true })
      await writeFile(join(dir, 'review', 'project.review.md'), '总分 81\n', 'utf8')
      await mkdir(join(dir, 'exports'), { recursive: true })
      await writeFile(join(dir, 'exports', '测试存储装置-交底书.docx'), 'docx', 'utf8')
      return dir
    }
    const clean = await scaffold('debt-clean')
    const cleanState = await assessLoopState(clean)
    expect(cleanState.complete).toBe(true)
    expect(cleanState.directive).not.toContain('查新降级债')

    const debt = await scaffold('debt-open')
    await mkdir(join(debt, 'reference'), { recursive: true })
    await writeFile(join(debt, 'reference', 'prior-art.md'), '查新不可用：代理未开启，待补查\n', 'utf8')
    const debtState = await assessLoopState(debt)
    expect(debtState.complete).toBe(true)
    expect(debtState.priorArtDegraded).toBe(true)
    expect(debtState.directive).toContain('未清偿的查新降级债')
  })

  it('reopens the export stage when a source file is newer than the exported docx', async () => {
    const dir = await fullProject('stale-export')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n图1 为流程总览图。\n${BODY}`, 'utf8')
    await mkdir(join(dir, 'figures'), { recursive: true })
    await writeFile(join(dir, 'figures', '图1.png'), 'png', 'utf8')
    await mkdir(join(dir, 'review'), { recursive: true })
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 81\n', 'utf8')
    await mkdir(join(dir, 'exports'), { recursive: true })
    await writeFile(join(dir, 'exports', '测试存储装置-交底书.docx'), 'docx', 'utf8')
    const stale = new Date(Date.now() - 60_000)
    await utimes(join(dir, 'exports', '测试存储装置-交底书.docx'), stale, stale)
    const state = await assessLoopState(dir)
    expect(state.stage).toBe('export')
    expect(state.gaps[0]?.detail).toContain('早于源文件')
  })

  it('judges review freshness by the stamped source digest, not mtimes', async () => {
    const dir = await fullProject('fingerprinted-review')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n无附图\n${BODY}`, 'utf8')
    await mkdir(join(dir, 'review'), { recursive: true })
    const fingerprint = await sourceFingerprint(dir)
    // A stamped report whose mtime lies in the past still counts as fresh —
    // this is the checkout/sync case the mtime gate got wrong.
    await writeFile(join(dir, 'review', 'project.review.md'), `总分 85\n\n> 源指纹：${fingerprint}\n`, 'utf8')
    const stale = new Date(Date.now() - 60_000)
    await utimes(join(dir, 'review', 'project.review.md'), stale, stale)
    expect((await assessLoopState(dir)).stage).toBe('export')

    // Editing a source after the review voids the stamp even with a fresh mtime.
    await writeFile(join(dir, 'chapters', '03-background.md'), `# 背景技术\n\n审查之后的源文件修订。${BODY}`, 'utf8')
    const voided = await assessLoopState(dir)
    expect(voided.stage).toBe('review')
    expect(voided.gaps[0]?.detail).toContain('源指纹与当前源文件不符')
  })

  it('judges export freshness by the exporter digest sidecar when present', async () => {
    const dir = await fullProject('sidecar-export')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n无附图\n${BODY}`, 'utf8')
    await mkdir(join(dir, 'review'), { recursive: true })
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 88\n', 'utf8')
    await mkdir(join(dir, 'exports'), { recursive: true })
    await writeFile(join(dir, 'exports', '测试存储装置-交底书.docx'), 'docx', 'utf8')
    // Sidecar matches: the export gate passes even when the docx mtime is old.
    const fingerprint = await sourceFingerprint(dir)
    await writeFile(join(dir, 'exports', '测试存储装置-交底书.fingerprint'), fingerprint, 'utf8')
    const stale = new Date(Date.now() - 60_000)
    await utimes(join(dir, 'exports', '测试存储装置-交底书.docx'), stale, stale)
    expect((await assessLoopState(dir)).stage).toBe('done')

    // A source edit after the export voids the sidecar. The review gate stays
    // green on purpose (its unstamped report gets a future mtime), isolating
    // the export verdict to the sidecar comparison.
    await writeFile(join(dir, 'chapters', '02-field.md'), `# 技术领域\n\n导出之后的源文件修订。${BODY}`, 'utf8')
    const future = new Date(Date.now() + 60_000)
    await utimes(join(dir, 'review', 'project.review.md'), future, future)
    const voided = await assessLoopState(dir)
    expect(voided.stage).toBe('export')
    expect(voided.gaps[0]?.detail).toContain('源指纹与当前源文件不符')
  })

  it('names the top revision-list items as priorities in the below-threshold gap', async () => {
    const dir = await fullProject('revision-priorities')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n无附图\n${BODY}`, 'utf8')
    await mkdir(join(dir, 'review'), { recursive: true })
    await writeFile(
      join(dir, 'review', 'project.review.md'),
      [
        '总分 62',
        '',
        '## 修订清单（按影响排序）',
        '',
        '- **有益效果**（均分 55，影响 9.0）：补一个与方案组件逐项对应的量化对比。',
        '- **背景技术**（均分 60，影响 8.0）：给出可检索的现有技术文献描述。',
        '- **技术方案**（均分 70，影响 6.0）：说明信号采集模块与判决模块的接口。',
        '- **关键点**（均分 75，影响 5.0）：收敛欲保护点的范围表述。',
      ].join('\n'),
      'utf8',
    )
    const state = await assessLoopState(dir)
    expect(state.stage).toBe('review')
    const gap = state.gaps[0]?.detail ?? ''
    expect(gap).toContain('低于达标线 80')
    expect(gap).toContain('优先修订：有益效果：补一个与方案组件逐项对应的量化对比。；背景技术')
    expect(gap).not.toContain('关键点') // top-3 cut, not the whole list
  })
})

describe('patent_loop tool and patent-loop command registration', () => {
  interface LoopToolShape {
    name: string
    execute: (args: unknown, exec: unknown) => Promise<{
      stage: string
      complete: boolean
      directive: string
      gaps: string[]
    }>
  }

  interface LoopAgentStub {
    session: { header: { cwd?: string } }
    followup: (message: unknown) => void
  }

  type LoopHandler = (invocation: { rawInput: string; agent?: LoopAgentStub }) => Promise<{ kind: string; text?: string }>

  function mount(): {
    tool: LoopToolShape
    handler: LoopHandler
    followups: unknown[]
  } {
    let tool: LoopToolShape | undefined
    let handler!: LoopHandler
    const followups: unknown[] = []
    const drained: unknown[] = []
    const ctx = {
      tools: {
        register: vi.fn((definition: LoopToolShape) => {
          if (definition.name === 'patent_loop') tool = definition
          return () => {}
        }),
      },
      commands: {
        register: vi.fn((definition: { handler: LoopHandler }) => {
          handler = definition.handler
          return () => {}
        }),
      },
      effect: (callback: (() => Generator) | Generator): void => {
        const iterator = typeof callback === 'function' ? (callback as () => Generator)() : callback
        for (const step of iterator) drained.push(step)
      },
    }
    void ToolPatent.apply(ctx as never)
    expect(tool).toBeDefined()
    expect(handler).toBeInstanceOf(Function)
    return {
      tool: tool!,
      handler,
      followups,
    }
  }

  it('exposes the assessor tool whose execute projects the loop state', async () => {
    const dir = await scratch('tool-probe')
    const { tool } = mount()
    const value = await tool.execute({ project_dir: dir }, {})
    expect(value.stage).toBe('init')
    expect(value.complete).toBe(false)
    expect(value.directive.length).toBeGreaterThan(0)
    expect(value.gaps.length).toBeGreaterThan(0)
  })

  it('injects the loop prompt through followup and returns a UI-only summary', async () => {
    const dir = await scratch('command-probe')
    await writeFile(join(dir, 'patent.yml'), MANIFEST, 'utf8')
    const { handler, followups } = mount()
    const agent: LoopAgentStub = {
      session: { header: { cwd: root } },
      followup: (message: unknown) => { followups.push(message) },
    }
    const result = await handler({ rawInput: 'command-probe', agent })
    expect(result.kind).toBe('success')
    expect(result.text).toContain('patent-loop 已启动')
    expect(followups).toHaveLength(1)
  })

  it('skips the followup entirely when the project is already complete', async () => {
    const dir = await fullProject('done-project')
    await writeFile(join(dir, 'chapters', '08-drawings.md'), `# 附图说明\n\n图1 为流程总览图。\n${BODY}`, 'utf8')
    await mkdir(join(dir, 'figures'), { recursive: true })
    await writeFile(join(dir, 'figures', '图1.png'), 'png', 'utf8')
    await mkdir(join(dir, 'review'), { recursive: true })
    await writeFile(join(dir, 'review', 'project.review.md'), '总分 81\n', 'utf8')
    await mkdir(join(dir, 'exports'), { recursive: true })
    await writeFile(join(dir, 'exports', '测试存储装置-交底书.docx'), 'docx', 'utf8')
    const { handler, followups } = mount()
    const agent: LoopAgentStub = {
      session: { header: { cwd: root } },
      followup: (message: unknown) => { followups.push(message) },
    }
    const result = await handler({ rawInput: 'done-project', agent })
    expect(result.text).toContain('已成稿')
    expect(followups).toHaveLength(0)
  })
})

describe('readManifest', () => {
  it('parses the shared manifest fields including the review-passes override', async () => {
    const dir = await scratch('manifest')
    await writeFile(join(dir, 'patent.yml'), `${MANIFEST}reviewThreshold: 85\nreviewPasses: 1\n`, 'utf8')
    expect(await readManifest(dir)).toEqual({ name: '测试存储装置', status: 'drafting', reviewThreshold: 85, reviewPasses: 1 })
  })

  it('drops an out-of-range reviewPasses and returns undefined without patent.yml', async () => {
    const dir = await scratch('manifest-range')
    await writeFile(join(dir, 'patent.yml'), `${MANIFEST}reviewPasses: 9\n`, 'utf8')
    expect(await readManifest(dir)).toEqual({ name: '测试存储装置', status: 'drafting' })
    expect(await readManifest(join(root, 'no-such-project'))).toBeUndefined()
  })
})
