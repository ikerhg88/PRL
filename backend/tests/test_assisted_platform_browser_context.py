from scripts.assisted_platform_browser import (
    HELPER_VERSION,
    _looks_like_public_contact_or_login,
    context_tokens,
    normalize_text,
)


def test_context_tokens_focus_on_external_company() -> None:
    assert context_tokens("ARM INDUSTRIAL ASSEMBLIES S.L en Sofidel, S.L.") == ["sofidel"]
    assert context_tokens("ARM ROBOTICS en RENAULT") == ["renault"]


def test_normalize_text_removes_accents_for_company_selector() -> None:
    assert normalize_text("\u00bfCon qu\u00e9 empresa quieres coordinarte? SOFIDEL") == (
        "\u00bfcon que empresa quieres coordinarte? sofidel"
    )


def test_assisted_browser_version_marks_deeper_editable_discovery() -> None:
    assert HELPER_VERSION == "readonly_capture_v13_server_dom_add_links"


def test_contact_form_is_not_worker_editable_capture() -> None:
    assert _looks_like_public_contact_or_login(
        {
            "title": "Contacto",
            "headings": ["Quieres saber mas"],
            "buttons": ["ENVIAR"],
            "links": ["politica de privacidad"],
            "fields": [
                {"fieldLabel": "Nombre", "type": "text"},
                {"fieldLabel": "Correo electronico", "type": "email"},
                {"fieldLabel": "Mensaje", "type": "text"},
            ],
        }
    )


def test_worker_form_is_not_treated_as_public_contact() -> None:
    assert not _looks_like_public_contact_or_login(
        {
            "title": "Alta trabajador",
            "headings": ["Trabajadores"],
            "buttons": ["Nuevo trabajador"],
            "links": ["Plantilla"],
            "fields": [
                {"fieldLabel": "Nombre", "type": "text"},
                {"fieldLabel": "DNI", "type": "text"},
            ],
        }
    )
