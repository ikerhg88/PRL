from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.platform_credentials import resolve_platform_credentials  # noqa: E402

HELPER_VERSION = "readonly_capture_v8_persistent_session"
MAX_USERNAME_STEP_SUBMISSIONS = 1
MAX_PASSWORD_SUBMISSIONS = 1
LOGIN_VARIANT_POLICY = {
    "parallel_attempts": False,
    "max_credential_submissions_per_account": MAX_PASSWORD_SUBMISSIONS,
    "max_username_step_submissions": MAX_USERNAME_STEP_SUBMISSIONS,
    "selector_guessing_allowed": False,
    "stop_on": [
        "captcha",
        "mfa",
        "legal_notice",
        "session_conflict",
        "rate_limit_or_lock_warning",
        "unexpected_company_or_account",
    ],
}


@dataclass(frozen=True)
class BrowserSession:
    context: Any
    browser: Any | None
    persistent: bool
    profile_reused: bool
    profile_key: str | None


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch a visible assisted browser for authorized human-assisted RPA.")
    parser.add_argument("--entry-url", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--secret-ref", default="")
    parser.add_argument("--platform-label", default="Plataforma externa")
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--session-profile-dir", type=Path, default=None)
    parser.add_argument("--target-context", default="")
    parser.add_argument("--timeout-minutes", type=int, default=20)
    args = parser.parse_args()

    args.status_file.parent.mkdir(parents=True, exist_ok=True)
    session_profile = prepare_session_profile(args.session_profile_dir)
    credential_resolution = resolve_platform_credentials(
        secret_ref=args.secret_ref or None,
        platform_account_id=args.account_id,
    )
    if credential_resolution.credentials is None:
        write_status(
            args.status_file,
            state="credentials_missing",
            platform_label=args.platform_label,
            entry_url=args.entry_url,
            message="No se encontraron credenciales configuradas para esta cuenta.",
            session=session_profile,
        )
        return 2

    credentials = credential_resolution.credentials
    write_status(
        args.status_file,
        state="launching_browser",
        platform_label=args.platform_label,
        entry_url=args.entry_url,
        message=(
            "Lanzando navegador visible con perfil de sesion local."
            if session_profile is not None
            else "Lanzando navegador visible."
        ),
        session=session_profile,
    )

    deadline = time.monotonic() + max(args.timeout_minutes, 1) * 60
    with sync_playwright() as playwright:
        browser_session = launch_visible_session(
            playwright,
            args.status_file,
            args.platform_label,
            args.entry_url,
            session_profile,
        )
        if browser_session is None:
            return 3
        context = browser_session.context
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(args.entry_url, wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            pass
        except Exception as exc:
            write_status(
                args.status_file,
                state="navigation_error_waiting_operator",
                platform_label=args.platform_label,
                entry_url=safe_url(page.url),
                message=f"No se pudo completar la navegacion inicial automaticamente: {type(exc).__name__}. Revisa la ventana visible.",
                session=browser_session,
            )

        username_submitted = False
        username_submit_attempts = 0
        credentials_submitted = False
        authenticated_by_existing_session = False
        password_submit_attempts = 0
        selected_login_variant: str | None = None
        while time.monotonic() < deadline and not credentials_submitted and not authenticated_by_existing_session:
            username_field = find_username_field(page)
            password_field = find_password_field(page)
            shape = collect_shape(page)
            if is_authenticated_page(page, args.entry_url, shape, password_field=password_field):
                authenticated_by_existing_session = True
                selected_login_variant = "existing_session_or_resume"
                write_status(
                    args.status_file,
                    state="session_resumed",
                    platform_label=args.platform_label,
                    entry_url=safe_url(page.url),
                    message="Sesion local reutilizada; no se han reenviado credenciales.",
                    extra={
                        "selected_login_variant": selected_login_variant,
                        "login_variant_policy": LOGIN_VARIANT_POLICY,
                    },
                    session=browser_session,
                )
                break
            if (shape["captcha"] or shape["mfa"]) and username_field is None and password_field is None:
                write_status(
                    args.status_file,
                    state="human_control_required",
                    platform_label=args.platform_label,
                    entry_url=safe_url(page.url),
                    message="Resuelve captcha/MFA/aviso en el navegador visible; el asistente seguira cuando pueda localizar el formulario.",
                    extra={"login_variant_policy": LOGIN_VARIANT_POLICY},
                    session=browser_session,
                )
                time.sleep(2)
                continue

            if password_field is not None and password_submit_attempts < MAX_PASSWORD_SUBMISSIONS:
                try:
                    selected_login_variant = (
                        "single_page_password"
                        if username_field is not None
                        else "password_after_username"
                        if username_submitted
                        else "password_only_visible"
                    )
                    if username_field is not None:
                        fill_field(username_field, credentials.username)
                    fill_field(password_field, credentials.password)
                    password_submit_attempts += 1
                    click_submit(page)
                    credentials_submitted = True
                    write_status(
                        args.status_file,
                        state="credentials_submitted",
                        platform_label=args.platform_label,
                        entry_url=safe_url(page.url),
                        message="Credenciales introducidas desde configuracion local; completa cualquier paso humano y revisa la plataforma.",
                        extra={
                            "selected_login_variant": selected_login_variant,
                            "login_variant_policy": LOGIN_VARIANT_POLICY,
                        },
                        session=browser_session,
                    )
                except Exception as exc:
                    write_status(
                        args.status_file,
                        state="autofill_failed",
                        platform_label=args.platform_label,
                        entry_url=safe_url(page.url),
                        message=f"No se pudo completar el formulario automaticamente: {type(exc).__name__}.",
                        extra={
                            "selected_login_variant": selected_login_variant,
                            "login_variant_policy": LOGIN_VARIANT_POLICY,
                        },
                        session=browser_session,
                    )
                    time.sleep(2)
                    continue
            elif (
                username_field is not None
                and password_field is None
                and username_submit_attempts < MAX_USERNAME_STEP_SUBMISSIONS
            ):
                try:
                    selected_login_variant = "two_step_password"
                    fill_field(username_field, credentials.username)
                    click_submit(page)
                    username_submitted = True
                    username_submit_attempts += 1
                    write_status(
                        args.status_file,
                        state="username_submitted",
                        platform_label=args.platform_label,
                        entry_url=safe_url(page.url),
                        message="Usuario introducido desde configuracion local; esperando pantalla de password o control humano.",
                        extra={
                            "selected_login_variant": selected_login_variant,
                            "login_variant_policy": LOGIN_VARIANT_POLICY,
                        },
                        session=browser_session,
                    )
                except Exception as exc:
                    write_status(
                        args.status_file,
                        state="autofill_failed",
                        platform_label=args.platform_label,
                        entry_url=safe_url(page.url),
                        message=f"No se pudo completar el usuario automaticamente: {type(exc).__name__}.",
                        extra={
                            "selected_login_variant": selected_login_variant,
                            "login_variant_policy": LOGIN_VARIANT_POLICY,
                        },
                        session=browser_session,
                    )
                    time.sleep(2)
                    continue
            else:
                write_status(
                    args.status_file,
                    state="waiting_for_login_form",
                    platform_label=args.platform_label,
                    entry_url=safe_url(page.url),
                    message=(
                        "Esperando pantalla de usuario/password o resolucion humana en navegador visible."
                        if username_submitted
                        else "Esperando formulario de login o resolucion humana en navegador visible."
                    ),
                    extra={
                        "selected_login_variant": selected_login_variant,
                        "login_variant_policy": LOGIN_VARIANT_POLICY,
                    },
                    session=browser_session,
                )
            time.sleep(2)

        capture_summary: dict[str, Any] | None = None
        if credentials_submitted or authenticated_by_existing_session:
            capture_summary = perform_readonly_capture(
                page,
                status_file=args.status_file,
                platform_label=args.platform_label,
                original_entry_url=args.entry_url,
                deadline=deadline,
                session=browser_session,
                target_context=args.target_context,
            )

        while time.monotonic() < deadline and len(context.pages) > 0:
            write_status(
                args.status_file,
                state=(
                    "browser_open_for_operator"
                    if credentials_submitted or authenticated_by_existing_session
                    else "login_not_completed_waiting_operator"
                ),
                platform_label=args.platform_label,
                entry_url=safe_url(page.url),
                message=(
                    "Navegador abierto para el operador; vuelve al Hub para marcar el resultado cuando termines."
                    if credentials_submitted or authenticated_by_existing_session
                    else "No se pudo completar el login automatico; revisa la ventana visible."
                ),
                extra={"capture_summary": capture_summary} if capture_summary is not None else None,
                session=browser_session,
            )
            time.sleep(5)

        context.close()
        if browser_session.browser is not None:
            browser_session.browser.close()

    write_status(
        args.status_file,
        state="browser_closed",
        platform_label=args.platform_label,
        entry_url=args.entry_url,
        message=(
            "Sesion asistida cerrada; el perfil local queda disponible para reutilizacion."
            if browser_session.persistent
            else "Sesion asistida cerrada."
        ),
        session=browser_session,
    )
    return 0


def prepare_session_profile(profile_dir: Path | None) -> dict[str, Any] | None:
    if profile_dir is None:
        return None
    existed = profile_dir.exists() and any(profile_dir.iterdir()) if profile_dir.exists() else False
    profile_dir.mkdir(parents=True, exist_ok=True)
    return {"path": profile_dir, "profile_key": profile_dir.name, "reused": existed}


def launch_visible_session(
    playwright: Any,
    status_file: Path,
    platform_label: str,
    entry_url: str,
    session_profile: dict[str, Any] | None,
) -> BrowserSession | None:
    if session_profile is not None:
        profile_dir = session_profile["path"]
        for launch_kwargs in [{}, {"channel": "chrome"}, {"channel": "msedge"}]:
            try:
                context = playwright.chromium.launch_persistent_context(
                    str(profile_dir),
                    headless=False,
                    viewport={"width": 1366, "height": 900},
                    locale="es-ES",
                    accept_downloads=False,
                    **launch_kwargs,
                )
                write_status(
                    status_file,
                    state="browser_launched",
                    platform_label=platform_label,
                    entry_url=entry_url,
                    message="Navegador visible lanzado con perfil persistente de sesion local.",
                    session={
                        "persistent": True,
                        "profile_key": session_profile["profile_key"],
                        "profile_reused": bool(session_profile["reused"]),
                    },
                )
                return BrowserSession(
                    context=context,
                    browser=None,
                    persistent=True,
                    profile_reused=bool(session_profile["reused"]),
                    profile_key=str(session_profile["profile_key"]),
                )
            except Exception:
                continue
        write_status(
            status_file,
            state="persistent_browser_launch_failed",
            platform_label=platform_label,
            entry_url=entry_url,
            message="No se pudo abrir navegador visible con perfil persistente; se intentara sesion no persistente.",
            session={
                "persistent": True,
                "profile_key": session_profile["profile_key"],
                "profile_reused": bool(session_profile["reused"]),
            },
        )

    try:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1366, "height": 900}, locale="es-ES", accept_downloads=False)
        return BrowserSession(context=context, browser=browser, persistent=False, profile_reused=False, profile_key=None)
    except Exception:
        write_status(
            status_file,
            state="managed_browser_missing",
            platform_label=platform_label,
            entry_url=entry_url,
            message="Chromium de Playwright no esta instalado; probando Chrome instalado en el equipo.",
            session=None,
        )
    for channel, label in [("chrome", "Chrome"), ("msedge", "Microsoft Edge")]:
        try:
            browser = playwright.chromium.launch(channel=channel, headless=False)
            context = browser.new_context(viewport={"width": 1366, "height": 900}, locale="es-ES", accept_downloads=False)
            write_status(
                status_file,
                state="browser_launched",
                platform_label=platform_label,
                entry_url=entry_url,
                message=f"Navegador visible lanzado con {label}.",
                session=None,
            )
            return BrowserSession(context=context, browser=browser, persistent=False, profile_reused=False, profile_key=None)
        except Exception:
            continue
    write_status(
        status_file,
        state="browser_launch_failed",
        platform_label=platform_label,
        entry_url=entry_url,
        message=(
            "No se pudo abrir navegador visible. Instala navegadores de Playwright con "
            "'python -m playwright install chromium' o configura Chrome/Microsoft Edge."
        ),
        session=None,
    )
    return None


def perform_readonly_capture(
    page: Any,
    *,
    status_file: Path,
    platform_label: str,
    original_entry_url: str,
    deadline: float,
    session: BrowserSession,
    target_context: str,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    navigation_actions: list[dict[str, Any]] = []
    wait_until = deadline
    while time.monotonic() < wait_until:
        shape = collect_shape(page)
        if shape["captcha"] or shape["mfa"]:
            write_status(
                status_file,
                state="human_control_required",
                platform_label=platform_label,
                entry_url=safe_url(page.url),
                message="Resuelve captcha/MFA/aviso en el navegador visible; la lectura seguira despues.",
                session=session,
            )
            time.sleep(2)
            continue
        if shape.get("human_context_required"):
            selection = auto_select_context_if_unique(page, target_context)
            if selection.get("ok"):
                write_status(
                    status_file,
                    state="context_selected",
                    platform_label=platform_label,
                    entry_url=safe_url(page.url),
                    message=f"Contexto seleccionado automaticamente: {selection.get('matched_text')}.",
                    extra={"context_selection": selection},
                    session=session,
                )
                time.sleep(3)
                continue
            write_status(
                status_file,
                state="human_context_required",
                platform_label=platform_label,
                entry_url=safe_url(page.url),
                message=(
                    "Selecciona la empresa/cuenta correcta en el navegador visible; la lectura continuara despues."
                    if not selection.get("reason")
                    else f"No hay seleccion automatica segura ({selection.get('reason')}); selecciona la empresa/cuenta correcta."
                ),
                extra={"context_selection": selection},
                session=session,
            )
            time.sleep(2)
            continue
        if (not is_login_url(page.url) and page.url != original_entry_url) or shape.get("post_login_likely"):
            break
        time.sleep(2)

    pages.append(readonly_page_snapshot("post-login", page))
    coordination = click_readonly_text(page, ["Coordinación", "Coordinacion"])
    navigation_actions.append(coordination)
    if coordination.get("ok"):
        wait_after_readonly_navigation(page)
        pages.append(readonly_page_snapshot("coordinacion", page))

    summary = readonly_capture_summary(pages, navigation_actions)
    state = "readonly_capture_collected"
    message = "Lectura de solo lectura recogida; se puede sincronizar con el Hub."
    if summary.get("session_conflict"):
        state = "session_conflict"
        message = "La plataforma informa de una sesion activa duplicada; no hay datos operativos accesibles hasta cerrarla."
    write_status(
        status_file,
        state=state,
        platform_label=platform_label,
        entry_url=safe_url(page.url),
        message=message,
        extra={"capture_summary": summary},
        session=session,
    )
    return summary


def readonly_page_snapshot(label: str, page: Any) -> dict[str, Any]:
    shape = collect_readonly_shape(page)
    return {
        "label": label,
        "url": safe_url(page.url),
        "title": redact(safe_title(page)),
        "headings": [redact(item) for item in shape.get("headings", [])],
        "cards": [redact(item) for item in shape.get("cards", [])],
        "buttons": [redact(item) for item in shape.get("buttons", [])],
        "links": [redact(item) for item in shape.get("links", [])],
        "forms": shape.get("forms", []),
        "table_headers": shape.get("table_headers", []),
        "grid_headers": [redact(item) for item in shape.get("grid_headers", [])],
        "status_counts": shape.get("status_counts", []),
        "target_signals": shape.get("target_signals", {}),
    }


def readonly_capture_summary(pages: list[dict[str, Any]], navigation_actions: list[dict[str, Any]]) -> dict[str, Any]:
    total_status_counts: dict[str, int] = {}
    target_signals = {"cliente_a": False, "alicia": False, "epis": False}
    session_conflict = False
    for page in pages:
        page_title = str(page.get("title") or "").lower()
        page_headings = " ".join(str(item) for item in page.get("headings", [])).lower()
        session_conflict = (
            session_conflict
            or "sesion activa" in page_title
            or "sesión activa" in page_title
            or "sesion abierta" in page_headings
            or "sesión abierta" in page_headings
            or "mismas credenciales" in page_headings
        )
        for item in page.get("status_counts", []):
            status = str(item.get("normalized_status") or "unknown")
            count = int(item.get("count") or 0)
            total_status_counts[status] = total_status_counts.get(status, 0) + count
        signals = page.get("target_signals", {})
        for key in target_signals:
            target_signals[key] = target_signals[key] or bool(signals.get(key))
    return {
        "mode": "assisted_browser_readonly_capture",
        "pages_captured": len(pages),
        "pages": pages,
        "navigation_actions": navigation_actions,
        "status_counts": sorted(total_status_counts.items()),
        "target_signals": target_signals,
        "session_conflict": session_conflict,
        "persisted_row_level": False,
        "row_level_blocker": (
            "La plataforma ha devuelto bloqueo por sesion activa duplicada."
            if session_conflict
            else "Falta mapeo aprobado entre campos de la plataforma y documentos/trabajadores del Hub."
        ),
    }


def collect_readonly_shape(page: Any) -> dict[str, Any]:
    try:
        result = page.evaluate(
            """() => {
              const clean = (value) => (value || '').toString().replace(/\\s+/g, ' ').trim().slice(0, 160);
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              const texts = (selector, max = 40) => Array.from(document.querySelectorAll(selector))
                .filter(visible)
                .slice(0, max)
                .map((el) => clean(el.innerText || el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || ''))
                .filter(Boolean);
              const inputShape = (input) => ({
                tag: input.tagName.toLowerCase(),
                type: input.getAttribute('type') || '',
                name: input.getAttribute('name') || '',
                id: input.getAttribute('id') || '',
                placeholder: clean(input.getAttribute('placeholder') || ''),
                aria_label: clean(input.getAttribute('aria-label') || ''),
              });
              const forms = Array.from(document.querySelectorAll('form')).filter(visible).slice(0, 8).map((form) => ({
                method: (form.getAttribute('method') || 'get').toLowerCase(),
                action_host: (() => {
                  try { return new URL(form.getAttribute('action') || window.location.href, window.location.href).host; }
                  catch { return ''; }
                })(),
                inputs: Array.from(form.querySelectorAll('input, select, textarea')).slice(0, 40).map(inputShape),
              }));
              const tableHeaders = Array.from(document.querySelectorAll('table')).filter(visible).slice(0, 12).map((table) =>
                Array.from(table.querySelectorAll('thead th, tr:first-child th')).slice(0, 30).map((h) => clean(h.innerText || h.textContent || '')).filter(Boolean)
              ).filter((headers) => headers.length);
              const gridHeaders = texts('.x-grid3-hd-inner, .x-column-header-text, [role=columnheader]', 80);
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
              const statusCounts = statusTerms.map(([normalized, terms]) => {
                const count = terms.reduce((acc, term) => acc + (fullText.match(new RegExp(term, 'g')) || []).length, 0);
                return { normalized_status: normalized, count };
              }).filter((item) => item.count > 0);
              return {
                headings: texts('h1, h2, h3, .titulo, .title', 40),
                cards: texts('.card, .programa, .x-panel, [class*=card], [class*=Programa]', 40),
                buttons: texts('button, input[type=button], input[type=submit], .x-btn, [role=button]', 80),
                links: texts('a[href]', 80),
                forms,
                table_headers: tableHeaders,
                grid_headers: gridHeaders,
                status_counts: statusCounts,
                target_signals: {
                  cliente_a: fullText.includes('cliente_a'),
                  alicia: fullText.includes('alicia'),
                  epis: fullText.includes('epis') || fullText.includes('epi')
                },
                post_login_likely: fullText.includes('coordinación') || fullText.includes('coordinacion') || fullText.includes('gestión usuarios')
              };
            }"""
        )
    except Exception:
        return {
            "headings": [],
            "cards": [],
            "buttons": [],
            "links": [],
            "forms": [],
            "table_headers": [],
            "grid_headers": [],
            "status_counts": [],
            "target_signals": {},
            "post_login_likely": False,
        }
    return result if isinstance(result, dict) else {}


def click_readonly_text(page: Any, labels: list[str]) -> dict[str, Any]:
    for label in labels:
        locator = page.get_by_text(label, exact=False).first
        if locator.count() == 0 or not locator.is_visible():
            continue
        try:
            locator.click(timeout=10_000)
            return {"ok": True, "label": redact(label), "method": "visible_text_click"}
        except Exception as exc:
            return {"ok": False, "label": redact(label), "reason": type(exc).__name__}
    return {"ok": False, "label": " / ".join(labels), "reason": "not_found"}


def auto_select_context_if_unique(page: Any, target_context: str) -> dict[str, Any]:
    tokens = context_tokens(target_context)
    if not tokens:
        return {"ok": False, "reason": "target_context_missing"}
    selection = _select_visible_context_match(page, tokens)
    if selection.get("reason") == "no_context_match":
        opener = open_context_selector(page)
        if opener.get("ok"):
            try:
                page.wait_for_timeout(1_000)
            except Exception:
                pass
            selection = _select_visible_context_match(page, tokens)
            if selection.get("ok"):
                selection["opener"] = opener
            elif selection.get("reason") == "no_context_match":
                selection = {"ok": False, "reason": "no_context_match_after_open", "tokens": tokens, "opener": opener}
        elif opener.get("reason"):
            selection["opener"] = opener
    return redact_selection(selection)


def _select_visible_context_match(page: Any, tokens: list[str]) -> dict[str, Any]:
    try:
        result = page.evaluate(
            """(tokens) => {
              const clean = (value) => (value || '').toString().replace(/\\s+/g, ' ').trim();
              const normalize = (value) => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              const nativeSelects = Array.from(document.querySelectorAll('select')).filter(visible);
              for (const token of tokens) {
                const matches = [];
                for (const select of nativeSelects) {
                  for (const option of Array.from(select.options || [])) {
                    const text = clean(option.textContent || option.label || '');
                    if (normalize(text).includes(token)) matches.push({ type: 'native_select', select, option, text });
                  }
                }
                if (matches.length === 1) {
                  const match = matches[0];
                  match.select.value = match.option.value;
                  match.option.selected = true;
                  match.select.dispatchEvent(new Event('input', { bubbles: true }));
                  match.select.dispatchEvent(new Event('change', { bubbles: true }));
                  return { ok: true, method: 'native_select', token, matched_text: match.text };
                }
                if (matches.length > 1) return { ok: false, reason: 'ambiguous_native_select', token, matches: matches.slice(0, 5).map((m) => m.text) };
              }

              const elements = Array.from(document.querySelectorAll('[role=option], option, li, a, button, div, span'))
                .filter(visible)
                .map((element) => ({ element, text: clean(element.innerText || element.textContent || element.getAttribute('aria-label') || element.getAttribute('title') || '') }))
                .filter((item) => item.text.length >= 3 && item.text.length <= 220);
              for (const token of tokens) {
                const rawMatches = elements.filter((item) => normalize(item.text).includes(token));
                const matches = rawMatches.filter((item) => !rawMatches.some((other) => other !== item && item.element.contains(other.element)));
                if (matches.length === 1) {
                  matches[0].element.click();
                  return { ok: true, method: 'visible_option_click', token, matched_text: matches[0].text };
                }
                if (matches.length > 1) return { ok: false, reason: 'ambiguous_visible_option', token, matches: matches.slice(0, 5).map((m) => m.text) };
              }
              return { ok: false, reason: 'no_context_match', tokens };
            }""",
            tokens,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"selection_error:{type(exc).__name__}"}
    if not isinstance(result, dict):
        return {"ok": False, "reason": "unexpected_selection_result"}
    return result


def open_context_selector(page: Any) -> dict[str, Any]:
    try:
        result = page.evaluate(
            """() => {
              const clean = (value) => (value || '').toString().replace(/\\s+/g, ' ').trim();
              const normalize = (value) => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              const companyCue = /\\b(empresa|company|coordinar|coordinacion|selecciona|select)\\b/;
              const candidates = Array.from(document.querySelectorAll(
                'select, [role=combobox], [aria-haspopup=listbox], input, button, a, .select2-selection, .select2-choice, .select2-container'
              ))
                .filter(visible)
                .map((element) => ({
                  element,
                  text: clean([
                    element.innerText,
                    element.textContent,
                    element.getAttribute('placeholder'),
                    element.getAttribute('aria-label'),
                    element.getAttribute('title'),
                    element.getAttribute('name'),
                    element.getAttribute('id')
                  ].filter(Boolean).join(' '))
                }))
                .filter((item) => companyCue.test(normalize(item.text)));
              if (candidates.length === 0) return { ok: false, reason: 'context_selector_not_found' };
              const candidate = candidates[0];
              candidate.element.click();
              return { ok: true, method: 'context_selector_click', label: candidate.text };
            }"""
        )
    except Exception as exc:
        return {"ok": False, "reason": f"open_selector_error:{type(exc).__name__}"}
    return result if isinstance(result, dict) else {"ok": False, "reason": "unexpected_open_selector_result"}


def redact_selection(selection: dict[str, Any]) -> dict[str, Any]:
    if isinstance(selection.get("matched_text"), str):
        selection["matched_text"] = redact(selection["matched_text"])
    if isinstance(selection.get("matches"), list):
        selection["matches"] = [redact(str(item)) for item in selection["matches"][:5]]
    opener = selection.get("opener")
    if isinstance(opener, dict) and isinstance(opener.get("label"), str):
        opener["label"] = redact(opener["label"])
    return selection


def context_tokens(target_context: str) -> list[str]:
    normalized = normalize_text(target_context)
    raw_tokens = [token for token in re.split(r"[^a-z0-9_]+", normalized) if len(token) >= 3]
    ignored = {"arm", "sll", "industrial", "assemblies", "robotics", "spain", "grupo", "empresa", "demo", "cae"}
    tokens = [token for token in raw_tokens if token not in ignored]
    return list(dict.fromkeys(tokens))


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(character for character in decomposed if not unicodedata.combining(character)).lower()


def wait_after_readonly_navigation(page: Any) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(2_500)
    except Exception:
        pass


def is_login_url(value: str) -> bool:
    lowered = value.lower()
    return "login.ctaima.com" in lowered or "/account/login" in lowered


def collect_shape(page: Any) -> dict[str, bool]:
    try:
        result = page.evaluate(
            """() => {
              const text = (document.body ? document.body.innerText : '').toLowerCase();
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              const signals = Array.from(document.querySelectorAll('iframe, div, input, label, textarea')).slice(0, 700)
                .filter(visible)
                .map((el) =>
                  `${el.getAttribute('src') || ''} ${el.getAttribute('title') || ''} ${el.getAttribute('class') || ''} ${el.getAttribute('id') || ''} ${el.getAttribute('name') || ''} ${el.getAttribute('aria-label') || ''} ${el.textContent || ''}`.toLowerCase()
                ).join(' ');
              return {
                captcha: /\\b(captcha|recaptcha|hcaptcha|no soy un robot|i am not a robot|i'm not a robot|verifica que no eres|verificacion humana)\\b/i.test(signals),
                mfa: /\\b(mfa|2fa|otp|verification code|codigo de verificacion|c[oó]digo de verificaci[oó]n|doble factor)\\b/i.test(text),
                post_login_likely: /\\b(coordinaci[oó]n|dashboard|panel de control|trabajadores|documentaci[oó]n|programas|men[uú] principal|control de marcajes)\\b/i.test(text),
                human_context_required: /\\b(seleccione la empresa|selecciona empresa|empresa quieres coordinarte|con qu[eé] empresa|sesion activa|sesi[oó]n activa|sesi[oó]n abierta|mismas credenciales|cerrar la sesi[oó]n)\\b/i.test(text)
              };
            }"""
        )
    except Exception:
        return {"captcha": False, "mfa": False, "post_login_likely": False, "human_context_required": False}
    if not isinstance(result, dict):
        return {"captcha": False, "mfa": False, "post_login_likely": False, "human_context_required": False}
    return {
        "captcha": bool(result.get("captcha")),
        "mfa": bool(result.get("mfa")),
        "post_login_likely": bool(result.get("post_login_likely")),
        "human_context_required": bool(result.get("human_context_required")),
    }


def is_authenticated_page(page: Any, original_entry_url: str, shape: dict[str, bool], *, password_field: Any | None) -> bool:
    if password_field is not None:
        return False
    if shape.get("captcha") or shape.get("mfa"):
        return False
    if shape.get("post_login_likely") and not shape.get("human_context_required"):
        return True
    current_url = safe_url(page.url)
    return bool(current_url and current_url != safe_url(original_entry_url) and not is_login_url(current_url))


def safe_title(page: Any) -> str:
    try:
        return str(page.title())
    except Exception:
        return ""


def find_password_field(page: Any) -> Any | None:
    password = page.locator("input[type='password']").first
    if password.count() > 0 and password.is_visible():
        return password
    return None


def find_username_field(page: Any) -> Any | None:
    for selector in [
        "input[type='email']",
        "input[autocomplete='username']",
        "input[placeholder*='correo' i]",
        "input[placeholder*='email' i]",
        "input[aria-label*='correo' i]",
        "input[aria-label*='email' i]",
        "input[name*='email' i]",
        "input[id*='email' i]",
        "input[name*='correo' i]",
        "input[id*='correo' i]",
        "input[name*='user' i]",
        "input[id*='user' i]",
        "input[name*='login' i]",
        "input[id*='login' i]",
        "input[type='text']",
        "input:not([type='password']):not([type='hidden'])",
    ]:
        locator = page.locator(selector).first
        if locator.count() > 0 and locator.is_visible():
            return locator
    return None


def fill_field(locator: Any, value: str) -> None:
    try:
        locator.fill(value, timeout=10_000)
        return
    except Exception:
        pass
    locator.evaluate(
        """(element, value) => {
          element.focus();
          element.value = value;
          element.dispatchEvent(new Event('input', { bubbles: true }));
          element.dispatchEvent(new Event('change', { bubbles: true }));
          element.blur();
        }""",
        value,
        timeout=10_000,
    )


def click_submit(page: Any) -> None:
    for selector in [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('CONTINUAR')",
        "button:has-text('Continuar')",
        "button:has-text('Acceder')",
        "button:has-text('Entrar')",
        "button:has-text('Iniciar')",
        "button:has-text('Login')",
        "button:has-text('Validar')",
        "text=/^(Acceder|Entrar|Iniciar sesi[oó]n|Login|Validar|Continuar)$/i",
    ]:
        locator = page.locator(selector).first
        if locator.count() > 0 and locator.is_visible():
            try:
                locator.click(timeout=10_000)
            except Exception:
                locator.evaluate(
                    """(element) => {
                      element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                      if (typeof element.click === 'function') element.click();
                    }""",
                    timeout=10_000,
                )
            return
    page.keyboard.press("Enter")


def write_status(
    path: Path,
    *,
    state: str,
    platform_label: str,
    entry_url: str,
    message: str,
    extra: dict[str, Any] | None = None,
    session: BrowserSession | dict[str, Any] | None = None,
) -> None:
    payload = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "state": state,
        "helper_version": HELPER_VERSION,
        "platform_label": redact(platform_label),
        "entry_url": safe_url(entry_url),
        "message": redact(message),
    }
    if extra:
        payload.update(extra)
    if session is not None:
        if isinstance(session, BrowserSession):
            payload["session_persistence"] = {
                "enabled": session.persistent,
                "profile_key": session.profile_key,
                "profile_reused": session.profile_reused,
                "stores_raw_cookies_in_status": False,
            }
        else:
            payload["session_persistence"] = {
                "enabled": bool(session.get("persistent", True)),
                "profile_key": session.get("profile_key"),
                "profile_reused": bool(session.get("profile_reused") or session.get("reused")),
                "stores_raw_cookies_in_status": False,
            }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def safe_url(value: str) -> str:
    return re.sub(r"([?&][^=]*(?:token|pass|secret|auth|session)[^=]*=)[^&]+", r"\1[redacted]", value, flags=re.I)


def redact(value: str) -> str:
    text = re.sub(r"[\w.\-+]+@[\w.\-]+\.\w+", "[email]", value)
    text = re.sub(r"\b\d{8}[A-Za-z]\b", "[dni]", text)
    text = re.sub(r"\b[XYZ]\d{7}[A-Za-z]\b", "[nie]", text, flags=re.I)
    return text[:500]


if __name__ == "__main__":
    raise SystemExit(main())
