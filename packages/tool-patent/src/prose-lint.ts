/**
 * Deterministic de-AI prose lint for disclosure chapters: the machine half of
 * the patent-de-ai skill. The skill's features become nine checkable rules —
 * filler, apologetic and colloquial-opener phrases, overlong sentences,
 * inversion rhetoric, triple parallelisms, dense 顿号 enumerations,
 * paragraph-ending summaries, textbook definitions, sentence-initial
 * topic shells, and recurring terms whose first occurrence carries no
 * explanation — each a pure function over the submitted text, so "read like
 * a senior patent engineer" stops being a hope and becomes a gate the model
 * must clear. Rhythm and same-entity renaming (rules 5/9) are left to the
 * checklist: no honest regex exists for them.
 * @module dsh-tool-patent/prose-lint
 */

/** One lint finding: what rule tripped, how badly, and where roughly. */
export interface ProseViolation {
  /** The rule key that tripped (stable identifier). */
  rule: 'cliche' | 'long-sentence' | 'inversion' | 'parallelism' | 'enumeration' | 'paragraph-summary' | 'definition' | 'topic-shell' | 'undefined-term'
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
    undefinedTerms: number
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

/**
 * Recurring-term rule (undefined-term): a noun repeated this often is a backbone
 * concept of the disclosure, so its first occurrence must explain it (the
 * patent-writing-quality skill's 首现即释 discipline). Warning-level and tuned
 * for precision: only CJK windows of 4-12 chars recurring at least three times
 * are considered, patent-meta boilerplate is excluded, and a first occurrence
 * counts as explained when a gloss follows the term or a definition verb sits
 * in the same sentence.
 */
const TERM_MIN_CHARS = 4
const TERM_MAX_CHARS = 12
const TERM_MIN_COUNT = 3

/** Sentence-level definitional cues that satisfy a first-occurrence explanation. */
const TERM_DEFINITION_CUE = /(是指|指的是|称为|称作|下称|简称为|以下简称|记作|记为|定义为|定义成|表示|指代|也就是|即)/

/** Component nouns may also be introduced by the 用于/负责… duty pattern. */
const TERM_COMPONENT_CUE = /(是指|指的是|称为|称作|下称|简称为|以下简称|记作|记为|定义为|定义成|表示|指代|也就是|即|用于|负责|配置为|用以)/

/** Component nouns may also be introduced by the duty pattern above. */
const TERM_COMPONENT = /(模块|组件|单元|装置|插件|节点|子系统|引擎|代理|网关|服务器|客户端|服务|层|器|池|队列|缓存|表|库|树|环|域)$/

/** An appositive gloss right after the term: 仲裁评分（对冲突证据量化裁决的分值）. */
const TERM_GLOSS = /^[（(][^（）()]{4,}[）)]/

/** Windows starting with these particles are prose, not terms. */
const TERM_NOT_FIRST = '一二三四五六七八九十第该此本其各每某所在是为有和与或及并把被将对从向以等之的了这那很更最都不无非已又再还就才只均也太'

/** Windows ending with these particles are prose, not terms. */
const TERM_NOT_LAST = '的了等之在是为有和与或及并把被将对从向以中上下里内外时后前当则而且所该此这那各每某能可会需须使让得着过地很更最都均也就才只还再又已无非不'

/** Term interiors never contain these particles. */
const TERM_NOT_INSIDE = '的之'

/** Windows starting with these verb/function prefixes are prose, not terms. */
const TERM_NOT_FIRST_WORDS = [
  '进行', '采用', '使用', '通过', '基于', '用于', '包括', '包含', '具有', '设有',
  '所述', '对应', '执行', '处理', '生成', '计算', '确定', '判断', '获得', '得到',
  '提供', '实现', '输出', '写入', '读取', '发送', '接收', '返回', '调用', '触发',
  '完成', '存在', '涉及', '属于', '针对', '根据', '依据', '使得', '从而', '以及',
  '并且', '其中', '上述', '其他', '多个', '多种', '一种', '各个', '然后', '随后',
  '接着', '最后', '首先', '其次', '同时', '此外', '因此', '所以', '例如', '比如',
]

/** Patent-meta and boilerplate phrases that are never disclosure terms. */
const TERM_STOPLIST = new Set([
  '现有技术', '背景技术', '技术领域', '技术问题', '技术效果', '技术方案', '技术特征',
  '有益效果', '发明内容', '发明目的', '附图说明', '具体实施方式', '实施方式', '实施例',
  '优选实施例', '权利要求', '说明书', '说明书附图', '摘要附图', '申请文件', '交底书',
  '对比文件', '保护范围', '必要技术特征', '附加技术特征', '从属权利要求', '独立权利要求',
  '本发明', '本申请', '本方案', '本实施例', '该方案', '该系统', '该方法', '该装置',
  '该模块', '所述方法', '所述系统', '所述模块', '所属领域', '本领域技术人员',
  '普通技术人员', '技术人员', '现有方案', '传统方案', '常用方案', '常见方案',
  '相关技术', '解决方案', '改进方案', '整体架构', '整体流程', '工作原理', '协作流程',
  '执行流程', '处理流程', '数据流程', '数据处理', '数据传输', '数据存储', '数据管理',
  '信息系统', '信息处理', '计算机系统', '操作系统', '网络通信', '通信网络', '电子设备',
  '终端设备', '用户终端', '存储介质', '计算机可读存储介质', '存储空间', '计算资源',
  '硬件环境', '软件环境', '应用场景', '使用场景', '实际场景', '具体场景', '应用领域',
  '使用需求', '功能需求', '性能需求', '业务需求', '用户体验', '使用体验', '实际应用',
  '实际使用', '实际需求', '正常运行', '正常使用',
])

/** True when a candidate window reads like prose rather than a term. */
function termShaped(candidate: string): boolean {
  if (TERM_STOPLIST.has(candidate)) return false
  for (const particle of TERM_NOT_INSIDE) if (candidate.includes(particle)) return false
  if (TERM_NOT_FIRST.includes(candidate[0])) return false
  if (TERM_NOT_LAST.includes(candidate.at(-1) ?? '')) return false
  return !TERM_NOT_FIRST_WORDS.some(word => candidate.startsWith(word))
}

/** Every CJK window of TERM_MIN_CHARS..TERM_MAX_CHARS with its occurrence count. */
function countTermWindows(text: string): Map<string, number> {
  const counts = new Map<string, number>()
  for (const run of text.match(/[\u4e00-\u9fff]+/g) ?? []) {
    for (let size = TERM_MIN_CHARS; size <= Math.min(TERM_MAX_CHARS, run.length); size++) {
      for (let start = 0; start + size <= run.length; start++) {
        const window = run.slice(start, start + size)
        counts.set(window, (counts.get(window) ?? 0) + 1)
      }
    }
  }
  return counts
}

/**
 * Recurring term candidates: windows seen at least TERM_MIN_COUNT times that no
 * larger recurring window fully contains with an equal-or-higher count (such
 * fragments only ever occur inside the larger phrase — prose scaffolding, not
 * a term in its own right).
 */
function recurringTerms(text: string): Array<{ term: string; count: number; first: number }> {
  const recurring = [...countTermWindows(text).entries()].filter(([, count]) => count >= TERM_MIN_COUNT)
  const terms: Array<{ term: string; count: number; first: number }> = []
  for (const [term, count] of recurring) {
    if (!termShaped(term)) continue
    const dominates = recurring.some(([other, otherCount]) => other.length > term.length && other.includes(term) && otherCount >= count)
    if (!dominates) terms.push({ term, count, first: text.indexOf(term) })
  }
  return terms
}

/** Bounds of the sentence containing `index`, plus the sentence after it. */
function sentencesAround(text: string, index: number): [string, string] {
  const before = [...text.slice(0, index).matchAll(/[。！？]/g)]
  const lastBoundary = before.at(-1)?.index
  const start = lastBoundary === undefined ? 0 : lastBoundary + 1
  const after = text.slice(index).match(/[。！？]/)
  const afterAt = after?.index
  const end = afterAt === undefined ? text.length : index + afterAt + 1
  const current = text.slice(start, end)
  const rest = text.slice(end)
  const nextEnd = rest.match(/[。！？]/)
  const nextEndAt = nextEnd?.index
  return [current, nextEndAt === undefined ? rest : rest.slice(0, nextEndAt + 1)]
}

/** True when the term's first occurrence reads as explained (gloss or definition verb). */
function explainedAtFirstOccurrence(text: string, term: string, first: number): boolean {
  if (TERM_GLOSS.test(text.slice(first + term.length, first + term.length + 64))) return true
  const [current, next] = sentencesAround(text, first)
  const cue = TERM_COMPONENT.test(term) ? TERM_COMPONENT_CUE : TERM_DEFINITION_CUE
  if (cue.test(current)) return true
  return next.startsWith(term) || (current.endsWith('：') && cue.test(next))
}

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
  // undefined-term: longest candidates first, so a shorter variant contained in
  // an already-reported term is skipped — one warning per concept, not per alias.
  const reported: string[] = []
  for (const { term, count: times, first } of recurringTerms(text).sort((a, b) => b.term.length - a.term.length)) {
    if (reported.some(seen => seen.includes(term))) continue
    if (explainedAtFirstOccurrence(text, term, first)) continue
    reported.push(term)
    violations.push({
      rule: 'undefined-term', severity: 'warning',
      message: `高频术语「${term}」（出现 ${times} 次）首现未见解释——首现处补括注「${term}（一句定义）」或定义句；公知术语先在背景技术交代；已在前文章节定义、本章复用属正常豁免`,
      excerpt: excerptOf(text, first, term.length),
    })
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
    undefinedTerms: count('undefined-term'),
    errors: violations.filter(violation => violation.severity === 'error').length,
    warnings: violations.filter(violation => violation.severity === 'warning').length,
  }
  violations.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'error' ? -1 : 1))
  return { summary, violations }
}
