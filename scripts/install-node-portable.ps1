$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$version = "v24.15.0"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$tools = Join-Path $root ".tools"
$target = Join-Path $tools "node-$version-win-x64"
$zipPath = Join-Path $tools "node-$version-win-x64.zip"
$url = "https://nodejs.org/dist/$version/node-$version-win-x64.zip"

New-Item -ItemType Directory -Force -Path $tools | Out-Null

if (-not (Test-Path $target)) {
  if (-not (Test-Path $zipPath)) {
    Invoke-WebRequest -Uri $url -OutFile $zipPath -TimeoutSec 300
  }
  Expand-Archive -LiteralPath $zipPath -DestinationPath $tools -Force
}

& (Join-Path $target "node.exe") --version
& (Join-Path $target "npm.cmd") --version
