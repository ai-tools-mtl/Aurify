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
| Release artifacts unpacked | Unpack the bundle tarball into a `bundle/` directory beside the package tarballs — `tar -xzf mtl-academic-dsh-patent-*.tgz -C bundle --strip-components=1` — and put them in any directory, e.g. `%USERPROFILE%\.dsh\plugin-dist\patent` | The installer's first step validates this |
| Python services (optional) | The 9 MCP tools (export, Word parsing, figure linting/rendering, experiments, prior-art search) | Preferred single file: write `mcp_enabled: true` plus `mcp_project_dir: <absolute path to a patent-services source checkout>` (or `mcp_wheel: true` after `uv tool install deepseek_harness_patent_services-*.whl`) into `~/.dsh/patent-services.yaml`, with [uv](https://docs.astral.sh/uv/) on PATH. Scripted setups may instead set a user-level env var — `DSH_PATENT_SERVICES=1` (installed wheel) or `DSH_PATENT_SERVICES_DIR` (source checkout); `setx` on Windows, `export` in your shell profile on macOS/Linux. Either way, fully restart the desktop app — the MCP row loads at process start, so a new conversation is not enough; all profiles inherit it |
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
powershell -ExecutionPolicy Bypass -File <dist-directory>\install-patent-profile.ps1 -Name patent-test
```

- `-Name <name>` — the new profile's name (created under `%USERPROFILE%\.dsh\profiles\<name>`). Default `patent-test`.
- `-DistDir <dir>` — where you unpacked the release. Default `%USERPROFILE%\.dsh\plugin-dist\patent`.
- `-PersonaFrom auto` (default) — installs the persona from a shipped `persona.patch.yml` in the dist directory; with `-PersonaFrom <existing-profile>` it copies that profile's patch instead; `-PersonaFrom ""` skips.
- Idempotent — re-running on an existing profile refreshes it in place.

When it prints `DONE`, **fully quit and relaunch the desktop app**, pick the new profile, and open a session in a patent project directory.

## Manual install (what the script does, step by step)

### 1. Validate the dist layout

```
<dist-dir>\
├─ bundle\                                        # @mtl-academic/dsh-patent (directory form; the 14 skills live here)
├─ mtl-academic-dsh-patent-<version>.tgz
├─ deepseek-ai-dsh-tool-patent-<version>.tgz
├─ deepseek-ai-dsh-command-patent-review-<version>.tgz
├─ deepseek-ai-schemastery-<version>.tgz          # the registry only carries the 3.18.x line; the bundle builds against the vendored fork
├─ deepseek-ai-cosmokit-<version>.tgz
├─ persona.patch.yml                              # the persona as a ready profile patch (optional but recommended)
├─ deepseek_harness_patent_services-<version>.whl # optional Python services (uv tool install, then mcp_wheel: true or DSH_PATENT_SERVICES=1)
├─ install-patent-profile.ps1                     # the quick-install script this guide documents
└─ README.md                                      # the Chinese receiver guide (manual walkthrough)
```

### 2. Initialize the profile and declare the bundle

```cmd
dsh plugin --profile <name> add file:<dist-dir>/bundle
```

- **The `file:` target must be the DIRECTORY, never the tgz** — the desktop app's self-heal resolves every `file:`/`link:` dependency in a profile manifest and uninstalls ones that are not directories. A tarball-shaped install disappears on the next launch.
- This initializes the profile (`dsh.profile.bundles` + `patchReload: live`). The pnpm leg **fails on the bundle's internal `workspace:^` dependencies (they are not published to npm) — expected**; steps 4–5 repair it.

### 3. Write `<profile-dir>\package.json`

Declare the bundle as a directory dependency and complete the bundle stack:

```json
{
  "name": "dsh-profile-<name>",
  "private": true,
  "dependencies": {
    "@mtl-academic/dsh-patent": "file:<dist-dir>/bundle"
  },
  "dsh": {
    "profile": {
      "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "@mtl-academic/dsh-patent"],
      "patchReload": "live"
    }
  }
}
```

### 4. Write `<profile-dir>\pnpm-workspace.yaml` (overrides)

The internal packages are not on npm; pnpm overrides point them at the local tarballs (**pnpm 11 reads overrides from this yaml only — a `pnpm` field in package.json is ignored**):

```yaml
packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false

overrides:
  '@deepseek-ai/dsh-tool-patent': file:<dist-dir>/deepseek-ai-dsh-tool-patent-<version>.tgz
  '@deepseek-ai/dsh-command-patent-review': file:<dist-dir>/deepseek-ai-dsh-command-patent-review-<version>.tgz
  '@deepseek-ai/schemastery': file:<dist-dir>/deepseek-ai-schemastery-<version>.tgz
  '@deepseek-ai/cosmokit': file:<dist-dir>/deepseek-ai-cosmokit-<version>.tgz
```

### 5. Install

```cmd
dsh plugin --profile <name> install
```

Success: pnpm prints `Done`, and `node_modules` under the profile contains `@mtl-academic/dsh-patent` plus `@deepseek-ai/{dsh-tool-patent,dsh-command-patent-review,schemastery,cosmokit}`.

### 6. Install the persona

The bundle ships **persona-free on purpose** (it is a capability layer any profile can mount). The persona lives in the profile's patch layer:

```powershell
Copy-Item <dist-dir>\persona.patch.yml %USERPROFILE%\.dsh\profiles\<name>\cordis.patch.yml
```

The canonical text is also documented in the bundle README ("The persona lives in the profile") — hand-write `cordis.patch.yml`'s `system-prompt.config.persona` from it if you prefer. **Without the persona the assistant has no gatekeeper behavior**: it will not assess ideas before drafting, route through the skills, or push back with publication numbers.

### 7. Verify

```cmd
dsh --profile <name> --dump-config
```

Check three things: the `tool-patent` / `patent-assets` / `command-patent-review` / `mcp-patent-services` rows are present; a `persona:` key appears; the log shows no `DANGLING`/`UNINSTALLING` lines (those mean step 2 was not directory-shaped). `workflow-ptc not found`-style warnings are benign cross-core no-ops.

## What you get

| Capability | Entry point | Needs |
|---|---|---|
| Idea assessment, five-party interview, chapter drafting, review, export — the whole pipeline | Just ask in a session, or `/patent-loop`, `/patent-review` | nothing |
| Disclosure/application export, Word reference parsing | MCP tools, invoked by the model | the single-file gate `~/.dsh/patent-services.yaml`: `mcp_enabled: true` plus `mcp_project_dir` (absolute source path) or `mcp_wheel: true`; scripted setups may set `DSH_PATENT_SERVICES=1` / `DSH_PATENT_SERVICES_DIR` instead |
| Simulation experiments, drawio/HTML figure rendering | MCP tools, invoked by the model | the above + Docker Desktop |
| Chinese prior-art discovery | `search_cn_patents` (model-invoked) | network access to patents.google.com (a proxy is the usual route) |

## Upgrading

Drop the new release's tarballs and `bundle/` over the dist directory, then re-run the installer (it re-resolves the tarball names by pattern and reinstalls). Note that pnpm integrity-checks same-version tarballs — after replacing a tarball in place, delete the `overrides:` block in the profile's `pnpm-workspace.yaml` (or just re-run the installer, which rewrites the manifest and forces a reinstall). The Python services run from their source directory, so updating that directory is enough — no reinstall.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The plugin vanishes after a desktop relaunch; log shows `DANGLING_LINK_UNINSTALLING` | The bundle was installed tarball-shaped. Delete the profile and reinstall — step 2 must target the `bundle` directory |
| `ERR_PNPM_WORKSPACE_PKG_NOT_FOUND` (workspace:^) | The overrides block is missing or its paths are wrong. Check the 4 `overrides:` lines against the tarballs actually present |
| The model cannot see the export/render tools | No Python-services gate is enabled — the preferred single file is `~/.dsh/patent-services.yaml` with `mcp_enabled: true` plus `mcp_project_dir` (absolute path) or `mcp_wheel: true`; scripted setups use `DSH_PATENT_SERVICES=1` / `DSH_PATENT_SERVICES_DIR` — or the gate was enabled after the app started: the MCP row loads at process start, so fully quit and relaunch the desktop app (a new conversation is not enough). In a session, `patent_setup_check` reports 已装载 (loaded) versus 待重启 (restart pending) |
| Review reports "model not found" / auth errors | Pick a GLM model from the `zai-coding-cn` group in the session; the default deepseek line through a GLM gateway fails with "model not found" |
| A review dimension reports all scoring passes failed | Gateway rate limiting. The scripted review batches, backs off, and retries; running `patent_review` once more usually recovers the dimension |
