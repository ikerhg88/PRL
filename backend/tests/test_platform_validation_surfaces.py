from __future__ import annotations

import json
from pathlib import Path

from app.services.platform_validation_surfaces import (
    build_validation_surface_map,
    write_validation_surface_artifacts,
)


def _write_capture(root: Path, capture_id: str, payload: dict[str, object]) -> None:
    capture_dir = root / capture_id
    capture_dir.mkdir(parents=True)
    (capture_dir / "technical_capture.redacted.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_validation_surface_map_detects_readback_and_pending_surfaces(tmp_path: Path) -> None:
    capture_root = tmp_path / "captures"
    _write_capture(
        capture_root,
        "sixconecta",
        {
            "source": {
                "platform_label": "VELARTIA / 6conecta",
                "initial_url_sanitized": "https://www.6conecta.com/es/iniciar-sesion",
            },
            "outcome": {"final_url_sanitized": "https://www.6conecta.com/dashboard"},
            "pages": [
                {
                    "label": "home",
                    "title": "Home 6conecta",
                    "url_sanitized": "https://www.6conecta.com/dashboard",
                    "nav_labels": [
                        "Empleados",
                        "Inter. Documentacion",
                        "Homologacion",
                        "Consulta accesos",
                        "Listado",
                    ],
                    "headings": ["Pendientes de validacion"],
                    "table_headers": [["Trabajador", "Documento", "Estado", "Caducidad"]],
                    "forms": [
                        {
                            "inputs": [
                                {"name": "dni"},
                                {"name": "nombre"},
                            ]
                        }
                    ],
                }
            ],
            "requests_sample": [
                {
                    "url": "https://api.6conecta.com/v2/notification-summary?r=[value]",
                    "method": "GET",
                }
            ],
        },
    )

    payload = build_validation_surface_map(capture_root=capture_root)

    assert payload["totals"]["platforms"] == 1
    platform = payload["platforms"][0]
    assert platform["platform_slug"] == "seisconecta"
    assert set(platform["summary"]) >= {
        "worker_readback",
        "document_readback",
        "pending_validation",
        "notification_inbox",
        "access_readback",
    }
    assert [item["use"] for item in platform["readback_plan"]][:2] == [
        "worker_readback",
        "document_readback",
    ]
    notification = next(item for item in platform["surfaces"] if item["use"] == "notification_inbox")
    assert notification["safe_for_automation"] is False
    assert "Endpoint observado" in notification["notes"]


def test_validation_surface_artifacts_are_redacted(tmp_path: Path) -> None:
    payload = {
        "generated_at": "2026-05-20T00:00:00+00:00",
        "totals": {"platforms": 1, "surfaces": 1},
        "platforms": [
            {
                "platform_slug": "e_coordina",
                "platform_name": "e-coordina",
                "capture_count": 1,
                "summary": {"pending_validation": 1},
                "readback_plan": [
                    {
                        "priority": 30,
                        "label": "Pendientes de validacion",
                        "suggested_entry": "Solicitudes de documentacion",
                        "page_label": "Documentacion",
                        "evidence_count": 1,
                    }
                ],
                "surfaces": [
                    {
                        "use": "pending_validation",
                        "label": "Pendientes de validacion",
                        "evidence_kind": "heading",
                        "candidate_text": "Solicitudes de documentacion",
                        "confidence": 80,
                        "page_label": "Documentacion",
                        "page_title": "Documentacion",
                        "url_sanitized": "https://v5.e-coordina.com/path?token=[value]",
                        "capture_id": "capture",
                        "safe_for_automation": True,
                        "notes": "Superficie de UI observada.",
                    }
                ],
            }
        ],
    }

    outputs = write_validation_surface_artifacts(payload, out_dir=tmp_path)

    assert (tmp_path / "platform_validation_surfaces.redacted.json").exists()
    assert (tmp_path / "platform_validation_surfaces.redacted.csv").exists()
    markdown = (tmp_path / "platform_validation_surfaces_summary.redacted.md").read_text(
        encoding="utf-8"
    )
    assert "e-coordina" in markdown
    assert "token=[value]" in (tmp_path / "platform_validation_surfaces.redacted.csv").read_text(
        encoding="utf-8"
    )
    assert set(outputs) == {"json", "csv", "markdown"}
