# install-patent-profile.ps1 — Aurify (dsh-patent) one-command profile installer
#
# Installs the Aurify patent-writing plugin into a fresh (or existing) dsh
# profile on a Windows machine where Deepseek Harness Desktop is installed
# (macOS/Linux: follow the manual steps in INSTALL-NEW-PROFILE.md instead).
# Idempotent: safe to re-run.
#
# Usage (PowerShell):
#   .\install-patent-profile.ps1 -Name patent-test
#     npm route (default, needs registry access): resolves
#     @mtl-academic/dsh-patent from npm, installs the persona from the shipped
#     persona.patch.yml beside this script, and verifies via dump-config. No
#     tarballs, no unpacking, no overrides.
#   .\install-patent-profile.ps1 -Name my-patent -Offline -DistDir D:\rel\patent-dist
#     offline route (air-gapped machines): the legacy flow — validates the
#     dist artifacts, installs the unpacked bundle/ directory as a file:
#     dependency, and pins the internal packages to the local tarballs via
#     pnpm-workspace.yaml overrides.
#
# What the npm route does:
#   1. Locates the dsh CLI
#   2. `dsh plugin add @mtl-academic/dsh-patent` — creates the profile
#      scaffold on first run (base + web-app + patent bundle stack), or
#      updates the dependency to the published version on later runs
#   3. Strips a legacy install's `overrides:` block if present (it would pin
#      the npm dependency back to stale local tarballs)
#   4. Installs the persona (see -PersonaFrom; the bundle ships persona-free)
#   5. Verifies the composed profile via dump-config
#
# Prereqs: desktop app installed. MCP export/render/experiment tools need a
#   Python-services gate — preferred: ~/.dsh/patent-services.yaml with
#   mcp_enabled: true plus mcp_project_dir (absolute source path) or
#   mcp_wheel: true (uvx fetches deepseek-harness-patent-services from PyPI);
#   scripted setups may set user-level DSH_PATENT_SERVICES=1
#   or DSH_PATENT_SERVICES_DIR instead. Either way the MCP row loads at
#   process start, so restart the desktop app after enabling;
#   experiments/rendering also need Docker Desktop.

param(
  # The profile to create/install into (relative to ~/.dsh/profiles).
  [string]$Name = "patent-test",
  # Offline route: the directory holding the unpacked release (a bundle/
  # subdirectory plus the package tarballs). Ignored without -Offline; the
  # persona is always taken from the script's own directory when present.
  [string]$DistDir = $PSScriptRoot,
  # Use the offline flow (local tarballs + overrides) instead of npm.
  [switch]$Offline,
  # Where to copy the persona patch from: an existing profile name, or the
  # shipped file "<script dir>\persona.patch.yml" when present. "" skips persona.
  [string]$PersonaFrom = "auto",
  # Skip the final dump-config verification.
  [switch]$NoVerify
)

$ErrorActionPreference = "Stop"

function Fail($message) { Write-Host "FAIL: $message" -ForegroundColor Red; exit 1 }
function Step($message) { Write-Host "== $message" -ForegroundColor Cyan }

# Snapshot the four files that encode a profile's dependency state before the
# installer rewrites any of them — a bad merge is recoverable from the backup
# instead of a rebuild-from-the-lockfile exercise.
function Backup-ProfileManifests {
  $backupDir = Join-Path $env:USERPROFILE ".dsh\.plugin-backups\$Name-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
  foreach ($f in @("package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml", "cordis.patch.yml")) {
    $source = Join-Path $profileDir $f
    if (Test-Path $source) { Copy-Item $source (Join-Path $backupDir $f) -Force }
  }
  Write-Host "   previous manifest backed up to $backupDir"
}

function Read-Manifest {
  $manifestPath = Join-Path $profileDir "package.json"
  $manifest = $null
  if (Test-Path $manifestPath) {
    try { $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json } catch { $manifest = $null }
  }
  if ($null -eq $manifest) { $manifest = [pscustomobject]@{} }
  return $manifest
}

function Write-Manifest($manifest) {
  $manifestPath = Join-Path $profileDir "package.json"
  $manifestJson = $manifest | ConvertTo-Json -Depth 8
  # Force UTF-8 without BOM: Windows PowerShell defaults would mangle the file
  # for downstream readers and flip line endings for the pnpm layer.
  [System.IO.File]::WriteAllText($manifestPath, $manifestJson,
    (New-Object System.Text.UTF8Encoding($false)))
}

# Remove the bundle dependency when a legacy install declared it as a
# `file:` spec. `dsh plugin add` must resolve the whole tree before it can
# rewrite the manifest, so a file: spec pointing at a deleted dist directory
# fails the add with ENOENT before the npm replacement happens — drop the key
# here and the add below re-declares it from the registry.
function Remove-LegacyBundleFileDep {
  $manifest = Read-Manifest
  $deps = $manifest.PSObject.Properties["dependencies"]
  if ($null -eq $deps -or $null -eq $deps.Value) { return }
  $p = $deps.Value.PSObject.Properties["@mtl-academic/dsh-patent"]
  if ($null -ne $p -and $p.Value -is [string] -and $p.Value.StartsWith("file:")) {
    # Windows PowerShell 5.1: member removal goes through the Properties
    # collection, not the PSObject wrapper.
    $deps.Value.PSObject.Properties.Remove("@mtl-academic/dsh-patent")
    Write-Manifest $manifest
    Write-Host "   removed the legacy file: bundle dependency (re-added from npm by the next step)"
  }
}

# Strip the overrides block the offline route writes into pnpm-workspace.yaml
# (banner comment, `overrides:` header, and the four file:-pinned keys). On
# the npm route those pins defeat registry resolution: an upgrade would
# resolve to the stale pinned tarball instead of the published package. The
# base keys (packages / nodeLinker / autoInstallPeers) and any unrelated
# overrides stay untouched.
function Remove-LegacyOverrides {
  $wsPath = Join-Path $profileDir "pnpm-workspace.yaml"
  if (-not (Test-Path $wsPath)) { return }
  $lines = [System.IO.File]::ReadAllLines($wsPath)
  $pinnedKeys = @("'@mtl-academic/dsh-tool-patent':", "'@mtl-academic/dsh-command-patent-review':", "'@deepseek-ai/schemastery':", "'@deepseek-ai/cosmokit':")
  $out = New-Object System.Collections.Generic.List[string]
  $inBanner = $false
  $removed = 0
  foreach ($line in $lines) {
    if ($inBanner) {
      if ($line -match '^#') { $removed++; continue }
      if ($line -match '^overrides:') { $removed++; $inBanner = $false; continue }
      $inBanner = $false
    }
    if ($line -match '^# Aurify plugin:') { $inBanner = $true; $removed++; continue }
    $isPinned = $false
    foreach ($k in $pinnedKeys) {
      if ($line.TrimStart().StartsWith($k)) { $isPinned = $true; break }
    }
    if ($isPinned) { $removed++; continue }
    [void]$out.Add($line)
  }
  if ($removed -gt 0) {
    [System.IO.File]::WriteAllText($wsPath, (($out -join "`n").TrimEnd() + "`n"),
      (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "   removed $removed legacy override lines (npm route resolves from the registry)"
  }
}

# Windows-only by design: the dsh CLI discovery below reads the desktop app's
# Windows shim directory (%LOCALAPPDATA%\deepseek-harness\bin\dsh.cmd) and the
# profile paths default to %USERPROFILE%. Fail loud on pwsh/non-Windows runs
# instead of a cryptic null-argument error. ($IsWindows is undefined on
# Windows PowerShell 5.1, hence the version short-circuit.)
if (($PSVersionTable.PSVersion.Major -ge 6) -and -not $IsWindows) {
  Fail "this installer is Windows-only. On macOS/Linux follow the manual steps in INSTALL-NEW-PROFILE.md"
}

# Locate the dsh CLI: the desktop shim knows the bundled core; fall back to PATH.
$dshCmd = Join-Path $env:LOCALAPPDATA "deepseek-harness\bin\dsh.cmd"
if (-not (Test-Path $dshCmd)) {
  $onPath = Get-Command dsh -ErrorAction SilentlyContinue
  if ($null -eq $onPath) { Fail "dsh CLI not found (expected $dshCmd or dsh on PATH)" }
  $dshCmd = $onPath.Source
}

$profileDir = Join-Path $env:USERPROFILE ".dsh\profiles\$Name"

if ($Offline) {
  # ------------------------------------------------------------------
  # Offline route: local tarballs + overrides (no registry access needed)
  # ------------------------------------------------------------------

  # Validate the distribution artifacts before touching the profile. Tarball
  # file names carry the package version — resolve by pattern so the script
  # survives version bumps.
  $bundleDir = Join-Path $DistDir "bundle"
  Step "Checking dist artifacts in $DistDir"
  if (-not (Test-Path (Join-Path $bundleDir "package.json"))) { Fail "bundle directory missing: $bundleDir (unpack the release first: tar -xzf mtl-academic-dsh-patent-*.tgz -C bundle --strip-components=1)" }

  # Anchor both paths before anything writes them into the profile. The manifest
  # records the release directory verbatim as a `file:` dependency, and the dsh
  # core resolves every `file:` value against the PROFILE directory — never
  # against the shell's current directory. A relative -DistDir would therefore
  # install a profile whose bundle dependency points at nothing.
  $DistDir = (Resolve-Path -LiteralPath $DistDir).Path
  $bundleDir = (Resolve-Path -LiteralPath $bundleDir).Path

  $patterns = @{
    bundle    = "mtl-academic-dsh-patent-*.tgz"
    tool      = "mtl-academic-dsh-tool-patent-*.tgz"
    command   = "mtl-academic-dsh-command-patent-review-*.tgz"
    schemastery = "deepseek-ai-schemastery-*.tgz"
    cosmokit  = "deepseek-ai-cosmokit-*.tgz"
  }
  $tarballs = @{}
  foreach ($key in $patterns.Keys) {
    $match = Get-ChildItem $DistDir -Filter $patterns[$key] -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $match) { Fail "missing tarball matching $($patterns[$key]) in $DistDir" }
    $tarballs[$key] = $match.Name
  }
  $skills = (Get-ChildItem (Join-Path $bundleDir "skills") -Directory).Count
  Write-Host "   bundle ok ($skills skills); tarballs: $($tarballs.Values -join ', ')"

  $newProfile = -not (Test-Path $profileDir)

  # Initialize the profile through the official channel. The add writes the
  # manifest scaffolding; its pnpm leg may fail on the workspace:^
  # dependencies resolved by the overrides below — that is expected.
  if ($newProfile) {
    Step "Initializing profile $Name via dsh plugin add (directory form)"
    & $dshCmd plugin --profile $Name add "file:$($bundleDir -replace '\\','/')"
    if (-not (Test-Path (Join-Path $profileDir "package.json"))) {
      Fail "profile was not initialized at $profileDir"
    }
    Write-Host "   profile initialized (dependency resolution errors here are expected and repaired below)"
  } else {
    Step "Profile $Name already exists — refreshing in place"
    # Refresh-in-place rewrites files a user may never have copied aside, and an
    # existing profile can carry entries this installer does not manage (the
    # desktop app's own dsh-tauri*/dshmarket dependencies and bundle layers).
    # Snapshot the files that encode its dependency state first, so a bad
    # merge is recoverable instead of a rebuild-from-the-lockfile exercise.
    Backup-ProfileManifests
  }

  # package.json: the bundle as a DIRECTORY dependency + the three-layer bundle stack.
  # MERGE, never overwrite: an existing profile may carry other plugins'
  # dependencies and bundle entries (the desktop's own profiles do), and a
  # re-run must not wipe them. Our entries are ensured present; everything
  # else is preserved as is.
  Step "Writing package.json (bundle dir dependency + bundle stack)"
  $bundleDep = "file:$($bundleDir -replace '\\','/')"
  $manifest = Read-Manifest
  if (-not $manifest.PSObject.Properties["name"]) { $manifest | Add-Member name "dsh-profile-$Name" }
  if (-not $manifest.PSObject.Properties["private"]) { $manifest | Add-Member private $true }
  if (-not $manifest.PSObject.Properties["dependencies"] -or $null -eq $manifest.dependencies) {
    $manifest | Add-Member dependencies ([pscustomobject]@{})
  }
  $existingDeps = $manifest.dependencies.PSObject.Properties
  if ($existingDeps["@mtl-academic/dsh-patent"]) {
    $existingDeps["@mtl-academic/dsh-patent"].Value = $bundleDep
  } else {
    $manifest.dependencies | Add-Member "@mtl-academic/dsh-patent" $bundleDep
  }
  $ourBundles = @("@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app")
  $dsh = $manifest.PSObject.Properties["dsh"].Value
  $profile = if ($dsh -and $dsh.profile) { $dsh.profile } else { $null }
  $stack = if ($profile -and $profile.bundles) { @($profile.bundles) } else { @() }
  # Layer order is semantic: base and web-app are the foundation — pulled out
  # of wherever they sit and re-fronted in this fixed order — and the patent
  # bundle layers last (its patch re-enables the workflow engine the web layer
  # disables). Every other entry keeps its existing relative order, including
  # anything deliberately layered after patent.
  $stack = @($stack | Where-Object { $ourBundles -notcontains $_ })
  $stack = $ourBundles + $stack
  if ($stack -notcontains "@mtl-academic/dsh-patent") { $stack += "@mtl-academic/dsh-patent" }
  if ($null -eq $profile) {
    $profile = [pscustomobject]@{ bundles = $stack }
    if ($dsh) {
      if ($dsh.PSObject.Properties["profile"]) { $dsh.profile = $profile } else { $dsh | Add-Member profile $profile }
    } else {
      $manifest | Add-Member dsh ([pscustomobject]@{ profile = $profile })
    }
  } else {
    $profile.bundles = $stack
  }
  Write-Manifest $manifest

  # pnpm-workspace.yaml overrides: pin the internal packages (and the
  # schemastery/cosmokit fork line) to this release's local tarballs. pnpm 11
  # reads overrides from this yaml only (package.json#pnpm is ignored). The
  # file: values are single-quoted — an unquoted path containing a space would
  # break the yaml parse on the next pnpm run.
  Step "Writing pnpm-workspace.yaml overrides"
  $distForward = ($DistDir -replace '\\','/') -replace "'", "''"
  $toolTgz = $tarballs['tool']; $commandTgz = $tarballs['command']
  $smTgz = $tarballs['schemastery']; $ckTgz = $tarballs['cosmokit']
  $overrides = @"

# Aurify plugin: the offline path pins the two internal packages (and the
# schemastery/cosmokit fork line the bundle was built against) to this
# release's local tarballs. Install from npm instead and this block is not
# written at all; remove it to let the registry resolve everything.
overrides:
  '@mtl-academic/dsh-tool-patent': 'file:$distForward/$toolTgz'
  '@mtl-academic/dsh-command-patent-review': 'file:$distForward/$commandTgz'
  '@deepseek-ai/schemastery': 'file:$distForward/$smTgz'
  '@deepseek-ai/cosmokit': 'file:$distForward/$ckTgz'
"@
  $wsPath = Join-Path $profileDir "pnpm-workspace.yaml"
  $ws = ""
  if (Test-Path $wsPath) { $ws = [System.IO.File]::ReadAllText($wsPath) }
  if ($ws -match "overrides:") {
    # The tarball file names carry versions, so an existing block must be
    # refreshed in place on every run — leaving it would pin the previous
    # release's tarball names and break `dsh plugin install` after an upgrade.
    $refreshTargets = [ordered]@{
      "'@mtl-academic/dsh-tool-patent'" = "file:$distForward/$toolTgz"
      "'@mtl-academic/dsh-command-patent-review'" = "file:$distForward/$commandTgz"
      "'@deepseek-ai/schemastery'" = "file:$distForward/$smTgz"
      "'@deepseek-ai/cosmokit'" = "file:$distForward/$ckTgz"
    }
    $replaced = 0
    foreach ($key in $refreshTargets.Keys) {
      $pattern = "(?m)^  $key`: .*$"
      if ($ws -match $pattern) {
        $ws = $ws -replace $pattern, "  $key`: '$($refreshTargets[$key])'"
        $replaced += 1
      }
    }
    [System.IO.File]::WriteAllText($wsPath, $ws, (New-Object System.Text.UTF8Encoding($false)))
    if ($replaced -eq 4) {
      Write-Host "   refreshed 4 override lines to the current tarballs"
    } else {
      Write-Host "   WARN: refreshed $replaced of 4 override lines — review $wsPath by hand" -ForegroundColor Yellow
    }
  } else {
    [System.IO.File]::WriteAllText($wsPath, ($ws.TrimEnd() + "`n" + $overrides),
      (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "   appended 4 overrides (tool-patent / command-patent-review / schemastery / cosmokit)"
  }

  # Install: pnpm materializes the bundle and the overridden internal deps.
  Step "dsh plugin install (pnpm leg)"
  & $dshCmd plugin --profile $Name install
  if ($LASTEXITCODE -ne 0) { Fail "pnpm install failed in $profileDir — check the output above" }
} else {
  # ------------------------------------------------------------------
  # npm route (default): the registry resolves everything
  # ------------------------------------------------------------------

  if (Test-Path $profileDir) {
    Step "Profile $Name already exists — refreshing in place"
    # Snapshot the dependency state first (same safety as the offline route),
    # and strip a legacy install's overrides block: it pins the npm dependency
    # back to local tarballs and defeats the registry resolution below.
    Backup-ProfileManifests
    Remove-LegacyOverrides
    Remove-LegacyBundleFileDep
  } else {
    Step "Profile $Name is new — dsh plugin add will create it"
  }

  Step "dsh plugin add @mtl-academic/dsh-patent (from npm)"
  & $dshCmd plugin --profile $Name add "@mtl-academic/dsh-patent"
  if ($LASTEXITCODE -ne 0) {
    Fail "dsh plugin add failed — check registry access (npm/npmmirror) and that the pnpm metadata cache is not stale (clear %LOCALAPPDATA%\pnpm-cache\v11\metadata* if a just-published version is not found)"
  }
  if (-not (Test-Path (Join-Path $profileDir "package.json"))) {
    Fail "profile was not initialized at $profileDir"
  }

  # Ensure the patent bundle is declared in the stack. `dsh plugin add`
  # writes the full stack on a fresh profile; on a profile created before
  # this plugin existed, the entry may be missing while the dependency is now
  # present — declare it last (its patch re-enables the workflow engine).
  $manifest = Read-Manifest
  $dsh = $manifest.PSObject.Properties["dsh"].Value
  $profile = if ($dsh -and $dsh.profile) { $dsh.profile } else { $null }
  $stack = if ($profile -and $profile.bundles) { @($profile.bundles) } else { @() }
  if ($stack -notcontains "@mtl-academic/dsh-patent") {
    if ($null -eq $profile) {
      $profile = [pscustomobject]@{ bundles = @("@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "@mtl-academic/dsh-patent") }
      if ($dsh) {
        if ($dsh.PSObject.Properties["profile"]) { $dsh.profile = $profile } else { $dsh | Add-Member profile $profile }
      } else {
        $manifest | Add-Member dsh ([pscustomobject]@{ profile = $profile })
      }
    } else {
      $profile.bundles = @($stack) + "@mtl-academic/dsh-patent"
    }
    Write-Manifest $manifest
    Write-Host "   ensured bundles stack carries @mtl-academic/dsh-patent"
  }
}

# Persona: the bundle is persona-free on purpose; the profile patch layer
# carries it. Sources, in order: an existing profile (-PersonaFrom <name>),
# then the shipped persona.patch.yml beside this script. Without either,
# follow the bundle README ("The persona lives in the profile") to hand-write
# <profile>\cordis.patch.yml — without a persona the assistant has no
# gatekeeper behavior at all.
function Test-HasPersona($patchPath) {
  (Test-Path $patchPath) -and ((Get-Content $patchPath -Raw) -match "persona:")
}
$targetPatch = Join-Path $profileDir "cordis.patch.yml"
if ($PersonaFrom -eq "") {
  Write-Host "== Skipping persona (PersonaFrom is empty)"
} elseif (Test-HasPersona $targetPatch) {
  # Never overwrite a persona the profile already carries — a -Force copy from
  # a reference profile would also wipe any other rows this patch holds.
  Write-Host "== Persona already present in $targetPatch — leaving as is"
} else {
  Step "Installing persona"
  $shipped = Join-Path $PSScriptRoot "persona.patch.yml"
  $copied = $false
  if ($PersonaFrom -ne "auto") {
    $reference = Join-Path $env:USERPROFILE ".dsh\profiles\$PersonaFrom\cordis.patch.yml"
    if (Test-HasPersona $reference) {
      Copy-Item $reference $targetPatch -Force
      Write-Host "   persona copied from profile $PersonaFrom"
      $copied = $true
    } else {
      Write-Host "   reference profile patch not usable ($reference) — falling back"
    }
  }
  if (-not $copied -and (Test-HasPersona $shipped)) {
    Copy-Item $shipped $targetPatch -Force
    Write-Host "   persona installed from shipped persona.patch.yml"
    $copied = $true
  }
  if (-not $copied) {
    Write-Host "   WARN: no persona source found. Copy the persona text from the bundle README" -ForegroundColor Yellow
    Write-Host "   ('The persona lives in the profile' section) into $targetPatch." -ForegroundColor Yellow
  }
}

# Verify: the composed profile must carry the patent rows.
if (-not $NoVerify) {
  Step "Verifying composition (dump-config)"
  $desktopBin = Join-Path $env:APPDATA "io.github.hairyf.deepseek-harness-desktop\dependencies\dsh\node_modules\@deepseek-ai\dsh\lib\bin.js"
  if (-not (Test-Path $desktopBin)) {
    Write-Host "   desktop core not found at the default location — run manually: dsh --profile $Name --dump-config"
  } else {
    # The core prints benign cross-core warnings (e.g. "workflow-ptc not
    # found" on the rc line, the bundle's other engine row no-ops) on stderr;
    # let them through instead of tripping $ErrorActionPreference.
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $dump = (& node $desktopBin --profile $Name --dump-config 2>&1 | ForEach-Object { "$_" }) -join "`n"
    $ErrorActionPreference = $previousEap
    $patentRows = ([regex]::Matches($dump, "tool-patent|patent-assets|command-patent-review|mcp-patent-services")).Count
    # Match the config KEY (ASCII) — the persona TEXT itself gets mangled by
    # console code pages, and matching mangled text would always fail.
    $persona = ([regex]::Matches($dump, "persona:")).Count
    Write-Host "   patent rows in dump: $patentRows; persona present: $($persona -ge 1)"
    if ($patentRows -lt 3) { Fail "expected at least 3 patent rows in the composed profile" }
    if ($persona -lt 1) { Fail "persona not visible in the composed profile" }
  }
}

Write-Host ""
Write-Host "DONE: profile '$Name' installed." -ForegroundColor Green
Write-Host "  - Restart the desktop app (fully quit + relaunch) to pick up the new profile."
Write-Host "  - Pick the '$Name' profile in the desktop app, open a session in a patent project directory."
Write-Host "  - MCP export/render/experiment tools need a Python-services gate:"
Write-Host "    preferred: ~/.dsh/patent-services.yaml with mcp_enabled: true plus mcp_wheel: true"
Write-Host "    (uvx fetches deepseek-harness-patent-services from PyPI) or mcp_project_dir"
Write-Host "    (absolute source path); scripted: user-level DSH_PATENT_SERVICES=1 /"
Write-Host "    DSH_PATENT_SERVICES_DIR. The MCP row loads at process start - restart the"
Write-Host "    desktop app after enabling. Experiments and figure rendering also need"
Write-Host "    Docker Desktop."

exit 0
