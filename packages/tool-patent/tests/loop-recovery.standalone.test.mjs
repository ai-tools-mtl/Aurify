// Run without the host monorepo:
// node --test packages/tool-patent/tests/loop-recovery.standalone.test.mjs
// Only the host registration/message wrappers are substituted. The command,
// tool, stage assessor, fingerprint and filesystem operations are real.
import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../../../scripts/package.json', import.meta.url))
const { build } = require('esbuild')
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const tempBase = resolve(tmpdir())
let root
let plugin
let fingerprint

before(async () => {
  root = await mkdtemp(join(tempBase, 'aurify-loop-recovery-'))
  const result = await build({
    entryPoints: {
      plugin: join(packageRoot, 'src/index.ts'),
      fingerprint: join(packageRoot, 'src/fingerprint.ts'),
    },
    outdir: join(root, 'bundle'),
    bundle: true,
    write: false,
    platform: 'node',
    format: 'esm',
    target: 'node20',
    tsconfigRaw: {},
    plugins: [{
      name: 'host-registration-wrappers',
      setup(build) {
        build.onResolve({ filter: /^@deepseek-ai\// }, args => ({ path: args.path, namespace: 'host' }))
        build.onLoad({ filter: /.*/, namespace: 'host' }, args => {
          const contents = {
            '@deepseek-ai/dsh-tools': 'export const defineTool = definition => definition',
            '@deepseek-ai/dsh-llm': 'export const createUserMessage = message => message',
            '@deepseek-ai/dsh-mcp-client': 'export const name = "unused-mcp-client"',
          }[args.path]
          if (contents === undefined) throw new Error(`Unexpected runtime host dependency: ${args.path}`)
          return { contents, loader: 'js' }
        })
      },
    }],
  })
  const load = async name => {
    const file = result.outputFiles.find(file => file.path.endsWith(`${name}.js`))
    assert.ok(file, `Missing ${name} bundle`)
    return import(`data:text/javascript;base64,${Buffer.from(file.text).toString('base64')}`)
  }
  plugin = await load('plugin')
  fingerprint = (await load('fingerprint')).sourceFingerprint
})

after(async () => {
  if (root === undefined) return
  const child = relative(tempBase, root)
  assert.ok(child.startsWith('aurify-loop-recovery-') && !child.includes(sep))
  await rm(root, { recursive: true, force: true })
})

async function mount() {
  const tools = new Map()
  const commands = new Map()
  const followups = []
  // Avoid user settings and optional MCP startup; no setup or network tools run.
  const previous = process.env.DSH_PATENT_SERVICES
  process.env.DSH_PATENT_SERVICES = 'standalone-test-no-spawn'
  try {
    await plugin.apply({
      tools: { register(definition) { tools.set(definition.name, definition) } },
      commands: { register(definition) { commands.set(definition.name, definition) } },
      effect(callback) { for (const step of callback()) void step },
      plugin() { throw new Error('Unexpected MCP startup') },
    })
  } finally {
    if (previous === undefined) delete process.env.DSH_PATENT_SERVICES
    else process.env.DSH_PATENT_SERVICES = previous
  }
  return {
    tool: tools.get('patent_loop'),
    command: commands.get('patent-loop'),
    followups,
    agent: {
      session: { header: { cwd: root } },
      followup(message) { followups.push(message) },
    },
  }
}

async function completedProject(name, status) {
  const dir = join(root, name)
  await mkdir(dir)
  for (const subdir of ['chapters', 'figures', 'review', 'exports', 'reference']) {
    await mkdir(join(dir, subdir))
  }
  await writeFile(join(dir, 'patent.yml'), 'formatVersion: 1\nname: 验收夹具\nstatus: drafting\n')
  await writeFile(join(dir, 'brief.md'), [
    '# 评估', `状态：${status}；评估版本：v1；证据记录版本：v1；待补：公开日期。`,
    '## 技术领域', '数据存储技术。',
    '## 背景技术', '现有处理流程存在冗余。',
    '## 技术问题', '减少处理冗余。',
    '## 发明内容', '使用分阶段索引和批处理机制。',
    '## 有益效果', '减少处理冗余并改善响应。',
  ].join('\n\n'))
  const body = '这里是用于状态机验证的技术正文，完整描述分阶段索引与批处理的组合及其实现。'
  for (const name of ['01-name', '02-field', '03-background', '04-problem', '05-solution', '06-effect', '07-key-points', '08-drawings']) {
    await writeFile(join(dir, 'chapters', `${name}.md`), name === '01-name'
      ? '一种采用分阶段索引以及批处理机制的数据存储方法'
      : name === '08-drawings' ? `图1 为处理流程示意图。\n${body}` : body)
  }
  await writeFile(join(dir, 'figures', '图1.png'), 'fixture')
  await writeFile(join(dir, 'reference', 'prior-art.md'), '证据记录版本：v1\n')
  const digest = await fingerprint(dir)
  await writeFile(join(dir, 'review', 'project.review.md'), `**总分**：81 / 100\n> 源指纹：${digest}\n`)
  await writeFile(join(dir, 'exports', '验收夹具-交底书.docx'), 'fixture')
  await writeFile(join(dir, 'exports', '验收夹具-交底书.fingerprint'), digest)
  return dir
}

test('completed slash command still injects recovery for deferred and stale evaluations', async () => {
  for (const status of ['暂缓评估', '待重评']) {
    const dir = await completedProject(`done-${status}`, status)
    const runtime = await mount()
    const result = await runtime.command.handler({ rawInput: dir, agent: runtime.agent })
    assert.equal(result.kind, 'success')
    assert.match(result.text, /评估记录核对/)
    assert.equal(runtime.followups.length, 1)
    const prompt = runtime.followups[0].content[0].text
    assert.match(prompt, /当前阶段：done/)
    assert.match(prompt, /brief\.md 与 reference\//)
    assert.match(prompt, /包括 done/)
    assert.match(prompt, /适用版本与未清事项/)
    const state = await runtime.tool.execute({ project_dir: dir }, {})
    assert.equal(state.complete, true)
    assert.match(state.directive, /评估状态由技能维护/)
  }
})

test('evidence recovery updates invalidate artifacts and keep recovery available in review', async () => {
  const dir = await completedProject('evidence-update', '已形成建议')
  const runtime = await mount()
  const before = await fingerprint(dir)
  await writeFile(join(dir, 'reference', 'prior-art.md'), '证据记录版本：v2\n新增影响结论的文献。\n')
  // Reference files are deliberately outside the fingerprint contract. Skills
  // must sync the impact and state to brief.md; the assessor must not pretend
  // to have detected or completed this semantic evaluation itself.
  assert.equal(await fingerprint(dir), before)
  assert.equal((await runtime.tool.execute({ project_dir: dir }, {})).complete, true)
  const brief = await readFile(join(dir, 'brief.md'), 'utf8')
  await writeFile(join(dir, 'brief.md'), brief.replace('已形成建议', '待重评').replaceAll('v1', 'v2'))
  const state = await runtime.tool.execute({ project_dir: dir }, {})
  assert.equal(state.complete, false)
  assert.equal(state.stage, 'review')
  assert.ok(state.gaps.some(gap => gap.includes('源指纹')))
  assert.match(state.directive, /无论当前材料阶段/)
  await runtime.command.handler({ rawInput: dir, agent: runtime.agent })
  assert.equal(runtime.followups.length, 1)
  assert.match(runtime.followups[0].content[0].text, /当前阶段：review/)
  assert.match(runtime.followups[0].content[0].text, /恢复不受 init\/align 限制/)

  // Stand in for a completed reevaluation, fresh review and re-export. The
  // command must return to delivery without changing source records itself.
  const updated = await readFile(join(dir, 'brief.md'), 'utf8')
  await writeFile(join(dir, 'brief.md'), updated.replace('待重评', '已形成建议'))
  const refreshed = await fingerprint(dir)
  await writeFile(join(dir, 'review', 'project.review.md'), `**总分**：81 / 100\n> 源指纹：${refreshed}\n`)
  await writeFile(join(dir, 'exports', '验收夹具-交底书.fingerprint'), refreshed)
  assert.equal((await runtime.tool.execute({ project_dir: dir }, {})).complete, true)
  await runtime.command.handler({ rawInput: dir, agent: runtime.agent })
  assert.equal(runtime.followups.length, 2)
  assert.match(runtime.followups[1].content[0].text, /当前阶段：done/)
  assert.equal(await fingerprint(dir), refreshed)
})

test('new projects retain the environment and user-choice gates', async () => {
  const dir = join(root, 'new-project')
  await mkdir(dir)
  const runtime = await mount()
  const state = await runtime.tool.execute({ project_dir: dir }, {})
  assert.equal(state.stage, 'init')
  assert.equal(state.complete, false)
  assert.match(state.directive, /patent_setup_check/)
  assert.match(state.directive, /除检索通道外必须修复复检/)
  assert.match(state.directive, /用户已授权带缺口继续材料工作/)
  assert.match(state.directive, /未执行环节如实注明/)
})
