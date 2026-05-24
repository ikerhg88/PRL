param(
    [int]$WaitSeconds = 45,
    [string]$BrowserChannel = "auto",
    [switch]$AllAccounts
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$argsList = @(
    "scripts/run_platform_mapping_batch.py",
    "--wait-seconds", "$WaitSeconds",
    "--close-after",
    "--browser-channel", $BrowserChannel
)

if (-not $AllAccounts) {
    $argsList += "--one-per-platform"
}

python @argsList
