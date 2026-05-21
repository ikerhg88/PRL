$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$nodeDir = Join-Path $root ".tools\node-v24.15.0-win-x64"

if (-not (Test-Path (Join-Path $nodeDir "node.exe"))) {
  throw "Node portable no esta instalado. Ejecuta primero la instalacion preparada en .tools o pide a Codex que la repita."
}

$env:PATH = "$nodeDir;$env:PATH"
$env:IPRL_CAE_CONFIG_FILE = Join-Path $root "config\iprl-cae.local.example.toml"
$env:IPRL_CAE_ENVIRONMENT = "local"
$env:IPRL_CAE_DATABASE_URL = "sqlite:///$((Join-Path $root 'storage\demo.db').Replace('\', '/'))"
$env:IPRL_CAE_DOCUMENT_STORAGE_PATH = Join-Path $root "storage\documents"
$env:IPRL_CAE_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
$env:IPRL_CAE_PUBLIC_BASE_URL = "http://127.0.0.1:8001"
$env:IPRL_CAE_FRONTEND_BASE_URL = "http://127.0.0.1:3000"
$env:IPRL_CAE_SECRET_KEY = "local-demo-secret-key-for-development-only-32"
$env:IPRL_CAE_AUTH_DEV_TOKENS_ENABLED = "true"
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8001"

New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "storage") | Out-Null

python (Join-Path $root "scripts\load_arm_operational_state.py") | Out-File -FilePath (Join-Path $root "logs\arm-operational-state.out.log") -Encoding utf8

foreach ($port in @(3000, 8001)) {
  Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq "Listen" -and $_.OwningProcess -ne 0 } |
    ForEach-Object {
      Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
}

$backend = Start-Process -FilePath python `
  -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001") `
  -WorkingDirectory (Join-Path $root "backend") `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $root "logs\backend-8001.out.log") `
  -RedirectStandardError (Join-Path $root "logs\backend-8001.err.log") `
  -PassThru

$frontend = Start-Process -FilePath (Join-Path $nodeDir "npm.cmd") `
  -ArgumentList @("run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000") `
  -WorkingDirectory (Join-Path $root "frontend") `
  -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $root "logs\frontend-3000.out.log") `
  -RedirectStandardError (Join-Path $root "logs\frontend-3000.err.log") `
  -PassThru

Start-Sleep -Seconds 4

Write-Output "Backend PID: $($backend.Id)  http://localhost:8001/api/v1/docs"
Write-Output "Frontend PID: $($frontend.Id) http://localhost:3000"
