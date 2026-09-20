import { describe, expect, it } from 'vitest'
import { ABSTRACT_MAX_CHARS, countAbstractChars, lintClaims, parseClaims } from '../src/claims-lint.ts'

const CLEAN = [
  '1. 一种多分区植物生长灯的动态节能控制方法，其特征在于，包括以下步骤：感知各分区环境；按生长阶段决策目标光配方；分区执行调光。',
  '2. 根据权利要求1所述的方法，其特征在于，感知各分区环境包括读取各分区照度与温度。',
  '3. 根据权利要求1所述的方法，其特征在于，按生长阶段决策目标光配方包括查询内置光需求曲线。',
  '4. 根据权利要求2所述的方法，其特征在于，还包括传感失效时回落保守光配方。',
].join('\n')

describe('parseClaims', () => {
  it('splits numbered claims and classifies independent versus dependent', () => {
    const claims = parseClaims(CLEAN)
    expect(claims.map(claim => claim.number)).toEqual([1, 2, 3, 4])
    expect(claims[0]!.kind).toBe('independent')
    expect(claims[1]!.kind).toBe('dependent')
    expect(claims[1]!.references).toEqual([1])
  })

  it('parses the multiple-dependent range citation into the full reference span', () => {
    const claims = parseClaims('1. 独权。\n5. 根据权利要求2至4中任一项所述的方法，其特征在于…')
    expect(claims[1]!.multiDependent).toBe(true)
    expect(claims[1]!.references).toEqual([2, 3, 4])
  })

  it('ignores text before the first claim marker', () => {
    const claims = parseClaims('权利要求书\n\n1. 独权，其特征在于X。')
    expect(claims).toHaveLength(1)
    expect(claims[0]!.text).toContain('1. 独权')
  })
})

describe('lintClaims', () => {
  it('passes a clean draft with the two-part form everywhere', () => {
    const result = lintClaims(CLEAN)
    expect(result.violations).toEqual([])
    expect(result.summary).toEqual({ total: 4, independent: 1, dependent: 3, errors: 0, warnings: 0 })
  })

  it('flags non-consecutive numbering as C1', () => {
    const result = lintClaims('1. 独权，其特征在于X。\n3. 根据权利要求1所述的方法，其特征在于Y。')
    expect(result.violations).toEqual([
      expect.objectContaining({ claim: 3, rule: 'C1', severity: 'error' }),
    ])
  })

  it('flags a self or forward reference as C2', () => {
    const text = [
      '1. 独权，其特征在于X。',
      '2. 根据权利要求3所述的方法，其特征在于Y。',
      '3. 根据权利要求1所述的方法，其特征在于Z。',
    ].join('\n')
    const result = lintClaims(text)
    expect(result.violations).toEqual([
      expect.objectContaining({ claim: 2, rule: 'C2', severity: 'error' }),
    ])
  })

  it('flags a citation of a nonexistent earlier claim as C1', () => {
    const result = lintClaims('1. 独权，其特征在于X。\n2. 根据权利要求9所述的方法，其特征在于Y。')
    expect(result.violations).toEqual([
      expect.objectContaining({ claim: 2, rule: 'C1', severity: 'error' }),
    ])
  })

  it('warns when an independent claim lacks the two-part form marker', () => {
    const result = lintClaims('1. 一种方法，包括步骤A和步骤B。')
    expect(result.violations).toEqual([
      expect.objectContaining({ claim: 1, rule: 'C5', severity: 'warning' }),
    ])
  })

  it('flags a multiple-dependent claim built on another multiple-dependent claim as C4', () => {
    const text = [
      '1. 独权，其特征在于X。',
      '2. 根据权利要求1所述的方法，其特征在于Y。',
      '3. 根据权利要求1所述的方法，其特征在于Z。',
      '4. 根据权利要求2至3中任一项所述的方法，其特征在于W。',
      '5. 根据权利要求2至4中任一项所述的方法，其特征在于V。',
    ].join('\n')
    const result = lintClaims(text)
    expect(result.violations).toEqual([
      expect.objectContaining({ claim: 5, rule: 'C4', severity: 'error' }),
    ])
  })

  it('flags an abstract over the cap as A1 and skips the rule when no abstract is supplied', () => {
    const long = '字'.repeat(ABSTRACT_MAX_CHARS + 1)
    expect(lintClaims(CLEAN, long).violations).toEqual([
      expect.objectContaining({ rule: 'A1', severity: 'error' }),
    ])
    expect(lintClaims(CLEAN).violations).toEqual([])
  })

  it('flags a drawing reference inside a claim as C6', () => {
    const text = '1. 一种控制方法，如图1所示，其特征在于执行分区调光。'
    expect(lintClaims(text).violations).toEqual([
      expect.objectContaining({ claim: 1, rule: 'C6', severity: 'error' }),
    ])
  })

  it('flags promotional wording in the abstract as A2 and passes a technical abstract', () => {
    const promotional = '本发明提供一种国际领先的调光方法，效果最佳。'
    const violations = lintClaims(CLEAN, promotional).violations
    expect(violations).toEqual([expect.objectContaining({ rule: 'A2', severity: 'warning' })])
    expect(violations[0]?.message).toContain('国际领先')
    expect(lintClaims(CLEAN, '本发明提供一种分区调光方法，可降低能耗。').violations).toEqual([])
  })
})

describe('countAbstractChars', () => {
  it('counts every non-whitespace character and tolerates absence', () => {
    expect(countAbstractChars('一种 方法\nX')).toBe(5)
    expect(countAbstractChars(undefined)).toBe(0)
  })
})
