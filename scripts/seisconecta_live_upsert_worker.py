from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.platform_credentials import resolve_platform_credentials  # noqa: E402
from scripts.assisted_platform_browser import (  # noqa: E402
    auto_select_context_if_unique,
    click_submit,
    collect_shape,
    fill_field,
    find_password_field,
    find_username_field,
    is_authenticated_page,
    launch_visible_session,
    prepare_session_profile,
    safe_url,
    write_status,
)

HELPER_VERSION = "seisconecta_live_upsert_worker_v2"
LOGIN_URL = "https://www.6conecta.com/es/iniciar-sesion"
WORKER_FORM_URL = "https://www.6conecta.com/index.php/component/seysconecta/p3:trabajadores/?Itemid=549"
WORKER_FORM_ACTION_MARKER = "task=trabajador.apply"


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorized live worker upsert for 6conecta dummy accounts.")
    parser.add_argument("--entry-url", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--secret-ref", default="")
    parser.add_argument("--platform-label", default="6conecta")
    parser.add_argument("--target-context", default="")
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--session-profile-dir", type=Path, required=True)
    parser.add_argument("--payload-file", type=Path, default=None)
    parser.add_argument("--worker-ref", default="")
    parser.add_argument("--identifier-value", default="")
    parser.add_argument("--identifier-last4", default="")
    parser.add_argument("--first-name", default="")
    parser.add_argument("--last-name", default="")
    parser.add_argument("--nationality", default="")
    parser.add_argument("--contract-type", default="")
    parser.add_argument("--work-position", default="")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--readback-only", action="store_true")
    parser.add_argument("--timeout-minutes", type=int, default=20)
    args = parser.parse_args()
    if args.payload_file is not None:
        _load_worker_payload(args, args.payload_file)
    missing = [
        name
        for name in ("worker_ref", "identifier_value", "first_name", "last_name", "nationality", "contract_type", "work_position")
        if not str(getattr(args, name)).strip()
    ]
    if missing:
        _print_result(
            f"missing_worker_payload:{','.join(missing)}",
            external_write_executed=False,
            post_write_read_confirmed=False,
        )
        return 2

    args.status_file.parent.mkdir(parents=True, exist_ok=True)
    session_profile = prepare_session_profile(args.session_profile_dir)
    resolution = resolve_platform_credentials(
        secret_ref=args.secret_ref or None,
        platform_account_id=args.account_id,
    )
    if resolution.credentials is None:
        _status(args, "credentials_missing", args.entry_url, "No configured credentials found.", session_profile)
        _print_result("credentials_missing", external_write_executed=False, post_write_read_confirmed=False)
        return 2

    deadline = time.monotonic() + max(args.timeout_minutes, 1) * 60
    _status(args, "launching_browser", args.entry_url, "Launching visible browser for authorized live write.", session_profile)
    with sync_playwright() as playwright:
        browser_session = launch_visible_session(
            playwright,
            args.status_file,
            args.platform_label,
            args.entry_url,
            session_profile,
        )
        if browser_session is None:
            _print_result("browser_launch_failed", external_write_executed=False, post_write_read_confirmed=False)
            return 3
        page = browser_session.context.pages[0] if browser_session.context.pages else browser_session.context.new_page()
        try:
            page.goto(args.entry_url, wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            pass

        login_ok = _login_or_resume(page, args, resolution.credentials, deadline, browser_session)
        if not login_ok:
            _print_result(
                "login_not_completed",
                external_write_executed=False,
                post_write_read_confirmed=False,
                status_file=args.status_file,
            )
            return 4

        if args.readback_only:
            readback = _verify_worker_readback(page, args, deadline, browser_session)
            state = "readback_confirmed" if readback["confirmed"] else "readback_not_confirmed"
            _status(
                args,
                state,
                page.url,
                readback["message"],
                browser_session,
                extra={
                    "worker": _worker_summary(args),
                    "external_write_executed": False,
                    "post_write_read_confirmed": readback["confirmed"],
                    "post_write_readback": readback,
                },
            )
            result = {
                "status": state,
                "external_write_executed": False,
                "post_write_read_confirmed": readback["confirmed"],
                "exit_code": 0 if readback["confirmed"] else 8,
            }
        else:
            result = _open_fill_and_submit(page, args, deadline, browser_session)
        try:
            browser_session.context.close()
        finally:
            if browser_session.browser is not None:
                browser_session.browser.close()
        _print_result(
            result["status"],
            external_write_executed=result["external_write_executed"],
            post_write_read_confirmed=bool(result.get("post_write_read_confirmed")),
            status_file=args.status_file,
        )
        return int(result["exit_code"])


def _login_or_resume(page: Any, args: argparse.Namespace, credentials: Any, deadline: float, browser_session: Any) -> bool:
    username_attempts = 0
    password_attempts = 0
    username_submitted = False
    while time.monotonic() < deadline:
        shape = collect_shape(page)
        password_field = find_password_field(page)
        if is_authenticated_page(page, args.entry_url, shape, password_field=password_field):
            _status(args, "session_resumed", page.url, "Existing session reused.", browser_session)
            return True
        if shape.get("captcha") or shape.get("mfa"):
            _status(args, "human_control_required", page.url, "Resolve captcha/MFA in visible browser; automation will continue.", browser_session)
            time.sleep(2)
            continue
        username_field = find_username_field(page)
        if password_field is not None and password_attempts == 0:
            if username_field is not None:
                fill_field(username_field, credentials.username)
            fill_field(password_field, credentials.password)
            password_attempts += 1
            click_submit(page)
            _status(args, "credentials_submitted", page.url, "Credentials submitted from configured store.", browser_session)
            time.sleep(4)
            continue
        if username_field is not None and password_field is None and username_attempts == 0:
            fill_field(username_field, credentials.username)
            username_attempts += 1
            username_submitted = True
            click_submit(page)
            _status(args, "username_submitted", page.url, "Username submitted from configured store.", browser_session)
            time.sleep(3)
            continue
        if username_submitted or password_attempts:
            time.sleep(2)
            continue
        if _open_login_page_if_public_landing(page):
            _status(args, "opening_login_page", page.url, "Opening login page after public landing redirect.", browser_session)
            time.sleep(2)
            continue
        _status(args, "waiting_for_login_form", page.url, "Waiting for login form or human control.", browser_session)
        time.sleep(2)
    return False


def _open_fill_and_submit(page: Any, args: argparse.Namespace, deadline: float, browser_session: Any) -> dict[str, Any]:
    while time.monotonic() < deadline:
        shape = collect_shape(page)
        if shape.get("captcha") or shape.get("mfa"):
            _status(args, "human_control_required", page.url, "Resolve captcha/MFA before live write continues.", browser_session)
            time.sleep(2)
            continue
        if shape.get("human_context_required"):
            selection = auto_select_context_if_unique(page, args.target_context)
            if selection.get("ok"):
                _status(
                    args,
                    "context_selected",
                    page.url,
                    f"Context selected: {selection.get('matched_text')}.",
                    browser_session,
                    extra={"context_selection": selection},
                )
                time.sleep(2)
                continue
            _status(
                args,
                "human_context_required",
                page.url,
                "Select the authorized company/context in the visible browser.",
                browser_session,
                extra={"context_selection": selection},
            )
            time.sleep(2)
            continue
        break

    preflight_readback = _verify_worker_readback(page, args, deadline, browser_session, max_seconds=45)
    if preflight_readback["confirmed"]:
        _status(
            args,
            "already_exists_external",
            page.url,
            "Worker already exists in 6conecta; duplicate live registration was prevented.",
            browser_session,
            extra={
                "worker": _worker_summary(args),
                "external_write_executed": False,
                "post_write_read_confirmed": True,
                "post_write_readback": preflight_readback,
                "external_worker_id": _external_worker_id_from_readback(preflight_readback),
            },
        )
        return {
            "status": "already_exists_external",
            "external_write_executed": False,
            "post_write_read_confirmed": True,
            "exit_code": 0,
        }

    try:
        page.goto(WORKER_FORM_URL, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeoutError:
        pass

    if not _ensure_worker_form(page):
        _status(
            args,
            "worker_form_not_found",
            page.url,
            "Worker form was not found after login.",
            browser_session,
            extra={"page_shape": _redacted_shape(page)},
        )
        return {"status": "worker_form_not_found", "external_write_executed": False, "exit_code": 5}
    if not _open_worker_creation_form(page):
        _status(
            args,
            "worker_creation_form_not_visible",
            page.url,
            "Worker creation form exists but could not be opened through the platform UI.",
            browser_session,
            extra={"page_shape": _redacted_shape(page), "form_readiness": _worker_form_readiness(page)},
        )
        return {"status": "worker_creation_form_not_visible", "external_write_executed": False, "exit_code": 5}

    _type_identifier_and_wait(page, args.identifier_value)
    _fill_text_if_editable(page, "input[name='jform[codigo]']", args.identifier_value)
    _fill_text(page, "input[name='jform[nombre]']", args.first_name)
    _fill_text(page, "input[name='jform[apellidos]']", args.last_name)
    optional_selection_results = [
        _select_author_company(
            page,
            "select[name='jform[id_empresaautora]']",
            args.target_context or "ARM",
            aliases=["ARM"],
        ),
    ]
    page.wait_for_timeout(2_000)
    select_results = [
        _select_option(page, "select[name='jform[nacionalidad_trabajador]']", args.nationality, aliases=["espana", "spain", "es"]),
        _select_option(page, "select[name='jform[id_contrato][]']", args.contract_type),
        _select_option(page, "select[name='jform[tipo_empresa]']", "Contratado", aliases=["contratado"]),
        _select_option(page, "select[name='jform[id_puesto]']", args.work_position),
    ]
    unresolved = [item for item in select_results if not item["ok"]]
    if unresolved:
        _status(
            args,
            "human_selection_required",
            page.url,
            "Text fields filled. Select unmatched catalog values in the visible browser.",
            browser_session,
            extra={
                "optional_selection_results": optional_selection_results,
                "unresolved_selects": unresolved,
                "worker": _worker_summary(args),
            },
        )
        while time.monotonic() < deadline and not _required_selects_have_values(page):
            time.sleep(2)
        if not _required_selects_have_values(page):
            return {"status": "human_selection_required", "external_write_executed": False, "exit_code": 6}

    _status(
        args,
        "ready_to_submit",
        page.url,
        "Worker form is filled. Submitting because live authorization was provided.",
        browser_session,
        extra={"worker": _worker_summary(args), "submit": bool(args.submit), "form_readiness": _worker_form_readiness(page)},
    )
    if not args.submit:
        return {"status": "ready_to_submit", "external_write_executed": False, "exit_code": 7}

    before_url = safe_url(page.url)
    submit_events: list[dict[str, Any]] = []
    _attach_submit_tracker(page, submit_events)
    if not _click_register_employee(page):
        _status(
            args,
            "submit_button_not_ready",
            page.url,
            "Worker form was filled but the platform submit button was not ready.",
            browser_session,
            extra={
                "worker": _worker_summary(args),
                "submit_observed": False,
                "form_readiness": _worker_form_readiness(page),
            },
        )
        return {"status": "submit_button_not_ready", "external_write_executed": False, "exit_code": 9}
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        pass
    time.sleep(3)
    after_url = safe_url(page.url)
    submit_observed = _submit_request_observed(submit_events) or _is_worker_edit_url(page.url)
    if not submit_observed:
        post_click_readback = _verify_worker_readback(page, args, deadline, browser_session, max_seconds=60)
        if post_click_readback["confirmed"]:
            _status(
                args,
                "confirmed_external",
                page.url,
                "Live submit was confirmed by posterior platform readback.",
                browser_session,
                extra={
                    "worker": _worker_summary(args),
                    "before_url": before_url,
                    "after_url": after_url,
                    "submit_events": submit_events[-8:],
                    "external_write_executed": True,
                    "post_write_read_confirmed": True,
                    "post_write_readback": post_click_readback,
                    "external_worker_id": _external_worker_id_from_readback(post_click_readback),
                },
            )
            return {
                "status": "confirmed_external",
                "external_write_executed": True,
                "post_write_read_confirmed": True,
                "exit_code": 0,
            }
        _status(
            args,
            "submit_not_observed",
            page.url,
            "No worker submit request was observed after clicking the platform button.",
            browser_session,
            extra={
                "worker": _worker_summary(args),
                "before_url": before_url,
                "after_url": after_url,
                "submit_events": submit_events[-8:],
                "external_write_executed": False,
                "post_write_read_confirmed": False,
            },
        )
        return {"status": "submit_not_observed", "external_write_executed": False, "exit_code": 10}
    readback = _verify_worker_readback(page, args, deadline, browser_session)
    state = "confirmed_external" if readback["confirmed"] else "submitted_external_pending_readback"
    message = (
        "Live submit executed and posterior platform read confirmed the worker."
        if readback["confirmed"]
        else "Live submit executed, but posterior platform read did not confirm the worker yet."
    )
    _status(
        args,
        state,
        page.url,
        message,
        browser_session,
        extra={
            "worker": _worker_summary(args),
            "before_url": before_url,
            "after_url": after_url,
            "form_action_marker": WORKER_FORM_ACTION_MARKER,
            "submit_events": submit_events[-8:],
            "external_write_executed": True,
            "post_write_read_confirmed": readback["confirmed"],
            "post_write_readback": readback,
            "external_worker_id": _external_worker_id_from_readback(readback),
        },
    )
    return {
        "status": state,
        "external_write_executed": True,
        "post_write_read_confirmed": readback["confirmed"],
        "exit_code": 0,
    }


def _verify_worker_readback(
    page: Any,
    args: argparse.Namespace,
    deadline: float,
    browser_session: Any,
    *,
    max_seconds: int = 120,
) -> dict[str, Any]:
    checked_pages: list[dict[str, Any]] = []
    read_deadline = min(deadline, time.monotonic() + max_seconds)
    attempts = 0
    _open_worker_area_for_readback(page)
    while time.monotonic() < read_deadline and attempts < 6:
        attempts += 1
        shape = collect_shape(page)
        if shape.get("captcha") or shape.get("mfa"):
            _status(args, "human_control_required", page.url, "Resolve captcha/MFA before post-write readback continues.", browser_session)
            time.sleep(2)
            continue
        match = _worker_match_on_visible_page(page, args)
        checked_pages.append(match["page"])
        if match["confirmed"]:
            return {
                "confirmed": True,
                "method": match["method"],
                "checked_pages": checked_pages[-4:],
                "signals": match["signals"],
                "message": "Posterior readback found the worker using redacted identifier/name signals.",
            }
        if _click_list_view(page):
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass
            time.sleep(2)
            match = _worker_match_on_visible_page(page, args)
            checked_pages.append(match["page"])
            if match["confirmed"]:
                return {
                    "confirmed": True,
                    "method": match["method"],
                    "checked_pages": checked_pages[-4:],
                    "signals": match["signals"],
                    "message": "Posterior readback found the worker in the list view.",
                }
        if _filter_visible_lists(page, args):
            time.sleep(2)
            match = _worker_match_on_visible_page(page, args)
            checked_pages.append(match["page"])
            if match["confirmed"]:
                return {
                    "confirmed": True,
                    "method": match["method"],
                    "checked_pages": checked_pages[-4:],
                    "signals": match["signals"],
                    "message": "Posterior readback found the worker after filtering visible lists.",
                }
        try:
            page.reload(wait_until="domcontentloaded", timeout=20_000)
        except PlaywrightTimeoutError:
            pass
        if _attached_worker_field_count(page) == 0:
            _open_worker_area_for_readback(page)
        time.sleep(3)
    return {
        "confirmed": False,
        "method": "not_found_after_submit",
        "checked_pages": checked_pages[-6:],
        "signals": {
            "identifier_full_seen": False,
            "identifier_last4_seen": False,
            "name_seen": False,
        },
        "message": "Posterior readback did not find a matching worker before timeout.",
    }


def _open_worker_area_for_readback(page: Any) -> None:
    try:
        if "trabajadores" not in str(page.url).lower():
            page.goto(WORKER_FORM_URL, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass
            time.sleep(2)
    except PlaywrightTimeoutError:
        pass


def _worker_match_on_visible_page(page: Any, args: argparse.Namespace) -> dict[str, Any]:
    try:
        visible_text = page.locator("body").inner_text(timeout=5_000)
    except Exception:
        visible_text = ""
    normalized_text = _norm(visible_text)
    identifier_norm = _norm(args.identifier_value)
    last4_norm = _norm(args.identifier_last4 or args.identifier_value[-4:])
    name_tokens = [
        token
        for token in (_norm(args.first_name), _norm(args.last_name))
        if token
    ]
    identifier_full_seen = bool(identifier_norm and identifier_norm in normalized_text)
    identifier_last4_seen = bool(last4_norm and last4_norm in normalized_text)
    name_seen = bool(name_tokens and all(token in normalized_text for token in name_tokens))
    confirmed = identifier_full_seen or (identifier_last4_seen and name_seen)
    method = "identifier_full_visible_text" if identifier_full_seen else "identifier_last4_and_name_visible_text"
    return {
        "confirmed": confirmed,
        "method": method,
        "signals": {
            "identifier_full_seen": identifier_full_seen,
            "identifier_last4_seen": identifier_last4_seen,
            "name_seen": name_seen,
        },
        "page": {
            "url": safe_url(page.url),
            "title": _redacted_page_title(page),
            "text_length": len(visible_text),
            "attached_worker_fields": _attached_worker_field_count(page),
        },
    }


def _click_list_view(page: Any) -> bool:
    for selector in ("a:has-text('Listado')", "button:has-text('Listado')", "text=/^Listado$/i"):
        locator = page.locator(selector).first
        try:
            if locator.count() == 0 or not locator.is_visible(timeout=2_000):
                continue
            href = str(locator.get_attribute("href") or "")
            if _is_access_control_url(href):
                continue
            locator.click(timeout=10_000)
            return True
        except Exception:
            continue
    try:
        return bool(
            page.evaluate(
                """() => {
                  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                  const visible = (element) => {
                    const style = window.getComputedStyle(element);
                    const rect = element.getBoundingClientRect();
                    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
                  };
                  const candidates = Array.from(document.querySelectorAll('a, button, li, span, div'))
                    .filter((element) => visible(element) && clean(element.innerText || element.textContent) === 'listado');
                  const target = candidates.find((element) => {
                    const clickable = element.closest('a, button') || element;
                    const href = clickable.getAttribute('href') || '';
                    return !href.includes('/access-control/');
                  });
                  if (!target) return false;
                  const clickable = target.closest('a, button') || target;
                  clickable.click();
                  return true;
                }"""
            )
        )
    except Exception:
        return False
    return False


def _open_login_page_if_public_landing(page: Any) -> bool:
    current_url = str(page.url).lower()
    if "iniciar-sesion" in current_url or "component/users" in current_url:
        return False
    try:
        has_login_link = page.locator("a[href*='iniciar-sesion'], a:has-text('Acceder')").count() > 0
    except Exception:
        has_login_link = False
    if not has_login_link and not current_url.rstrip("/").endswith("/es"):
        return False
    try:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        return True
    except PlaywrightTimeoutError:
        return True


def _is_access_control_url(value: str) -> bool:
    return "/access-control/" in value.lower()


def _filter_visible_lists(page: Any, args: argparse.Namespace) -> bool:
    query = args.identifier_value or args.identifier_last4 or args.last_name
    if not query:
        return False
    try:
        inputs = page.locator(
            "input[type='search'], input[name*='search' i], input[id*='search' i], "
            "input[name*='buscar' i], input[id*='buscar' i], input[placeholder*='buscar' i], "
            "input[placeholder*='search' i], input[aria-label*='buscar' i], input[aria-label*='search' i]"
        )
        count = min(inputs.count(), 5)
        for index in range(count):
            item = inputs.nth(index)
            if not item.is_visible(timeout=1_000):
                continue
            item.fill(query, timeout=5_000)
            item.press("Enter", timeout=5_000)
            return True
    except Exception:
        return False
    return False


def _fill_text(page: Any, selector: str, value: str) -> None:
    locator = page.locator(selector).first
    if locator.is_visible(timeout=2_000):
        locator.fill(value, timeout=15_000)
        return
    locator.evaluate(
        """(element, value) => {
          element.value = value;
          for (const eventName of ['input', 'change']) {
            const event = document.createEvent('HTMLEvents');
            event.initEvent(eventName, true, false);
            element.dispatchEvent(event);
          }
        }""",
        value,
        timeout=15_000,
    )


def _type_identifier_and_wait(page: Any, value: str) -> None:
    locator = page.locator("input[name='jform[nif]']").first
    locator.click(timeout=10_000)
    locator.fill("", timeout=10_000)
    locator.type(value, delay=40, timeout=15_000)
    locator.press("Tab", timeout=5_000)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if page.locator("input[name='jform[nombre]']").first.is_enabled(timeout=500):
                return
        except Exception:
            pass
        page.wait_for_timeout(500)


def _fill_text_if_editable(page: Any, selector: str, value: str) -> bool:
    locator = page.locator(selector).first
    try:
        if locator.count() == 0:
            return False
        if locator.is_visible(timeout=2_000) and locator.is_enabled(timeout=1_000):
            locator.fill(value, timeout=15_000)
            return True
        return False
    except Exception:
        return False


def _attach_submit_tracker(page: Any, submit_events: list[dict[str, Any]]) -> None:
    def on_request(request: Any) -> None:
        url = str(request.url or "")
        if _is_tracking_url(url):
            return
        if "trabajador" not in url.lower() and "seysconecta" not in url.lower():
            return
        submit_events.append(
            {
                "method": str(request.method or ""),
                "url": safe_url(url),
                "is_worker_submit": _is_worker_submit_url(url),
            }
        )

    page.on("request", on_request)


def _submit_request_observed(submit_events: list[dict[str, Any]]) -> bool:
    return any(bool(event.get("is_worker_submit")) for event in submit_events)


def _is_worker_submit_url(value: str) -> bool:
    normalized = value.lower()
    return (
        "task=trabajador.apply" in normalized
        or "task=trabajador.save" in normalized
        or _is_worker_edit_url(value)
    )


def _is_worker_edit_url(value: str) -> bool:
    normalized = value.lower()
    return "/component/seysconecta/p3:trabajador/p4:edit/p0:" in normalized


def _is_tracking_url(value: str) -> bool:
    normalized = value.lower()
    return "google-analytics.com" in normalized or "googletagmanager.com" in normalized or "__utm.gif" in normalized


def _external_worker_id_from_readback(readback: dict[str, Any]) -> str | None:
    for page_info in readback.get("checked_pages") or []:
        if not isinstance(page_info, dict):
            continue
        match = re.search(r"/p0:(\d+)", str(page_info.get("url") or ""))
        if match:
            return match.group(1)
    return None


def _click_register_employee(page: Any) -> bool:
    button = page.locator("#bRegistrarEmpleado").first
    if button.count() > 0 and button.is_visible(timeout=2_000):
        try:
            if button.is_disabled(timeout=1_000):
                return False
        except Exception:
            return False
        if _invoke_visible_enabled_click_handler(page, "#bRegistrarEmpleado"):
            return True
        try:
            button.click(timeout=20_000)
            return True
        except Exception:
            center = _visible_enabled_element_center(page, "#bRegistrarEmpleado")
            if center is None:
                return False
            try:
                page.mouse.click(center["x"], center["y"])
                return True
            except Exception:
                return False
    center = _visible_enabled_element_center(page, "#bRegistrarEmpleado")
    if center is None:
        return False
    try:
        page.mouse.click(center["x"], center["y"])
        return True
    except Exception:
        return False


def _invoke_visible_enabled_click_handler(page: Any, selector: str) -> bool:
    try:
        return bool(
            page.evaluate(
                """(selector) => {
                  const items = Array.from(document.querySelectorAll(selector));
                  for (const item of items) {
                    const style = window.getComputedStyle(item);
                    const rect = item.getBoundingClientRect();
                    const visible = rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                    if (!visible || item.disabled) continue;
                    item.click();
                    return true;
                  }
                  return false;
                }""",
                selector,
            )
        )
    except Exception:
        return False


def _worker_form_readiness(page: Any) -> dict[str, Any]:
    try:
        return dict(
            page.evaluate(
                """() => {
                  const hasValue = (selector) => {
                    const item = document.querySelector(selector);
                    if (!item) return false;
                    if (item.tagName === 'SELECT' && item.multiple) {
                      return Array.from(item.options || []).some((option) => option.selected && String(option.value || '').trim());
                    }
                    return Boolean(String(item.value || '').trim());
                  };
                  const selectedCount = (selector) => {
                    const item = document.querySelector(selector);
                    if (!item || item.tagName !== 'SELECT') return 0;
                    return Array.from(item.options || []).filter((option) => option.selected && String(option.value || '').trim()).length;
                  };
                  const button = document.querySelector('#bRegistrarEmpleado');
                  const visibleText = (selector) => {
                    const items = Array.from(document.querySelectorAll(selector));
                    return items.map((item) => String(item.innerText || item.textContent || '').replace(/\\s+/g, ' ').trim())
                      .filter(Boolean).slice(0, 8);
                  };
                  return {
                    nif_has_value: hasValue("input[name='jform[nif]']"),
                    code_has_value: hasValue("input[name='jform[codigo]']"),
                    first_name_has_value: hasValue("input[name='jform[nombre]']"),
                    last_name_has_value: hasValue("input[name='jform[apellidos]']"),
                    author_company_has_value: hasValue("select[name='jform[id_empresaautora]']"),
                    contract_selected_count: selectedCount("select[name='jform[id_contrato][]']"),
                    profile_selected_count: selectedCount("select[name='jform[id_perfiles][]']"),
                    nationality_has_value: hasValue("select[name='jform[nacionalidad_trabajador]']"),
                    country_has_value: hasValue("select[name='jform[pais]']"),
                    company_type_has_value: hasValue("select[name='jform[tipo_empresa]']"),
                    work_position_has_value: hasValue("select[name='jform[id_puesto]']"),
                    button_present: Boolean(button),
                    button_disabled: button ? Boolean(button.disabled) : null,
                    alert_count: visibleText(".alert,.message,.warning,.error,[class*=alert],[class*=error],[id*=system-message]").length
                  };
                }"""
            )
        )
    except Exception as exc:
        return {"error": type(exc).__name__}


def _ensure_worker_form(page: Any) -> bool:
    if _has_worker_form(page, timeout=45_000):
        return True
    for selector in [
        "text=/^Empleados$/i",
        "text=/^Trabajadores$/i",
        "a:has-text('Empleados')",
        "a:has-text('Trabajadores')",
        "button:has-text('Empleados')",
        "button:has-text('Trabajadores')",
    ]:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0 or not locator.is_visible():
                continue
            locator.click(timeout=10_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass
            if _has_worker_form(page, timeout=15_000):
                return True
        except Exception:
            continue
    return _has_worker_form(page, timeout=5_000)


def _has_worker_form(page: Any, *, timeout: int) -> bool:
    try:
        page.wait_for_selector("input[name='jform[nif]']", state="attached", timeout=timeout)
        return True
    except PlaywrightTimeoutError:
        return False


def _open_worker_creation_form(page: Any) -> bool:
    if _worker_creation_fields_visible(page):
        return True
    selectors = [
        "a[title='Registrar Empleado']",
        "a.btn:has-text('Registrar Empleado')",
        "a:has-text('Registrar Empleado')",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = min(locator.count(), 6)
            for index in range(count):
                item = locator.nth(index)
                if not item.is_visible(timeout=1_000):
                    continue
                item.click(timeout=10_000)
                page.wait_for_timeout(1_500)
                if _worker_creation_fields_visible(page):
                    return True
        except Exception:
            continue
    center = _visible_element_center_by_text(page, "a", "Registrar Empleado")
    if center is not None:
        try:
            page.mouse.click(center["x"], center["y"])
            page.wait_for_timeout(1_500)
            if _worker_creation_fields_visible(page):
                return True
        except Exception:
            pass
    return _worker_creation_fields_visible(page)


def _visible_enabled_element_center(page: Any, selector: str) -> dict[str, float] | None:
    try:
        return page.evaluate(
            """(selector) => {
              const items = Array.from(document.querySelectorAll(selector));
              for (const item of items) {
                const style = window.getComputedStyle(item);
                const rect = item.getBoundingClientRect();
                const visible = rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                if (!visible || item.disabled) continue;
                return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
              }
              return null;
            }""",
            selector,
        )
    except Exception:
        return None


def _visible_element_center_by_text(page: Any, selector: str, expected_text: str) -> dict[str, float] | None:
    try:
        return page.evaluate(
            """({selector, expectedText}) => {
              const wanted = String(expectedText || '').toLowerCase();
              const items = Array.from(document.querySelectorAll(selector));
              for (const item of items) {
                const text = String(item.innerText || item.textContent || item.title || '').replace(/\s+/g, ' ').trim().toLowerCase();
                if (!text.includes(wanted)) continue;
                const style = window.getComputedStyle(item);
                const rect = item.getBoundingClientRect();
                const visible = rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                if (!visible) continue;
                return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
              }
              return null;
            }""",
            {"selector": selector, "expectedText": expected_text},
        )
    except Exception:
        return None


def _worker_creation_fields_visible(page: Any) -> bool:
    try:
        return bool(
            page.locator("input[name='jform[nif]']").first.is_visible(timeout=1_000)
            and page.locator("input[name='jform[nombre]']").first.is_visible(timeout=1_000)
            and page.locator("input[name='jform[apellidos]']").first.is_visible(timeout=1_000)
        )
    except Exception:
        return False


def _redacted_shape(page: Any) -> dict[str, Any]:
    shape = collect_shape(page)
    return {
        "url": safe_url(page.url),
        "title": str(_safe_title(page))[:160],
        "captcha": bool(shape.get("captcha")),
        "mfa": bool(shape.get("mfa")),
        "human_context_required": bool(shape.get("human_context_required")),
        "post_login_likely": bool(shape.get("post_login_likely")),
        "form_count": len(shape.get("forms") or []),
        "attached_worker_fields": _attached_worker_field_count(page),
        "button_texts": [str(item)[:80] for item in (shape.get("buttons") or [])[:20]],
        "link_texts": [str(item)[:80] for item in (shape.get("links") or [])[:20]],
    }


def _safe_title(page: Any) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def _redacted_page_title(page: Any) -> str:
    if _is_worker_edit_url(page.url):
        return "worker_detail"
    return str(_safe_title(page))[:80]


def _attached_worker_field_count(page: Any) -> int:
    try:
        return int(
            page.locator(
                "input[name='jform[nif]'], input[name='jform[nombre]'], input[name='jform[apellidos]'], "
                "select[name='jform[nacionalidad_trabajador]'], select[name='jform[id_contrato][]'], "
                "select[name='jform[id_puesto]']"
            ).count()
        )
    except Exception:
        return 0


def _select_option(page: Any, selector: str, desired: str, aliases: list[str] | None = None) -> dict[str, Any]:
    locator = page.locator(selector).first
    if locator.count() == 0:
        return {"selector": selector, "ok": False, "reason": "missing_select"}
    options = locator.evaluate(
        """(select) => Array.from(select.options || []).map((option) => ({
          value: option.value || '',
          text: option.textContent || '',
          selected: option.selected
        }))"""
    )
    desired_norms = {_norm(desired), *(_norm(item) for item in (aliases or []))}
    current = next((item for item in options if item.get("selected") and str(item.get("value") or "").strip()), None)
    for item in options:
        value_norm = _norm(str(item.get("value") or ""))
        text_norm = _norm(str(item.get("text") or ""))
        if value_norm in desired_norms or text_norm in desired_norms or any(token and token in text_norm for token in desired_norms):
            _set_select_value(locator, str(item.get("value") or ""))
            return {"selector": selector, "ok": True, "mode": "matched_option"}
    select2_result = _select2_search_and_pick(page, locator, desired)
    if select2_result["ok"]:
        return {"selector": selector, **select2_result}
    if current:
        return {"selector": selector, "ok": True, "mode": "kept_current_value"}
    non_empty = [item for item in options if str(item.get("value") or "").strip()]
    if len(non_empty) == 1:
        _set_select_value(locator, str(non_empty[0].get("value") or ""))
        return {
            "selector": selector,
            "ok": True,
            "mode": "single_available_option",
            "option_text": str(non_empty[0].get("text") or "").strip()[:120],
        }
    return {
        "selector": selector,
        "ok": False,
        "reason": "option_not_matched",
        "desired": _norm(desired),
        "option_count": len(options),
        "option_texts": [str(item.get("text") or "").strip()[:120] for item in non_empty[:8]],
        "select2_result": select2_result,
    }


def _select_author_company(page: Any, selector: str, desired: str, aliases: list[str] | None = None) -> dict[str, Any]:
    locator = page.locator(selector).first
    if locator.count() == 0:
        return {"selector": selector, "ok": False, "reason": "missing_select"}
    options = locator.evaluate(
        """(select) => Array.from(select.options || []).map((option) => ({
          value: option.value || '',
          text: option.textContent || '',
          selected: option.selected
        }))"""
    )
    current = next((item for item in options if item.get("selected") and str(item.get("value") or "").strip()), None)
    if current:
        return {"selector": selector, "ok": True, "mode": "kept_current_value"}
    desired_norms = [_norm(desired), *[_norm(item) for item in (aliases or [])]]
    non_empty = [item for item in options if str(item.get("value") or "").strip()]
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in non_empty:
        option_norm = _norm(str(item.get("text") or ""))
        if any(token and (token in option_norm or option_norm in token) for token in desired_norms):
            _set_select_value(locator, str(item.get("value") or ""))
            return {"selector": selector, "ok": True, "mode": "matched_author_company"}
        scored.append((_token_overlap_score(option_norm, desired_norms), item))
    scored = [item for item in scored if item[0] > 0]
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        _set_select_value(locator, str(scored[0][1].get("value") or ""))
        return {"selector": selector, "ok": True, "mode": "token_matched_author_company", "score": scored[0][0]}
    if len(non_empty) == 1:
        _set_select_value(locator, str(non_empty[0].get("value") or ""))
        return {"selector": selector, "ok": True, "mode": "single_author_company"}
    return {
        "selector": selector,
        "ok": False,
        "reason": "author_company_not_matched",
        "option_count": len(options),
        "option_texts": [str(item.get("text") or "").strip()[:120] for item in non_empty[:8]],
    }


def _token_overlap_score(option_norm: str, desired_norms: list[str]) -> int:
    option_tokens = {token for token in option_norm.split() if len(token) >= 4}
    desired_tokens = {
        token
        for desired_norm in desired_norms
        for token in desired_norm.split()
        if len(token) >= 4
    }
    score = 0
    for option_token in option_tokens:
        for desired_token in desired_tokens:
            if option_token == desired_token or option_token in desired_token or desired_token in option_token:
                score += 1
                break
    return score


def _set_select_value(locator: Any, value: str) -> None:
    if locator.is_visible(timeout=2_000):
        locator.select_option(value=value, timeout=15_000)
        return
    locator.evaluate(
        """(element, value) => {
          element.value = value;
          for (const eventName of ['input', 'change']) {
            const event = document.createEvent('HTMLEvents');
            event.initEvent(eventName, true, false);
            element.dispatchEvent(event);
          }
        }""",
        value,
        timeout=15_000,
    )


def _select2_search_and_pick(page: Any, select_locator: Any, desired: str) -> dict[str, Any]:
    select_id = str(select_locator.get_attribute("id") or "").strip()
    if not select_id:
        return {"ok": False, "reason": "select2_missing_select_id"}
    for container_selector in (f"#s2id_{select_id}", f"div[id='s2id_{select_id}']"):
        container = page.locator(container_selector).first
        try:
            if container.count() == 0:
                continue
            container.click(timeout=10_000)
            search = page.locator(".select2-drop-active input.select2-input, .select2-search input.select2-input").last
            search.fill(desired, timeout=10_000)
            page.wait_for_timeout(2_000)
            normalized_desired = _norm(desired)
            results = page.locator(".select2-result-selectable")
            count = results.count()
            if count == 0:
                return {"ok": False, "reason": "select2_no_results", "mode": "select2_search"}
            chosen = None
            for index in range(count):
                item = results.nth(index)
                text = _norm(item.inner_text(timeout=2_000))
                if normalized_desired in text or text in normalized_desired:
                    chosen = item
                    break
            if chosen is None:
                chosen = results.first
            chosen.click(timeout=10_000)
            page.wait_for_timeout(1_000)
            value = select_locator.input_value(timeout=5_000)
            if str(value or "").strip():
                return {"ok": True, "mode": "select2_search"}
            return {"ok": False, "reason": "select2_value_empty_after_pick", "mode": "select2_search"}
        except Exception as exc:
            return {"ok": False, "reason": f"select2_error:{type(exc).__name__}", "mode": "select2_search"}
    input_fallback = _select2_input_fallback(page, select_locator, select_id, desired)
    if input_fallback["ok"]:
        return input_fallback
    return {
        "ok": False,
        "reason": "select2_container_not_found",
        "mode": "select2_search",
        "input_fallback": input_fallback,
    }


def _select2_input_fallback(page: Any, select_locator: Any, select_id: str, desired: str) -> dict[str, Any]:
    fallback_by_select_id = {
        "jform_id_contrato": "#s2id_autogen8",
        "jform_nacionalidad_trabajador": "#s2id_autogen5",
        "jform_pais": "#s2id_autogen4",
        "jform_id_puesto": "#s2id_autogen7",
    }
    input_selector = fallback_by_select_id.get(select_id)
    if not input_selector:
        return {"ok": False, "reason": "select2_input_fallback_not_configured", "mode": "select2_input"}
    search = page.locator(input_selector).first
    try:
        if search.count() == 0 or not search.is_visible(timeout=2_000):
            return {"ok": False, "reason": "select2_input_not_visible", "mode": "select2_input"}
        search.click(timeout=10_000)
        search.fill(desired, timeout=10_000)
        page.wait_for_timeout(2_000)
        results = page.locator(".select2-result-selectable, li.select2-result")
        if results.count() > 0:
            results.first.click(timeout=10_000)
        else:
            search.press("Enter", timeout=10_000)
        page.wait_for_timeout(1_000)
        value = select_locator.input_value(timeout=5_000)
        if str(value or "").strip():
            return {"ok": True, "mode": "select2_input", "input_selector": input_selector}
        return {"ok": False, "reason": "select2_input_value_empty_after_pick", "mode": "select2_input"}
    except Exception as exc:
        return {"ok": False, "reason": f"select2_input_error:{type(exc).__name__}", "mode": "select2_input"}


def _required_selects_have_values(page: Any) -> bool:
    selectors = [
        "select[name='jform[nacionalidad_trabajador]']",
        "select[name='jform[id_contrato][]']",
        "select[name='jform[id_puesto]']",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() == 0:
            return False
        value = locator.input_value(timeout=5_000)
        if not str(value or "").strip():
            return False
    return True


def _status(
    args: argparse.Namespace,
    state: str,
    entry_url: str,
    message: str,
    session: Any,
    extra: dict[str, Any] | None = None,
) -> None:
    payload_extra = {"live_helper_version": HELPER_VERSION}
    if extra:
        payload_extra.update(extra)
    write_status(
        args.status_file,
        state=state,
        platform_label=args.platform_label,
        entry_url=entry_url,
        message=message,
        extra=payload_extra,
        session=session,
    )


def _worker_summary(args: argparse.Namespace) -> dict[str, str]:
    return {
        "worker_ref": args.worker_ref,
        "identifier_last4": args.identifier_last4 or args.identifier_value[-4:],
        "first_name_present": str(bool(args.first_name)),
        "last_name_present": str(bool(args.last_name)),
        "nationality": args.nationality,
        "contract_type": args.contract_type,
        "work_position": args.work_position,
    }


def _load_worker_payload(args: argparse.Namespace, payload_file: Path) -> None:
    payload = json.loads(payload_file.read_text(encoding="utf-8"))
    for key in (
        "worker_ref",
        "identifier_value",
        "identifier_last4",
        "first_name",
        "last_name",
        "nationality",
        "contract_type",
        "work_position",
    ):
        value = payload.get(key)
        if value is not None:
            setattr(args, key.replace("-", "_"), str(value))


def _print_result(
    status: str,
    *,
    external_write_executed: bool,
    post_write_read_confirmed: bool,
    status_file: Path | None = None,
) -> None:
    payload = {
        "status": status,
        "external_write_executed": external_write_executed,
        "post_write_read_confirmed": post_write_read_confirmed,
        "status_file": str(status_file) if status_file else None,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(payload, ensure_ascii=False))


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    ascii_value = re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value).strip().lower()
    return re.sub(r"\s+", " ", ascii_value)


if __name__ == "__main__":
    raise SystemExit(main())
