/**
 * Deterministic de-AI prose lint for disclosure chapters: the machine half of
 * the patent-de-ai skill. The skill's features become eight checkable rules —
 * filler, apologetic and colloquial-opener phrases, overlong sentences,
 * inversion rhetoric, triple parallelisms, dense 顿号 enumerations,
 * paragraph-ending summaries, textbook definitions, and sentence-initial
 * topic shells — each a pure function over the submitted text, so "read like
 * a senior patent engineer" stops being a hope and becomes a gate the model
 * must clear. Rhythm and same-entity renaming (rules 5/9) are left to the
 * checklist: no honest regex exists for them.
 * @module dsh-tool-patent/prose-lint
 */

/** One lint finding: what rule tripped, how badly, and where roughly. */
export interface ProseViolation {
  /** The rule key that tripped (stable identifier). */
  rule: 'cliche' | 'long-sentence' | 'inversion' | 'parallelism' | 'enumeration' | 'paragraph-summary' | 'definition' | 'topic-shell'
  /** 'error' rules must be cleared; 'warning' rules are drafting hints. */
  severity: 'error' | 'warning'
  /** What to do about it, in the skill's own terms. */
  message: string
  /** A short excerpt of the offending text (trimmed around the match). */
  excerpt: string
}

/** The lint's folded projection: counts by rule plus the violation list. */
export interface ProseLintResult {
  summary: {
    cliches: number
    longSentences: number
    inversions: number
    parallelisms: number
    enumerations: number
    paragraphSummaries: number
    definitions: number
    topicShells: number
    errors: number
    warnings: number
  }
  violations: ProseViolation[]
}

/** Filler transition phrases the skill bans outright (rule 1, 必删). */
const CLICHES = [
  '更为关键的是', '需要指出的是', '需特别指出', '换言之', '换句话说',
  '值得注意的是', '值得一提的是', '需要注意的是', '这意味着', '这表明', '综上所述',
  '总而言之', '不难发现', '可以看出', '由此可知', '由此可见', '众所周知', '毋庸置疑', '不可否认',
  '说白了', '说穿了', '先说结论',
]

/** Apologetic self-weakening openers (rule 7): the apology goes, the fact stays. */
const APOLOGIES = ['遗憾的是', '不得不承认', '必须承认']

/** Every banned phrase with its own rewrite guidance. */
const CLICHE_RULES = [
  ...CLICHES.map(phrase => ({ phrase, message: `套话转折词「${phrase}」——删掉或改写，直接陈述事实` })),
  ...APOLOGIES.map(phrase => ({ phrase, message: `道歉式措辞「${phrase}」——删掉道歉姿态，改成事实陈述；局限本身照实保留` })),
]

/** A sentence longer than this must be split (rule 2). */
const MAX_SENTENCE_CHARS = 150

/** Consecutive clauses sharing this leading character read as a parallelism (rule 3). */
const PARALLELISM_PREFIX_CHARS = 1
const PARALLELISM_MIN_CLAUSES = 3
const PARALLELISM_MIN_CLAUSE_CHARS = 2

/** Sentences starting with these openers at a paragraph's end feed the reader (rule 4). */
const SUMMARY_OPENERS = /^(这意味着|因此|所以|由此可知|由此可见)/

/** Textbook-style definition openers (rule 6). */
const DEFINITION = /(是指[^。]{0,60}。|被定义为)/

/** Inversion rhetoric (rule 8): set up a misunderstanding, then flip it. */
const INVERSIONS: Array<{ pattern: RegExp; label: string }> = [
  { pattern: /不是[^。！？]{0,40}而是/g, label: '不是A而是B' },
  { pattern: /并非[^。！？]{0,40}而是/g, label: '并非A而是B' },
  { pattern: /与其说[^。！？]{0,40}不如说/g, label: '与其说A不如说B' },
  { pattern: /看似[^。！？]{0,30}实则/g, label: '看似A实则B' },
]

/** 顿号 items per comma-bounded clause above this reads as dense enumeration (rule 3). */
const MAX_DUNHAO_PER_CLAUSE = 2

/** Sentence-initial topic shells (translationese, rule 2). */
const TOPIC_SHELL = /^(对于[^，。！？]{0,24}来说|就[^，。！？]{0,24}而言)/

/** Split text into sentences (。！？ terminators kept attached). */
function sentencesOf(text: string): string[] {
  return text.split(/(?<=[。！？])/).map(sentence => sentence.trim()).filter(sentence => sentence.length > 0)
}

/** Trim one excerpt around an offset for the violation message. */
function excerptOf(text: string, start: number, length: number): string {
  const from = Math.max(0, start - 8)
  const to = Math.min(text.length, start + length + 12)
  const body = text.slice(from, to).replaceAll('\n', ' ')
  return (from > 0 ? '…' : '') + body + (to < text.length ? '…' : '')
}

/**
 * Lint one chapter (or any prose span) against the de-AI rules.
 * @param text - the prose to check.
 * @returns the folded counts and the violation list (errors first).
 */
export function lintProse(text: string): ProseLintResult {
  const violations: ProseViolation[] = []
  for (const { phrase, message } of CLICHE_RULES) {
    let from = 0
    while (true) {
      const index = text.indexOf(phrase, from)
      if (index < 0) break
      violations.push({
        rule: 'cliche', severity: 'error',
        message,
        excerpt: excerptOf(text, index, phrase.length),
      })
      from = index + phrase.length
    }
  }
  for (const { pattern, label } of INVERSIONS) {
    pattern.lastIndex = 0
    let match: RegExpExecArray | null
    while ((match = pattern.exec(text)) !== null) {
      violations.push({
        rule: 'inversion', severity: 'warning',
        message: `翻案腔「${label}」——先立误解再推翻；改为正面直接下判断，真实的技术对比改写后保留全部限定`,
        excerpt: excerptOf(text, match.index, match[0].length),
      })
    }
  }
  let cursor = 0
  for (const sentence of sentencesOf(text)) {
    const start = text.indexOf(sentence, cursor)
    cursor = start + sentence.length
    if (sentence.length > MAX_SENTENCE_CHARS) {
      violations.push({
        rule: 'long-sentence', severity: 'error',
        message: `单句 ${sentence.length} 字（上限 ${MAX_SENTENCE_CHARS}）——拆成 2-3 句，每句最多承载三个信息量`,
        excerpt: excerptOf(text, start, 24),
      })
    }
    const clauses = sentence.split(/[，；、]/).map(clause => clause.trim()).filter(clause => clause.length >= PARALLELISM_MIN_CLAUSE_CHARS)
    const prefixes = new Map<string, number>()
    for (const clause of clauses) {
      const prefix = clause.slice(0, PARALLELISM_PREFIX_CHARS)
      prefixes.set(prefix, (prefixes.get(prefix) ?? 0) + 1)
    }
    for (const [prefix, count] of prefixes) {
      if (count >= PARALLELISM_MIN_CLAUSES) {
        violations.push({
          rule: 'parallelism', severity: 'warning',
          message: `三连排比：${count} 个分句都以「${prefix}」开头——改为直接陈述具体改进点，每个对应一个量化依据`,
          excerpt: excerptOf(text, start, 24),
        })
        break
      }
    }
    const shell = TOPIC_SHELL.exec(sentence)
    if (shell !== null) {
      violations.push({
        rule: 'topic-shell', severity: 'warning',
        message: '前置话题壳（对于…来说/就…而言）——删掉壳子，让主语直接开头',
        excerpt: excerptOf(text, start, 24),
      })
    }
    for (const clause of sentence.split(/[，；]/)) {
      const dunhao = (clause.match(/、/g) ?? []).length
      if (dunhao > MAX_DUNHAO_PER_CLAUSE) {
        violations.push({
          rule: 'enumeration', severity: 'warning',
          message: `顿号罗列过密（${dunhao + 1} 项并列）——能概括就概括，或打散其中一项的句法；部件与配置类必须完整列出的清单可保留`,
          excerpt: excerptOf(text, start, 24),
        })
        break
      }
    }
  }
  for (const paragraph of text.split(/\n{2,}/)) {
    const trimmed = paragraph.trim()
    const lastSentence = sentencesOf(trimmed).at(-1)
    if (lastSentence !== undefined && SUMMARY_OPENERS.test(lastSentence) && trimmed.includes(lastSentence)) {
      violations.push({
        rule: 'paragraph-summary', severity: 'warning',
        message: '段末总结句（这意味着/因此…）——删掉，让事实陈述自己说话',
        excerpt: excerptOf(trimmed, Math.max(0, trimmed.length - 24), 24),
      })
    }
    const definition = DEFINITION.exec(paragraph)
    if (definition !== null) {
      violations.push({
        rule: 'definition', severity: 'warning',
        message: '教科书定义口吻（是指/被定义为）——背景技术应从具体使用场景讲起，精确定义留给技术方案章节',
        excerpt: excerptOf(paragraph, definition.index, 20),
      })
    }
  }
  const count = (rule: ProseViolation['rule']): number => violations.filter(violation => violation.rule === rule).length
  const summary = {
    cliches: count('cliche'),
    longSentences: count('long-sentence'),
    inversions: count('inversion'),
    parallelisms: count('parallelism'),
    enumerations: count('enumeration'),
    paragraphSummaries: count('paragraph-summary'),
    definitions: count('definition'),
    topicShells: count('topic-shell'),
    errors: violations.filter(violation => violation.severity === 'error').length,
    warnings: violations.filter(violation => violation.severity === 'warning').length,
  }
  violations.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'error' ? -1 : 1))
  return { summary, violations }
}
