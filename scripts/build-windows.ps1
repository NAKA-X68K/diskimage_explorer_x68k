$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

if (-Not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

if (Test-Path "dist") {
  Remove-Item -Recurse -Force "dist"
}
if (Test-Path "build") {
  Remove-Item -Recurse -Force "build"
}

pyinstaller --clean diskimage_explorer_x68k.spec

$DistDir = Join-Path $ProjectRoot "dist\diskimage_explorer_x68k"
$ExePath = Join-Path $DistDir "diskimage_explorer_x68k.exe"

if (-not (Test-Path $ExePath)) {
  throw "Build failed or unexpected layout: $ExePath not found."
}

Write-Host "Build complete: $DistDir"
Write-Host "Run this file: $ExePath"
Write-Host "IMPORTANT: Do not run EXE from build\\. Use dist\\diskimage_explorer_x68k\\ and keep _internal folder together."
