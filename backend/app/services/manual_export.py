from __future__ import annotations

import csv
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile


def build_manual_export_zip(rows: list[dict[str, str]]) -> bytes:
    csv_buffer = StringIO()
    base_fieldnames = [
        "operation",
        "tenant_id",
        "platform_key",
        "entity_type",
        "entity_id",
        "worker_display",
        "identifier_last4",
        "work_position",
        "document_code",
        "filename",
        "sha256",
        "expires_at",
    ]
    extra_fieldnames = sorted({key for row in rows for key in row} - set(base_fieldnames))
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=base_fieldnames + extra_fieldnames,
    )
    writer.writeheader()
    writer.writerows(rows)

    checklist = "\n".join(
        [
            "# Checklist de subida manual",
            "",
            "1. Revisar que el lote corresponde al tenant y plataforma indicados.",
            "2. Verificar hash SHA-256 antes de subir documentos.",
            "3. Verificar que las altas de trabajadores corresponden a una entidad dummy/sandbox o a una aprobacion firmada.",
            "4. Subir cada elemento en la plataforma destino de forma manual.",
            "5. Registrar resultado externo en IPRL/CAE Hub.",
            "6. No incluir credenciales ni datos no requeridos en el paquete.",
        ]
    )

    readme = "\n".join(
        [
            "# Paquete de exportacion manual IPRL/CAE",
            "",
            "Este ZIP no ejecuta acciones contra plataformas comerciales.",
            "Contiene metadatos y checklist para operacion humana autorizada.",
        ]
    )

    output = BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("README.md", readme)
        archive.writestr("metadata.csv", csv_buffer.getvalue())
        archive.writestr("checklist.md", checklist)
    return output.getvalue()
