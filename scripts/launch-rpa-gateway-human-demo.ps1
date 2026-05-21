$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$nodeDir = Join-Path $root ".tools\node-v24.15.0-win-x64"
$artifactDir = Join-Path $root "artifacts\rpa-gateway"
$demoHtml = Join-Path $artifactDir "human-control-visible-demo.html"

if (-not (Test-Path (Join-Path $nodeDir "node.exe"))) {
  throw "Node portable no esta instalado en .tools."
}

New-Item -ItemType Directory -Force -Path (Join-Path $root "logs") | Out-Null
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null

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

Push-Location (Join-Path $root "backend")
python -m app.db.demo_seed | Out-Null
Pop-Location

function Test-HttpOk($Url) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
  } catch {
    return $false
  }
}

if (-not (Test-HttpOk "http://127.0.0.1:8001/api/v1/health")) {
  Start-Process -FilePath python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001") `
    -WorkingDirectory (Join-Path $root "backend") `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $root "logs\backend-8001.out.log") `
    -RedirectStandardError (Join-Path $root "logs\backend-8001.err.log") | Out-Null
}

$frontendReady = Test-HttpOk "http://127.0.0.1:3000/rpa-gateway"
if (-not $frontendReady) {
  if (-not (Test-Path (Join-Path $root "frontend\.next"))) {
    Push-Location (Join-Path $root "frontend")
    npm.cmd run build
    Pop-Location
  }
  Start-Process -FilePath (Join-Path $nodeDir "npm.cmd") `
    -ArgumentList @("run", "start", "--", "--hostname", "127.0.0.1", "--port", "3000") `
    -WorkingDirectory (Join-Path $root "frontend") `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $root "logs\frontend-3000.out.log") `
    -RedirectStandardError (Join-Path $root "logs\frontend-3000.err.log") | Out-Null
}

for ($i = 0; $i -lt 20; $i++) {
  if ((Test-HttpOk "http://127.0.0.1:8001/api/v1/health") -and (Test-HttpOk "http://127.0.0.1:3000/rpa-gateway")) {
    break
  }
  Start-Sleep -Seconds 1
}

$html = @"
<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>Demo visible control humano</title>
    <style>
      body { margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #f6f7f9; color: #17202a; }
      main { max-width: 760px; margin: 48px auto; background: #fff; border: 1px solid #d9e0e8; border-radius: 8px; padding: 28px; }
      h1 { margin: 0 0 10px; font-size: 28px; }
      p { color: #647184; line-height: 1.5; }
      .captcha { border: 2px dashed #b45309; background: #fff7ed; border-radius: 8px; padding: 18px; margin: 18px 0; }
      label { display: grid; gap: 6px; margin: 12px 0; font-weight: 700; }
      input { border: 1px solid #d9e0e8; border-radius: 6px; font: inherit; padding: 10px; }
      button { background: #0f766e; border: 0; border-radius: 6px; color: #fff; font: inherit; font-weight: 800; padding: 10px 14px; }
      small { display: block; margin-top: 12px; color: #647184; }
    </style>
  </head>
  <body>
    <main>
      <h1>Pagina demo con control humano</h1>
      <p>Esta pagina es local. Simula una plataforma que muestra captcha/MFA. Resuelvelo manualmente y vuelve a la pasarela del Hub para registrar la decision.</p>
      <form>
        <label>Usuario demo<input name="user" autocomplete="username" value="operador.demo" /></label>
        <label>Clave demo<input name="password" type="password" value="no-real-secret" /></label>
        <section class="captcha">
          <strong>captcha demo / recaptcha</strong>
          <p>Marca mentalmente este bloque como resuelto. No hay bypass ni servicio externo.</p>
          <label><input type="checkbox" name="captcha_demo" /> Soy humano y estoy delante de la pantalla</label>
        </section>
        <label>Codigo de verificacion MFA<input name="otp" placeholder="codigo de verificacion" /></label>
        <button type="button">Entrar en pagina demo</button>
        <small>No introduzcas credenciales reales aqui. Este fichero esta en tu equipo.</small>
      </form>
    </main>
  </body>
</html>
"@
Set-Content -LiteralPath $demoHtml -Value $html -Encoding UTF8

$login = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8001/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body (@{ email = "demo"; password = "demo" } | ConvertTo-Json)
$headers = @{
  Authorization = "Bearer $($login.access_token)"
  "X-Tenant-ID" = "$($login.tenant_id)"
}
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/v1/platform-review-schedules/ensure" -Headers $headers | Out-Null
$options = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/v1/rpa-gateway/options" -Headers $headers
$schedule = $options.schedules | Where-Object { $_.platform_slug -eq "e_coordina" } | Select-Object -First 1
if (-not $schedule) {
  throw "No se encontro schedule e-coordina para crear la peticion demo."
}
$requestBody = @{
  schedule_id = $schedule.schedule_id
  action_key = "read_external_status"
  request_comment = "Demo visible: validar control humano en pantalla local sin cambios externos."
} | ConvertTo-Json
$run = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8001/api/v1/rpa-gateway/requests" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $requestBody

Start-Process "http://127.0.0.1:3000/rpa-gateway"
Start-Process $demoHtml

Write-Output "Pasarela abierta: http://127.0.0.1:3000/rpa-gateway"
Write-Output "Pagina demo local abierta: $demoHtml"
Write-Output "Peticion creada: #$($run.id) / $($run.platform_name) / $($run.status)"
Write-Output "Login demo si lo pide el navegador: demo / demo"
Write-Output "Cuando veas la pasarela, pulsa Autorizar entrada, resuelve la demo local y pulsa Marcar resuelto."
