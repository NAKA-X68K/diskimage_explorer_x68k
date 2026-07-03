$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $ProjectRoot

if (-Not (Test-Path ".venv")) {
  py -3 -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

pyinstaller --clean diskimage_explorer_x68k.spec

Write-Host "Build complete: $ProjectRoot\dist\diskimage_explorer_x68k"
