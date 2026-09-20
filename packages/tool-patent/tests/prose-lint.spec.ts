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

  it('flags the extended filler set (需要注意的是/众所周知/毋庸置疑/不可否认)', () => {
    for (const phrase of ['需要注意的是', '众所周知', '毋庸置疑', '不可否认']) {
      const result = lintProse(`分区调度器按负载分配光配额。${phrase}，该策略由中央节点统一执行。`)
      expect(result.summary.cliches, phrase).toBe(1)
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

  it('passes clean technical prose with zero errors', () => {
    const result = lintProse('预检组件在写入生效前完成读写集交集判定，写集不相交的写入立即并行生效。判定结果与资源占用表一同落盘。')
    expect(result.summary.errors).toBe(0)
    expect(result.summary.warnings).toBe(0)
  })
})
