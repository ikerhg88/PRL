from scripts.assisted_platform_browser import context_tokens, normalize_text


def test_context_tokens_focus_on_external_company() -> None:
    assert context_tokens("EMPRESA DEMO INDUSTRIAL S.L en Cliente A, S.L.") == ["cliente"]
    assert context_tokens("EMPRESA DEMO ROBOTICS en CLIENTE_B") == ["cliente_b"]


def test_normalize_text_removes_accents_for_company_selector() -> None:
    assert normalize_text("\u00bfCon qu\u00e9 empresa quieres coordinarte? CLIENTE_A") == (
        "\u00bfcon que empresa quieres coordinarte? cliente_a"
    )
