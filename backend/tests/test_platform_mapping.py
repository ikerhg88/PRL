from __future__ import annotations

from app.services.platform_mapping import extract_labels_from_capture


def test_extract_labels_from_grid_columns_and_status_counts() -> None:
    labels = extract_labels_from_capture(
        {
            "pages": [
                {
                    "label": "Solicitudes de documentacion",
                    "grid_headers": ["Documento", "Estado", "Empresa"],
                    "grid_columns": [
                        {
                            "columns": [
                                {"header": "Documento", "data_index": "documento", "hidden": False},
                                {"header": "Estado", "data_index": "documentacion_estado", "hidden": False},
                                {"header": "F.caducidad", "data_index": "fecha_caducidad", "hidden": False},
                            ],
                            "store_fields": ["documentacion_estado", "fecha_caducidad"],
                        }
                    ],
                    "status_column_counts": [
                        {
                            "field": "documentacion_estado",
                            "values": [
                                {"status_text": "Validado", "count": 5},
                                {"status_text": "Caducado", "count": 4},
                            ],
                        }
                    ],
                }
            ],
            "navigation_actions": [{"label": "Solicitudes de documentacion", "item_id": "documentacion_solicitud"}],
        }
    )

    by_raw = {(label.label_kind, label.raw_label): label for label in labels}
    assert by_raw[("grid_header", "Estado")].standard_key == "document.status"
    assert by_raw[("grid_column", "F.caducidad")].standard_key == "document.expires_at"
    assert by_raw[("grid_store_field", "documentacion_estado")].standard_key == "document.status"
    assert by_raw[("status_value", "Validado")].standard_key == "document.status"
    assert by_raw[("nav_action", "Solicitudes de documentacion")].standard_key == "document.type"
