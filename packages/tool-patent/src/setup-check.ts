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
    if (match !== null) {
      // A value with control characters is a corrupted line (escape-folded
      // path), not a setting: python's loader rejects the whole file over it,
      // so honoring it here would fork the two planes' truth.
      const value = match[2] as string
      if (!CONTROL_CHARACTERS.test(value)) map.set(match[1] as string, scalarValue(value))
    }
  }
  return map
}

/**
 * One scalar the way the python plane's yaml loader would read it: a trailing
 * ` #` comment is dropped and one layer of matching quotes is stripped. The
 * file is written by hand or by the model, so a commented `mcp_enabled` line
 * or a quoted Windows path must not leak comment text or quote characters
 * into the value. Backslash escapes are not processed — this file's values
 * are paths, written unquoted.
 * @param raw - the value text after the key's colon.
 * @returns the effective scalar value.
 */
function scalarValue(raw: string): string {
  const quote = raw.charAt(0)
  if ((quote === '"' || quote === "'") && raw.length > 1) {
    const end = raw.indexOf(quote, 1)
    if (end > 0) return raw.slice(1, end)
  }
  const comment = raw.indexOf(' #')
  return (comment >= 0 ? raw.slice(0, comment) : raw).trim()
}

/** The truthy spellings yaml booleans take in this file, case-insensitive. */
function isTruthy(value: string | undefined): boolean {
  if (value === undefined) return false
  const normalized = value.toLowerCase()
  return normalized === 'true' || normalized === '1' || normalized === 'yes' || normalized === 'on'
}

/** The falsy spellings python's yaml loader maps to False. */
function isFalsy(value: string | undefined): boolean {
  if (value === undefined) return false
  const normalized = value.toLowerCase()
  return normalized === 'false' || normalized === 'no' || normalized === 'off'
}

/** Windows (drive-letter or UNC) or POSIX absolute — platform independent. */
function isAbsolutePath(dir: string): boolean {
  return /^([A-Za-z]:[\\/]|\\\\|\/)/.test(dir)
}

/**
 * Control characters no value line may carry: python's yaml loader rejects
 * the whole settings file over one, so every runtime knob dies with it. The
 * classic cause is a path whose `\02` some shell layer folded into a literal
 * `0x02` byte (`G:\02-Sandbox` written through echo/heredoc escape
 * processing) — invisible in most editors, fatal to the python plane.
 */
const CONTROL_CHARACTERS = /[\x00-\x08\x0B\x0C\x0E-\x1F]/

/**
 * The first settings-file line carrying a control character, when there is
 * one — the corruption report behind both the reader's line skip and the
 * setup check's dedicated fail row.
 * @returns the human diagnosis naming the line, or null when the file is clean.
 */
export function settingsCorruption(): string | null {
  const path = join(dshHome(), 'patent-services.yaml')
  if (!existsSync(path)) return null
  const lines = readFileSync(path, 'utf8').split(/\r?\n/)
  for (const [index, line] of lines.entries()) {
    if (!CONTROL_CHARACTERS.test(line)) continue
    return (
      `~/.dsh/patent-services.yaml 第 ${index + 1} 行含控制字符`
      + '——常见成因是路径里的 \\02 被某层转义折叠（G:\\02-Sandbox 变成 G: 后跟一个 0x02 字节），'
      + '编辑器里几乎不可见，但 python 侧解析器会因此拒绝整个文件、全部运行时开关同时失效。'
      + '用编辑器或写文件工具重写该行，重启 dsh 进程后复检。'
    )
  }
  return null
}

/**
 * The mounted-or-pending verdict for a validated settings-file launch: a
 * recorded load failure wins — it explains why the tools are absent without
 * any restart — then the boot marker decides between live and pending.
 * @param okLine - the loaded verdict line.
 * @param pendingLine - the pending-restart verdict line.
 * @returns the channel for the current boot state.
 */
function mcpLoadVerdict(okLine: string, pendingLine: string): SetupChannel {
  if (settingsMcpLoadErrorMessage !== undefined) {
    return { status: 'fail', gates: 'MCP 服务', line: `❌ MCP 服务（配置文件模式）：装载失败——${settingsMcpLoadErrorMessage}。修复后重启 dsh 进程复检（桌面端：重启整个桌面壳，仅新开会话无效）。` }
  }
  return settingsMcpLoaded()
    ? { status: 'ok', gates: 'MCP 服务', line: okLine }
    : { status: 'fail', gates: 'MCP 服务', line: pendingLine }
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
  if (value !== undefined && value.length > 0 && !isFalsy(value)) return value
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
    if (/^\s*disabled:\s*(!!js.*)?true/i.test(line)) return false
    if (/^\s*disabled:\s*(!!js.*)?false/i.test(line)) return true
  }
  return true
}

/** One launch shape for the patent MCP services, resolved from the settings file. */
export interface McpLaunch {
  /** How the settings file named the backend. */
  mode: 'source' | 'wheel'
  /** The executable `ctx.plugin` spawns. */
  command: string
  /** Its argv. */
  args: readonly string[]
  /** The source directory when mode is 'source' — the check validates it. */
  projectDir?: string
}

/**
 * Whether THIS process boot loaded the MCP client from the settings file —
 * set by apply() once `ctx.plugin(McpClient, …)` has run. The check reads it
 * to separate "configured" from "configured and live": the file can be
 * written (or changed) after boot, and only a process restart picks it up,
 * so a freshly configured machine must not be told the tools are usable now.
 */
let settingsMcpLoadedThisBoot = false

/** The cause the settings-file MCP load failed with this boot, if it did. */
let settingsMcpLoadErrorMessage: string | undefined

/** Record that this boot loaded the MCP client from the settings file. */
export function markSettingsMcpLoaded(): void {
  settingsMcpLoadedThisBoot = true
}

/**
 * Record that the settings-file MCP load failed this boot. apply() catches
 * the mount error so a broken optional row never takes the host-plane tools
 * down with it; the check turns the cause into a report row instead.
 * @param error - whatever `ctx.plugin(McpClient, …)` rejected with.
 */
export function noteSettingsMcpLoadError(error: unknown): void {
  const message = error instanceof Error ? error.message : String(error)
  settingsMcpLoadErrorMessage = message.replace(/\s+/g, ' ').trim().slice(0, 200)
}

/** Whether this boot loaded the MCP client from the settings file.
 * @returns whether apply() ran the settings-file MCP load in this process.
 */
export function settingsMcpLoaded(): boolean {
  return settingsMcpLoadedThisBoot
}

/** Clear the boot marker and load-error cause (test isolation only). */
export function resetSettingsMcpLoadedForTests(): void {
  settingsMcpLoadedThisBoot = false
  settingsMcpLoadErrorMessage = undefined
}

/**
 * Resolve the patent MCP services launch from the settings file's flat keys
 * (`mcp_enabled` plus `mcp_project_dir` or `mcp_wheel`) — the single-file way
 * of enabling the services, read by the plugin itself at load time. Callers
 * skip it when the env opt-in or a home-patch row already enabled the static
 * bundle row (a duplicate `serverName` fails loud). Pure resolver: it does
 * not touch the filesystem or PATH — `checkSetupChannels` validates the
 * resolved launch and names whatever is wrong with it.
 * @returns the launch, or null when the file does not enable it.
 */
export function mcpFromSettings(): McpLaunch | null {
  const settings = readSettings()
  if (!isTruthy(settings.get('mcp_enabled'))) return null
  const dir = settings.get('mcp_project_dir')
  if (dir !== undefined && dir.length > 0 && !isFalsy(dir)) {
    return { mode: 'source', command: 'uv', args: ['run', '--project', dir, 'python', '-m', 'patent_services'], projectDir: dir }
  }
  const wheel = settings.get('mcp_wheel')
  if (wheel !== undefined && wheel.length > 0 && !isFalsy(wheel)) {
    return { mode: 'wheel', command: 'uvx', args: ['--from', 'deepseek-harness-patent-services', 'patent-services'] }
  }
  return null
}

/**
 * The config-shape problems that make a settings-file launch unspawnable:
 * a relative project dir (uv would resolve it against the dsh process's
 * working directory — the desktop app's install dir, not the user's) or a
 * directory without a pyproject.toml. The loader runs this before spawning
 * so the load-failure state carries a readable cause instead of uv's raw
 * error; the check reuses it for the same messages.
 * @param launch - the resolved settings-file launch.
 * @returns the blocking reason, or null when the launch shape is spawnable.
 */
export function launchBlockage(launch: McpLaunch): string | null {
  if (launch.mode !== 'source') return null
  const dir = launch.projectDir ?? ''
  if (!isAbsolutePath(dir)) {
    return `mcp_project_dir 需写绝对路径（当前：${dir}）——相对路径按 dsh 进程的工作目录解析，会指错位置`
  }
  if (!existsSync(join(dir, 'pyproject.toml'))) {
    return `mcp_project_dir 指向的目录缺 pyproject.toml（${dir}）——改为指向 python/patent-services 检出`
  }
  return null
}

/** One channel's verdict. */
export interface SetupChannel {
  /** `ok` works, `warn` works with a caveat, `fail` is unusable, `info` is neutral state. */
  status: 'ok' | 'warn' | 'fail' | 'info'
  /** The user-facing verdict line (Chinese), fix included when the status is not `ok`. */
  line: string
  /** Which capability the channel gates, for the summary line. */
  gates: 'MCP 服务' | '附图渲染与实验' | '附图渲染' | '查新检索' | '配置文件' | ''
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

/**
 * Whether the patent-services wheel is installed as a uv tool — the real
 * precondition of wheel mode: the package is not on PyPI, so `uvx --from`
 * only resolves against a tool uv installed locally. False on any probe
 * failure too: an unprovable precondition is reported as not met, never as
 * a green light.
 */
async function wheelToolInstalled(): Promise<boolean> {
  try {
    const { stdout } = await run('uv', ['tool', 'list'], { timeout: 15_000, windowsHide: true })
    return stdout.split(/\r?\n/).some(line => line.startsWith('deepseek-harness-patent-services'))
  } catch {
    return false
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

  // A corrupt settings file is its own channel: the python plane refuses the
  // whole file (every runtime knob dies) while the line reader still sees the
  // clean lines, so the divergence must be named, not left to inference.
  const corruption = settingsCorruption()
  if (corruption !== null) {
    channels.push({ status: 'fail', gates: '配置文件', line: `❌ 配置文件损坏：${corruption}` })
  }

  const uvReady = await commandExists('uv')
  const uvxReady = await commandExists('uvx')
  const servicesDir = process.env.DSH_PATENT_SERVICES_DIR
  const servicesWheel = process.env.DSH_PATENT_SERVICES
  if (servicesDir !== undefined && servicesDir.length > 0) {
    const manifest = join(servicesDir, 'pyproject.toml')
    if (!isAbsolutePath(servicesDir)) {
      channels.push({ status: 'fail', gates: 'MCP 服务', line: `❌ MCP 服务（源码模式）：DSH_PATENT_SERVICES_DIR 需写绝对路径（当前：${servicesDir}）——相对路径按 dsh 进程的工作目录解析，会指错位置；改为绝对路径后重启进程。` })
    } else if (!existsSync(manifest)) {
      channels.push({ status: 'fail', gates: 'MCP 服务', line: `❌ MCP 服务（源码模式）：DSH_PATENT_SERVICES_DIR 指向的目录缺 pyproject.toml（${servicesDir}）——改为指向 python/patent-services 检出后重启进程。` })
    } else if (!uvReady) {
      channels.push({ status: 'fail', gates: 'MCP 服务', line: '❌ MCP 服务（源码模式）：目录有效但未检出 uv——MCP 行由 uv 拉起，安装 uv（https://docs.astral.sh/uv/）后重启进程复检。' })
    } else {
      channels.push({ status: 'ok', gates: 'MCP 服务', line: '✅ MCP 服务（源码模式）：DSH_PATENT_SERVICES_DIR 已设且目录与 uv 有效——MCP 工具应已装载（调用报错时按报错指引处理）。' })
    }
  } else if (servicesWheel !== undefined && servicesWheel.length > 0) {
    if (!uvxReady) {
      channels.push({ status: 'fail', gates: 'MCP 服务', line: '❌ MCP 服务（wheel 模式）：DSH_PATENT_SERVICES 已设但未检出 uvx——安装 uv（自带 uvx）后重启进程复检。' })
    } else if (!(await wheelToolInstalled())) {
      channels.push({ status: 'fail', gates: 'MCP 服务', line: '❌ MCP 服务（wheel 模式）：未检出已安装的 patent-services 包——wheel 模式生效前提是先装本地 wheel（该包未发布 PyPI，uvx 只能运行 uv 已装的工具）：uv tool install <分发目录>/deepseek_harness_patent_services-*.whl，装完重启进程复检。' })
    } else {
      channels.push({ status: 'ok', gates: 'MCP 服务', line: '✅ MCP 服务（wheel 模式）：DSH_PATENT_SERVICES 已设——MCP 工具经 uvx 运行已安装的包。' })
    }
  } else if (homePatchEnablesMcp()) {
    channels.push({ status: 'ok', gates: 'MCP 服务', line: '✅ MCP 服务（配置文件模式·home patch）：~/.dsh/cordis.patch.yml 已启用 mcp-patent-services 行——MCP 工具按该行的 command/args 运行。' })
  } else {
    const launch = mcpFromSettings()
    if (launch === null) {
      channels.push({ status: 'fail', gates: 'MCP 服务', line: '❌ MCP 服务未启用——导出/渲染/实验/检索的 MCP 工具全部不可见。启用方式（首选，单文件）：在 ~/.dsh/patent-services.yaml 写 mcp_enabled: true 加 mcp_project_dir: <patent-services 源码目录的绝对路径>（安装 wheel 的机器写 mcp_wheel: true），并确保 PATH 上有 uv/uvx；保存后重启 dsh 进程生效（桌面端：重启整个桌面壳，仅新开会话无效），复检应显示「已装载」。脚本化场景也可设环境变量 DSH_PATENT_SERVICES_DIR/DSH_PATENT_SERVICES。本工具不受影响。' })
    } else if (launch.mode === 'source') {
      const blockage = launchBlockage(launch)
      if (blockage !== null) {
        channels.push({ status: 'fail', gates: 'MCP 服务', line: `❌ MCP 服务（配置文件模式）：${blockage}。` })
      } else if (!uvReady) {
        channels.push({ status: 'fail', gates: 'MCP 服务', line: '❌ MCP 服务（配置文件模式）：未检出 uv——源码模式的 MCP 行由 uv 拉起，安装 uv（https://docs.astral.sh/uv/）后重启进程复检。' })
      } else {
        channels.push(mcpLoadVerdict(
          '✅ MCP 服务（配置文件模式·已装载）：~/.dsh/patent-services.yaml 的 mcp_enabled 已启用，本进程启动时已按 mcp_project_dir 装载 MCP 工具。',
          '❌ MCP 服务（配置文件模式·待重启）：~/.dsh/patent-services.yaml 已配置（mcp_project_dir），但本进程启动时未装载——配置写入晚于进程启动。重启 dsh 进程后生效（桌面端：重启整个桌面壳，仅新开会话无效）；重启后复检应显示「已装载」。'))
      }
    } else if (!uvxReady) {
      channels.push({ status: 'fail', gates: 'MCP 服务', line: '❌ MCP 服务（配置文件模式）：未检出 uvx——wheel 模式的 MCP 行由 uvx 拉起，安装 uv（自带 uvx）后重启进程复检。' })
    } else if (!(await wheelToolInstalled())) {
      channels.push({ status: 'fail', gates: 'MCP 服务', line: '❌ MCP 服务（配置文件模式）：mcp_wheel 已启用但未检出已安装的 patent-services 包——wheel 模式生效前提是先装本地 wheel（该包未发布 PyPI，uvx 只能运行 uv 已装的工具）：uv tool install <分发目录>/deepseek_harness_patent_services-*.whl，装完重启进程复检。' })
    } else {
      channels.push(mcpLoadVerdict(
        '✅ MCP 服务（配置文件模式·已装载）：~/.dsh/patent-services.yaml 的 mcp_enabled 已启用，本进程启动时已按 mcp_wheel 装载 MCP 工具。',
        '❌ MCP 服务（配置文件模式·待重启）：~/.dsh/patent-services.yaml 已配置（mcp_wheel），但本进程启动时未装载——配置写入晚于进程启动。重启 dsh 进程后生效（桌面端：重启整个桌面壳，仅新开会话无效）；重启后复检应显示「已装载」。'))
    }
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
