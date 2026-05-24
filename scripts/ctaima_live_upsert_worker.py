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
    open_worker_add_form_from_dom_link,
    prepare_session_profile,
    redact,
    safe_url,
    write_status,
)

HELPER_VERSION = "ctaima_live_upsert_worker_v1"
OBSERVED_WORKER_FIELD_NAMES = {
    "TipoIPF",
    "DNI",
    "NSS",
    "Nombre1",
    "Apellido1",
    "Apellido2",
    "email",
    "phone",
    "Puesto",
    "Activo",
    "TipoTRAB",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorized live worker upsert for CTAIMA CAE.")
    parser.add_argument("--entry-url", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--secret-ref", default="")
    parser.add_argument("--platform-label", default="CTAIMA / CTAIMA CAE")
    parser.add_argument("--target-context", default="")
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--session-profile-dir", type=Path, required=True)
    parser.add_argument("--payload-file", type=Path, default=None)
    parser.add_argument("--worker-ref", default="")
    parser.add_argument("--identifier-type", default="")
    parser.add_argument("--identifier-value", default="")
    parser.add_argument("--identifier-last4", default="")
    parser.add_argument("--social-security-number", default="")
    parser.add_argument("--social-security-last4", default="")
    parser.add_argument("--first-name", default="")
    parser.add_argument("--last-name", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--phone", default="")
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
        for name in (
            "worker_ref",
            "identifier_value",
            "social_security_number",
            "first_name",
            "last_name",
            "email",
            "phone",
            "contract_type",
            "work_position",
        )
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
    _status(args, "launching_browser", args.entry_url, "Launching visible browser for authorized CTAIMA live write.", session_profile)
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
                    "external_worker_id": _external_worker_id_from_readback(readback),
                },
            )
            result = {
                "status": state,
                "external_write_executed": False,
                "post_write_read_confirmed": readback["confirmed"],
                "external_worker_id": _external_worker_id_from_readback(readback),
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
            external_worker_id=result.get("external_worker_id"),
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
            _status(args, "session_resumed", page.url, "Existing CTAIMA session reused.", browser_session)
            return True
        if _session_conflict_visible(page):
            _status(
                args,
                "human_session_conflict_required",
                page.url,
                "CTAIMA reports an active duplicate session. Resolve it in the visible browser before the write continues.",
                browser_session,
            )
            time.sleep(2)
            continue
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
        _status(args, "waiting_for_login_form", page.url, "Waiting for login form or human control.", browser_session)
        time.sleep(2)
    return False


def _open_fill_and_submit(page: Any, args: argparse.Namespace, deadline: float, browser_session: Any) -> dict[str, Any]:
    while time.monotonic() < deadline:
        shape = collect_shape(page)
        if _session_conflict_visible(page):
            _status(args, "human_session_conflict_required", page.url, "Resolve CTAIMA duplicate-session prompt in the visible browser.", browser_session)
            time.sleep(2)
            continue
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
        external_worker_id = _external_worker_id_from_readback(preflight_readback)
        _status(
            args,
            "already_exists_external",
            page.url,
            "Worker already exists in CTAIMA; duplicate live registration was prevented.",
            browser_session,
            extra={
                "worker": _worker_summary(args),
                "external_write_executed": False,
                "post_write_read_confirmed": True,
                "post_write_readback": preflight_readback,
                "external_worker_id": external_worker_id,
            },
        )
        return {
            "status": "already_exists_external",
            "external_write_executed": False,
            "post_write_read_confirmed": True,
            "external_worker_id": external_worker_id,
            "exit_code": 0,
        }

    if not _open_worker_add_form(page, args, deadline, browser_session):
        _status(
            args,
            "worker_form_not_found",
            page.url,
            "CTAIMA worker add form was not found through captured DOM links.",
            browser_session,
            extra={"page": _redacted_page(page)},
        )
        return {"status": "worker_form_not_found", "external_write_executed": False, "exit_code": 5}

    fill_result = _fill_worker_form(page, args)
    unresolved = [item for item in fill_result["field_results"] if not item.get("ok")]
    if unresolved:
        _status(
            args,
            "human_selection_required",
            page.url,
            "Worker form was filled where mapping is approved. Complete unresolved CTAIMA selections in the visible browser.",
            browser_session,
            extra={
                "worker": _worker_summary(args),
                "unresolved_fields": unresolved,
                "form_readiness": _worker_form_readiness(page),
                "observed_field_names": sorted(OBSERVED_WORKER_FIELD_NAMES),
            },
        )
        while time.monotonic() < deadline and not _worker_form_required_values_ready(page):
            time.sleep(2)
        if not _worker_form_required_values_ready(page):
            return {"status": "human_selection_required", "external_write_executed": False, "exit_code": 6}

    _status(
        args,
        "ready_to_submit",
        page.url,
        "CTAIMA worker form is filled. Submitting because live authorization was provided.",
        browser_session,
        extra={
            "worker": _worker_summary(args),
            "submit": bool(args.submit),
            "form_readiness": _worker_form_readiness(page),
            "fill_result": fill_result,
            "submit_controls": _submit_control_candidates(page),
        },
    )
    if not args.submit:
        return {"status": "ready_to_submit", "external_write_executed": False, "exit_code": 7}

    before_url = safe_url(page.url)
    form_readiness_before_click = _worker_form_readiness(page)
    submit_events: list[dict[str, Any]] = []
    _attach_submit_tracker(page, submit_events)
    if not _click_accept_worker_form(page):
        _status(
            args,
            "submit_button_not_ready",
            page.url,
            "CTAIMA worker form was filled but the observed submit button was not ready.",
            browser_session,
            extra={"worker": _worker_summary(args), "form_readiness": _worker_form_readiness(page)},
        )
        return {"status": "submit_button_not_ready", "external_write_executed": False, "exit_code": 9}
    try:
        page.wait_for_load_state("networkidle", timeout=20_000)
    except PlaywrightTimeoutError:
        pass
    time.sleep(3)
    after_url = safe_url(page.url)
    submit_events_after_click = list(submit_events)
    readback = _verify_worker_readback(page, args, deadline, browser_session, max_seconds=120)
    external_worker_id = _external_worker_id_from_readback(readback)
    submit_observed = _submit_request_observed(submit_events_after_click) or readback["confirmed"]
    if not submit_observed:
        _status(
            args,
            "submit_not_observed",
            page.url,
            "No CTAIMA worker submit request or posterior readback was observed after clicking the platform button.",
            browser_session,
            extra={
                "worker": _worker_summary(args),
                "before_url": before_url,
                "after_url": after_url,
                "submit_events": submit_events_after_click[-8:],
                "external_write_executed": False,
                "post_write_read_confirmed": False,
                "form_readiness_before_click": form_readiness_before_click,
                "form_readiness_after_click": _worker_form_readiness(page),
                "page_alerts_after_click": _page_alerts(page),
                "submit_controls": _submit_control_candidates(page),
            },
        )
        return {"status": "submit_not_observed", "external_write_executed": False, "exit_code": 10}

    state = "confirmed_external" if readback["confirmed"] else "submitted_external_pending_readback"
    _status(
        args,
        state,
        page.url,
        "CTAIMA submit executed and posterior readback was evaluated.",
        browser_session,
        extra={
            "worker": _worker_summary(args),
            "before_url": before_url,
            "after_url": after_url,
            "submit_events": submit_events_after_click[-8:],
            "external_write_executed": True,
            "post_write_read_confirmed": readback["confirmed"],
            "post_write_readback": readback,
            "external_worker_id": external_worker_id,
        },
    )
    return {
        "status": state,
        "external_write_executed": True,
        "post_write_read_confirmed": readback["confirmed"],
        "external_worker_id": external_worker_id,
        "exit_code": 0,
    }


def _open_worker_add_form(page: Any, args: argparse.Namespace, deadline: float, browser_session: Any) -> bool:
    if _worker_form_visible(page):
        return True
    if not _open_worker_list(page, args, deadline, browser_session, max_seconds=30):
        return False
    action = open_worker_add_form_from_dom_link(page)
    if action.get("ok"):
        _status(args, "worker_add_form_opened", page.url, "CTAIMA worker add form opened through server-issued DOM link.", browser_session, extra={"navigation": action})
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(1)
    else:
        _status(args, "worker_add_form_link_missing", page.url, "CTAIMA worker add link was not found in the current DOM.", browser_session, extra={"navigation": action})
    return _worker_form_visible(page)


def _verify_worker_readback(
    page: Any,
    args: argparse.Namespace,
    deadline: float,
    browser_session: Any,
    *,
    max_seconds: int = 120,
) -> dict[str, Any]:
    read_deadline = min(deadline, time.monotonic() + max_seconds)
    checked_pages: list[dict[str, Any]] = []
    attempts = 0
    _open_worker_list(page, args, deadline, browser_session, max_seconds=25)
    while time.monotonic() < read_deadline and attempts < 6:
        attempts += 1
        shape = collect_shape(page)
        if _session_conflict_visible(page):
            _status(args, "human_session_conflict_required", page.url, "Resolve CTAIMA duplicate-session prompt before readback continues.", browser_session)
            time.sleep(2)
            continue
        if shape.get("captcha") or shape.get("mfa"):
            _status(args, "human_control_required", page.url, "Resolve captcha/MFA before readback continues.", browser_session)
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
                "matched_worker": match.get("matched_worker"),
                "message": "Posterior readback found the worker using redacted identifier/name signals.",
            }
        if _filter_worker_list_by_identifier(page, args):
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            time.sleep(2)
            continue
        time.sleep(2)
    return {
        "confirmed": False,
        "method": "ctaima_worker_list_visible_text",
        "checked_pages": checked_pages[-4:],
        "signals": {
            "identifier_full_seen": False,
            "identifier_last4_seen": False,
            "name_seen": False,
        },
        "message": "Posterior readback did not find a matching worker before timeout.",
    }


def _open_worker_list(
    page: Any,
    args: argparse.Namespace,
    deadline: float,
    browser_session: Any,
    *,
    max_seconds: int = 45,
) -> bool:
    list_deadline = min(deadline, time.monotonic() + max_seconds)
    navigation_labels = (
        "Coordinacion",
        "Gestionar trabajadores",
        "Gestion Usuarios",
        "Trabajadores",
        "Mis Recursos",
        "Como crear trabajadores",
        "Alta o edicion trabajador",
    )
    attempted_labels: set[str] = set()
    while time.monotonic() < list_deadline:
        if _is_ctaima_worker_list_url(page.url) or _worker_list_visible(page):
            return True
        if _session_conflict_visible(page):
            _status(args, "human_session_conflict_required", page.url, "Resolve CTAIMA duplicate-session prompt before worker list navigation.", browser_session)
            time.sleep(2)
            continue
        shape = collect_shape(page)
        if shape.get("captcha") or shape.get("mfa"):
            _status(args, "human_control_required", page.url, "Resolve captcha/MFA before worker list navigation.", browser_session)
            time.sleep(2)
            continue
        if shape.get("human_context_required"):
            selection = auto_select_context_if_unique(page, args.target_context)
            if selection.get("ok"):
                _status(
                    args,
                    "context_selected_for_readback",
                    page.url,
                    f"Context selected for CTAIMA readback: {selection.get('matched_text')}.",
                    browser_session,
                    extra={"context_selection": selection},
                )
                time.sleep(2)
                continue
            _status(
                args,
                "human_context_required",
                page.url,
                "Select the authorized CTAIMA company/context before worker list readback.",
                browser_session,
                extra={"context_selection": selection},
            )
            time.sleep(2)
            continue
        if _goto_server_issued_worker_list(page):
            return True
        if _click_cancel_to_list(page):
            time.sleep(1)
            continue
        next_label = next((label for label in navigation_labels if label not in attempted_labels), "")
        if next_label:
            attempted_labels.add(next_label)
        if next_label and _click_visible_text(page, (next_label,)):
            _status(
                args,
                "worker_list_navigation_click",
                page.url,
                "CTAIMA worker-list navigation click executed from observed text.",
                browser_session,
                extra={"navigation_label": next_label},
            )
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeoutError:
                pass
            time.sleep(2)
            continue
        if len(attempted_labels) >= len(navigation_labels):
            return False
        time.sleep(1)
    return _is_ctaima_worker_list_url(page.url) or _worker_list_visible(page)


def _goto_server_issued_worker_list(page: Any) -> bool:
    try:
        href = page.evaluate(
            """() => {
              const current = new URL(window.location.href);
              const host = current.hostname.toLowerCase();
              if (!host.endsWith('ctaimacae.net')) return '';
              for (const anchor of Array.from(document.querySelectorAll('a[href]'))) {
                let url;
                try { url = new URL(anchor.getAttribute('href') || '', window.location.href); }
                catch { continue; }
                const path = url.pathname.toLowerCase();
                if (path.endsWith('/trabajadores/list.asp') || (path.includes('/trabajadores/') && path.endsWith('/list.asp'))) {
                  return url.href;
                }
              }
              return '';
            }"""
        )
    except Exception:
        return False
    if not href:
        return False
    try:
        page.goto(str(href), wait_until="domcontentloaded", timeout=30_000)
        return _is_ctaima_worker_list_url(page.url) or _worker_list_visible(page)
    except Exception:
        return False


def _fill_worker_form(page: Any, args: argparse.Namespace) -> dict[str, Any]:
    apellido1, apellido2, split_mode = _split_last_name(args.last_name)
    results = [
        _set_identifier_type(page, args),
        _fill_text_by_name(page, "DNI", args.identifier_value),
        _fill_text_by_name(page, "NSS", args.social_security_number),
        _fill_text_by_name(page, "Nombre1", args.first_name),
        _fill_text_by_name(page, "Apellido1", apellido1),
        _fill_text_by_name(page, "Apellido2", apellido2) if apellido2 else {"field": "Apellido2", "ok": True, "mode": "left_blank"},
        _fill_text_by_name(page, "email", args.email),
        _fill_text_by_name(page, "phone", args.phone),
        _fill_text_by_name(page, "Puesto", args.work_position),
        _select_by_name(page, "Activo", "SI", aliases=["si", "sí", "yes", "true"]),
        _set_worker_type(page, args.contract_type),
        _set_radio_checked(page, "AdjuntoNo"),
        _select_context_role_checkboxes(page, args.target_context, args.contract_type),
    ]
    return {
        "field_results": results,
        "surname_split_mode": split_mode,
        "observed_field_names": sorted(OBSERVED_WORKER_FIELD_NAMES),
    }


def _set_identifier_type(page: Any, args: argparse.Namespace) -> dict[str, Any]:
    identifier_type = _norm(args.identifier_type or "")
    desired = "NIF"
    aliases = ["nif", "nie", "nacional espana", "nacional espana nif nie", "nacional espana nif"]
    if "passport" in identifier_type or "pasaporte" in identifier_type:
        desired = "Pasaporte"
        aliases = ["pasaporte", "passport"]
    return _select_by_name(page, "TipoIPF", desired, aliases=aliases, keep_current=True)


def _set_worker_type(page: Any, contract_type: str) -> dict[str, Any]:
    aliases = ["trabajador por cuenta ajena", "cuenta ajena"]
    if "autonom" in _norm(contract_type):
        aliases = ["autonomo", "autonomo/a", "trabajador autonomo"]
    return _select_by_name(page, "TipoTRAB", contract_type, aliases=aliases, keep_current=True)


def _fill_text_by_name(page: Any, name: str, value: str) -> dict[str, Any]:
    locator = page.locator(f"input[name='{name}'], textarea[name='{name}']").first
    try:
        if locator.count() == 0:
            return {"field": name, "ok": False, "reason": "missing_field"}
        if not locator.is_visible(timeout=2_000):
            return {"field": name, "ok": False, "reason": "field_not_visible"}
        locator.fill(value, timeout=10_000)
        return {"field": name, "ok": True, "mode": "filled_observed_name"}
    except Exception as exc:
        return {"field": name, "ok": False, "reason": type(exc).__name__}


def _select_by_name(
    page: Any,
    name: str,
    desired: str,
    *,
    aliases: list[str] | None = None,
    keep_current: bool = False,
) -> dict[str, Any]:
    locator = page.locator(f"select[name='{name}']").first
    try:
        if locator.count() == 0:
            return {"field": name, "ok": False, "reason": "missing_select"}
        options = locator.evaluate(
            """(select) => Array.from(select.options || []).map((option) => ({
              value: option.value || '',
              text: option.textContent || '',
              selected: option.selected
            }))"""
        )
        current = next((item for item in options if item.get("selected") and str(item.get("value") or "").strip()), None)
        if keep_current and current:
            return {"field": name, "ok": True, "mode": "kept_current_value"}
        desired_norms = {_norm(desired), *(_norm(item) for item in (aliases or []))}
        for item in options:
            value = str(item.get("value") or "")
            text = str(item.get("text") or "")
            value_norm = _norm(value)
            text_norm = _norm(text)
            if value_norm in desired_norms or text_norm in desired_norms or any(token and token in text_norm for token in desired_norms):
                locator.select_option(value=value, timeout=10_000)
                return {"field": name, "ok": True, "mode": "matched_option"}
        non_empty = [item for item in options if str(item.get("value") or "").strip()]
        if len(non_empty) == 1:
            locator.select_option(value=str(non_empty[0].get("value") or ""), timeout=10_000)
            return {"field": name, "ok": True, "mode": "single_available_option"}
        if current:
            return {"field": name, "ok": True, "mode": "kept_current_value_after_no_match"}
        return {
            "field": name,
            "ok": False,
            "reason": "option_not_matched",
            "desired": _norm(desired),
            "option_count": len(options),
            "option_texts": [redact(str(item.get("text") or "").strip())[:120] for item in non_empty[:8]],
        }
    except Exception as exc:
        return {"field": name, "ok": False, "reason": type(exc).__name__}


def _set_radio_checked(page: Any, element_id: str) -> dict[str, Any]:
    locator = page.locator(f"#{element_id}").first
    try:
        if locator.count() == 0:
            return {"field": element_id, "ok": True, "mode": "optional_missing"}
        locator.check(timeout=5_000)
        return {"field": element_id, "ok": True, "mode": "checked"}
    except Exception:
        try:
            locator.evaluate(
                """(element) => {
                  element.checked = true;
                  element.dispatchEvent(new Event('input', { bubbles: true }));
                  element.dispatchEvent(new Event('change', { bubbles: true }));
                }""",
                timeout=5_000,
            )
            return {"field": element_id, "ok": True, "mode": "checked_by_dom_event"}
        except Exception as exc:
            return {"field": element_id, "ok": False, "reason": type(exc).__name__}


def _select_context_role_checkboxes(page: Any, target_context: str, contract_type: str) -> dict[str, Any]:
    roles = _visible_client_role_checkboxes(page)
    if not roles:
        return {"field": "client_role_checkboxes", "ok": True, "mode": "not_present"}
    already_checked = [role for role in roles if role.get("checked")]
    if already_checked:
        select_results = [
            _select_by_name(page, str(role.get("role_select_name") or ""), contract_type, aliases=["trabajador por cuenta ajena", "cuenta ajena"], keep_current=True)
            for role in already_checked
            if role.get("role_select_name")
        ]
        return {
            "field": "client_role_checkboxes",
            "ok": True,
            "mode": "kept_existing_checked_roles",
            "checked_count": len(already_checked),
            "select_results": select_results,
        }
    matched = _roles_matching_context(roles, target_context)
    if not matched:
        return {
            "field": "client_role_checkboxes",
            "ok": False,
            "reason": "client_role_mapping_required",
            "role_labels": [redact(str(role.get("label") or ""))[:120] for role in roles],
            "target_context_present": bool(target_context.strip()),
        }
    checked: list[dict[str, Any]] = []
    for role in matched:
        checkbox_result = _check_by_id_or_name(page, str(role.get("id") or ""), str(role.get("name") or ""))
        checked.append(
            {
                "label": redact(str(role.get("label") or ""))[:120],
                "checkbox": checkbox_result,
                "match_token": role.get("match_token"),
            }
        )
    try:
        page.wait_for_timeout(1_500)
    except Exception:
        pass
    select_results: list[dict[str, Any]] = []
    for role in matched:
        if role.get("role_select_name"):
            select_results.append(
                _select_by_name(
                    page,
                    str(role.get("role_select_name") or ""),
                    contract_type,
                    aliases=["trabajador por cuenta ajena", "cuenta ajena"],
                    keep_current=True,
                )
            )
    failed_checks = [item for item in checked if not item.get("checkbox", {}).get("ok")]
    failed_selects = [item for item in select_results if not item.get("ok")]
    return {
        "field": "client_role_checkboxes",
        "ok": not failed_checks and not failed_selects,
        "mode": "matched_target_context_roles",
        "checked_roles": checked,
        "select_results": select_results,
    }


def _visible_client_role_checkboxes(page: Any) -> list[dict[str, Any]]:
    try:
        result = page.evaluate(
            """() => {
              const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              const labelFor = (input) => {
                const labels = [];
                if (input.id) {
                  const byFor = document.querySelector(`label[for="${input.id.replace(/"/g, '\\"')}"]`);
                  if (byFor) labels.push(byFor.innerText || byFor.textContent || '');
                }
                const parent = input.closest('label');
                if (parent) labels.push(parent.innerText || parent.textContent || '');
                const row = input.closest('tr, .row, div, p');
                if (row) {
                  const candidates = Array.from(row.querySelectorAll('label, span, td, div'))
                    .map((item) => clean(item.innerText || item.textContent || ''))
                    .filter(Boolean);
                  labels.push(...candidates);
                }
                return clean(labels.find((item) => item && item.length <= 180) || input.getAttribute('title') || input.getAttribute('aria-label') || input.id || input.name || '');
              };
              return Array.from(document.querySelectorAll("input[type='checkbox'][name^='checkbox'], input[type='checkbox'][id^='checkbox']"))
                .filter(visible)
                .map((box) => {
                  const name = box.getAttribute('name') || '';
                  const id = box.getAttribute('id') || '';
                  const suffix = ((name || id).match(/(\\d+)/) || [])[1] || '';
                  return {
                    id,
                    name,
                    checked: Boolean(box.checked),
                    label: labelFor(box),
                    role_select_name: suffix ? `TipoTRAB${suffix}` : ''
                  };
                });
            }"""
        )
    except Exception:
        return []
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def _roles_matching_context(roles: list[dict[str, Any]], target_context: str) -> list[dict[str, Any]]:
    context_tokens = [
        token
        for token in _norm(target_context).split()
        if len(token) >= 4 and token not in {"grupo", "empresa", "spain", "sucursal", "espana"}
    ]
    matched: list[dict[str, Any]] = []
    for role in roles:
        label_norm = _norm(str(role.get("label") or ""))
        for token in context_tokens:
            variants = {token, token.replace("b", "v"), token.replace("v", "b")}
            if any(variant and (variant in label_norm or label_norm in variant) for variant in variants):
                role = dict(role)
                role["match_token"] = token
                matched.append(role)
                break
    return matched


def _check_by_id_or_name(page: Any, element_id: str, name: str) -> dict[str, Any]:
    selectors = []
    if element_id:
        selectors.append(f"#{element_id}")
    if name:
        selectors.append(f"input[name='{name}']")
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue
            locator.check(timeout=5_000)
            return {"ok": True, "selector_kind": "id" if selector.startswith("#") else "name"}
        except Exception:
            try:
                locator.evaluate(
                    """(element) => {
                      element.checked = true;
                      element.dispatchEvent(new Event('input', { bubbles: true }));
                      element.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    timeout=5_000,
                )
                return {"ok": True, "selector_kind": "dom_event"}
            except Exception:
                continue
    return {"ok": False, "reason": "checkbox_not_found_or_not_checkable"}


def _worker_form_visible(page: Any) -> bool:
    try:
        return bool(
            page.locator("input[name='DNI']").first.is_visible(timeout=1_000)
            and page.locator("input[name='Nombre1']").first.is_visible(timeout=1_000)
            and page.locator("input[name='Apellido1']").first.is_visible(timeout=1_000)
        )
    except Exception:
        return False


def _worker_form_required_values_ready(page: Any) -> bool:
    readiness = _worker_form_readiness(page)
    required = (
        "dni_has_value",
        "nss_has_value",
        "first_name_has_value",
        "last_name_has_value",
        "email_has_value",
        "phone_has_value",
        "position_has_value",
        "worker_type_has_value",
    )
    if not all(bool(readiness.get(key)) for key in required):
        return False
    checkbox_count = int(readiness.get("client_role_checkbox_count") or 0)
    if checkbox_count > 0 and int(readiness.get("client_role_checked_count") or 0) == 0:
        return False
    return True


def _worker_form_readiness(page: Any) -> dict[str, Any]:
    try:
        return dict(
            page.evaluate(
                """() => {
                  const hasValue = (selector) => {
                    const item = document.querySelector(selector);
                    return Boolean(item && String(item.value || '').trim());
                  };
                  const selectedCount = (selector) => {
                    const item = document.querySelector(selector);
                    if (!item || item.tagName !== 'SELECT') return 0;
                    return Array.from(item.options || []).filter((option) => option.selected && String(option.value || '').trim()).length;
                  };
                  const roleBoxes = Array.from(document.querySelectorAll("input[type='checkbox'][name^='checkbox']"));
                  const buttonTexts = Array.from(document.querySelectorAll("input[type='submit'], button, a"))
                    .map((item) => String(item.value || item.innerText || item.textContent || item.title || '').replace(/\\s+/g, ' ').trim())
                    .filter(Boolean)
                    .slice(0, 12);
                  return {
                    dni_has_value: hasValue("input[name='DNI']"),
                    nss_has_value: hasValue("input[name='NSS']"),
                    first_name_has_value: hasValue("input[name='Nombre1']"),
                    last_name_has_value: hasValue("input[name='Apellido1']"),
                    second_last_name_has_value: hasValue("input[name='Apellido2']"),
                    email_has_value: hasValue("input[name='email']"),
                    phone_has_value: hasValue("input[name='phone']"),
                    position_has_value: hasValue("input[name='Puesto']"),
                    active_has_value: hasValue("select[name='Activo']"),
                    worker_type_has_value: hasValue("select[name='TipoTRAB']"),
                    worker_type_selected_count: selectedCount("select[name='TipoTRAB']"),
                    client_role_checkbox_count: roleBoxes.length,
                    client_role_checked_count: roleBoxes.filter((item) => item.checked).length,
                    submit_button_candidates: buttonTexts
                  };
                }"""
            )
        )
    except Exception as exc:
        return {"error": type(exc).__name__}


def _page_alerts(page: Any) -> list[str]:
    try:
        result = page.evaluate(
            """() => {
              const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              return Array.from(document.querySelectorAll(".alert,.message,.warning,.error,[class*=alert],[class*=error],[id*=system-message],.validation-summary-errors"))
                .filter(visible)
                .map((item) => clean(item.innerText || item.textContent || ''))
                .filter(Boolean)
                .slice(0, 8);
            }"""
        )
    except Exception:
        return []
    if not isinstance(result, list):
        return []
    return [redact(str(item))[:300] for item in result]


def _submit_control_candidates(page: Any) -> list[dict[str, Any]]:
    try:
        result = page.evaluate(
            """() => {
              const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
              const normalize = (value) => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              return Array.from(document.querySelectorAll("input[type='submit'], input[type='button'], button, a[onclick], a[href]"))
                .filter(visible)
                .map((item) => {
                  const text = clean(item.value || item.innerText || item.textContent || item.title || item.getAttribute('aria-label') || '');
                  const form = item.closest('form');
                  return {
                    tag: item.tagName.toLowerCase(),
                    type: item.getAttribute('type') || '',
                    id: item.getAttribute('id') || '',
                    name: item.getAttribute('name') || '',
                    text,
                    matches_submit_label: /^(aceptar|guardar|alta|crear|anadir|insertar)/.test(normalize(text)) && !/cancelar/.test(normalize(text)),
                    onclick_present: Boolean(item.getAttribute('onclick')),
                    href_present: Boolean(item.getAttribute('href')),
                    form_method: form ? (form.getAttribute('method') || '') : '',
                    form_action_path: (() => {
                      if (!form) return '';
                      try { return new URL(form.getAttribute('action') || window.location.href, window.location.href).pathname; }
                      catch { return ''; }
                    })()
                  };
                })
                .filter((item) => item.matches_submit_label || item.text.toLowerCase().includes('aceptar') || item.text.toLowerCase().includes('guardar'))
                .slice(0, 12);
            }"""
        )
    except Exception:
        return []
    if not isinstance(result, list):
        return []
    cleaned = []
    for item in result:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "tag": str(item.get("tag") or "")[:40],
                "type": str(item.get("type") or "")[:40],
                "id": redact(str(item.get("id") or ""))[:120],
                "name": redact(str(item.get("name") or ""))[:120],
                "text": redact(str(item.get("text") or ""))[:160],
                "matches_submit_label": bool(item.get("matches_submit_label")),
                "onclick_present": bool(item.get("onclick_present")),
                "href_present": bool(item.get("href_present")),
                "form_method": str(item.get("form_method") or "")[:20],
                "form_action_path": str(item.get("form_action_path") or "")[:240],
            }
        )
    return cleaned


def _click_accept_worker_form(page: Any) -> bool:
    if not _worker_form_visible(page):
        return False
    for selector in (
        "form:has(input[name='DNI']) input[type='submit'][value='Aceptar']",
        "form:has(input[name='DNI']) input[type='button'][value='Aceptar']",
        "form:has(input[name='DNI']) button:has-text('Aceptar')",
        "input[type='submit'][value='Aceptar']",
        "input[type='button'][value='Aceptar']",
        "button:has-text('Aceptar')",
    ):
        locator = page.locator(selector).first
        try:
            if locator.count() == 0 or not locator.is_visible(timeout=1_000):
                continue
            if locator.is_disabled(timeout=1_000):
                return False
            locator.click(timeout=10_000)
            return True
        except Exception:
            continue
    try:
        return bool(
            page.evaluate(
                """() => {
                  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                  const normalize = (value) => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
                  };
                  const form = document.querySelector("input[name='DNI']")?.closest('form') || document;
                  const candidates = Array.from(form.querySelectorAll("input[type='submit'], input[type='button'], button, a[onclick], a[href]"))
                    .filter(visible)
                    .filter((element) => {
                      const text = normalize(element.value || element.innerText || element.textContent || element.title || element.getAttribute('aria-label') || '');
                      return /^(aceptar|guardar|alta|crear|anadir|insertar)/.test(text) && !/cancelar/.test(text);
                    });
                  if (!candidates.length) return false;
                  candidates[0].click();
                  return true;
                }"""
            )
        )
    except Exception:
        return False


def _attach_submit_tracker(page: Any, submit_events: list[dict[str, Any]]) -> None:
    def on_request(request: Any) -> None:
        url = str(request.url or "")
        submit_flag = _is_worker_submit_url(url, str(request.method or ""))
        if not submit_flag:
            return
        submit_events.append(
            {
                "method": str(request.method or ""),
                "url": safe_url(url),
                "is_worker_submit": submit_flag,
            }
        )

    page.on("request", on_request)


def _submit_request_observed(submit_events: list[dict[str, Any]]) -> bool:
    return any(bool(event.get("is_worker_submit")) for event in submit_events)


def _is_worker_submit_url(value: str, method: str) -> bool:
    if method.upper() != "POST":
        return False
    try:
        from urllib.parse import urlparse

        parsed = urlparse(value)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    return host.endswith("ctaimacae.net") and path.endswith("/trabajadores/update.asp")


def _worker_match_on_visible_page(page: Any, args: argparse.Namespace) -> dict[str, Any]:
    rows = _extract_ctaima_worker_rows(page)
    identifier_norm = _norm(args.identifier_value)
    last4 = (args.identifier_last4 or args.identifier_value[-4:]).upper()
    first_norm = _norm(args.first_name)
    last_tokens = [token for token in _norm(args.last_name).split() if len(token) >= 3]
    for row in rows:
        row_identifier_norm = _norm(str(row.get("identifier_value") or ""))
        row_last4 = str(row.get("identifier_last4") or "").upper()
        row_name_norm = _norm(str(row.get("display_name") or ""))
        identifier_full_seen = bool(identifier_norm and identifier_norm == row_identifier_norm)
        identifier_last4_seen = bool(last4 and last4 == row_last4)
        name_seen = bool(first_norm and first_norm in row_name_norm and all(token in row_name_norm for token in last_tokens[:2]))
        if identifier_full_seen or (identifier_last4_seen and name_seen):
            redacted_row = {
                "display_name": redact(str(row.get("display_name") or "")),
                "identifier_last4": row_last4,
                "work_position": redact(str(row.get("work_position") or "")),
                "external_worker_id": row.get("external_worker_id"),
            }
            return {
                "confirmed": True,
                "method": "ctaima_worker_table_row",
                "signals": {
                    "identifier_full_seen": identifier_full_seen,
                    "identifier_last4_seen": identifier_last4_seen,
                    "name_seen": name_seen,
                },
                "matched_worker": redacted_row,
                "page": _readback_page_summary(page),
            }
    try:
        visible_text = page.locator("body").inner_text(timeout=5_000)
    except Exception:
        visible_text = ""
    normalized_text = _norm(visible_text)
    identifier_full_seen = bool(identifier_norm and identifier_norm in normalized_text)
    identifier_last4_seen = bool(last4 and _norm(last4) in normalized_text)
    name_seen = bool(first_norm and first_norm in normalized_text and all(token in normalized_text for token in last_tokens[:2]))
    confirmed = identifier_full_seen or (identifier_last4_seen and name_seen)
    return {
        "confirmed": confirmed,
        "method": "ctaima_visible_text",
        "signals": {
            "identifier_full_seen": identifier_full_seen,
            "identifier_last4_seen": identifier_last4_seen,
            "name_seen": name_seen,
        },
        "page": _readback_page_summary(page),
    }


def _extract_ctaima_worker_rows(page: Any) -> list[dict[str, Any]]:
    try:
        result = page.evaluate(
            """() => {
              const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              const rows = [];
              for (const row of Array.from(document.querySelectorAll('tr')).filter(visible).slice(0, 500)) {
                const cells = Array.from(row.querySelectorAll('td, th')).map((cell) => clean(cell.innerText || cell.textContent || ''));
                const rowText = cells.join(' ');
                const identifier = (rowText.match(/\\b(?:\\d{8}[A-Z]|[XYZ]\\d{7}[A-Z])\\b/i) || [])[0] || '';
                if (!identifier || cells.length < 3) continue;
                const nameCell = cells.find((cell) => /,/.test(cell) && /[A-ZÁÉÍÓÚÑ]/i.test(cell)) || '';
                if (!nameCell) continue;
                const actionText = Array.from(row.querySelectorAll('a[href], [onclick], i, button, input'))
                  .map((el) => [
                    el.getAttribute('href') || '',
                    el.getAttribute('onclick') || '',
                    el.getAttribute('title') || '',
                    el.getAttribute('id') || '',
                    el.getAttribute('class') || ''
                  ].join(' '))
                  .join(' ');
                const externalId = (actionText.match(/desactivaTrabajador\\((\\d+)/i) || [])[1] || '';
                const nameIndex = cells.indexOf(nameCell);
                rows.push({
                  identifier_value: identifier.replace(/\\s+/g, '').toUpperCase(),
                  identifier_last4: identifier.replace(/\\s+/g, '').slice(-4).toUpperCase(),
                  display_name: nameCell,
                  work_position: nameIndex >= 0 ? clean(cells[nameIndex + 1] || '') : '',
                  external_worker_id: externalId || null
                });
              }
              return rows;
            }"""
        )
    except Exception:
        return []
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def _filter_worker_list_by_identifier(page: Any, args: argparse.Namespace) -> bool:
    if not (_is_ctaima_worker_list_url(page.url) or _worker_list_visible(page)):
        return False
    query = args.identifier_value or args.identifier_last4
    if not query:
        return False
    try:
        return bool(
            page.evaluate(
                """(query) => {
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
                  };
                  const inputs = Array.from(document.querySelectorAll("input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='password'])"))
                    .filter(visible)
                    .filter((input) => !['DNI', 'NSS', 'Nombre1', 'Apellido1', 'Apellido2', 'email', 'phone', 'Puesto'].includes(input.getAttribute('name') || input.getAttribute('id') || ''));
                  const input = inputs[0];
                  if (!input) return false;
                  input.focus();
                  input.value = query;
                  input.dispatchEvent(new Event('input', { bubbles: true }));
                  input.dispatchEvent(new Event('change', { bubbles: true }));
                  const buttons = Array.from(document.querySelectorAll("button, input[type='submit'], input[type='button'], a[onclick], [role='button']"))
                    .filter(visible)
                    .filter((item) => /buscar|search|lupa|fa-search|icon-search/i.test([
                      item.value,
                      item.innerText,
                      item.textContent,
                      item.title,
                      item.getAttribute('class'),
                      item.getAttribute('aria-label')
                    ].join(' ')));
                  if (buttons[0]) buttons[0].click();
                  else input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                  return true;
                }""",
                query,
            )
        )
    except Exception:
        return False


def _worker_list_visible(page: Any) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=2_000)
    except Exception:
        return False
    normalized = _norm(text)
    return "trabajadores" in normalized and "apellidos nombre" in normalized and "accion dni" in normalized


def _click_cancel_to_list(page: Any) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                  const normalize = (value) => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
                  };
                  const candidates = Array.from(document.querySelectorAll("input[type='button'], button, a[onclick], a[href]"))
                    .filter(visible)
                    .filter((element) => normalize(element.value || element.innerText || element.textContent || element.title || '').startsWith('cancelar'));
                  if (!candidates.length) return false;
                  candidates[0].click();
                  return true;
                }"""
            )
        )
    except Exception:
        return False


def _click_visible_text(page: Any, labels: tuple[str, ...]) -> bool:
    try:
        return bool(
            page.evaluate(
                """(labels) => {
                  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
                  const wanted = labels.map(normalize).filter(Boolean);
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
                  };
                  const candidates = Array.from(document.querySelectorAll('a, button, input[type=button], input[type=image], img[title], img[alt], [onclick], [role=button], [role=menuitem], li, div, span'))
                    .filter(visible)
                    .map((element) => ({
                      element,
                      text: normalize(element.innerText || element.textContent || element.value || element.title || element.alt || element.getAttribute('aria-label') || element.getAttribute('id') || '')
                    }))
                    .filter((item) => item.text);
                  for (const label of wanted) {
                    const match = candidates.find((item) => item.text === label) || candidates.find((item) => item.text.includes(label));
                    if (match) {
                      const clickable = match.element.closest('a, button') || match.element;
                      clickable.click();
                      return true;
                    }
                  }
                  return false;
                }""",
                list(labels),
            )
        )
    except Exception:
        return False


def _session_conflict_visible(page: Any) -> bool:
    try:
        text = page.locator("body").inner_text(timeout=2_000)
    except Exception:
        return False
    normalized = _norm(text)
    return "sesion activa" in normalized or "sesion abierta" in normalized or "mismas credenciales" in normalized


def _is_ctaima_worker_list_url(value: str) -> bool:
    normalized = value.lower()
    return "ctaimacae.net" in normalized and "/trabajadores/list.asp" in normalized


def _readback_page_summary(page: Any) -> dict[str, Any]:
    return {
        "url": safe_url(page.url),
        "title": redact(_safe_title(page))[:120],
        "worker_row_count": len(_extract_ctaima_worker_rows(page)),
        "worker_list_visible": _worker_list_visible(page),
        "worker_form_visible": _worker_form_visible(page),
    }


def _redacted_page(page: Any) -> dict[str, Any]:
    return {
        "url": safe_url(page.url),
        "title": redact(_safe_title(page))[:120],
        "worker_list_visible": _worker_list_visible(page),
        "worker_form_visible": _worker_form_visible(page),
    }


def _safe_title(page: Any) -> str:
    try:
        return str(page.title())
    except Exception:
        return ""


def _external_worker_id_from_readback(readback: dict[str, Any]) -> str | None:
    matched = readback.get("matched_worker")
    if isinstance(matched, dict) and matched.get("external_worker_id"):
        return str(matched.get("external_worker_id"))
    return None


def _split_last_name(value: str) -> tuple[str, str, str]:
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return "", "", "empty"
    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        return parts[0], parts[1] if len(parts) > 1 else "", "comma"
    tokens = text.split()
    if len(tokens) == 1:
        return text, "", "single_token"
    if len(tokens) == 2:
        return tokens[0], tokens[1], "two_tokens"
    return " ".join(tokens[:-1]), tokens[-1], "last_token_as_second_surname"


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
        "social_security_last4": args.social_security_last4 or args.social_security_number[-4:],
        "first_name_present": str(bool(args.first_name)),
        "last_name_token_count": str(len(args.last_name.split())),
        "email_present": str(bool(args.email)),
        "phone_present": str(bool(args.phone)),
        "contract_type_present": str(bool(args.contract_type)),
        "work_position": redact(args.work_position),
    }


def _load_worker_payload(args: argparse.Namespace, payload_file: Path) -> None:
    payload = json.loads(payload_file.read_text(encoding="utf-8"))
    for key in (
        "worker_ref",
        "identifier_type",
        "identifier_value",
        "identifier_last4",
        "social_security_number",
        "social_security_last4",
        "first_name",
        "last_name",
        "email",
        "phone",
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
    external_worker_id: str | None = None,
    status_file: Path | None = None,
) -> None:
    payload = {
        "status": status,
        "external_write_executed": external_write_executed,
        "post_write_read_confirmed": post_write_read_confirmed,
        "external_worker_id": external_worker_id,
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
