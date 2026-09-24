# Aurify (dsh-patent) — installing into a new dsh profile

> Audience: anyone with the Deepseek Harness Desktop (Tauri) app installed who
> wants the Aurify patent-writing plugin in a **fresh dsh profile**, without
> touching existing profiles.
>
> Everything happens inside the `.dsh` directory under your home — no admin
> rights, no npm access needed. The Chinese walkthrough of the manual install
> path lives in [README.md](README.md).
>
> **Windows vs macOS/Linux** — the quick-install script is Windows-only: it
> locates the dsh CLI through the desktop app's Windows shim directory and
> defaults to `%USERPROFILE%` paths. On macOS/Linux skip to
> [Manual install](#manual-install-what-the-script-does-step-by-step) with the
> substitution table below — the manual steps are the cross-platform path.

## Prerequisites

| Requirement | Notes | How to check |
|---|---|---|
| Desktop app installed | Provides the dsh core and the `dsh` CLI shim | `dsh --version` prints a version (Windows shim: `%LOCALAPPDATA%\deepseek-harness\bin\dsh.cmd`; macOS/Linux: `~/.local/bin/dsh`) |
| Release artifacts unpacked | Unpack the bundle tarball into a `bundle/` directory beside the package tarballs — `tar -xzf mtl-academic-dsh-patent-*.tgz -C bundle --strip-components=1`, run from the directory holding the tarballs — and put them anywhere, e.g. `%USERPROFILE%\.dsh\plugin-dist\patent`. That directory is the installer's `-DistDir`: **pass it as an absolute path** (a relative one is anchored to the shell's current directory, and the value it writes into the profile manifest is resolved against the *profile* directory, not the shell's — see step 2) | The installer's first step validates this |
| `tar` (Windows) | System bsdtar (`C:\Windows\System32\tar.exe`, shipped since Win10 1803), **not** Git's MSYS tar: under a restricted shell or a sandboxed agent, `C:\Program Files\Git\usr\bin\tar.exe` dies with `fatal error - couldn't create signal pipe, Win32 error 5` | `C:\Windows\System32\tar.exe --version` |
| Python services (optional) | The 9 MCP tools (export, Word parsing, figure linting/rendering, experiments, prior-art search) | Preferred single file: `~/.dsh/patent-services.yaml` with `mcp_enabled: true` — the master switch, required in both modes, so a file carrying only the mode key stays off — plus `mcp_project_dir: <absolute path to a patent-services source checkout>` or `mcp_wheel: true`; wheel mode needs nothing pre-installed: `uvx` fetches the package from PyPI on first use; `uv tool install <DIST>/deepseek_harness_patent_services-<version>-py3-none-any.whl` of the shipped wheel is the offline alternative. [uv](https://docs.astral.sh/uv/) must be on PATH; if `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` fails in a restricted shell (`基础连接已经关闭` / `SEC_E_NO_CREDENTIALS`), download it with `curl.exe -LsSf -o "$env:TEMP\uv-install.ps1" https://astral.sh/uv/install.ps1` and run that file instead — either route updates the *user* PATH, which only a new process sees, and the `warning: ...\.local\bin is not on your PATH` line refers to the shell you ran it in. Scripted setups may instead set a user-level env var — `DSH_PATENT_SERVICES=1` (installed wheel) or `DSH_PATENT_SERVICES_DIR` (source checkout); `setx` on Windows, `export` in your shell profile on macOS/Linux. Either way, fully restart the desktop app — the MCP row loads at process start, so a new conversation is not enough; all profiles inherit it. In-session, `patent_setup_check` reports 已装载 (loaded) versus 待重启 (restart pending) |
| Docker Desktop (optional) | Only for simulation experiments and drawio figure rendering | Start it manually when needed |

## macOS/Linux substitutions for the manual steps

| Windows path / command as written below | macOS / Linux |
|---|---|
| `%USERPROFILE%\.dsh\profiles\<name>\...` | `~/.dsh/profiles/<name>/...` |
| `%LOCALAPPDATA%\deepseek-harness\bin\dsh` | `~/.local/bin/dsh` (the desktop app's shim; XDG convention, usually already on PATH) |
| `%APPDATA%\io.github.hairyf.deepseek-harness-desktop\dependencies\dsh\...` | `~/.local/share/io.github.hairyf.deepseek-harness-desktop/dependencies/dsh/...` (macOS: `~/Library/Application Support/...`) |
| `setx <VAR> <value>` (user env var) | add `export <VAR>=<value>` to `~/.zshrc` / `~/.bashrc` |

## Quick install (recommended, Windows)

```powershell
powershell -ExecutionPolicy Bypass -File <DIST>\install-patent-profile.ps1 -Name patent-test -DistDir "$env:USERPROFILE\.dsh\plugin-dist\patent"
```

- `-Name <name>` — the new profile's name (created under `%USERPROFILE%\.dsh\profiles\<name>`). Default `patent-test`.
- `-DistDir <DIST>` — where you unpacked the release (the same `<DIST>` the manual steps below use). Default `%USERPROFILE%\.dsh\plugin-dist\patent`. **Give an absolute path**: the installer writes it verbatim into the profile manifest as a `file:` dependency, and dsh resolves every `file:` value against the *profile* directory. A relative `-DistDir` used to produce an unbootable profile (`file:./bundle`); the installer now anchors it to the current directory, and older releases did not — so check `<profile>\package.json` if you installed with an earlier copy.
- `-PersonaFrom auto` (default) — installs the persona from a shipped `persona.patch.yml` in the dist directory; with `-PersonaFrom <existing-profile>` it copies that profile's patch instead; `-PersonaFrom ""` skips.
- Idempotent — re-running on an existing profile refreshes it in place, **merging** into `package.json` (an existing profile's other dependencies and bundle layers, e.g. the desktop app's own `dsh-tauri*`/`dshmarket`/`@xmanrui/dsh-im` entries, are preserved) and refreshing the 4 `overrides:` lines in `pnpm-workspace.yaml` to the tarballs actually present.

When it prints `DONE`, **fully quit and relaunch the desktop app**, pick the new profile, and open a session in a patent project directory.

> Verify before you relaunch anything: `dsh --profile <name> --dump-config` must exit 0. A manifest that cannot be resolved does not merely leave the plugin off — the desktop app cannot launch that profile at all (`cannot resolve profile bundle "@mtl-academic/dsh-patent"`). Note that `--dump-config` rewrites the profile's root `cordis.yml`, so it needs write access to the profile directory; a read-only shell (or an agent sandbox) fails with `EPERM: operation not permitted, open '...\cordis.yml'`, which is a shell permission problem, not a broken profile.

## Manual install (what the script does, step by step)

### 1. Validate the dist layout

```
<DIST>\
├─ bundle\                                        # @mtl-academic/dsh-patent (directory form; the 14 skills live here)
├─ mtl-academic-dsh-patent-<version>.tgz
├─ mtl-academic-dsh-tool-patent-<version>.tgz
├─ mtl-academic-dsh-command-patent-review-<version>.tgz
├─ deepseek-ai-schemastery-<version>.tgz          # the registry only carries the 3.18.x line; the bundle builds against the vendored fork
├─ deepseek-ai-cosmokit-<version>.tgz
├─ persona.patch.yml                              # the persona as a ready profile patch (optional but recommended)
├─ deepseek_harness_patent_services-<version>.whl # optional Python services (mcp_wheel: true - uvx fetches from PyPI - or DSH_PATENT_SERVICES=1; offline: uv tool install the wheel first)
├─ install-patent-profile.ps1                     # the quick-install script this guide documents
└─ README.md                                      # the Chinese receiver guide (manual walkthrough)
```

`<DIST>` must be an **absolute path you keep**: the profile manifest references `<DIST>/bundle` verbatim, and the desktop shell re-resolves every `file:` dependency at launch (one whose directory has vanished is uninstalled as a dangling link). Unpacking `bundle/` anywhere else — e.g. next to the repository root instead of beside the tarballs — fails the installer's first validation.

### 2. Initialize the profile and declare the bundle

```cmd
dsh plugin --profile <name> add file:<DIST>/bundle
```

- **The `file:` target must be the DIRECTORY, never the tgz** — the desktop app's self-heal resolves every `file:`/`link:` dependency in a profile manifest and uninstalls ones that are not directories. A tarball-shaped install disappears on the next launch.
- **Every `file:` value must be an absolute path** (`file:C:/dsh-patent-dist/bundle`, not `file:./bundle`). dsh resolves these against the **profile directory**, never against the shell you typed them in — a relative value installs a profile that cannot boot at all, which is worse than a missing plugin: `dsh --profile <name> --dump-config` fails with `cannot resolve profile bundle "@mtl-academic/dsh-patent"` and the desktop app refuses to launch that profile until it is repaired. The same rule applies to the 4 `overrides:` values in step 4.
- This initializes the profile (`dsh.profile.bundles` + `patchReload: live`). The pnpm leg **fails on the bundle's internal `workspace:^` dependencies (they are not published to npm) — expected**; steps 4–5 repair it.

### 3. Write `<profile-dir>\package.json`

Declare the bundle as a directory dependency (`file:` value **absolute**) and complete the bundle stack:

```json
{
  "name": "dsh-profile-<name>",
  "private": true,
  "dependencies": {
    "@mtl-academic/dsh-patent": "file:<DIST>/bundle"
  },
  "dsh": {
    "profile": {
      "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "@mtl-academic/dsh-patent"],
      "patchReload": "live"
    }
  }
}
```

If the profile already exists, **merge into it — add only, never delete**. A desktop-managed profile carries the desktop app's own dependencies and bundle layers (`dsh-tauri`, `dsh-tauri-connection`, `dsh-tauri-model-config`, `dsh-tauri-panel-extension`, `dsh-tauri-panel-scheduler`, `dsh-tauri-pet`, `dsh-tauri-rightclick`, `dsh-tauri-session`, `dsh-tauri-turnrewind`, `dsh-tauri-ui`, `dsh-tauri-worktree` as `link:` deps, plus `dshmarket`, `dsh-better-sidebar`, `dsh-rewind-plugin`, `@xmanrui/dsh-im`). Overwriting the file drops those declarations, and the next `dsh plugin install` then prunes them out of `node_modules` as extraneous packages — the profile silently loses the desktop's plugins (market, sidebar, IM, rewind, Tauri bridge). See [Installing into an existing profile](#installing-into-an-existing-desktop-managed-profile) for the recovery path.

### 4. Write `<profile-dir>\pnpm-workspace.yaml` (overrides)

The internal packages are not on npm; pnpm overrides point them at the local tarballs (**pnpm 11 reads overrides from this yaml only — a `pnpm` field in package.json is ignored**). All 4 values must be **absolute** paths for the same reason as step 2:

```yaml
packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false

overrides:
  '@mtl-academic/dsh-tool-patent': file:<DIST>/mtl-academic-dsh-tool-patent-<version>.tgz
  '@mtl-academic/dsh-command-patent-review': file:<DIST>/mtl-academic-dsh-command-patent-review-<version>.tgz
  '@deepseek-ai/schemastery': file:<DIST>/deepseek-ai-schemastery-<version>.tgz
  '@deepseek-ai/cosmokit': file:<DIST>/deepseek-ai-cosmokit-<version>.tgz
```

### 5. Install

```cmd
dsh plugin --profile <name> install
```

Success: pnpm prints `Done`, and `node_modules` under the profile contains `@mtl-academic/dsh-patent` plus `@deepseek-ai/{dsh-tool-patent,dsh-command-patent-review,schemastery,cosmokit}`.

### 6. Install the persona

The bundle ships **persona-free on purpose** (it is a capability layer any profile can mount). The persona lives in the profile's patch layer:

```powershell
Copy-Item <DIST>\persona.patch.yml %USERPROFILE%\.dsh\profiles\<name>\cordis.patch.yml
```

**This overwrites the whole patch file.** On a profile that already has loader patch entries of its own, append the persona's `- id: system-prompt` entry to `<profile-dir>\cordis.patch.yml` instead of copying the file over it. (The quick-install script takes the safe route: it installs the persona only when the profile's patch has no `persona:` yet.)

The canonical text is also documented in the bundle README ("The persona lives in the profile") — hand-write `cordis.patch.yml`'s `system-prompt.config.persona` from it if you prefer. **Without the persona the assistant has no gatekeeper behavior**: it will not assess ideas before drafting, route through the skills, or push back with publication numbers.

### 7. Verify

```cmd
dsh --profile <name> --dump-config
```

The command must **exit 0**. Then check three things: the `tool-patent` / `patent-assets` / `command-patent-review` / `mcp-patent-services` rows are present; a `persona:` key appears; the log shows no `DANGLING`/`UNINSTALLING` lines (those mean step 2 was not directory-shaped). `workflow-ptc not found`-style warnings are benign cross-core no-ops.

Do this **before** relaunching the desktop app, and treat a non-zero exit as blocking: `cannot resolve profile bundle` means the app cannot open that profile at all. `EPERM ... open '...\cordis.yml'` is different — `--dump-config` rewrites the profile's root `cordis.yml`, so a read-only shell or an agent sandbox hits that even on a perfectly good profile; rerun from a normal terminal.

## Installing into an existing (desktop-managed) profile

A profile the desktop app created and runs carries the app's own dependencies and bundle layers (listed in step 3). The quick-install script merges into `package.json` and preserves them; a hand-edit or an **older** installer copy overwrote the file and dropped them, and the ensuing `dsh plugin install` pruned the corresponding packages out of `node_modules` (`Packages: +N -M` in the pnpm output).

Signs: after relaunch the market / sidebar / IM / rewind / Tauri-bridge plugins are gone in that profile (`CORE_PLUGIN_PROFILE_ENTRY_MISSING` or a new `CORE_PLUGIN_LINKED` burst in `%APPDATA%\io.github.hairyf.deepseek-harness-desktop\logs\desktop.log`).

Recovery, in order of preference:

1. Restore the manifest from the installer's snapshot: refreshing an existing profile copies `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml` and `cordis.patch.yml` into `~/.dsh/.plugin-backups/<name>-<timestamp>/` first.
2. Rebuild it from the profile's own lockfile: `pnpm-lock.yaml` has an `importers:` → `.:` → `dependencies:` block listing every specifier (including the `link:` ones) — copy those keys/values back into `package.json#dependencies`, and add the matching names back to `dsh.profile.bundles` (order in the desktop's own profiles: the 11 `dsh-tauri*` entries, then `dsh-better-sidebar`, `dsh-rewind-plugin`, `dshmarket`, `dsh-tauri-connection`, `@xmanrui/dsh-im`).
3. Re-run the installer (or `dsh plugin --profile <name> install`) and verify with `--dump-config` before relaunching.

## What you get

| Capability | Entry point | Needs |
|---|---|---|
| Idea assessment, five-party interview, chapter drafting, review, export — the whole pipeline | Just ask in a session, or `/patent-loop`, `/patent-review` | nothing |
| Disclosure/application export, Word reference parsing | MCP tools, invoked by the model | the single-file gate `~/.dsh/patent-services.yaml`: `mcp_enabled: true` plus `mcp_project_dir` (absolute source path) or `mcp_wheel: true`; scripted setups may set `DSH_PATENT_SERVICES=1` / `DSH_PATENT_SERVICES_DIR` instead |
| Simulation experiments, drawio/HTML figure rendering | MCP tools, invoked by the model | the above + Docker Desktop |
| Chinese prior-art discovery | `search_cn_patents` (model-invoked) | network access to patents.google.com (a proxy is the usual route) |

## Upgrading

Drop the new release's tarballs and `bundle/` over the dist directory (**same absolute path** — every profile that installed from it points there), then re-run the installer (it re-resolves the tarball names by pattern and refreshes the 4 `overrides:` lines to them). Note that pnpm integrity-checks same-version tarballs — after replacing a tarball in place, delete the `overrides:` block in the profile's `pnpm-workspace.yaml` (or just re-run the installer, which rewrites the manifest and forces a reinstall). The Python services run from their source directory, so updating that directory is enough — no reinstall; wheel mode resolves new versions from PyPI via uvx (offline installs: `uv tool install` the new wheel). Before refreshing a profile you care about, copy `package.json` / `pnpm-workspace.yaml` / `pnpm-lock.yaml` aside: the installer merges, but a hand-edit does not, and the lockfile's `importers:` block is the authoritative list of what the profile is supposed to declare.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `--dump-config` fails with `cannot resolve profile bundle "@mtl-academic/dsh-patent"`, and the desktop app cannot open that profile | The manifest's `file:` value points somewhere dsh cannot resolve. `file:` values are resolved against the **profile directory**, so `file:./bundle`, a moved/renamed `<DIST>`, or a deleted `bundle/` all hit this. Repoint `package.json#dependencies` and the 4 `overrides:` lines at the current absolute paths (re-running the installer refreshes the overrides in place), then `dsh plugin --profile <name> install` |
| The plugin vanishes after a desktop relaunch; log shows `DANGLING_LINK_UNINSTALLING` | The bundle was installed tarball-shaped. Delete the profile and reinstall — step 2 must target the `bundle` directory |
| After the install the profile has lost the desktop's own plugins (market, sidebar, IM, rewind, Tauri bridge); the pnpm output shows `Packages: +N -M` | `package.json` was overwritten instead of merged, so the desktop's dependency and bundle entries vanished and pnpm pruned the packages. See [Installing into an existing profile](#installing-into-an-existing-desktop-managed-profile) for the recovery path |
| `ERR_PNPM_WORKSPACE_PKG_NOT_FOUND` (workspace:^) | The overrides block is missing or its paths are wrong. Check the 4 `overrides:` lines against the tarballs actually present |
| `tar -xzf` fails with `fatal error - couldn't create signal pipe, Win32 error 5` | `tar` resolved to Git's MSYS build, which cannot run under a restricted shell / agent sandbox. Use `C:\Windows\System32\tar.exe` |
| `--dump-config` fails with `EPERM: operation not permitted, open '...\profiles\<name>\cordis.yml'` | Not a profile problem: the command rewrites the profile's root `cordis.yml` and the shell has no write access there. Rerun from a normal (writable) terminal |
| The model cannot see the export/render tools | No Python-services gate is enabled — the preferred single file is `~/.dsh/patent-services.yaml` with `mcp_enabled: true` **plus** `mcp_project_dir` (absolute path) or `mcp_wheel: true`; the `mcp_enabled` master switch is required in both modes (a file with only `mcp_wheel: true` stays off). Scripted setups use `DSH_PATENT_SERVICES=1` / `DSH_PATENT_SERVICES_DIR`. Or the gate was enabled after the app started: the MCP row loads at process start, so fully quit and relaunch the desktop app (a new conversation is not enough). In a session, `patent_setup_check` reports 已装载 (loaded) versus 待重启 (restart pending) |
| Wheel mode reports no installed `patent-services` package | Verify the uvx path directly: `uvx --from deepseek-harness-patent-services python -c "import patent_services"` (needs `uv`/`uvx` on `PATH` and PyPI reachable; note the check's wheel probe reads `uv tool list`, so under PyPI+uvx without `uv tool install` this row is a false alarm when that command passes). Offline machines: `uv tool install <DIST>\deepseek_harness_patent_services-<version>-py3-none-any.whl`, then relaunch |
| Review reports "model not found" / auth errors | Switch to a model your gateway actually serves in the session — review really spawns scoring subagents. Calling the default deepseek line through a GLM gateway fails with "model not found"; this distribution pairs with a GLM gateway's GLM model group, whose exact group name is whatever your `Settings → Models` shows (`zai-coding-cn` in the docs is an example, not a requirement) |
| A review dimension reports all scoring passes failed | Gateway rate limiting. The scripted review batches, backs off, and retries; running `patent_review` once more usually recovers the dimension |
