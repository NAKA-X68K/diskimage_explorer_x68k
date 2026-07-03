param(
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

function Invoke-NativeChecked {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments,
    [string]$Step = "command"
  )

  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Step failed (exit code: $LASTEXITCODE): $FilePath $($Arguments -join ' ')"
  }
}

if ([System.Environment]::OSVersion.Platform -ne "Win32NT") {
  throw "This script must be run on Windows."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

$PyProjectPath = Join-Path $ProjectRoot "pyproject.toml"
$Version = "0.1.0"
if (Test-Path $PyProjectPath) {
  $m = Select-String -Path $PyProjectPath -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1
  if ($m -and $m.Matches.Count -gt 0) {
    $Version = $m.Matches[0].Groups[1].Value
  }
}

if (-not $SkipBuild) {
  Write-Host "==> Building Windows app bundle with PyInstaller"
  & "$ScriptDir\build-windows.ps1"
}

$DistDir = Join-Path $ProjectRoot "dist\diskimage_explorer_x68k"
$ExePath = Join-Path $DistDir "diskimage_explorer_x68k.exe"
if (-not (Test-Path $ExePath)) {
  throw "Windows build output not found: $ExePath"
}

$DotnetCandidates = @(
  "dotnet",
  "$env:ProgramFiles\dotnet\dotnet.exe",
  "$env:ProgramFiles(x86)\dotnet\dotnet.exe"
)
$DotnetPath = $null
foreach ($candidate in $DotnetCandidates) {
  if ($candidate -eq "dotnet") {
    $cmd = Get-Command dotnet -ErrorAction SilentlyContinue
    if ($cmd) {
      $DotnetPath = $cmd.Path
      break
    }
    continue
  }
  if (Test-Path $candidate) {
    $DotnetPath = $candidate
    break
  }
}
if (-not $DotnetPath) {
  throw "dotnet was not found. Install .NET SDK 8+ and rerun."
}

$ToolsDir = Join-Path $env:USERPROFILE ".dotnet\tools"
if (-not ($env:PATH -split ";" | Where-Object { $_ -eq $ToolsDir })) {
  $env:PATH = "$ToolsDir;$env:PATH"
}

Write-Host "==> Ensuring WiX v4 tool"
Invoke-NativeChecked -FilePath $DotnetPath -Arguments @("tool", "update", "--global", "wix", "--version", "4.*") -Step "dotnet tool update wix"

$WixExe = Join-Path $ToolsDir "wix.exe"
if (-not (Test-Path $WixExe)) {
  $WixCmd = Get-Command wix -ErrorAction SilentlyContinue
  if ($WixCmd) {
    $WixExe = $WixCmd.Path
  }
}
if (-not (Test-Path $WixExe)) {
  throw "wix command was not found after installation."
}

$ProductWxs = Join-Path $ProjectRoot "installer\windows\Product.wxs"
if (-not (Test-Path $ProductWxs)) {
  throw "WiX source not found: $ProductWxs"
}

$ObjDir = Join-Path $ProjectRoot "installer\windows\obj"
New-Item -Path $ObjDir -ItemType Directory -Force | Out-Null
$HarvestWxs = Join-Path $ObjDir "AppFiles.wxs"

Invoke-NativeChecked -FilePath $WixExe -Arguments @("extension", "add", "WixToolset.Heat") -Step "wix extension add WixToolset.Heat"
Write-Host "==> Harvesting dist files"
$harvested = $false

# Preferred for WiX v4 tool syntax.
& $WixExe harvest directory "$DistDir" -nologo -dr INSTALLFOLDER -cg AppFiles -gg -srd -var var.SourceDir -out "$HarvestWxs"
if ($LASTEXITCODE -eq 0 -and (Test-Path $HarvestWxs)) {
  $harvested = $true
}

# Backward compatibility for environments that still expose heat-style command shape.
if (-not $harvested) {
  & $WixExe heat dir "$DistDir" -nologo -dr INSTALLFOLDER -cg AppFiles -gg -srd -var var.SourceDir -out "$HarvestWxs"
  if ($LASTEXITCODE -eq 0 -and (Test-Path $HarvestWxs)) {
    $harvested = $true
  }
}

if (-not $harvested) {
  throw "Harvest step failed. WiX command syntax may differ by version. Try updating WiX (`dotnet tool update --global wix`) and rerun."
}

$MsiOut = Join-Path $ProjectRoot "dist\diskimage_explorer_x68k-windows-$Version.msi"
Write-Host "==> Building MSI"
Invoke-NativeChecked -FilePath $WixExe -Arguments @("build", "-nologo", "-d", "AppVersion=$Version", "-d", "SourceDir=$DistDir", "$ProductWxs", "$HarvestWxs", "-o", "$MsiOut") -Step "wix build"

if (Test-Path $MsiOut) {
  Write-Host "MSI complete: $MsiOut"
} else {
  throw "MSI build failed: output file not found."
}
