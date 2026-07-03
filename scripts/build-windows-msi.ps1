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

function Escape-XmlAttr {
  param([string]$Value)
  if ($null -eq $Value) {
    return ""
  }
  return $Value.Replace("&", "&amp;").Replace("<", "&lt;").Replace(">", "&gt;").Replace('"', "&quot;")
}

function New-WixId {
  param(
    [string]$Prefix,
    [string]$Text
  )
  $sha1 = [System.Security.Cryptography.SHA1]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $hash = [BitConverter]::ToString($sha1.ComputeHash($bytes)).Replace("-", "")
    return "${Prefix}_$($hash.Substring(0, 16))"
  }
  finally {
    $sha1.Dispose()
  }
}

function Build-DirectoryTree {
  param(
    [System.Collections.IDictionary]$Nodes,
    [string]$RelativeDir
  )
  if ($Nodes.Contains($RelativeDir)) {
    return
  }

  $name = ""
  $parent = $null
  if ([string]::IsNullOrEmpty($RelativeDir)) {
    $name = ""
    $parent = $null
  }
  else {
    $name = [System.IO.Path]::GetFileName($RelativeDir)
    $parent = [System.IO.Path]::GetDirectoryName($RelativeDir)
    if ($parent -eq ".") {
      $parent = ""
    }
    if ($null -eq $parent) {
      $parent = ""
    }
    Build-DirectoryTree -Nodes $Nodes -RelativeDir $parent
  }

  $Nodes[$RelativeDir] = [ordered]@{
    Name = $name
    Parent = $parent
    Children = New-Object System.Collections.Generic.List[string]
    Files = New-Object System.Collections.Generic.List[object]
    DirId = $(if ([string]::IsNullOrEmpty($RelativeDir)) { "INSTALLFOLDER" } else { New-WixId -Prefix "DIR" -Text $RelativeDir })
  }

  if (-not [string]::IsNullOrEmpty($RelativeDir)) {
    $Nodes[$parent].Children.Add($RelativeDir)
  }
}

function Write-WixAppFilesFragment {
  param(
    [string]$DistDir,
    [string]$OutFile
  )

  $files = Get-ChildItem -Path $DistDir -Recurse -File | Sort-Object FullName
  if (-not $files -or $files.Count -eq 0) {
    throw "No files found in dist directory: $DistDir"
  }

  $nodes = @{}
  Build-DirectoryTree -Nodes $nodes -RelativeDir ""

  foreach ($file in $files) {
    $relPath = [System.IO.Path]::GetRelativePath($DistDir, $file.FullName)
    $relPath = $relPath.Replace("/", "\\")
    $relDir = [System.IO.Path]::GetDirectoryName($relPath)
    if ($relDir -eq "." -or $null -eq $relDir) {
      $relDir = ""
    }

    Build-DirectoryTree -Nodes $nodes -RelativeDir $relDir

    $entry = [ordered]@{
      RelativePath = $relPath
      SourcePath = $file.FullName
      ComponentId = New-WixId -Prefix "CMP" -Text $relPath
      FileId = New-WixId -Prefix "FIL" -Text $relPath
    }
    $nodes[$relDir].Files.Add($entry)
  }

  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("<?xml version=\"1.0\" encoding=\"UTF-8\"?>")
  $lines.Add("<Wix xmlns=\"http://wixtoolset.org/schemas/v4/wxs\">")
  $lines.Add("  <Fragment>")
  $lines.Add("    <DirectoryRef Id=\"INSTALLFOLDER\">")

  function Render-Node {
    param(
      [string]$DirKey,
      [int]$Indent
    )

    $node = $nodes[$DirKey]
    $prefix = " " * $Indent

    foreach ($file in ($node.Files | Sort-Object RelativePath)) {
      $componentId = Escape-XmlAttr $file.ComponentId
      $fileId = Escape-XmlAttr $file.FileId
      $source = Escape-XmlAttr $file.SourcePath
      $lines.Add("${prefix}<Component Id=\"$componentId\" Guid=\"*\">")
      $lines.Add("${prefix}  <File Id=\"$fileId\" Source=\"$source\" KeyPath=\"yes\" />")
      $lines.Add("${prefix}</Component>")
    }

    foreach ($childKey in ($node.Children | Sort-Object { $nodes[$_].Name })) {
      $child = $nodes[$childKey]
      $childId = Escape-XmlAttr $child.DirId
      $childName = Escape-XmlAttr $child.Name
      $lines.Add("${prefix}<Directory Id=\"$childId\" Name=\"$childName\">")
      Render-Node -DirKey $childKey -Indent ($Indent + 2)
      $lines.Add("${prefix}</Directory>")
    }
  }

  Render-Node -DirKey "" -Indent 6

  $lines.Add("    </DirectoryRef>")
  $lines.Add("  </Fragment>")
  $lines.Add("  <Fragment>")
  $lines.Add("    <ComponentGroup Id=\"AppFiles\">")

  foreach ($dirKey in ($nodes.Keys | Sort-Object)) {
    foreach ($file in ($nodes[$dirKey].Files | Sort-Object RelativePath)) {
      $componentId = Escape-XmlAttr $file.ComponentId
      $lines.Add("      <ComponentRef Id=\"$componentId\" />")
    }
  }

  $lines.Add("    </ComponentGroup>")
  $lines.Add("  </Fragment>")
  $lines.Add("</Wix>")

  [System.IO.File]::WriteAllLines($OutFile, $lines, [System.Text.UTF8Encoding]::new($false))
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
$AppFilesWxs = Join-Path $ObjDir "AppFiles.wxs"

Write-Host "==> Generating AppFiles.wxs"
Write-WixAppFilesFragment -DistDir $DistDir -OutFile $AppFilesWxs
if (-not (Test-Path $AppFilesWxs)) {
  throw "Failed to generate WiX fragment: $AppFilesWxs"
}

$MsiOut = Join-Path $ProjectRoot "dist\diskimage_explorer_x68k-windows-$Version.msi"
Write-Host "==> Building MSI"
Invoke-NativeChecked -FilePath $WixExe -Arguments @("build", "-nologo", "-d", "AppVersion=$Version", "-d", "SourceDir=$DistDir", "$ProductWxs", "$AppFilesWxs", "-o", "$MsiOut") -Step "wix build"

if (Test-Path $MsiOut) {
  Write-Host "MSI complete: $MsiOut"
} else {
  throw "MSI build failed: output file not found."
}
