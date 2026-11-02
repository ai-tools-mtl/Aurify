import { describe, expect, it } from 'vitest'
import { lintProse } from '../src/prose-lint.ts'

describe('lintProse', () => {
  it('flags filler phrases as errors with an excerpt', () => {
    const result = lintProse('该模块负责凭证托管。值得注意的是，密钥仅在调用时释放。')
    expect(result.summary.cliches).toBe(1)
    expect(result.summary.errors).toBe(1)
    expect(result.violations[0]?.rule).toBe('cliche')
    expect(result.violations[0]?.excerpt).toContain('值得注意的是')
  })

  it('flags the extended filler set (需要注意的是/综上所述/由此可见/众所周知/毋庸置疑/不可否认)', () => {
    for (const phrase of ['需要注意的是', '综上所述', '由此可知', '由此可见', '众所周知', '毋庸置疑', '不可否认']) {
      const result = lintProse(`分区调度器按负载分配光配额。${phrase}，该策略由中央节点统一执行。`)
      expect(result.summary.cliches, phrase).toBe(1)
    }
  })

  it('flags apologetic openers with the fact-stating rewrite guidance', () => {
    for (const phrase of ['遗憾的是', '不得不承认', '必须承认']) {
      const result = lintProse(`限频重排模块已完成单集群验证。${phrase}，跨集群场景尚未评估。`)
      expect(result.summary.cliches, phrase).toBe(1)
      expect(result.summary.errors, phrase).toBe(1)
      expect(result.violations[0]?.message, phrase).toContain('事实陈述')
    }
  })

  it('flags sentences over 150 characters', () => {
    const long = '该系统' + '通过校验模块完成数据核验，'.repeat(14) + '并输出结果。'
    expect(long.length).toBeGreaterThan(150)
    const result = lintProse(long)
    expect(result.summary.longSentences).toBe(1)
    expect(result.violations[0]?.rule).toBe('long-sentence')
  })

  it('flags triple parallelisms sharing the same clause prefix', () => {
    const result = lintProse('它提升效率，它降低成本，它增强可靠性。这是目标。')
    expect(result.summary.parallelisms).toBeGreaterThanOrEqual(1)
    expect(result.violations.some(violation => violation.rule === 'parallelism')).toBe(true)
  })

  it('flags paragraph-ending summary sentences as warnings', () => {
    const result = lintProse('预检组件在写入生效前完成交集判定，写集不相交的写入并行放行。因此协作并发度不受影响。')
    expect(result.summary.paragraphSummaries).toBe(1)
    expect(result.violations.every(violation => violation.severity === 'warning')).toBe(true)
  })

  it('flags textbook definitions', () => {
    const result = lintProse('分布式锁是指一种跨进程的互斥原语。')
    expect(result.summary.definitions).toBe(1)
  })

  it('flags inversion rhetoric as a warning without errors', () => {
    for (const [text, label] of [
      ['本方案的核心不是提高单核频率，而是重构调度粒度。', '不是A而是B'],
      ['与其说这是一次参数调整，不如说是一次架构重构。', '与其说A不如说B'],
    ] as const) {
      const result = lintProse(text)
      expect(result.summary.inversions, label).toBe(1)
      expect(result.summary.errors, label).toBe(0)
      expect(result.violations[0]?.severity, label).toBe('warning')
    }
  })

  it('flags dense 顿号 enumerations as warnings but spares three-item lists', () => {
    const dense = lintProse('该平台覆盖采集、清洗、对账、归档、校验等环节。')
    expect(dense.summary.enumerations).toBe(1)
    const lean = lintProse('调度模块负责采集、清洗与对账三个环节。')
    expect(lean.summary.enumerations).toBe(0)
  })

  it('flags sentence-initial topic shells', () => {
    for (const text of ['对于早期团队来说，招人是最难的事。', '就延迟而言，队列排队才是大头。']) {
      const result = lintProse(text)
      expect(result.summary.topicShells, text).toBe(1)
      expect(result.summary.errors, text).toBe(0)
    }
  })

  it('flags the colloquial opener set (说白了/说穿了/先说结论)', () => {
    for (const phrase of ['说白了', '说穿了', '先说结论']) {
      const result = lintProse(`调度器按水位线分流。${phrase}，延迟来自队列排队而非计算。`)
      expect(result.summary.cliches, phrase).toBe(1)
      expect(result.summary.errors, phrase).toBe(1)
    }
  })

  it('passes clean technical prose with zero errors', () => {
    const result = lintProse('预检组件在写入生效前完成读写集交集判定，写集不相交的写入立即并行生效。判定结果与资源占用表一同落盘。')
    expect(result.summary.errors).toBe(0)
    expect(result.summary.warnings).toBe(0)
  })
})
