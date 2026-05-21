# Importacion de paquetes PRL/CAE de empresa

Este flujo integra paquetes ZIP con documentacion propia de una empresa y sus trabajadores en el Hub. No valida automaticamente la documentacion ni la envia a plataformas externas.

## Flujo

1. Inventariar el ZIP: extensiones, carpetas, documentos por trabajador, documentos de empresa y ficheros no soportados.
2. Importar con `scripts/import_company_prl_archive.py`.
3. Crear o actualizar la empresa y trabajadores del tenant.
4. Guardar cada fichero aceptado en almacenamiento documental con SHA-256.
5. Crear `DocumentIntake` en `pending_review`.
6. Crear `Document` y `DocumentVersion` inmutables en `pending_internal_review`.
7. Generar reporte JSON/Markdown en `artifacts/arm-prl-import/`.
8. Revisar en `/arm`: ficha de empresa, ficha de trabajador, documentos, ultima version, fechas, tamano, hash y descarga.

## Comando local

```bash
python scripts/import_company_prl_archive.py requisitos/wetransfer_arm_2026-05-21_0759.zip
```

Si el usuario aprueba explicitamente toda la migracion documental, se puede cerrar la revision local con auditoria:

```bash
python scripts/approve_arm_imported_documents.py
```

## Analisis RAR/DB ARM 2026-05-21

El paquete ARM contenia tres `.rar` y dos `Thumbs.db`.

- `Thumbs.db`: cache de miniaturas de Windows; no es evidencia PRL/CAE y no se importa.
- `RLC+JUSTIFICANTE.rar`: contiene justificante de pago de seguros sociales y TC1/RLC.
- `Empresa Enero.rar`: contiene pago de seguros sociales, certificado Seguridad Social, RLC, RNT, certificado Hacienda e ITA.
- `rlc+seguros sociales.rar`: contiene pago de seguros sociales y RLC.

Los RAR se extrajeron en `artifacts/arm-prl-import/rar-db-analysis/extracted/` y se empaquetaron como `artifacts/arm-prl-import/rar-db-analysis/arm_prl_rar_extracted_docs.zip` para importarlos por el flujo documental normal. El informe tecnico queda en `artifacts/arm-prl-import/rar-db-analysis/rar_db_analysis.md`.

## Reglas de privacidad

- El OCR guarda solo extractos redactados y senales estructuradas.
- En vigilancia de salud laboral solo se conserva aptitud, fechas, proveedor, restricciones preventivas si procede y evidencia minima.
- La importacion no convierte ningun documento en valido salvo instruccion explicita del usuario y siempre con auditoria.
- Los ficheros no soportados, por ejemplo `.rar` o `.db`, se reportan como omitidos.

## Skill operativo

Se ha creado el skill local `iprl-cae-company-prl-onboarding` para repetir este proceso con nuevas empresas o nuevos paquetes documentales.
