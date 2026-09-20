import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { formatSetupReport, checkSetupChannels, type SetupChannel } from '../src/setup-check.ts'
import * as ToolPatent from '../src/index.ts'

/** Per-test probe state the mocked process boundaries read. */
const state = vi.hoisted(() => ({
  dockerVersion: true,
  images: new Map<string, boolean | null>(),
  files: new Map<string, boolean>(),
  fileText: new Map<string, string>(),
  reachable: true,
}))

vi.mock('node:child_process', () => ({
  execFile: ((command: string, args: readonly string[]) => {
    if (command === 'docker' && args[0] === '--version') {
      return state.dockerVersion
        ? Promise.resolve({ stdout: 'Docker version 27', stderr: '' })
        : Promise.reject(Object.assign(new Error('enoent'), { code: 'ENOENT' }))
    }
    if (command === 'docker' && args[0] === 'image' && args[1] === 'inspect') {
      const image = args[2] ?? ''
      const verdict = state.images.get(image)
      if (verdict === true) return Promise.resolve({ stdout: '[]', stderr: '' })
      if (verdict === false) return Promise.reject(Object.assign(new Error('no such'), { code: 1, stderr: `Error: No such image: ${image}` }))
      return Promise.reject(Object.assign(new Error('daemon down'), { code: 1, stderr: 'cannot connect to the Docker daemon' }))
    }
    return Promise.reject(Object.assign(new Error('enoent'), { code: 'ENOENT' }))
  }) as never,
}))

vi.mock('node:util', () => ({ promisify: (fn: unknown) => fn }))

vi.mock('node:fs', () => ({
  existsSync: (path: unknown) => {
    const key = String(path).replaceAll('\\', '/')
    if (state.files.has(key)) return state.files.get(key) === true
    return state.fileText.has(key)
  },
  readFileSync: (path: unknown) => {
    const key = String(path).replaceAll('\\', '/')
    if (state.fileText.has(key)) return state.fileText.get(key)
    throw new Error('ENOENT')
  },
}))

const ENV_KEYS = ['DSH_PATENT_SERVICES_DIR', 'DSH_PATENT_SERVICES', 'DSH_DRAWIO_BIN', 'DSH_EXPERIMENT_ALLOW_ANY_COMMAND', 'HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'] as const
const originalFetch = globalThis.fetch

beforeEach(() => {
  // The host machine carries real values for these keys; the specs must
  // control the environment completely, so stub every key away per run.
  for (const key of ENV_KEYS) vi.stubEnv(key, undefined)
  vi.stubEnv('DSH_HOME', '/fake-home')
})

afterEach(() => {
  vi.unstubAllEnvs()
  state.dockerVersion = true
  state.images = new Map()
  state.files = new Map()
  state.fileText = new Map()
  state.reachable = true
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

afterAll(() => {
  globalThis.fetch = originalFetch
})

function channel(status: SetupChannel['status'], gates: SetupChannel['gates'], line: string): SetupChannel {
  return { status, gates, line }
}

describe('formatSetupReport', () => {
  it('reports all-ready when no channel failed', () => {
    const report = formatSetupReport([
      channel('ok', 'MCP 服务', '✅ MCP 服务：…'),
      channel('info', '', 'ℹ️ 代理：…'),
    ])
    expect(report).toContain('全部就绪')
    expect(report).toContain('✅ MCP 服务：…')
  })

  it('names the limited capabilities in the conclusion when channels failed', () => {
    const report = formatSetupReport([
      channel('fail', 'MCP 服务', '❌ MCP 服务未启用…'),
      channel('fail', '查新检索', '❌ 检索通道…'),
      channel('ok', '附图渲染', '✅ docker：…'),
    ])
    expect(report).toContain('以下通道受限')
    expect(report).toContain('MCP 服务、查新检索受限')
  })

  it('dedupes the gated capability names', () => {
    const report = formatSetupReport([
      channel('fail', '附图渲染', 'a'),
      channel('fail', '附图渲染', 'b'),
    ])
    expect(report).toContain('附图渲染受限')
  })
})

describe('checkSetupChannels', () => {
  it('names the disabled MCP row with the enabling step when no env var is set', async () => {
    state.reachable = true
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('DSH_PATENT_SERVICES_DIR')
    expect(mcp?.line).toContain('本工具不受影响')
  })

  it('accepts source mode when the directory carries pyproject.toml', async () => {
    process.env.DSH_PATENT_SERVICES_DIR = 'G:/src/patent-services'
    state.files.set('G:/src/patent-services/pyproject.toml', true)
    const channels = await checkSetupChannels()
    expect(channels.find(c => c.gates === 'MCP 服务')?.status).toBe('ok')
  })

  it('fails source mode when the directory lacks pyproject.toml', async () => {
    process.env.DSH_PATENT_SERVICES_DIR = 'G:/wrong'
    const channels = await checkSetupChannels()
    expect(channels.find(c => c.gates === 'MCP 服务')?.status).toBe('fail')
    expect(channels.find(c => c.gates === 'MCP 服务')?.line).toContain('pyproject.toml')
  })

  it('accepts wheel mode through DSH_PATENT_SERVICES', async () => {
    process.env.DSH_PATENT_SERVICES = '1'
    const channels = await checkSetupChannels()
    expect(channels.find(c => c.gates === 'MCP 服务')?.status).toBe('ok')
  })

  it('fails docker, skips the image probes, and falls through to drawio discovery', async () => {
    state.dockerVersion = false
    const channels = await checkSetupChannels()
    expect(channels.find(c => c.line.startsWith('❌ docker'))?.status).toBe('fail')
    expect(channels.some(c => c.line.includes('镜像'))).toBe(false)
    expect(channels.find(c => c.line.includes('draw.io 原生 CLI 未检出'))?.status).toBe('info')
  })

  it('marks a missing image as a pre-pull warning and unknown probe states too', async () => {
    state.images.set('q771103517/dsh-patent:latest', false)
    state.images.set('q771103517/dsh-patent-experiment:latest', undefined as unknown as boolean)
    const channels = await checkSetupChannels()
    expect(channels.find(c => c.line.includes('渲染镜像未拉取'))?.status).toBe('warn')
    expect(channels.find(c => c.line.includes('实验镜像状态未知'))?.status).toBe('warn')
  })

  it('validates an explicit DSH_DRAWIO_BIN strictly', async () => {
    process.env.DSH_DRAWIO_BIN = 'D:/tools/draw.io.exe'
    state.files.set('D:/tools/draw.io.exe', false)
    const channels = await checkSetupChannels()
    const drawio = channels.find(c => c.line.includes('draw.io 原生 CLI'))
    expect(drawio?.status).toBe('fail')
    expect(drawio?.line).toContain('不会回退')
  })

  it('reports unreachable search with the proxy guidance', async () => {
    state.reachable = false
    globalThis.fetch = async () => { throw new Error('network down') }
    const channels = await checkSetupChannels()
    const search = channels.find(c => c.gates === '查新检索')
    expect(search?.status).toBe('fail')
    expect(search?.line).toContain('代理')
  })

  it('reports the widened command policy and proxy variables', async () => {
    process.env.DSH_EXPERIMENT_ALLOW_ANY_COMMAND = '1'
    process.env.HTTPS_PROXY = 'http://127.0.0.1:7890'
    const channels = await checkSetupChannels()
    expect(channels.some(c => c.line.includes('已放宽'))).toBe(true)
    expect(channels.some(c => c.line.includes('HTTPS_PROXY'))).toBe(true)
  })
})

describe('settings-file awareness', () => {
  it('parses the flat settings file and lets it enable the command policy', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', '# optional settings\nexperiment_allow_any_command: true\ndrawio_bin: D:/tools/draw.io.exe\n')
    const channels = await checkSetupChannels()
    expect(channels.some(c => c.line.includes('已放宽'))).toBe(true)
    const drawio = channels.find(c => c.line.includes('draw.io 原生 CLI'))
    expect(drawio?.line).toContain('D:/tools/draw.io.exe')
  })

  it('treats yaml false as unset and env as the winner', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'experiment_allow_any_command: false\n')
    process.env.DSH_EXPERIMENT_ALLOW_ANY_COMMAND = '1'
    const channels = await checkSetupChannels()
    expect(channels.some(c => c.line.includes('已放宽'))).toBe(true)
  })

  it('accepts an enabled mcp-patent-services row in the home patch as the config-file mode', async () => {
    state.fileText.set('/fake-home/cordis.patch.yml', '- id: web-search-deepseek\n  disabled: false\n- id: mcp-patent-services\n  name: dsh-mcp-client\n  disabled: false\n  config:\n    serverName: patent\n')
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('ok')
    expect(mcp?.line).toContain('配置文件模式')
  })

  it('rejects a disabled or absent home-patch row with the config-file guidance', async () => {
    state.fileText.set('/fake-home/cordis.patch.yml', '- id: mcp-patent-services\n  disabled: true\n')
    let channels = await checkSetupChannels()
    expect(channels.find(c => c.gates === 'MCP 服务')?.status).toBe('fail')
    state.fileText.delete('/fake-home/cordis.patch.yml')
    channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('cordis.patch.yml')
  })
})

describe('patent_setup_check registration', () => {
  interface ToolShape { name: string }

  it('registers the host-plane tool beside the loop tool', () => {
    const registered: ToolShape[] = []
    const ctx = {
      tools: { register: vi.fn((definition: ToolShape) => { registered.push(definition); return () => {} }) },
      commands: { register: vi.fn(() => () => {}) },
      effect: (callback: () => Generator): void => {
        for (const step of callback()) void step
      },
    }
    ToolPatent.apply(ctx as never)
    expect(registered.some(tool => tool.name === 'patent_setup_check')).toBe(true)
    expect(registered.some(tool => tool.name === 'patent_loop')).toBe(true)
  })
})
