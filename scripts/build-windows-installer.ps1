param(
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

$SpecPath = Join-Path $ProjectRoot "installer\windows\diskimage_explorer_x68k.iss"
if (-not (Test-Path $SpecPath)) {
  throw "Inno Setup script not found: $SpecPath"
}

$PyProjectPath = Join-Path $ProjectRoot "pyproject.toml"
$Version = "0.1.0"
if (Test-Path $PyProjectPath) {
  $m = Select-String -Path $PyProjectPath -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
  if ($m -and $m.Matches.Count -gt 0) {
    $Version = $m.Matches[0].Groups[1].Value
  }
}

if (-not $SkipBuild) {
  & "$ScriptDir\build-windows.ps1"
}

$DistDir = Join-Path $ProjectRoot "dist\diskimage_explorer_x68k"
$ExePath = Join-Path $DistDir "diskimage_explorer_x68k.exe"
if (-not (Test-Path $ExePath)) {
  throw "Windows build output not found: $ExePath"
}

$IsccCandidates = @(
  "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$IsccPath = $null
foreach ($candidate in $IsccCandidates) {
  if (Test-Path $candidate) {
    $IsccPath = $candidate
    break
  }
}

if (-not $IsccPath) {
  throw "ISCC.exe not found. Install Inno Setup 6, then rerun this script."
}

& $IsccPath "/DAppVersion=$Version" "$SpecPath"

$InstallerPattern = Join-Path $ProjectRoot "dist\diskimage_explorer_x68k-windows-setup-$Version.exe"
if (Test-Path $InstallerPattern) {
  Write-Host "Installer complete: $InstallerPattern"
} else {
  Write-Host "Installer build finished. Check dist folder."
}
