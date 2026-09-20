/**
 * The host-plane environment self-check: one probe per optional channel of
 * the patent plugin, usable before anything else is configured. This lives
 * on the host side deliberately — an MCP-served check cannot diagnose an MCP
 * row that never loaded, so the one tool that names the missing row must not
 * depend on it. Every probe is best-effort: a broken channel is a report
 * row, never a thrown error.
 * @module dsh-tool-patent/setup-check
 */

import { execFile } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { promisify } from 'node:util'

const run = promisify(execFile)

/** $DSH_HOME, defaulting to ~/.dsh — where both settings files live. */
function dshHome(): string {
  return process.env.DSH_HOME ?? join(homedir(), '.dsh')
}

/**
 * The optional-settings file (`~/.dsh/patent-services.yaml`), parsed as the
 * flat `key: value` map this plugin writes: comments and blank lines skipped,
 * nested keys left alone. Mirrors python's config.py resolution order — the
 * environment variable still wins — so both planes report one truth.
 * @returns the parsed flat key/value map; empty when the file is absent.
 */
export function readSettings(): Map<string, string> {
  const map = new Map<string, string>()
  const path = join(dshHome(), 'patent-services.yaml')
  if (!existsSync(path)) return map
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const match = /^([A-Za-z_][\w-]*):\s*(.+?)\s*$/.exec(line)
    if (match !== null) map.set(match[1] as string, match[2] as string)
  }
  return map
}

/**
 * Resolve one option: environment variable first, then the settings file.
 * @param envName - the option's environment variable name.
 * @param fileKey - its settings-file key.
 * @returns the resolved value, or undefined when neither source sets it.
 */
export function optionValue(envName: string, fileKey: string): string | undefined {
  const ambient = process.env[envName]
  if (ambient !== undefined && ambient.length > 0) return ambient
  const value = readSettings().get(fileKey)
  if (value !== undefined && value.length > 0 && value !== 'false') return value
  return undefined
}

/**
 * Whether the home-level patch layer (~/.dsh/cordis.patch.yml) carries an
 * enabled mcp-patent-services row — the configuration-file way of enabling
 * the MCP services, replacing setx for people. A text-level check on
 * purpose: the row's shape is ours, and YAML parsing here would import a
 * dependency the tool does not otherwise need.
 * @returns whether an enabled mcp-patent-services row sits in the home patch.
 */
export function homePatchEnablesMcp(): boolean {
  const path = join(dshHome(), 'cordis.patch.yml')
  if (!existsSync(path)) return false
  const lines = readFileSync(path, 'utf8').split(/\r?\n/)
  const start = lines.findIndex(line => /^-\s*id:\s*mcp-patent-services/.test(line))
  if (start < 0) return false
  for (const line of lines.slice(start + 1)) {
    if (/^-\s*id:/.test(line)) break
    if (/^\s*disabled:\s*(!!js.*)?true/.test(line)) return false
    if (/^\s*disabled:\s*(!!js.*)?false/.test(line)) return true
  }
  return true
}

/** One channel's verdict. */
export interface SetupChannel {
  /** `ok` works, `warn` works with a caveat, `fail` is unusable, `info` is neutral state. */
  status: 'ok' | 'warn' | 'fail' | 'info'
  /** The user-facing verdict line (Chinese), fix included when the status is not `ok`. */
  line: string
  /** Which capability the channel gates, for the summary line. */
  gates: 'MCP 服务' | '附图渲染与实验' | '附图渲染' | '查新检索' | ''
}

/** Seconds one docker probe may take. */
const DOCKER_TIMEOUT_MS = 20_000

/** Seconds the Google Patents reachability probe may take. */
const PROBE_TIMEOUT_MS = 8_000

/** The render image (mirrors render.py's default). */
const RENDER_IMAGE = 'q771103517/dsh-patent:latest'

/** The experiment image (mirrors experiments.py's default). */
const EXPERIMENT_IMAGE = 'q771103517/dsh-patent-experiment:latest'

/** Native draw.io CLI candidates, in resolution order (mirrors render.py). */
function drawioCandidates(): readonly string[] {
  const explicit = optionValue('DSH_DRAWIO_BIN', 'drawio_bin')
  const windowsInstall = join(process.env.LOCALAPPDATA ?? '', 'Programs', 'draw.io', 'draw.io.exe')
  return explicit !== undefined && explicit.length > 0 ? [explicit] : ['draw.io', 'drawio', windowsInstall]
}

/** Whether a command name resolves on PATH (or is an existing absolute path). */
async function commandExists(candidate: string): Promise<boolean> {
  try {
    await run(candidate, ['--version'], { timeout: 15_000, windowsHide: true })
    return true
  } catch (error: unknown) {
    // A version-flag mismatch still proves the binary exists and runs.
    return (error as { code?: number | string }).code !== 'ENOENT'
  }
}

/** Whether a docker image is present locally; null when the probe failed. */
async function imagePresent(image: string): Promise<boolean | null> {
  try {
    await run('docker', ['image', 'inspect', image], { timeout: DOCKER_TIMEOUT_MS, windowsHide: true })
    return true
  } catch (error: unknown) {
    const code = (error as { code?: number | string }).code
    if (code === 'ENOENT') return null
    const stderr = (error as { stderr?: string }).stderr ?? ''
    return /no such image|not found/i.test(stderr) ? false : null
  }
}

/** Whether patents.google.com answers — the search channel's reachability. */
async function searchReachable(): Promise<boolean> {
  try {
    const response = await fetch('https://patents.google.com/', { signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) })
    return response.ok
  } catch {
    return false
  }
}

/**
 * Probe every optional channel once. Pure environment reads plus bounded
 * child processes and one network fetch — no project state, no MCP.
 * @returns one verdict per channel, in report order.
 */
export async function checkSetupChannels(): Promise<SetupChannel[]> {
  const channels: SetupChannel[] = []

  const servicesDir = process.env.DSH_PATENT_SERVICES_DIR
  const servicesWheel = process.env.DSH_PATENT_SERVICES
  if (servicesDir !== undefined && servicesDir.length > 0) {
    const manifest = join(servicesDir, 'pyproject.toml')
    channels.push(existsSync(manifest)
      ? { status: 'ok', gates: 'MCP 服务', line: '✅ MCP 服务（源码模式）：DSH_PATENT_SERVICES_DIR 已设且目录有效——导出/渲染/实验/检索等 MCP 工具应已装载（调用报错时按报错指引处理）。' }
      : { status: 'fail', gates: 'MCP 服务', line: `❌ MCP 服务（源码模式）：DSH_PATENT_SERVICES_DIR 指向的目录缺 pyproject.toml（${servicesDir}）——改为指向 python/patent-services 检出后重启会话。` })
  } else if (servicesWheel !== undefined && servicesWheel.length > 0) {
    channels.push({ status: 'ok', gates: 'MCP 服务', line: '✅ MCP 服务（wheel 模式）：DSH_PATENT_SERVICES 已设——MCP 工具经 uvx 运行已安装的包。' })
  } else if (homePatchEnablesMcp()) {
    channels.push({ status: 'ok', gates: 'MCP 服务', line: '✅ MCP 服务（配置文件模式）：~/.dsh/cordis.patch.yml 已启用 mcp-patent-services 行——MCP 工具按该行的 command/args 运行。' })
  } else {
    channels.push({ status: 'fail', gates: 'MCP 服务', line: '❌ MCP 服务未启用——导出/渲染/实验/检索的 MCP 工具全部不可见。首选配置文件方式：编辑 ~/.dsh/cordis.patch.yml 加一段启用的 mcp-patent-services 行（command 用 uv、args 指向 patent-services 源码目录），保存后重启会话；脚本化场景也可设环境变量 DSH_PATENT_SERVICES_DIR/DSH_PATENT_SERVICES。本工具不受影响，配好后复检。' })
  }

  let dockerWorks = true
  try {
    await run('docker', ['--version'], { timeout: 15_000, windowsHide: true })
    channels.push({ status: 'ok', gates: '附图渲染与实验', line: '✅ docker：可用（附图渲染与仿真实验的后端）。' })
  } catch (error: unknown) {
    if ((error as { code?: number | string }).code === 'ENOENT') {
      dockerWorks = false
      channels.push({ status: 'fail', gates: '附图渲染与实验', line: '❌ docker：未检出——附图渲染（drawio 兜底）与仿真实验不可用。安装并启动 Docker Desktop（https://docs.docker.com/desktop/）后复检。' })
    } else {
      channels.push({ status: 'fail', gates: '附图渲染与实验', line: '❌ docker：命令存在但无法执行（未启动？）——启动 Docker Desktop 后复检。' })
    }
  }
  if (dockerWorks) {
    const renderImage = optionValue('DSH_DRAWIO_DOCKER_IMAGE', 'drawio_docker_image') ?? RENDER_IMAGE
    const experimentImage = optionValue('DSH_PATENT_EXPERIMENT_IMAGE', 'experiment_image') ?? EXPERIMENT_IMAGE
    for (const [label, image, gates] of [['渲染', renderImage, '附图渲染'], ['实验', experimentImage, '附图渲染与实验']] as const) {
      const present = await imagePresent(image)
      channels.push(present === true
        ? { status: 'ok', gates, line: `✅ ${label}镜像：${image} 已就位。` }
        : present === false
          ? { status: 'warn', gates, line: `⚠️ ${label}镜像未拉取：${image}——首次使用会自动拉取（较大，可先 docker pull ${image} 预热）。` }
          : { status: 'warn', gates, line: `⚠️ ${label}镜像状态未知：docker image inspect ${image} 无法执行——docker 未启动？启动 Docker Desktop 后复检。` })
    }
  }

  const explicit = optionValue('DSH_DRAWIO_BIN', 'drawio_bin')
  if (explicit !== undefined) {
    channels.push({ status: existsSync(explicit) ? 'ok' : 'fail', gates: '附图渲染',
      line: existsSync(explicit)
        ? `✅ draw.io 原生 CLI：指定且存在（${explicit}）。`
        : `❌ draw.io 原生 CLI：指定的路径不存在（${explicit}）——修正 drawio_bin（或环境变量 DSH_DRAWIO_BIN），或删掉该配置走 docker 兜底（该路径是严格匹配，坏路径不会回退）。` })
  } else {
    const found: string | undefined = await (async () => {
      for (const candidate of drawioCandidates()) {
        if (candidate.includes('\\') || candidate.includes('/')) {
          if (existsSync(candidate)) return candidate
        } else if (await commandExists(candidate)) {
          return candidate
        }
      }
      return undefined
    })()
    channels.push(found !== undefined
      ? { status: 'ok', gates: '附图渲染', line: `✅ draw.io 原生 CLI：检出（${found}）——渲染优先走原生，比 docker 快。` }
      : { status: 'info', gates: '附图渲染', line: 'ℹ️ draw.io 原生 CLI 未检出——渲染走 docker 兜底即可，无需配置；想加速可安装 draw.io Desktop 或设 DSH_DRAWIO_BIN。' })
  }

  channels.push(await searchReachable()
    ? { status: 'ok', gates: '查新检索', line: '✅ 检索通道：patents.google.com 可达——查新（search_cn_patents）与明细阅读可用。' }
    : { status: 'fail', gates: '查新检索', line: '❌ 检索通道：patents.google.com 不可达——查新受限（点子评估与查新门会受影响）。通常需要开启本机代理（如 Clash 系统代理或 TUN）；通道恢复后复检，期间检索工具会如实报错、禁止编造结果。' })

  const widenedValue = optionValue('DSH_EXPERIMENT_ALLOW_ANY_COMMAND', 'experiment_allow_any_command')
  const widened = widenedValue === '1' || widenedValue === 'true'
  channels.push({ status: 'info', gates: '', line: widened
    ? 'ℹ️ 实验命令白名单：已放宽（任意 shell 命令，仅建议确有需要时保留）；收紧：删除环境变量 DSH_EXPERIMENT_ALLOW_ANY_COMMAND，并把 ~/.dsh/patent-services.yaml 的 experiment_allow_any_command 改为 false 或删掉该行。'
    : 'ℹ️ 实验命令白名单：默认（只接受单个 python 调用）；放宽：环境变量 DSH_EXPERIMENT_ALLOW_ANY_COMMAND=1，或在 ~/.dsh/patent-services.yaml 写 experiment_allow_any_command: true。' })

  const proxies = ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'].filter(name => (process.env[name] ?? '').length > 0)
  channels.push({ status: 'info', gates: '', line: `ℹ️ 代理环境变量：${proxies.length > 0 ? proxies.join('、') : '未设置（node fetch 仍会读系统代理）'}。` })

  return channels
}

/**
 * Render the channels as the model- and user-facing report.
 * @param channels - the probed channels.
 * @returns the full Chinese report with the readiness conclusion.
 */
export function formatSetupReport(channels: readonly SetupChannel[]): string {
  const limited = [...new Set(channels.filter(channel => channel.status === 'fail').map(channel => channel.gates).filter(gates => gates.length > 0))]
  const body = channels.map(channel => channel.line).join('\n')
  return limited.length > 0
    ? `环境自检（点金 Aurify）——以下通道受限：\n${body}\n结论：${limited.join('、')}受限，其余就绪；按上述各行配置后重新调用本工具复检。`
    : `环境自检（点金 Aurify）——全部就绪：\n${body}\n结论：渲染、实验、检索、导出全部可用，可以直接开始。`
}
