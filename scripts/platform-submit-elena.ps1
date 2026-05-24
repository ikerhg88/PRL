param(
    [switch]$Live
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$argsList = @(
    "scripts/submit_platform_writes.py",
    "--worker-id", "28"
)

if ($Live) {
    $argsList += "--live"
}

python @argsList
