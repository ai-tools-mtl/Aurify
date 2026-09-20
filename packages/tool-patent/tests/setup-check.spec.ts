import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { checkSetupChannels, formatSetupReport, launchBlockage, markSettingsMcpLoaded, resetSettingsMcpLoadedForTests, type SetupChannel } from '../src/setup-check.ts'
import * as ToolPatent from '../src/index.ts'

/** Per-test probe state the mocked process boundaries read. */
const state = vi.hoisted(() => ({
  dockerVersion: true,
  uv: true,
  uvx: true,
  wheelTool: false,
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
    if ((command === 'uv' || command === 'uvx') && args[0] === '--version') {
      const ready = command === 'uv' ? state.uv : state.uvx
      return ready
        ? Promise.resolve({ stdout: `${command} 0.5`, stderr: '' })
        : Promise.reject(Object.assign(new Error('enoent'), { code: 'ENOENT' }))
    }
    if (command === 'uv' && args[0] === 'tool' && args[1] === 'list') {
      return Promise.resolve({
        stdout: state.wheelTool ? 'deepseek-harness-patent-services v0.1.0\n  - patent-services\n' : '',
        stderr: '',
      })
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
  state.uv = true
  state.uvx = true
  state.wheelTool = false
  state.images = new Map()
  state.files = new Map()
  state.fileText = new Map()
  state.reachable = true
  globalThis.fetch = originalFetch
  resetSettingsMcpLoadedForTests()
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
    state.wheelTool = true
    const channels = await checkSetupChannels()
    expect(channels.find(c => c.gates === 'MCP 服务')?.status).toBe('ok')
  })

  it('fails wheel mode through DSH_PATENT_SERVICES when the wheel is not installed', async () => {
    process.env.DSH_PATENT_SERVICES = '1'
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('uv tool install')
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
    expect(mcp?.line).toContain('patent-services.yaml')
    expect(mcp?.line).toContain('mcp_enabled')
  })

  it('accepts the settings file mcp keys as the single-file mode when loaded this boot', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_project_dir: G:/src/patent-services\n')
    state.files.set('G:/src/patent-services/pyproject.toml', true)
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('ok')
    expect(mcp?.line).toContain('已装载')
    expect(mcp?.line).toContain('mcp_project_dir')
  })

  it('refuses a false green light when the settings file was written after boot', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_project_dir: G:/src/patent-services\n')
    state.files.set('G:/src/patent-services/pyproject.toml', true)
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('待重启')
    expect(mcp?.line).toContain('重启整个桌面壳')
    expect(mcp?.line).toContain('仅新开会话无效')
  })

  it('fails the settings source mode on a relative project dir', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_project_dir: patent-services\n')
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('绝对路径')
  })

  it('fails the settings source mode when the directory lacks pyproject.toml', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_project_dir: G:/wrong\n')
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('pyproject.toml')
  })

  it('fails the settings source mode when uv is not on PATH', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_project_dir: G:/src/patent-services\n')
    state.files.set('G:/src/patent-services/pyproject.toml', true)
    state.uv = false
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('uv')
  })

  it('fails the settings wheel mode when uvx is not on PATH', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_wheel: true\n')
    state.uvx = false
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('uvx')
  })

  it('parses quoted values and trailing comments the way the python yaml loader would', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true  # enabled by the setup flow\nmcp_project_dir: "G:/src/patent-services"\n')
    state.files.set('G:/src/patent-services/pyproject.toml', true)
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('ok')
  })

  it('accepts capitalized yaml booleans for mcp_enabled', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: True\nmcp_wheel: true\n')
    state.wheelTool = true
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    expect(channels.find(c => c.gates === 'MCP 服务')?.line).toContain('mcp_wheel')
  })

  it('rejects mcp_enabled without a backend key', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\n')
    const channels = await checkSetupChannels()
    expect(channels.find(c => c.gates === 'MCP 服务')?.status).toBe('fail')
  })

  it('fails the settings wheel mode when the wheel is not installed as a uv tool', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_wheel: true\n')
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('uv tool install')
    expect(mcp?.line).toContain('未发布 PyPI')
  })

  it('accepts the settings wheel mode when the wheel is installed as a uv tool', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_wheel: true\n')
    state.wheelTool = true
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('ok')
    expect(mcp?.line).toContain('已装载')
  })

  it('treats a falsy mcp_project_dir as unset and falls through to the wheel key', async () => {
    state.fileText.set('/fake-home/patent-services.yaml', 'mcp_enabled: true\nmcp_project_dir: false\nmcp_wheel: true\n')
    state.wheelTool = true
    markSettingsMcpLoaded()
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('ok')
    expect(mcp?.line).toContain('mcp_wheel')
  })

  it('rejects a relative DSH_PATENT_SERVICES_DIR in the env mode', async () => {
    process.env.DSH_PATENT_SERVICES_DIR = 'relative/checkout'
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('绝对路径')
  })
})

describe('launchBlockage', () => {
  it('rejects a relative source dir and a dir without pyproject, passes a valid one, never blocks wheel mode', () => {
    expect(launchBlockage({ mode: 'wheel', command: 'uvx', args: [] })).toBeNull()
    expect(launchBlockage({ mode: 'source', command: 'uv', args: [], projectDir: 'relative/path' })).toContain('绝对路径')
    expect(launchBlockage({ mode: 'source', command: 'uv', args: [], projectDir: 'G:/nope' })).toContain('pyproject.toml')
    state.files.set('G:/ok/pyproject.toml', true)
    expect(launchBlockage({ mode: 'source', command: 'uv', args: [], projectDir: 'G:/ok' })).toBeNull()
  })
})

describe('the plugin loads the MCP client from the settings file', () => {
  interface ToolShape { name: string }
  interface PluginCall { module: unknown; config: Record<string, unknown> }

  async function mount(options: { env?: Record<string, string>; yaml?: string; pluginError?: string }): Promise<PluginCall[]> {
    const calls: PluginCall[] = []
    const registered: ToolShape[] = []
    for (const [k, v] of Object.entries(options.env ?? {})) vi.stubEnv(k, v)
    if (options.yaml !== undefined) state.fileText.set('/fake-home/patent-services.yaml', options.yaml)
    const ctx = {
      tools: { register: vi.fn((d: ToolShape) => { registered.push(d); return () => {} }) },
      commands: { register: vi.fn(() => () => {}) },
      plugin: vi.fn(async (module: unknown, config: Record<string, unknown>) => {
        if (options.pluginError !== undefined) throw new Error(options.pluginError)
        calls.push({ module, config })
      }),
      effect: (callback: () => Generator): void => {
        for (const step of callback()) void step
      },
    }
    await ToolPatent.apply(ctx as never)
    expect(registered.some(t => t.name === 'patent_loop')).toBe(true)
    return calls
  }

  it('loads uv with the settings project dir when nothing else enabled the row', async () => {
    state.files.set('G:/src/patent-services/pyproject.toml', true)
    const calls = await mount({ yaml: 'mcp_enabled: true\nmcp_project_dir: G:/src/patent-services\n' })
    expect(calls).toHaveLength(1)
    expect(calls[0]?.config).toMatchObject({ transport: 'stdio', serverName: 'patent', command: 'uv' })
    expect(calls[0]?.config.args).toEqual(['run', '--project', 'G:/src/patent-services', 'python', '-m', 'patent_services'])
  })

  it('refuses to spawn a relative project dir and records the readable cause', async () => {
    const calls = await mount({ yaml: 'mcp_enabled: true\nmcp_project_dir: src/patent-services\n' })
    expect(calls).toHaveLength(0)
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.line).toContain('绝对路径')
  })

  it('loads uvx for the wheel mode', async () => {
    const calls = await mount({ yaml: 'mcp_enabled: true\nmcp_wheel: true\n' })
    expect(calls).toHaveLength(1)
    expect(calls[0]?.config).toMatchObject({ command: 'uvx' })
  })

  it('loads the wheel mode for a capitalized yaml boolean too', async () => {
    const calls = await mount({ yaml: 'mcp_enabled: True\nmcp_wheel: true\n' })
    expect(calls).toHaveLength(1)
  })

  it('treats an empty-string env opt-in as unset and still loads from the settings file', async () => {
    const calls = await mount({ env: { DSH_PATENT_SERVICES_DIR: '', DSH_PATENT_SERVICES: '' }, yaml: 'mcp_enabled: true\nmcp_wheel: true\n' })
    expect(calls).toHaveLength(1)
  })

  it('survives a failed MCP mount and hands the cause to the setup check', async () => {
    state.files.set('G:/src/patent-services/pyproject.toml', true)
    await mount({
      yaml: 'mcp_enabled: true\nmcp_project_dir: G:/src/patent-services\n',
      pluginError: 'duplicate server name: patent',
    })
    const channels = await checkSetupChannels()
    const mcp = channels.find(c => c.gates === 'MCP 服务')
    expect(mcp?.status).toBe('fail')
    expect(mcp?.line).toContain('装载失败')
    expect(mcp?.line).toContain('duplicate server name: patent')
    expect(mcp?.line).toContain('重启 dsh 进程')
  })

  it('stays silent when the env opt-in already enabled the static row', async () => {
    const calls = await mount({ env: { DSH_PATENT_SERVICES_DIR: 'G:/any' }, yaml: 'mcp_enabled: true\nmcp_project_dir: G:/x\n' })
    expect(calls).toHaveLength(0)
  })

  it('stays silent when the settings file does not enable the services', async () => {
    const calls = await mount({ yaml: 'drawio_bin: D:/tools/draw.io.exe\n' })
    expect(calls).toHaveLength(0)
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
    void ToolPatent.apply(ctx as never)
    expect(registered.some(tool => tool.name === 'patent_setup_check')).toBe(true)
    expect(registered.some(tool => tool.name === 'patent_loop')).toBe(true)
  })
})
