# install-patent-profile.ps1 — Aurify (dsh-patent) one-command profile installer
#
# Installs the Aurify patent-writing plugin into a fresh (or existing) dsh
# profile on a Windows machine where Deepseek Harness Desktop is installed
# (macOS/Linux: follow the manual steps in INSTALL-NEW-PROFILE.md instead).
# Idempotent: safe to re-run.
#
# Usage (PowerShell):
#   .\install-patent-profile.ps1 -Name patent-test
#   .\install-patent-profile.ps1 -Name my-patent -DistDir D:\rel\patent-dist
#
# What it does:
#   1. Validates the dist artifacts (bundle/ directory + tarballs)
#   2. Initializes the profile via the dsh CLI and declares the bundle
#      (DIRECTORY form — the desktop self-heal uninstalls file: tarballs)
#   3. Writes package.json: the bundle dir dependency + the 3-layer bundle stack
#   4. Writes pnpm-workspace.yaml overrides: the not-yet-published internal
#      packages (tool-patent / command-patent-review / schemastery / cosmokit)
#      resolve from the local tarballs
#   5. `dsh plugin install` materializes everything with pnpm
#   6. Installs the persona (see -PersonaFrom; the bundle ships persona-free)
#   7. Verifies the composed profile via dump-config
#
# Prereqs: desktop app installed. MCP export/render/experiment tools need a
#   Python-services gate — preferred: ~/.dsh/patent-services.yaml with
#   mcp_enabled: true plus mcp_project_dir (absolute source path) or
#   mcp_wheel: true; scripted setups may set user-level DSH_PATENT_SERVICES=1
#   or DSH_PATENT_SERVICES_DIR instead. Either way the MCP row loads at
#   process start, so restart the desktop app after enabling; 
#   experiments/rendering also need Docker Desktop.

param(
  # The profile to create/install into (relative to ~/.dsh/profiles).
  [string]$Name = "patent-test",
  # The directory holding the unpacked release: a bundle/ subdirectory plus
  # the package tarballs. Any location works.
  [string]$DistDir = "$env:USERPROFILE\.dsh\plugin-dist\patent",
  # Where to copy the persona patch from: an existing profile name, or the
  # shipped file "<DistDir>\persona.patch.yml" when present. "" skips persona.
  [string]$PersonaFrom = "auto",
  # Skip the final dump-config verification.
  [switch]$NoVerify
)

$ErrorActionPreference = "Stop"

function Fail($message) { Write-Host "FAIL: $message" -ForegroundColor Red; exit 1 }
function Step($message) { Write-Host "== $message" -ForegroundColor Cyan }

# Windows-only by design: the dsh CLI discovery below reads the desktop app's
# Windows shim directory (%LOCALAPPDATA%\deepseek-harness\bin\dsh.cmd) and the
# profile paths default to %USERPROFILE%. Fail loud on pwsh/non-Windows runs
# instead of a cryptic null-argument error. ($IsWindows is undefined on
# Windows PowerShell 5.1, hence the version short-circuit.)
if (($PSVersionTable.PSVersion.Major -ge 6) -and -not $IsWindows) {
  Fail "this installer is Windows-only. On macOS/Linux follow the manual steps in INSTALL-NEW-PROFILE.md"
}

# 1. Locate the dsh CLI: the desktop shim knows the bundled core; fall back to PATH.
$dshCmd = Join-Path $env:LOCALAPPDATA "deepseek-harness\bin\dsh.cmd"
if (-not (Test-Path $dshCmd)) {
  $onPath = Get-Command dsh -ErrorAction SilentlyContinue
  if ($null -eq $onPath) { Fail "dsh CLI not found (expected $dshCmd or dsh on PATH)" }
  $dshCmd = $onPath.Source
}

# 2. Validate the distribution artifacts before touching the profile. Tarball
#    file names carry the package version — resolve by pattern so the script
#    survives version bumps.
$bundleDir = Join-Path $DistDir "bundle"
Step "Checking dist artifacts in $DistDir"
if (-not (Test-Path (Join-Path $bundleDir "package.json"))) { Fail "bundle directory missing: $bundleDir (unpack the release first)" }

$patterns = @{
  bundle    = "mtl-academic-dsh-patent-*.tgz"
  tool      = "deepseek-ai-dsh-tool-patent-*.tgz"
  command   = "deepseek-ai-dsh-command-patent-review-*.tgz"
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

$profileDir = Join-Path $env:USERPROFILE ".dsh\profiles\$Name"
$newProfile = -not (Test-Path $profileDir)

# 3. Initialize the profile through the official channel. The add writes the
#    manifest scaffolding; its pnpm leg may fail on the unpublished workspace:^
#    dependencies — that is expected and repaired by steps 4-5.
if ($newProfile) {
  Step "Initializing profile $Name via dsh plugin add (directory form)"
  & $dshCmd plugin --profile $Name add "file:$($bundleDir -replace '\\','/')"
  if (-not (Test-Path (Join-Path $profileDir "package.json"))) {
    Fail "profile was not initialized at $profileDir"
  }
  Write-Host "   profile initialized (dependency resolution errors here are expected and repaired below)"
} else {
  Step "Profile $Name already exists — refreshing in place"
}

# 4. package.json: the bundle as a DIRECTORY dependency + the three-layer bundle stack.
Step "Writing package.json (bundle dir dependency + bundle stack)"
$manifest = @{
  name = "dsh-profile-$Name"
  private = $true
  dependencies = @{
    "@mtl-academic/dsh-patent" = "file:$($bundleDir -replace '\\','/')"
  }
  dsh = @{
    profile = @{
      bundles = @("@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "@mtl-academic/dsh-patent")
      patchReload = "live"
    }
  }
}
$manifestJson = $manifest | ConvertTo-Json -Depth 8
# Force UTF-8 without BOM: Windows PowerShell defaults would mangle the file
# for downstream readers and flip line endings for the pnpm layer.
[System.IO.File]::WriteAllText((Join-Path $profileDir "package.json"), $manifestJson,
  (New-Object System.Text.UTF8Encoding($false)))
Write-Host "   wrote bundles: dsh-base + dsh-web-app + @mtl-academic/dsh-patent"

# 5. pnpm-workspace.yaml overrides: the internal packages are not on npm yet;
#    pnpm 11 reads overrides from this yaml (package.json#pnpm is ignored).
Step "Writing pnpm-workspace.yaml overrides"
$distForward = $DistDir -replace '\\','/'
$overrides = @"

# Aurify plugin: the internal packages are resolved from local tarballs until
# they are published to npm (the registry only carries the 3.18.x schemastery
# line; the bundle was built against the vendored fork). Remove this block
# after publication.
overrides:
  '@deepseek-ai/dsh-tool-patent': file:$distForward/$($tarballs['tool'])
  '@deepseek-ai/dsh-command-patent-review': file:$distForward/$($tarballs['command'])
  '@deepseek-ai/schemastery': file:$distForward/$($tarballs['schemastery'])
  '@deepseek-ai/cosmokit': file:$distForward/$($tarballs['cosmokit'])
"@
$wsPath = Join-Path $profileDir "pnpm-workspace.yaml"
$ws = ""
if (Test-Path $wsPath) { $ws = [System.IO.File]::ReadAllText($wsPath) }
if ($ws -match "overrides:") {
  Write-Host "   overrides block already present — leaving as is (delete it to re-resolve after a version bump)"
} else {
  [System.IO.File]::WriteAllText($wsPath, ($ws.TrimEnd() + "`n" + $overrides),
    (New-Object System.Text.UTF8Encoding($false)))
  Write-Host "   appended 4 overrides (tool-patent / command-patent-review / schemastery / cosmokit)"
}

# 6. Install: pnpm materializes the bundle and the overridden internal deps.
Step "dsh plugin install (pnpm leg)"
& $dshCmd plugin --profile $Name install
if ($LASTEXITCODE -ne 0) { Fail "pnpm install failed in $profileDir — check the output above" }

# 7. Persona: the bundle is persona-free on purpose; the profile patch layer
#    carries it. Sources, in order: an existing profile (-PersonaFrom <name>),
#    then the shipped <DistDir>\persona.patch.yml when present. Without either,
#    follow the bundle README ("The persona lives in the profile") to hand-write
#    <profile>\cordis.patch.yml — without a persona the assistant has no
#    gatekeeper behavior at all.
function Test-HasPersona($patchPath) {
  (Test-Path $patchPath) -and ((Get-Content $patchPath -Raw) -match "persona:")
}
$targetPatch = Join-Path $profileDir "cordis.patch.yml"
if ($PersonaFrom -eq "") {
  Write-Host "== Skipping persona (PersonaFrom is empty)"
} else {
  Step "Installing persona"
  $shipped = Join-Path $DistDir "persona.patch.yml"
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
    if (Test-HasPersona $targetPatch) {
      Write-Host "   persona already present — leaving as is"
    } else {
      Write-Host "   WARN: no persona source found. Copy the persona text from the bundle README" -ForegroundColor Yellow
      Write-Host "   ('The persona lives in the profile' section) into $targetPatch." -ForegroundColor Yellow
    }
  }
}

# 8. Verify: the composed profile must carry the patent rows.
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
Write-Host "    preferred: ~/.dsh/patent-services.yaml with mcp_enabled: true plus mcp_project_dir (absolute path)"
Write-Host "    or mcp_wheel: true; scripted: user-level DSH_PATENT_SERVICES=1 / DSH_PATENT_SERVICES_DIR."
Write-Host "    The MCP row loads at process start - restart the desktop app after enabling."
Write-Host "    Experiments and figure rendering also need Docker Desktop."
