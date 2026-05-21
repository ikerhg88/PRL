from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse, urlunparse

from app.services.platform_credentials import PlatformCredentials

SECRET_HINTS = (
    "password",
    "passwd",
    "pass",
    "contrase",
    "clave",
    "token",
    "secret",
    "cookie",
    "session",
    "authorization",
    "auth",
)

READONLY_NAVIGATION_ITEMS = (
    ("documentacion", "documentacion"),
    ("documentacion_solicitud", "documentacion_solicitud"),
)

BLOCKED_ACTION_WORDS = (
    "guardar",
    "save",
    "subir",
    "upload",
    "cargar",
    "enviar",
    "submit",
    "eliminar",
    "borrar",
    "delete",
    "descargar",
    "download",
)


@dataclass(frozen=True)
class ECoordinaReviewResult:
    status: str
    result_status: str
    result_summary: str
    evidence: dict[str, Any]


class ECoordinaReadonlyConnector:
    connector_key = "connector_rpa_e_coordina_readonly"
    platform_slug = "e_coordina"

    def run_login_probe(
        self,
        *,
        entry_url: str,
        credentials: PlatformCredentials,
        expected_context: str,
        timeout_ms: int = 30_000,
    ) -> ECoordinaReviewResult:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - exercised only without optional dependency.
            return ECoordinaReviewResult(
                status="failed",
                result_status="playwright_missing",
                result_summary="Playwright no esta instalado en el entorno backend.",
                evidence={"error": _redact_text(str(exc))},
            )

        requests: list[dict[str, Any]] = []
        responses: list[dict[str, Any]] = []
        outcome: dict[str, Any] = {
            "login_status": "not_attempted",
            "initial_title": "",
            "final_title": "",
            "final_url_sanitized": "",
            "captcha_detected": False,
            "mfa_detected": False,
            "username_field_found": False,
            "password_field_found": False,
            "context_detected": False,
        }
        pages: list[dict[str, Any]] = []
        navigation_actions: list[dict[str, Any]] = []

        with sync_playwright() as playwright:
            launch_kwargs: dict[str, Any] = {"headless": True}
            executable_path = _find_local_chromium()
            if executable_path is not None:
                launch_kwargs["executable_path"] = str(executable_path)
            try:
                browser = playwright.chromium.launch(**launch_kwargs)
            except Exception as exc:
                return ECoordinaReviewResult(
                    status="failed",
                    result_status="browser_launch_failed",
                    result_summary="No se pudo abrir Chromium para la revision e-coordina.",
                    evidence={"error": _redact_text(f"{type(exc).__name__}: {exc}")},
                )
            context = browser.new_context(
                viewport={"width": 1366, "height": 900},
                locale="es-ES",
                accept_downloads=False,
            )
            page = context.new_page()
            page.on(
                "request",
                lambda request: requests.append(
                    {
                        "method": request.method,
                        "url": _sanitize_url(request.url),
                        "resource_type": request.resource_type,
                        "is_navigation": request.is_navigation_request(),
                    }
                ),
            )
            page.on(
                "response",
                lambda response: responses.append(
                    {
                        "url": _sanitize_url(response.url),
                        "status": response.status,
                        "content_type": response.headers.get("content-type", ""),
                    }
                ),
            )

            try:
                page.goto(entry_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            initial_shape = _collect_shape(page)
            outcome["initial_title"] = _safe_title(page)
            outcome["captcha_detected"] = bool(initial_shape["captcha_signals"])
            outcome["mfa_detected"] = bool(initial_shape["mfa_signals"])
            pages.append(_page_snapshot("login", page, initial_shape))

            if outcome["captcha_detected"] or outcome["mfa_detected"]:
                outcome["login_status"] = "human_action_required_before_login"
            else:
                username_field = _first_visible(
                    page,
                    [
                        "input[name='txt_usuario']",
                        "input[type='email']",
                        "input[name*='email' i]",
                        "input[id*='email' i]",
                        "input[name*='user' i]",
                        "input[id*='user' i]",
                        "input[type='text']",
                    ],
                )
                password_field = _first_visible(page, ["input[name='txt_password']", "input[type='password']"])
                outcome["username_field_found"] = username_field is not None
                outcome["password_field_found"] = password_field is not None
                if username_field is None or password_field is None:
                    outcome["login_status"] = "login_form_not_found"
                else:
                    username_field.fill(credentials.username, timeout=10_000)
                    password_field.fill(credentials.password, timeout=10_000)
                    try:
                        with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
                            _click_login(page)
                    except PlaywrightTimeoutError:
                        pass
                    try:
                        page.wait_for_load_state("networkidle", timeout=12_000)
                    except PlaywrightTimeoutError:
                        pass

                    post_shape = _collect_shape(page)
                    outcome["captcha_detected"] = outcome["captcha_detected"] or bool(post_shape["captcha_signals"])
                    outcome["mfa_detected"] = outcome["mfa_detected"] or bool(post_shape["mfa_signals"])
                    outcome["context_detected"] = _contains_expected_context(post_shape, expected_context)
                    has_password_after = any(
                        field.get("type") == "password"
                        for form in post_shape["forms"]
                        for field in form.get("inputs", [])
                    )
                    if outcome["captcha_detected"] or outcome["mfa_detected"]:
                        outcome["login_status"] = "human_action_required_after_login"
                    elif has_password_after:
                        outcome["login_status"] = "login_not_confirmed_password_form_still_present"
                    elif outcome["context_detected"]:
                        outcome["login_status"] = "login_likely_success"
                    else:
                        outcome["login_status"] = "login_likely_success_context_unconfirmed"
                    pages.append(_page_snapshot("post-login landing", page, post_shape))
                    if outcome["login_status"].startswith("login_likely_success"):
                        for item_id, label in READONLY_NAVIGATION_ITEMS:
                            action = _click_readonly_navigation_item(page, item_id=item_id)
                            navigation_actions.append(action)
                            if not action.get("ok"):
                                if item_id == READONLY_NAVIGATION_ITEMS[0][0]:
                                    break
                                continue
                            _wait_after_navigation_click(page)
                            navigation_shape = _collect_shape(page)
                            outcome["captcha_detected"] = outcome["captcha_detected"] or bool(
                                navigation_shape["captcha_signals"]
                            )
                            outcome["mfa_detected"] = outcome["mfa_detected"] or bool(
                                navigation_shape["mfa_signals"]
                            )
                            pages.append(_page_snapshot(f"after {label}", page, navigation_shape))
                            if outcome["captcha_detected"] or outcome["mfa_detected"]:
                                outcome["login_status"] = "human_action_required_after_navigation"
                                break

            outcome["final_title"] = _safe_title(page)
            outcome["final_url_sanitized"] = _sanitize_url(page.url)
            context.close()
            browser.close()

        status = _status_from_login(outcome["login_status"])
        return ECoordinaReviewResult(
            status=status,
            result_status=outcome["login_status"],
            result_summary=_summary_from_outcome(outcome),
            evidence={
                "connector_key": self.connector_key,
                "platform_slug": self.platform_slug,
                "entry_url_sanitized": _sanitize_url(entry_url),
                "outcome": outcome,
                "navigation_actions": navigation_actions,
                "network_summary": _network_summary(requests, responses),
                "external_status_summary": _external_status_summary(pages),
                "pages": pages,
            },
        )


def _click_login(page: Any) -> None:
    for selector in ["#login_button_submit", "button:has-text('Iniciar')", "button:has-text('Entrar')"]:
        locator = page.locator(selector).first
        if locator.count() > 0 and locator.is_visible():
            locator.click(timeout=10_000)
            return
    page.keyboard.press("Enter")


def _click_readonly_navigation_item(page: Any, *, item_id: str) -> dict[str, Any]:
    action = page.evaluate(
        """(itemId) => {
          if (!window.Ext || !Ext.ComponentMgr || !Ext.ComponentMgr.all) {
            return { ok: false, reason: 'ext_missing', item_id: itemId };
          }
          const items = Ext.ComponentMgr.all.items || [];
          const component = items.find((candidate) => candidate && candidate.itemId === itemId);
          if (!component) return { ok: false, reason: 'component_not_found', item_id: itemId };
          const label = (component.text || component.title || component.itemId || '').toString();
          const lower = label.toLowerCase();
          const blocked = [
            'guardar', 'save', 'subir', 'upload', 'cargar', 'enviar', 'submit',
            'eliminar', 'borrar', 'delete', 'descargar', 'download'
          ];
          if (blocked.some((word) => lower.includes(word))) {
            return { ok: false, reason: 'blocked_action_label', item_id: itemId, label };
          }
          if (component.disabled) return { ok: false, reason: 'component_disabled', item_id: itemId, label };
          if (!component.el || !component.el.dom) {
            return { ok: false, reason: 'component_not_rendered', item_id: itemId, label };
          }
          const target = component.el.dom.querySelector('button, a, .x-btn, .x-menu-item, .x-btn-mc') || component.el.dom;
          target.click();
          return { ok: true, method: 'dom_click', item_id: itemId, label };
        }""",
        item_id,
    )
    if not isinstance(action, dict):
        return {"ok": False, "reason": "unexpected_action_result", "item_id": item_id}
    label = str(action.get("label") or "")
    if any(word in label.lower() for word in BLOCKED_ACTION_WORDS):
        return {"ok": False, "reason": "blocked_action_label", "item_id": item_id}
    action["label"] = _redact_text(label)
    return action


def _wait_after_navigation_click(page: Any) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(2_500)
    except Exception:
        pass


def _find_local_chromium() -> Path | None:
    root = Path.home() / "AppData" / "Local" / "ms-playwright"
    if not root.exists():
        return None
    candidates = sorted(
        root.glob("chromium-*/chrome-win*/chrome.exe"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _first_visible(page: Any, selectors: list[str]) -> Any | None:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() > 0 and locator.is_visible():
            return locator
    return None


def _collect_shape(page: Any) -> dict[str, Any]:
    result = page.evaluate(
        """() => {
          const clean = (value) => (value || '').toString().replace(/\\s+/g, ' ').trim().slice(0, 160);
          const inputShape = (input) => ({
            tag: input.tagName.toLowerCase(),
            type: input.getAttribute('type') || '',
            name: input.getAttribute('name') || '',
            id: input.getAttribute('id') || '',
            autocomplete: input.getAttribute('autocomplete') || '',
            placeholder: clean(input.getAttribute('placeholder') || ''),
            ariaLabel: clean(input.getAttribute('aria-label') || ''),
            required: Boolean(input.required),
          });
          const forms = Array.from(document.querySelectorAll('form')).slice(0, 8).map((form) => ({
            method: (form.getAttribute('method') || 'get').toLowerCase(),
            action: form.getAttribute('action') || '',
            inputs: Array.from(form.querySelectorAll('input, select, textarea')).slice(0, 40).map(inputShape),
            buttons: Array.from(form.querySelectorAll('button, input[type=submit], input[type=button]')).slice(0, 20).map((button) => ({
              tag: button.tagName.toLowerCase(),
              type: button.getAttribute('type') || '',
              text: clean(button.innerText || button.value || button.getAttribute('aria-label') || ''),
              id: button.getAttribute('id') || '',
              name: button.getAttribute('name') || '',
            })),
          }));
          const headings = Array.from(document.querySelectorAll('h1, h2, h3')).slice(0, 20).map((h) => clean(h.innerText));
          const tableHeaders = Array.from(document.querySelectorAll('table')).slice(0, 12).map((table) =>
            Array.from(table.querySelectorAll('thead th, tr:first-child th')).slice(0, 20).map((h) => clean(h.innerText))
          ).filter((headers) => headers.length);
          const gridHeaders = Array.from(document.querySelectorAll('.x-grid3-hd-inner, .x-column-header-text, [role=columnheader]'))
            .slice(0, 40)
            .map((h) => clean(h.innerText || h.textContent || ''))
            .filter(Boolean);
          const gridColumns = [];
          const statusColumnCounts = [];
          if (window.Ext && Ext.ComponentMgr && Ext.ComponentMgr.all) {
            const components = Ext.ComponentMgr.all.items || [];
            for (const component of components) {
              if (!component.getColumnModel || !component.store) continue;
              const columnModel = component.getColumnModel();
              const columns = [];
              for (let index = 0; index < columnModel.getColumnCount(); index++) {
                columns.push({
                  header: clean(columnModel.getColumnHeader(index)),
                  data_index: clean(columnModel.getDataIndex(index)),
                  hidden: Boolean(columnModel.isHidden(index)),
                });
              }
              gridColumns.push({
                title: clean(component.title || ''),
                item_id: clean(component.itemId || ''),
                visible: component.isVisible ? Boolean(component.isVisible()) : !Boolean(component.hidden),
                columns,
                store_fields: (
                  component.store.fields && component.store.fields.items
                    ? component.store.fields.items
                    : []
                ).slice(0, 80).map((field) => clean(field.name)),
              });
              const statusFields = columns
                .map((column) => column.data_index)
                .filter((name) => ['documentacion_estado', 'estado', 'status'].includes(name));
              for (const fieldName of statusFields) {
                const counts = {};
                component.store.each((record) => {
                  const value = clean(record.get(fieldName));
                  if (value) counts[value] = (counts[value] || 0) + 1;
                });
                const values = Object.entries(counts).map(([status_text, count]) => ({ status_text, count }));
                if (values.length) {
                  statusColumnCounts.push({ field: fieldName, values });
                }
              }
            }
          }
          const text = clean(document.body ? document.body.innerText : '');
          const fullText = (document.body ? document.body.innerText : '').toLowerCase();
          const statusTerms = [
            ['accepted', ['validado', 'validada', 'aceptado', 'aceptada']],
            ['rejected', ['rechazado', 'rechazada', 'no conforme']],
            ['expired_external', ['caducado', 'caducada', 'caducados', 'caducadas']],
            ['pending_external_validation', ['en revision', 'en revisión', 'subido', 'subida', 'enviado', 'enviada']],
            ['not_applicable', ['no requerido', 'no requerida', 'no aplica']],
            ['manual_required', ['pendiente', 'requerido', 'requerida', 'incompleto', 'incompleta']],
            ['blocked_by_platform', ['bloqueado', 'bloqueada']]
          ];
          const statusCandidates = statusTerms.map(([normalized, terms]) => {
            const count = terms.reduce((acc, term) => acc + (fullText.match(new RegExp(term, 'g')) || []).length, 0);
            return { normalized_status: normalized, count };
          }).filter((item) => item.count > 0);
          const captchaSignals = Array.from(document.querySelectorAll('iframe, script, div, input')).slice(0, 500).some((el) => {
            const value = `${el.getAttribute('src') || ''} ${el.getAttribute('class') || ''} ${el.getAttribute('id') || ''} ${el.getAttribute('name') || ''}`.toLowerCase();
            return value.includes('captcha') || value.includes('recaptcha') || value.includes('hcaptcha');
          });
          const mfaSignals = /\\b(mfa|2fa|otp|verification code|codigo de verificacion|c[oó]digo de verificaci[oó]n|doble factor)\\b/i.test(text);
          return {
            forms,
            headings,
            tableHeaders,
            gridHeaders,
            gridColumns,
            statusColumnCounts,
            statusCandidates,
            captcha_signals: captchaSignals,
            mfa_signals: mfaSignals,
            body_text: clean(text)
          };
        }"""
    )
    return result if isinstance(result, dict) else {}


def _page_snapshot(label: str, page: Any, shape: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "url_sanitized": _sanitize_url(page.url),
        "title": _redact_text(_safe_title(page)),
        "headings": [_redact_text(item) for item in shape["headings"]],
        "table_headers": shape["tableHeaders"],
        "grid_headers": [_redact_text(item) for item in shape.get("gridHeaders", [])],
        "grid_columns": _redact_grid_columns(shape.get("gridColumns", [])),
        "status_column_counts": _redact_status_column_counts(shape.get("statusColumnCounts", [])),
        "status_candidates": shape.get("statusCandidates", []),
        "forms": shape["forms"],
    }


def _external_status_summary(pages: list[dict[str, Any]]) -> dict[str, Any]:
    term_totals: Counter[str] = Counter()
    column_totals: Counter[str] = Counter()
    pages_with_candidates: list[str] = []
    pages_with_status_columns: list[str] = []
    for page in pages:
        for candidate in page.get("status_candidates", []):
            status = candidate.get("normalized_status")
            count = candidate.get("count")
            if isinstance(status, str) and isinstance(count, int):
                term_totals[status] += count
        if page.get("status_candidates"):
            pages_with_candidates.append(str(page.get("label") or page.get("title") or "page"))
        for status_column in page.get("status_column_counts", []):
            for value in status_column.get("values", []):
                status_text = value.get("status_text")
                count = value.get("count")
                if isinstance(status_text, str) and isinstance(count, int):
                    column_totals[_normalize_status_text(status_text)] += count
        if page.get("status_column_counts"):
            pages_with_status_columns.append(str(page.get("label") or page.get("title") or "page"))
    status_counts = column_totals if column_totals else term_totals
    return {
        "mode": "readonly_grid_status_counts" if column_totals else "readonly_unlinked_status_terms",
        "status_counts": status_counts.most_common(),
        "term_status_counts": term_totals.most_common(),
        "column_status_counts": column_totals.most_common(),
        "pages_with_status_terms": pages_with_candidates,
        "pages_with_status_columns": pages_with_status_columns,
        "persisted": False,
        "row_level_observations": False,
    }


def _redact_grid_columns(grid_columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for grid in grid_columns:
        redacted.append(
            {
                "title": _redact_text(grid.get("title", "")),
                "item_id": _redact_text(grid.get("item_id", "")),
                "visible": grid.get("visible"),
                "columns": [
                    {
                        "header": _redact_text(column.get("header", "")),
                        "data_index": _redact_text(column.get("data_index", "")),
                        "hidden": column.get("hidden"),
                    }
                    for column in grid.get("columns", [])
                ],
                "store_fields": [_redact_text(field) for field in grid.get("store_fields", [])],
            }
        )
    return redacted


def _redact_status_column_counts(status_column_counts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for column in status_column_counts:
        redacted.append(
            {
                "field": _redact_text(column.get("field", "")),
                "values": [
                    {
                        "status_text": _redact_text(value.get("status_text", "")),
                        "normalized_status": _normalize_status_text(str(value.get("status_text", ""))),
                        "count": value.get("count"),
                    }
                    for value in column.get("values", [])
                ],
            }
        )
    return redacted


def _normalize_status_text(status_text: str) -> str:
    value = _strip_accents(status_text).lower()
    if any(term in value for term in ("validado", "validada", "aceptado", "aceptada")):
        return "accepted"
    if any(term in value for term in ("rechazado", "rechazada", "no conforme")):
        return "rejected"
    if any(term in value for term in ("caducado", "caducada")):
        return "expired_external"
    if any(term in value for term in ("revision", "subido", "subida", "enviado", "enviada")):
        return "pending_external_validation"
    if any(term in value for term in ("no requerido", "no requerida", "no aplica")):
        return "not_applicable"
    if any(term in value for term in ("pendiente", "requerido", "requerida", "incompleto", "incompleta")):
        return "manual_required"
    if any(term in value for term in ("bloqueado", "bloqueada")):
        return "blocked_by_platform"
    return "unknown"


def _strip_accents(value: str) -> str:
    return (
        value.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
    )


def _contains_expected_context(shape: dict[str, Any], expected_context: str) -> bool:
    expected = expected_context.strip().lower()
    if not expected:
        return True
    haystack = " ".join([*shape.get("headings", []), shape.get("body_text", "")]).lower()
    return expected in haystack


def _network_summary(requests: list[dict[str, Any]], responses: list[dict[str, Any]]) -> dict[str, Any]:
    hosts = Counter(urlparse(item["url"]).netloc for item in requests)
    methods = Counter(item["method"] for item in requests)
    statuses = Counter(str(item["status"]) for item in responses)
    content_types = Counter(
        item["content_type"].split(";")[0].strip().lower()
        for item in responses
        if item.get("content_type")
    )
    return {
        "hosts": hosts.most_common(20),
        "methods": methods.most_common(),
        "statuses": statuses.most_common(),
        "content_types": content_types.most_common(20),
    }


def _status_from_login(login_status: str) -> str:
    if login_status == "login_likely_success":
        return "completed"
    if login_status.startswith("human_action_required"):
        return "human_action_required"
    if login_status.startswith("login_likely_success"):
        return "completed_with_warnings"
    return "failed"


def _summary_from_outcome(outcome: dict[str, Any]) -> str:
    login_status = str(outcome.get("login_status", "unknown"))
    if login_status == "login_likely_success":
        return "Login directo e-coordina confirmado en modo solo lectura."
    if login_status.startswith("human_action_required"):
        return "La plataforma requiere accion humana para captcha, MFA o aviso no determinista."
    if login_status == "login_likely_success_context_unconfirmed":
        return "Login probable, pero el contexto esperado no se pudo confirmar de forma estable."
    return f"Revision e-coordina no completada: {login_status}."


def _safe_title(page: Any) -> str:
    try:
        return str(page.title())
    except Exception:
        return ""


def _redact_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[email]", text)
    text = re.sub(r"\b\d{8}[A-Za-z]\b", "[dni]", text)
    text = re.sub(r"\b[XYZ]\d{7}[A-Za-z]\b", "[nie]", text, flags=re.I)
    text = re.sub(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b", "[phone-or-id]", text)
    for hint in SECRET_HINTS:
        text = re.sub(rf"({hint}\s*[:=]\s*)([^\s,;]+)", r"\1[redacted]", text, flags=re.I)
    return " ".join(text.split())[:240]


def _sanitize_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    safe_query = []
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        safe_query.append((key, "[redacted]" if any(hint in key.lower() for hint in SECRET_HINTS) else "[value]"))
    query = "&".join(f"{key}={value}" for key, value in safe_query)
    path = re.sub(r"/\d{3,}(?=/|$)", "/[id]", parsed.path)
    path = re.sub(r"/[0-9a-f]{16,}(?=/|$)", "/[hash]", path, flags=re.I)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", query, ""))
