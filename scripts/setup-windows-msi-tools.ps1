$ErrorActionPreference = "Stop"

Write-Host "==> Checking winget"
$wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
if (-not $wingetCmd) {
  throw "winget is required. Install App Installer from Microsoft Store and rerun."
}

Write-Host "==> Installing .NET SDK (8.x)"
winget install --id Microsoft.DotNet.SDK.8 --silent --accept-package-agreements --accept-source-agreements --disable-interactivity --exact

$dotnetCmd = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $dotnetCmd) {
  throw "dotnet command not found after installation. Open a new PowerShell and rerun."
}

Write-Host "==> Installing WiX v4 global tool"
& $dotnetCmd.Path tool update --global wix --version "4.*"

$toolsDir = Join-Path $env:USERPROFILE ".dotnet\tools"
if (-not ($env:PATH -split ";" | Where-Object { $_ -eq $toolsDir })) {
  $env:PATH = "$toolsDir;$env:PATH"
}

$wixCmd = Get-Command wix -ErrorAction SilentlyContinue
if (-not $wixCmd) {
  throw "wix command not found. Add $toolsDir to PATH and open a new terminal."
}

Write-Host "==> Tool versions"
& $dotnetCmd.Path --version
& $wixCmd.Path --version

Write-Host "MSI prerequisites are ready."
