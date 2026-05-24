# 29 - Operativa Playwright para mapeo de plataformas

Fecha: 2026-05-24.

## Objetivo

Repetir el mapeo asistido de plataformas CAE sin depender de Codex:

- abrir navegador visible por cuenta/plataforma;
- resolver solo pasos humanos delante de pantalla;
- capturar rutas, formularios, tablas y campos;
- sincronizar evidencia redaccionada en el Hub;
- bloquear escrituras hasta preview, aprobacion, auditoria y lectura posterior.

## Comandos

Mapear una cuenta concreta:

```powershell
python C:\Users\ikerh\.codex\skills\iprl-cae-playwright-assisted-navigator\scripts\gateway_playwright.py --project-root D:\PLATAFORMAS --account-id 12 --launch
```

Mapeo batch, una cuenta por plataforma:

```powershell
make platform-map
```

En Windows sin GNU Make:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\platform-map.ps1
```

Preview de alta de Elena sin escritura externa:

```powershell
make platform-preview-elena
```

En Windows sin GNU Make:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\platform-preview-elena.ps1
```

Submit de escrituras preparadas para Elena. Sin `-Live` queda en dry-run; con
`-Live` solicita escritura real, pero el backend solo ejecuta si hay preview
listo, helper live, aprobacion, auditoria y lectura posterior:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\platform-submit-elena.ps1
powershell -ExecutionPolicy Bypass -File scripts\platform-submit-elena.ps1 -Live
```

## Navegadores

El helper acepta `auto`, `chromium`, `chrome` y `msedge` mediante:

```powershell
python scripts/run_platform_mapping_batch.py --browser-channel msedge --one-per-platform --wait-seconds 45 --close-after
```

La comparacion debe hacerse por ruta redaccionada y estructura de campos, nunca por
tokens de query. En CTAIMA la ruta estable es `Trabajadores/Update.asp`; el valor
`cae=` se considera opaco y siempre se redacta.

Cada ejecucion deja resumen JSON/CSV/XLSX/Markdown en
`artifacts/platform-mapping-batch/` con `page_routes` y
`editable_field_names`, para poder comparar si un navegador cambia la ruta o la
estructura capturada.

## Politica

No se calculan tokens, no se saltan captcha/MFA y no se ejecutan escrituras
externas desde estos comandos. Un alta real requiere mapeo aprobado, preview,
autorizacion live, auditoria antes/despues y readback posterior.
