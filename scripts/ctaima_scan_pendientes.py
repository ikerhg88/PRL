from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlparse, urlunparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.platform_credentials import resolve_platform_credentials  # noqa: E402
from scripts.assisted_platform_browser import (  # noqa: E402
    auto_select_context_if_unique,
    browser_launch_variants,
    collect_shape,
    find_password_field,
    find_username_field,
    is_authenticated_page,
    prepare_session_profile,
    redact,
)

BLOCKED_NAV_TOKENS = {
    "aceptar",
    "alta",
    "anadir",
    "añadir",
    "baja",
    "borrar",
    "cancelar",
    "cambiar contrasena",
    "cambiar contraseña",
    "cambio de titular",
    "cerrar",
    "crear",
    "delete",
    "descargar",
    "desactivar",
    "eliminar",
    "enviar",
    "export",
    "guardar",
    "idioma",
    "importar",
    "insertar",
    "logout",
    "nuevo",
    "salir",
    "solicitar",
    "submit",
    "subir",
    "upload",
}

SAFE_PATH_HINTS = {
    "/acceso",
    "/admin_promotora/",
    "/centros/",
    "/contratas/",
    "/documentacion/",
    "/documentos/",
    "/empresas/",
    "/equipos/",
    "/informes/",
    "/maquinaria/",
    "/misdocumentos/",
    "/programas_admin/",
    "/recursos/",
    "/requisitos/",
    "/trabajadores/list.asp",
    "/validacion/",
    "/vehiculos/",
}

PENDING_RE = re.compile(r"\b\w*pendient\w*\b", re.IGNORECASE)
SAFE_MENU_LABELS = (
    "Coordinacion",
    "Coordinación",
    "Mis Recursos",
    "Trabajadores",
    "Mis Documentos",
    "Documentos",
    "Documentacion",
    "Documentación",
    "Acceso a Cliente",
    "Gestión preventiva",
    "Gestion preventiva",
    "Informes",
    "Pendientes",
    "Validaciones",
    "Solicitudes",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only CTAIMA scan for visible pending states.")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--account-id", type=int, default=12)
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--wait-human-seconds", type=int, default=180)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "ctaima-pending-scan")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    _configure_local_env()
    account = _account(args.tenant_id, args.account_id)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    status_file = args.out_dir / f"ctaima_pending_scan_{stamp}.status.json"
    profile_dir = _session_profile_dir(
        tenant_id=args.tenant_id,
        platform_slug=account["platform_slug"],
        platform_account_id=account["source_platform_account_id"],
    )

    resolution = resolve_platform_credentials(
        secret_ref=account.get("credential_secret_ref") or None,
        platform_account_id=str(account["source_platform_account_id"]),
    )
    if resolution.credentials is None:
        raise SystemExit("No configured CTAIMA credentials found for this account.")

    pages: list[dict[str, Any]] = []
    links_seen: dict[str, dict[str, str]] = {}
    launch_error = None
    with sync_playwright() as playwright:
        context = None
        profile = prepare_session_profile(profile_dir)
        for launch_kwargs in _launch_options(args.headless):
            try:
                context = playwright.chromium.launch_persistent_context(
                    str(profile["path"]),
                    headless=args.headless,
                    viewport={"width": 1366, "height": 900},
                    locale="es-ES",
                    accept_downloads=False,
                    **launch_kwargs,
                )
                break
            except Exception as exc:
                launch_error = str(exc)[:500]
        if context is None:
            raise SystemExit(f"Could not launch browser: {launch_error}")
        try:
            page = context.pages[0] if context.pages else context.new_page()
            _write_status(status_file, "browser_launched", account, page_url=account["entry_url"])
            try:
                page.goto(account["entry_url"], wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                pass
            if not _login_or_resume(page, account, resolution.credentials, status_file, args.wait_human_seconds):
                pages.append(_capture_page(page, "login_or_context_blocked"))
            elif not _ensure_context(page, account, status_file, args.wait_human_seconds):
                pages.append(_capture_page(page, "context_blocked"))
            else:
                pages = _scan_pages(page, account, status_file, max_pages=args.max_pages, links_seen=links_seen)
        finally:
            try:
                context.close()
            except Exception:
                pass

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "read_only": True,
            "external_write_executed": False,
            "captcha_bypass": False,
            "mfa_bypass": False,
            "stores_raw_cae_query": False,
            "stores_cookies_tokens_or_html": False,
            "stores_full_identifiers": False,
        },
        "account": {
            "account_proposal_id": account["id"],
            "platform_slug": account["platform_slug"],
            "external_company_name": account["external_company_name"],
        },
        "summary": _summary(pages),
        "discovered_links": list(links_seen.values())[:200],
        "pages": pages,
    }
    json_path = args.out_dir / f"ctaima_pending_scan_{stamp}.json"
    md_path = args.out_dir / f"ctaima_pending_scan_{stamp}.md"
    latest_json = args.out_dir / "ctaima_pending_scan_latest.json"
    latest_md = args.out_dir / "ctaima_pending_scan_latest.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(payload), encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), **payload["summary"]}, ensure_ascii=False, indent=2))
    return 0


def _configure_local_env() -> None:
    os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
    os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")
    os.environ.setdefault("IPRL_CAE_DATABASE_URL", f"sqlite:///{(ROOT / 'storage' / 'demo.db').as_posix()}")
    os.environ.setdefault("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(ROOT / "storage" / "documents"))
    os.environ.setdefault("IPRL_CAE_SECRET_KEY", "local-demo-secret-key-for-development-only-32")


def _account(tenant_id: int, account_id: int) -> dict[str, Any]:
    from app.db.models import PlatformRpaAccountProposal, PlatformRpaManifest
    from app.db.session import get_session_factory

    with get_session_factory()() as session:
        account = session.scalar(
            select(PlatformRpaAccountProposal).where(
                PlatformRpaAccountProposal.tenant_id == tenant_id,
                PlatformRpaAccountProposal.id == account_id,
            )
        )
        if account is None:
            raise SystemExit(f"Account proposal {account_id} not found.")
        manifest = session.scalar(
            select(PlatformRpaManifest).where(PlatformRpaManifest.id == account.manifest_id)
        )
        if manifest is None or manifest.platform_slug != "ctaima":
            raise SystemExit(f"Account proposal {account_id} is not CTAIMA.")
        return {
            "id": account.id,
            "entry_url": account.entry_url,
            "external_company_name": account.external_company_name,
            "source_platform_account_id": account.source_platform_account_id,
            "credential_secret_ref": account.credential_secret_ref,
            "platform_slug": manifest.platform_slug,
            "platform_name": manifest.platform_name,
        }


def _session_profile_dir(*, tenant_id: int, platform_slug: str, platform_account_id: str) -> Path:
    digest = hashlib.sha256(platform_account_id.encode("utf-8")).hexdigest()[:16]
    safe_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", platform_slug).strip("_") or "platform"
    return ROOT / "storage" / "rpa-browser-profiles" / f"tenant-{tenant_id}" / safe_slug / digest


def _launch_options(headless: bool) -> list[dict[str, Any]]:
    if headless:
        return [{"headless": True}]
    variants = browser_launch_variants("auto")
    return variants if variants else [{"headless": False}]


def _login_or_resume(page: Any, account: dict[str, Any], credentials: Any, status_file: Path, wait_seconds: int) -> bool:
    deadline = time.monotonic() + max(wait_seconds, 10)
    username_attempted = False
    password_attempted = False
    while time.monotonic() < deadline:
        shape = collect_shape(page)
        password_field = find_password_field(page)
        if is_authenticated_page(page, account["entry_url"], shape, password_field=password_field):
            _write_status(status_file, "session_ready", account, page_url=page.url)
            return True
        text = _visible_text(page)
        if "sesion activa" in _norm(text) or "sesion abierta" in _norm(text):
            _write_status(status_file, "human_session_conflict_required", account, page_url=page.url)
            time.sleep(2)
            continue
        if shape.get("captcha") or shape.get("mfa"):
            _write_status(status_file, "human_control_required", account, page_url=page.url)
            time.sleep(2)
            continue
        username_field = find_username_field(page)
        if password_field is not None and not password_attempted:
            if username_field is not None:
                username_field.fill(credentials.username)
            password_field.fill(credentials.password)
            password_attempted = True
            _click_submit(page)
            _write_status(status_file, "credentials_submitted", account, page_url=page.url)
            time.sleep(4)
            continue
        if username_field is not None and password_field is None and not username_attempted:
            username_field.fill(credentials.username)
            username_attempted = True
            _click_submit(page)
            _write_status(status_file, "username_submitted", account, page_url=page.url)
            time.sleep(3)
            continue
        _write_status(status_file, "waiting_for_login_or_human", account, page_url=page.url)
        time.sleep(2)
    return False


def _ensure_context(page: Any, account: dict[str, Any], status_file: Path, wait_seconds: int) -> bool:
    deadline = time.monotonic() + max(wait_seconds, 10)
    target_context = account["external_company_name"] or ""
    while time.monotonic() < deadline:
        shape = collect_shape(page)
        text = _visible_text(page)
        normalized = _norm(text)
        if "empresa quieres coordinarte" in normalized or "selecciona empresa" in normalized or shape.get("human_context_required"):
            selection = auto_select_context_if_unique(page, target_context)
            if not selection.get("ok"):
                selection = _selectize_context(page, target_context)
            _write_status(status_file, "context_selection_attempted", account, page_url=page.url, extra={"selection": selection})
            time.sleep(3)
            if selection.get("ok"):
                try:
                    page.wait_for_load_state("networkidle", timeout=10_000)
                except PlaywrightTimeoutError:
                    pass
                continue
            time.sleep(2)
            continue
        if _ctaima_internal_page(page.url):
            _write_status(status_file, "context_ready", account, page_url=page.url)
            return True
        time.sleep(2)
    return _ctaima_internal_page(page.url)


def _selectize_context(page: Any, target_context: str) -> dict[str, Any]:
    tokens = _context_tokens(target_context)
    if not tokens:
        return {"ok": False, "reason": "target_context_missing"}
    selector = "#listaempresas-selectized, input[placeholder*='empresa' i], input[aria-label*='empresa' i]"
    for token in tokens:
        try:
            input_box = page.locator(selector).first
            if input_box.count() == 0 or not input_box.is_visible(timeout=1_000):
                continue
            input_box.click(timeout=2_000)
            input_box.fill(token, timeout=2_000)
            page.wait_for_timeout(1_500)
            selection = page.evaluate(
                """(token) => {
                  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                  const normalize = (value) => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
                  const wanted = normalize(token);
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
                  };
                  const options = Array.from(document.querySelectorAll('.selectize-dropdown-content .option, [role=option], option, li'))
                    .filter(visible)
                    .map((element) => ({element, text: clean(element.innerText || element.textContent || element.label || '')}))
                    .filter((item) => item.text && normalize(item.text).includes(wanted));
                  if (options.length < 1) return {ok: false, reason: 'no_option_for_token', token};
                  options[0].element.click();
                  return {ok: true, method: 'selectize_option_click', token, matched_text: options[0].text, matches: options.length};
                }""",
                token,
            )
            if isinstance(selection, dict) and selection.get("ok"):
                return selection
        except Exception:
            continue
    try:
        return page.evaluate(
            """({targetText, tokens}) => {
              const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
              const normalize = (value) => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              const input = Array.from(document.querySelectorAll('input, [contenteditable=true]'))
                .filter(visible)
                .find((el) => /empresa|coordinar|select/i.test([el.placeholder, el.id, el.name, el.getAttribute('aria-label')].join(' ')));
              if (!input) return {ok: false, reason: 'selectize_input_not_found'};
              input.focus();
              input.value = targetText;
              input.dispatchEvent(new Event('input', {bubbles: true}));
              input.dispatchEvent(new Event('change', {bubbles: true}));
              const elements = Array.from(document.querySelectorAll('[role=option], .option, li, a, div, span'))
                .filter(visible)
                .map((element) => ({element, text: clean(element.innerText || element.textContent || element.getAttribute('title') || '')}))
                .filter((item) => item.text.length >= 3 && item.text.length <= 260);
              for (const token of tokens) {
                const matches = elements.filter((item) => normalize(item.text).includes(token));
                if (matches.length === 1) {
                  matches[0].element.click();
                  return {ok: true, method: 'selectize_visible_option_click', token, matched_text: matches[0].text};
                }
              }
              input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
              return {ok: true, method: 'selectize_enter', token: tokens[0], matched_text: ''};
            }""",
            {"targetText": target_context, "tokens": tokens},
        )
    except Exception as exc:
        return {"ok": False, "reason": f"selectize_error:{type(exc).__name__}"}


def _scan_pages(page: Any, account: dict[str, Any], status_file: Path, *, max_pages: int, links_seen: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    queue: deque[dict[str, str]] = deque()
    visited: set[str] = set()

    def capture_and_queue(label: str) -> None:
        captured = _capture_page(page, label)
        pages.append(captured)
        for link in captured.get("_raw_links", []):
            route = link["route"]
            links_seen.setdefault(route, {"route": route, "label": link["label"], "reason": link["reason"]})
            if route not in visited and not any(item["route"] == route for item in queue):
                queue.append(link)

    capture_and_queue("start")
    for label in SAFE_MENU_LABELS:
        if len(pages) >= max_pages:
            break
        if not _click_safe_text(page, label):
            continue
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(0.8)
        _write_status(status_file, "scanning_menu", account, page_url=page.url, extra={"label": label, "pages": len(pages)})
        capture_and_queue(f"menu:{label}")
    while queue and len(pages) < max_pages:
        link = queue.popleft()
        route = link["route"]
        if route in visited:
            continue
        visited.add(route)
        try:
            page.goto(link["href"], wait_until="domcontentloaded", timeout=25_000)
        except PlaywrightTimeoutError:
            pass
        except Exception:
            continue
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(0.6)
        _write_status(status_file, "scanning_page", account, page_url=page.url, extra={"pages": len(pages), "route": route})
        capture_and_queue(f"link:{link['label'] or link['path']}")
    return [_public_page(item) for item in pages]


def _click_safe_text(page: Any, label: str) -> bool:
    if any(token in _norm(label) for token in BLOCKED_NAV_TOKENS):
        return False
    try:
        return bool(
            page.evaluate(
                """({label, blockedTokens}) => {
                  const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                  const normalize = (value) => clean(value).normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
                  const wanted = normalize(label);
                  const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
                  };
                  const candidates = Array.from(document.querySelectorAll(
                    'a, button, [role=button], [role=menuitem], li, div, span, td'
                  ))
                    .filter(visible)
                    .map((element) => {
                      const text = clean(element.innerText || element.textContent || element.title || element.getAttribute('aria-label') || '');
                      return {element, text, normalized: normalize(text)};
                    })
                    .filter((item) => item.normalized && item.normalized.length <= 260)
                    .filter((item) => item.normalized === wanted || item.normalized.includes(wanted));
                  for (const item of candidates) {
                    if (blockedTokens.some((token) => item.normalized.includes(token))) continue;
                    const clickable = item.element.closest('a, button, [role=button], [role=menuitem]') || item.element;
                    clickable.click();
                    return true;
                  }
                  return false;
                }""",
                {"label": label, "blockedTokens": list(BLOCKED_NAV_TOKENS)},
            )
        )
    except Exception:
        return False


def _capture_page(page: Any, label: str) -> dict[str, Any]:
    route = safe_url(page.url)
    text = _visible_text(page)
    snippets = _pending_snippets(text)
    table_hits = _pending_table_rows(page)
    data = page.evaluate(
        """() => {
          const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim().slice(0, 240);
          const visible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
          };
          const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,.titulo,.title'))
            .filter(visible).map((el) => clean(el.innerText || el.textContent)).filter(Boolean).slice(0, 20);
          const anchors = Array.from(document.querySelectorAll('a[href], area[href]'))
            .map((el) => ({text: clean(el.innerText || el.textContent || el.title || el.getAttribute('aria-label')), title: clean(el.title || el.getAttribute('aria-label')), href: el.href || ''}))
            .slice(0, 500);
          const buttons = Array.from(document.querySelectorAll('button,input[type=button],input[type=submit],a img,[role=button]'))
            .filter(visible).map((el) => clean(el.innerText || el.textContent || el.value || el.title || el.alt || el.getAttribute('aria-label'))).filter(Boolean).slice(0, 80);
          return {title: clean(document.title), headings, anchors, buttons};
        }"""
    )
    links = [_link_candidate(link) for link in data.get("anchors", [])]
    links = [link for link in links if link is not None]
    return {
        "label": redact(label),
        "route": route,
        "title": redact(str(data.get("title") or "")),
        "headings": [redact(str(item)) for item in data.get("headings", [])],
        "buttons": [redact(str(item)) for item in data.get("buttons", [])],
        "pending_count": len(PENDING_RE.findall(_norm(text))),
        "pending_snippets": snippets,
        "pending_table_rows": table_hits,
        "_raw_links": links,
        "safe_links_count": len(links),
    }


def _public_page(page_data: dict[str, Any]) -> dict[str, Any]:
    public = dict(page_data)
    public.pop("_raw_links", None)
    return public


def _link_candidate(link: dict[str, Any]) -> dict[str, str] | None:
    href = str(link.get("href") or "")
    parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.hostname.lower().endswith("ctaimacae.net"):
        return None
    label = redact(str(link.get("text") or link.get("title") or ""))[:160]
    path = parsed.path or "/"
    path_lower = path.lower()
    route = safe_url(href)
    haystack = _norm(f"{label} {path} {parsed.query}")
    worker_list = path_lower.endswith("/trabajadores/list.asp")
    if parsed.fragment and not parsed.query:
        return None
    if "php_redirect.asp" in path_lower:
        return None
    if any(token in haystack for token in BLOCKED_NAV_TOKENS) and not worker_list:
        return None
    if "update.asp" in path_lower and "pendient" not in haystack:
        return None
    reason = "pending_label" if "pendient" in haystack else "safe_route"
    if reason != "pending_label" and not any(hint in path_lower for hint in SAFE_PATH_HINTS):
        return None
    return {"href": href, "route": route, "path": path, "label": label, "reason": reason}


def _pending_snippets(text: str) -> list[str]:
    clean = _redact_sensitive(re.sub(r"\s+", " ", text))
    snippets: list[str] = []
    for match in PENDING_RE.finditer(clean):
        start = max(0, match.start() - 120)
        end = min(len(clean), match.end() + 160)
        snippet = clean[start:end].strip()
        if snippet and snippet not in snippets:
            snippets.append(snippet[:400])
        if len(snippets) >= 12:
            break
    return snippets


def _pending_table_rows(page: Any) -> list[dict[str, Any]]:
    try:
        rows = page.evaluate(
            """() => {
              const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim().slice(0, 240);
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || '1') > 0 && rect.width > 0 && rect.height > 0;
              };
              const out = [];
              for (const table of Array.from(document.querySelectorAll('table')).filter(visible).slice(0, 20)) {
                const headers = Array.from(table.querySelectorAll('th')).map((th) => clean(th.innerText || th.textContent)).filter(Boolean);
                for (const row of Array.from(table.querySelectorAll('tr')).slice(0, 200)) {
                  const cells = Array.from(row.querySelectorAll('td, th')).map((cell) => clean(cell.innerText || cell.textContent)).filter(Boolean);
                  const text = cells.join(' ');
                  if (/pendient/i.test(text)) out.push({headers, cells});
                }
              }
              return out.slice(0, 40);
            }"""
        )
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    cleaned = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cleaned.append(
            {
                "headers": [_redact_sensitive(str(item)) for item in row.get("headers", [])[:12]],
                "cells": [_redact_sensitive(str(item)) for item in row.get("cells", [])[:12]],
            }
        )
    return cleaned


def _click_submit(page: Any) -> None:
    for selector in ("button[type=submit]", "input[type=submit]", "button", "input[type=button]"):
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible(timeout=1_000):
                locator.click(timeout=5_000)
                return
        except Exception:
            continue


def _visible_text(page: Any) -> str:
    try:
        return page.locator("body").inner_text(timeout=5_000)
    except Exception:
        return ""


def _ctaima_internal_page(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.hostname.lower().endswith("ctaimacae.net"):
        return False
    path = (parsed.path or "").lower()
    return "/ctaima_cae/" in path and not path.endswith("/connections/valida.asp")


def safe_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc and parsed.query:
        query_parts = []
        for key, raw_value in parse_qsl(parsed.query, keep_blank_values=True):
            redacted_value = "[empty]" if raw_value == "" else "[redacted]"
            query_parts.append(f"{quote(key, safe='')}={redacted_value}")
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "&".join(query_parts), ""))
    return value


def _redact_sensitive(value: str) -> str:
    text = redact(value)
    text = re.sub(r"\b\d{11,12}\b", "[naf]", text)
    text = re.sub(r"\b\d{9}\b", "[number]", text)
    text = re.sub(r"\b\d{3}[ -]?\d{2}[ -]?\d{2}[ -]?\d{2}\b", "[phone]", text)
    return text[:500]


def _context_tokens(target_context: str) -> list[str]:
    normalized = _norm(target_context)
    tokens = []
    for part in re.split(r"[,;/]+", normalized):
        part = part.strip()
        if len(part) >= 4:
            tokens.append(part)
    for word in normalized.split():
        if len(word) >= 6:
            tokens.append(word)
    seen: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return seen[:8]


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value).strip().lower())


def _write_status(
    path: Path,
    state: str,
    account: dict[str, Any],
    *,
    page_url: str,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "state": state,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "account_proposal_id": account["id"],
        "platform_slug": account["platform_slug"],
        "external_company_name": account["external_company_name"],
        "page_url": safe_url(page_url),
        "external_write_executed": False,
        "captcha_bypass": False,
        "mfa_bypass": False,
    }
    if extra:
        payload["extra"] = extra
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _summary(pages: list[dict[str, Any]]) -> dict[str, Any]:
    pages_with_pending = [page for page in pages if int(page.get("pending_count") or 0) > 0 or page.get("pending_table_rows")]
    return {
        "pages_scanned": len(pages),
        "pages_with_pending": len(pages_with_pending),
        "pending_occurrences": sum(int(page.get("pending_count") or 0) for page in pages),
        "pending_table_rows": sum(len(page.get("pending_table_rows") or []) for page in pages),
        "routes_with_pending": [page["route"] for page in pages_with_pending[:50]],
        "external_write_executed": 0,
    }


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# CTAIMA pending scan",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "Policy: read-only; no writes; no captcha/MFA bypass; no raw `cae` values stored.",
        "",
        f"- Account: `{payload['account']['account_proposal_id']}` / {payload['account']['external_company_name']}",
        f"- Pages scanned: `{summary['pages_scanned']}`",
        f"- Pages with `pendiente`: `{summary['pages_with_pending']}`",
        f"- Pending occurrences: `{summary['pending_occurrences']}`",
        f"- Pending table rows: `{summary['pending_table_rows']}`",
        "",
    ]
    for page in payload["pages"]:
        if int(page.get("pending_count") or 0) <= 0 and not page.get("pending_table_rows"):
            continue
        lines.append(f"## {page['label']}")
        lines.append(f"- Route: `{page['route']}`")
        if page.get("headings"):
            lines.append(f"- Headings: {', '.join(page['headings'][:8])}")
        lines.append(f"- Pending count: `{page.get('pending_count', 0)}`")
        for snippet in page.get("pending_snippets", [])[:8]:
            lines.append(f"- Snippet: {snippet}")
        for row in page.get("pending_table_rows", [])[:8]:
            headers = ", ".join(row.get("headers") or [])
            cells = " | ".join(row.get("cells") or [])
            if headers:
                lines.append(f"- Table headers: {headers}")
            lines.append(f"- Row: {cells}")
        lines.append("")
    if not summary["pages_with_pending"]:
        lines.append("No visible `pendiente` text was found in scanned CTAIMA pages.")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
