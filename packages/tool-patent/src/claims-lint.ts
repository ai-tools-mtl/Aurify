/**
 * Deterministic claims-and-abstract linter for a Chinese patent application
 * draft (CNIPA conventions). A pure function of its arguments: the model
 * supplies the drafted claims text (and the optional abstract text) and
 * receives per-claim structure and rule violations, mirroring how the
 * coverage scorer gates the Init dialogue.
 *
 * The rules are statutory-format minimums, not substantive examination:
 * numbering (C1), dependent-claim backward reference (C2), citation form
 * (C3), the multiple-dependent-reference base restriction (C4), the two-part
 * form hint for independent claims (C5), the ban on drawing references
 * inside claims (C6), the abstract length cap (A1), and the abstract
 * promotional-wording hint (A2).
 * @module
 */

/** One parsed claim's structure, derived from its citation prefix. */
export interface ParsedClaim {
  /** The claim's leading number. */
  number: number
  /** The claim's full text (marker included), trimmed. */
  text: string
  /** Independent (no citation prefix) or dependent (cites earlier claims). */
  kind: 'independent' | 'dependent'
  /** Claim numbers cited in the prefix, ascending as written. */
  references: number[]
  /** True when the prefix selects from several claims (任一项 form). */
  multiDependent: boolean
}

/** One rule violation; `claim` is absent for whole-document rules (A1). */
export interface ClaimViolation {
  claim?: number
  rule: string
  severity: 'error' | 'warning'
  message: string
}

/** Lint result: parsed claims, violations, and a count summary. */
export interface ClaimsLintResult {
  claims: ParsedClaim[]
  violations: ClaimViolation[]
  summary: {
    total: number
    independent: number
    dependent: number
    errors: number
    warnings: number
  }
}

/** Abstract hard cap in characters (细则: 说明书摘要不超过 300 个字). */
export const ABSTRACT_MAX_CHARS = 300

/** Drawing references are banned inside claims (细则): the claims must stand on wording alone. */
const DRAWING_REFERENCE = /如\s*附?\s*图\s*(?:\d+|所示)/

/** Promotional wording the abstract must not carry (细则: 不得使用商业性宣传用语); hint-level because context decides. */
const PROMOTIONAL_WORDS = ['最先进', '国际领先', '业内领先', '首创', '最佳', '最好', '最优', '完美']

const CLAIM_MARKER = /(?:^|\n)\s*(\d+)[.、．]\s*/g
const SINGLE_CITATION = /^根据权利要求(\d+)所述的/
const RANGE_CITATION = /^根据权利要求(\d+)[至到\-—](\d+)中任一项所述的/
/** Count CJK characters and letters/digits alike; exclude whitespace and markup. */
const COUNTED_CHARS = /[^\s]/

/**
 * Split the claims text into numbered claims. Text before the first marker is
 * ignored (headings like "权利要求书"); claims may span several lines.
 * @param claimsText - the drafted claims section.
 * @returns claims in document order; empty when no numbered claim is found.
 */
export function parseClaims(claimsText: string): ParsedClaim[] {
  const claims: ParsedClaim[] = []
  CLAIM_MARKER.lastIndex = 0
  let match: RegExpExecArray | null
  const spans: Array<{ number: number; start: number; textStart: number }> = []
  while ((match = CLAIM_MARKER.exec(claimsText)) !== null) {
    spans.push({ number: Number(match[1]), start: match.index, textStart: CLAIM_MARKER.lastIndex })
  }
  for (let index = 0; index < spans.length; index += 1) {
    const span = spans.at(index)
    if (span === undefined) continue
    const next = spans.at(index + 1)
    const end = next === undefined ? claimsText.length : next.start
    const text = claimsText.slice(span.start, end).trim()
    const body = claimsText.slice(span.textStart, end).trim()
    const range = RANGE_CITATION.exec(body)
    const single = range === null ? SINGLE_CITATION.exec(body) : null
    if (range !== null) {
      const from = Number(range[1])
      const to = Number(range[2])
      const references: number[] = []
      for (let n = Math.min(from, to); n <= Math.max(from, to); n += 1) references.push(n)
      claims.push({ number: span.number, text, kind: 'dependent', references, multiDependent: true })
    } else if (single !== null) {
      claims.push({ number: span.number, text, kind: 'dependent', references: [Number(single[1])], multiDependent: false })
    } else {
      claims.push({ number: span.number, text, kind: 'independent', references: [], multiDependent: false })
    }
  }
  return claims
}

/**
 * Count the abstract's chargeable characters: every non-whitespace character
 * (Chinese convention counts each character, punctuation included).
 * @param abstractText - the drafted abstract, or undefined when not supplied.
 * @returns the chargeable character count; 0 for absent input.
 */
export function countAbstractChars(abstractText: string | undefined): number {
  return (abstractText ?? '').split('').filter(char => COUNTED_CHARS.test(char)).length
}

/**
 * Lint a drafted claims section (and optional abstract) against the CNIPA
 * format minimums.
 * @param claimsText - the claims section text.
 * @param abstractText - the abstract text; the A1 rule is skipped when omitted.
 * @returns parsed claims, violations, and the count summary.
 */
export function lintClaims(claimsText: string, abstractText?: string): ClaimsLintResult {
  const claims = parseClaims(claimsText)
  const violations: ClaimViolation[] = []
  claims.forEach((claim, index) => {
    if (claim.number !== index + 1) {
      violations.push({
        claim: claim.number,
        rule: 'C1',
        severity: 'error',
        message: `编号不连续：第 ${index + 1} 条权利要求的编号是 ${claim.number}，应为 ${index + 1}。`,
      })
    }
    for (const reference of claim.references) {
      const target = claims.find(other => other.number === reference)
      if (target === undefined) {
        violations.push({
          claim: claim.number,
          rule: 'C1',
          severity: 'error',
          message: `引用的权利要求 ${reference} 不存在。`,
        })
        continue
      }
      if (reference >= claim.number) {
        violations.push({
          claim: claim.number,
          rule: 'C2',
          severity: 'error',
          message: `引用了自身或更晚的权利要求 ${reference}；从属权利要求只能引用在前的权利要求。`,
        })
      }
      if (claim.multiDependent && target.multiDependent) {
        violations.push({
          claim: claim.number,
          rule: 'C4',
          severity: 'error',
          message: `多项从属权利要求引用了权利要求 ${reference}，而它本身也是多项从属权利要求；多项从属权利要求不得作为另一多项从属权利要求的基础。`,
        })
      }
    }
    if (claim.references.length > 1 && !claim.multiDependent) {
      violations.push({
        claim: claim.number,
        rule: 'C3',
        severity: 'error',
        message: '引用了多项权利要求但未使用"根据权利要求N至M中任一项所述的"择一引用形式。',
      })
    }
    if (claim.kind === 'independent' && !claim.text.includes('其特征在于')) {
      violations.push({
        claim: claim.number,
        rule: 'C5',
        severity: 'warning',
        message: '独立权利要求未使用两部分式（未出现"其特征在于"）；改进型发明应当采用前序部分+特征部分写法。',
      })
    }
    if (DRAWING_REFERENCE.test(claim.text)) {
      violations.push({
        claim: claim.number,
        rule: 'C6',
        severity: 'error',
        message: '权利要求中引用了附图（如图N所示）——权利要求应当用文字独立表述，附图引用只属于说明书。',
      })
    }
  })
  if (abstractText !== undefined) {
    const chars = countAbstractChars(abstractText)
    if (chars > ABSTRACT_MAX_CHARS) {
      violations.push({
        rule: 'A1',
        severity: 'error',
        message: `说明书摘要 ${chars} 字，超过 ${ABSTRACT_MAX_CHARS} 字上限。`,
      })
    }
    const promotional = PROMOTIONAL_WORDS.filter(word => abstractText.includes(word))
    if (promotional.length > 0) {
      violations.push({
        rule: 'A2',
        severity: 'warning',
        message: `摘要含商业性宣传用语（${promotional.join('、')}）——摘要只写技术内容，宣传性评价删掉或改为客观限定。`,
      })
    }
  }
  return {
    claims,
    violations,
    summary: {
      total: claims.length,
      independent: claims.filter(claim => claim.kind === 'independent').length,
      dependent: claims.filter(claim => claim.kind === 'dependent').length,
      errors: violations.filter(violation => violation.severity === 'error').length,
      warnings: violations.filter(violation => violation.severity === 'warning').length,
    },
  }
}
