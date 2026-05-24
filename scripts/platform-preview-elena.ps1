$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

python scripts/probe_platform_write_previews.py --worker-id 28 --operations upsert_worker --connector-dry-run
