# Aurify · Installation and environment guide

English · [中文](README.md) · [Documentation index](../README.md)

For users with DeepSeek Harness Desktop or a compatible dsh host. Configure a working model and API key in the host first; Aurify includes no model. Compatibility branches target the 0.1.5-rc through 0.1.6-alpha host lines; this documentation update did not retest the version matrix.

See the [repository README](../../README.md) for source versions. GitHub Release, npm/PyPI and the marketplace publish independently; check the version in your chosen channel.

## Marketplace and natural-language initialization (recommended)

1. In the desktop app, open **Settings → Plugin marketplace**, search **Aurify** or **点金**, and install into the active profile.
2. In that profile, ask:

   > Help me initialize the Aurify plugin environment. Check and configure the required dependencies and services.

3. Follow the `patent_setup_check` report. After changing MCP configuration, **fully quit and relaunch the desktop app**, then ask:

   > Recheck the Aurify environment and confirm the required services are ready.

Use the recheck as evidence of readiness. Saving settings or opening a new conversation does not replace a restart. Then describe an idea or supply an existing docx. The remaining sections cover manual alternatives and troubleshooting.

## npm and the Windows installer

Cross-platform manual installation:

```sh
dsh plugin --profile patent-demo add @mtl-academic/dsh-patent
dsh --profile patent-demo --dump-config
```

If `dsh` is missing, check the desktop shim: `%LOCALAPPDATA%\deepseek-harness\bin\dsh.cmd` on Windows, usually `~/.local/bin/dsh` on macOS/Linux. Configuration defaults to `~/.dsh/` (`%USERPROFILE%\.dsh` on Windows).

On Windows, run from the repository root; omit `scripts/` when using Release attachments:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-patent-profile.ps1 -Name patent-demo
```

The installer merges profile dependencies, installs the persona from `persona.patch.yml` beside itself, and runs `--dump-config`. Options: `-Name` selects the profile; `-PersonaFrom` selects an existing profile (`auto` uses the shipped persona, an empty string skips it); `-NoVerify` skips validation. The installer is Windows-only; use manual commands on macOS/Linux.

A general-purpose profile can keep its persona. For a dedicated patent persona, merge entries from [`persona.patch.yml`](../../scripts/persona.patch.yml) into `~/.dsh/profiles/<name>/cordis.patch.yml`, preserving existing patches. The Bundle itself is persona-free.

When switching a legacy local-package install back to npm, remove Aurify's four `file:` overrides from `pnpm-workspace.yaml`, preserving unrelated configuration. The installer's npm route cleans up these legacy entries.

## Local-package installation

Download the matching version ZIP from [GitHub Releases](https://github.com/ai-tools-mtl/Aurify/releases) and verify `SHA256SUMS`. Source checkouts do not include `dist/`. The ZIP contains three plugin tarballs, two configuration-library tarballs, Python wheel/sdist, installer, persona and bilingual guides; create `bundle/` by unpacking it yourself.

Local packages replace only part of the downloads. Fully disconnected machines also need the host, npm/Python transitive dependencies and Docker images prepared in advance.

In the release directory, substitute the actual version:

```sh
mkdir bundle
tar -xzf mtl-academic-dsh-patent-<version>.tgz -C bundle --strip-components=1
```

On Windows prefer `C:\Windows\System32\tar.exe` to avoid Git MSYS tar's signal-pipe failure in restricted shells. Keep `bundle/` beside the five `.tgz` files.

Windows installation:

```powershell
powershell -ExecutionPolicy Bypass -File install-patent-profile.ps1 -Name patent-demo -Offline -DistDir "C:/aurify-release"
```

Use a forward-slash absolute `-DistDir`. Keep the release directory after installation: the profile references its `bundle/` at runtime, and moving or deleting it breaks resolution.

Cross-platform manual alternative:

1. For a new profile, run `dsh plugin --profile patent-demo add "file:<DIST>/bundle"` to create its manifest. Dependency resolution may fail before configuration is complete; confirm the manifest exists, then continue.
2. Merge `"@mtl-academic/dsh-patent": "file:<DIST>/bundle"` into the profile's `package.json` dependencies and ensure `dsh.profile.bundles` includes the package. Preserve host layers and other dependencies.
3. Merge these four entries into the profile's `pnpm-workspace.yaml`. Replace `<DIST>` and `<version>`; use configuration-library versions matching the downloaded filenames:

   ```yaml
   overrides:
     '@mtl-academic/dsh-tool-patent': 'file:<DIST>/mtl-academic-dsh-tool-patent-<version>.tgz'
     '@mtl-academic/dsh-command-patent-review': 'file:<DIST>/mtl-academic-dsh-command-patent-review-<version>.tgz'
     '@deepseek-ai/schemastery': 'file:<DIST>/deepseek-ai-schemastery-3.18.2.tgz'
     '@deepseek-ai/cosmokit': 'file:<DIST>/deepseek-ai-cosmokit-1.8.3.tgz'
   ```

4. Run `dsh plugin --profile patent-demo install`, optionally merge the persona, then run `dsh --profile patent-demo --dump-config`.

Every `file:` value must be absolute. Point the Bundle at its unpacked directory, not its `.tgz`. Upgrade with new-version attachments and rerun the installer; do not mix multiple versions or replace published same-version files.

## Services and runtime dependencies

[uv/uvx](https://docs.astral.sh/uv/) must be available to launch Python MCP services. Merge one mode into `$DSH_HOME/patent-services.yaml` (default `~/.dsh/patent-services.yaml`):

```yaml
mcp_enabled: true
mcp_wheel: true  # resolves from PyPI, not pinned to this source version
```

For exact-version use, or offline use after caching dependencies, select source mode:

```yaml
mcp_enabled: true
mcp_project_dir: /absolute/path/to/Aurify/python/patent-services
```

The source path must be absolute and contain `pyproject.toml`. Wheel mode runs `uvx --from deepseek-harness-patent-services patent-services`; it needs no prior `uv tool install` and does not guarantee use of a locally installed wheel. Both modes require `mcp_enabled: true`.

Scripted setups may use `DSH_PATENT_SERVICES=1` or `DSH_PATENT_SERVICES_DIR`. Fully restart and recheck after changing the mode, source path or PATH. GUI apps may not inherit shell-profile variables.

| Capability | Extra dependency |
|---|---|
| docx import/export, archive search | Python MCP services |
| PDF | Windows Word COM, or separately installed weasyprint and system libraries; fallback layout may differ |
| drawio rendering | draw.io CLI or Docker; default image `q771103517/dsh-patent:latest` |
| HTML rendering | Edge/Chrome; tall canvases may exceed the fixed viewport |
| Simulation | Running Docker; default image `q771103517/dsh-patent-experiment:latest` |
| CN patent search | Access to `patents.google.com` |

Images may need downloading on first use. Setup reports each channel; project initialization follows the skills' requirements for fixing unavailable channels. Skipping search requires an explicit user choice and a research-debt marker. See the [Python service reference](../../python/patent-services/README.md) for interfaces and preferences.

## Verification, recovery and troubleshooting

After manual installation, require exit code 0 from `--dump-config` before relaunching. Check for `tool-patent`, `patent-assets`, `command-patent-review` and `mcp-patent-services`. An MCP row does not establish that services are enabled; run the in-session check. Request `patent_brief_coverage` with `field=测试` to inspect a tool result. Older hosts may show plain text instead of a structured card.

Merge existing profile manifests, bundle layers and patches. Before refreshing an existing profile, the installer backs up state to `~/.dsh/.plugin-backups/<name>-<timestamp>/`. If host plugin declarations were lost, restore a backup first, or reconstruct dependencies and bundle layers from that profile's lockfile `importers`, then reinstall.

| Symptom | Action |
|---|---|
| `cannot resolve profile bundle` / plugin vanishes after relaunch | Check absolute `file:` paths and the retained `bundle/`; repair the directory dependency and reinstall without deleting the profile |
| `ERR_PNPM_WORKSPACE_PKG_NOT_FOUND` | Check paths and overrides; use built release manifests, not unconverted source manifests |
| `--dump-config` reports `EPERM` | It writes the profile's `cordis.yml`; rerun with write access |
| MCP tools missing / restart pending | Check master switch, mode and uv/uvx PATH; fully quit and relaunch |
| Wheel fetch fails | Check PyPI access and uv/uvx; use source mode with cached dependencies for exact-version or restricted-network operation |
| Review authentication error / `model not found` | Select a model the configured gateway supports, with valid credentials |
| All passes for a dimension fail | Inspect the report, resolve rate limits, network or model errors, then retry; do not judge only the total |
| Search unreachable | Check connectivity and proxy settings; retain the failure reason rather than inventing hits |

Older hosts use capability fallbacks for scoring temperature, discussion temperature and Web cards. Recheck after host upgrades; compatibility branches are not evidence of a fully tested version matrix.

See the [development guide](../DEVELOPMENT.md) and [release workflow](../RELEASING.md) for source builds, tests and packaging.
