from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

from app.connectors.rpa.e_coordina.readonly import (
    _collect_shape,
    _external_status_summary,
    _find_local_chromium,
    _first_visible,
    _network_summary,
    _page_snapshot,
    _redact_text,
    _safe_title,
    _sanitize_url,
)
from app.services.platform_credentials import PlatformCredentials


DEFAULT_USERNAME_SELECTORS = (
    "input[type='email']",
    "input[name*='email' i]",
    "input[id*='email' i]",
    "input[name*='correo' i]",
    "input[id*='correo' i]",
    "input[name*='user' i]",
    "input[id*='user' i]",
    "input[name*='usuario' i]",
    "input[id*='usuario' i]",
    "input[name*='login' i]",
    "input[id*='login' i]",
    "input[type='text']",
    "input:not([type])",
)

DEFAULT_PASSWORD_SELECTORS = (
    "input[type='password']",
    "input[name*='password' i]",
    "input[id*='password' i]",
    "input[name*='pass' i]",
    "input[id*='pass' i]",
    "input[name*='clave' i]",
    "input[id*='clave' i]",
)

DEFAULT_SUBMIT_SELECTORS = (
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Iniciar')",
    "button:has-text('Entrar')",
    "button:has-text('Continuar')",
    "button:has-text('Acceder')",
    "input[value*='Iniciar' i]",
    "input[value*='Entrar' i]",
    "input[value*='Continuar' i]",
    "input[value*='Acceder' i]",
)

CONTROL_TERMS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "mfa",
    "2fa",
    "otp",
    "codigo de verificacion",
    "código de verificación",
    "doble factor",
    "sesion activa",
    "sesión activa",
    "ya existe una sesion",
    "ya existe una sesión",
    "seleccione la empresa",
    "selecciona empresa",
)

BLOCKED_READONLY_PATH_WORDS = (
    "delete",
    "remove",
    "upload",
    "download",
    "export",
    "submit",
    "save",
    "logout",
    "borrar",
    "eliminar",
    "subir",
    "descargar",
    "guardar",
    "enviar",
    "salir",
)


@dataclass(frozen=True)
class ReadonlyReviewResult:
    status: str
    result_status: str
    result_summary: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class ReadonlyPlatformProfile:
    platform_slug: str
    connector_key: str
    display_name: str
    username_selectors: tuple[str, ...] = ()
    password_selectors: tuple[str, ...] = ()
    submit_selectors: tuple[str, ...] = ()
    readonly_paths: tuple[str, ...] = ()
    expected_success_terms: tuple[str, ...] = ()
    human_context_terms: tuple[str, ...] = ()
    sensitive_data_scope: str = "platform_structure_only"
    allow_two_step_login: bool = False


class ConfiguredReadonlyConnector:
    profile: ReadonlyPlatformProfile

    @property
    def connector_key(self) -> str:
        return self.profile.connector_key

    @property
    def platform_slug(self) -> str:
        return self.profile.platform_slug

    def run_login_probe(
        self,
        *,
        entry_url: str,
        credentials: PlatformCredentials,
        expected_context: str,
        timeout_ms: int = 30_000,
    ) -> ReadonlyReviewResult:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - exercised only without optional dependency.
            return ReadonlyReviewResult(
                status="failed",
                result_status="playwright_missing",
                result_summary="Playwright no esta instalado en el entorno backend.",
                evidence={"error": _redact_text(str(exc))},
            )

        requests: list[dict[str, Any]] = []
        responses: list[dict[str, Any]] = []
        pages: list[dict[str, Any]] = []
        navigation_actions: list[dict[str, Any]] = []
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
            "human_context_detected": False,
            "credential_submissions": 0,
            "readonly_pages_visited": 0,
        }

        if not entry_url:
            return ReadonlyReviewResult(
                status="failed",
                result_status="entry_url_missing",
                result_summary=f"{self.profile.display_name}: falta URL de entrada configurada.",
                evidence={"connector_key": self.connector_key, "platform_slug": self.platform_slug},
            )

        with sync_playwright() as playwright:
            launch_kwargs: dict[str, Any] = {"headless": True}
            executable_path = _find_local_chromium()
            if executable_path is not None:
                launch_kwargs["executable_path"] = str(executable_path)
            try:
                browser = playwright.chromium.launch(**launch_kwargs)
            except Exception as exc:
                return ReadonlyReviewResult(
                    status="failed",
                    result_status="browser_launch_failed",
                    result_summary=f"No se pudo abrir Chromium para la revision {self.profile.display_name}.",
                    evidence={
                        "connector_key": self.connector_key,
                        "platform_slug": self.platform_slug,
                        "error": _redact_text(f"{type(exc).__name__}: {exc}"),
                    },
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
            outcome["captcha_detected"] = bool(initial_shape.get("captcha_signals"))
            outcome["mfa_detected"] = bool(initial_shape.get("mfa_signals"))
            outcome["human_context_detected"] = _has_control_term(initial_shape, self.profile.human_context_terms)
            pages.append(_safe_page_snapshot("login", page, initial_shape))

            if outcome["captcha_detected"] or outcome["mfa_detected"] or outcome["human_context_detected"]:
                outcome["login_status"] = "human_action_required_before_login"
            else:
                username_field = _first_visible(
                    page,
                    [*self.profile.username_selectors, *DEFAULT_USERNAME_SELECTORS],
                )
                password_field = _first_visible(
                    page,
                    [*self.profile.password_selectors, *DEFAULT_PASSWORD_SELECTORS],
                )
                outcome["username_field_found"] = username_field is not None
                outcome["password_field_found"] = password_field is not None

                if username_field is None or password_field is None:
                    if username_field is not None and self.profile.allow_two_step_login:
                        outcome["login_status"] = "human_action_required_two_step_login"
                    else:
                        outcome["login_status"] = "login_form_not_found"
                else:
                    username_field.fill(credentials.username, timeout=10_000)
                    password_field.fill(credentials.password, timeout=10_000)
                    outcome["credential_submissions"] = 1
                    try:
                        with page.expect_navigation(wait_until="domcontentloaded", timeout=15_000):
                            _click_submit(page, [*self.profile.submit_selectors, *DEFAULT_SUBMIT_SELECTORS])
                    except PlaywrightTimeoutError:
                        pass
                    try:
                        page.wait_for_load_state("networkidle", timeout=12_000)
                    except PlaywrightTimeoutError:
                        pass
                    _wait_soft(page)

                    post_shape = _collect_shape(page)
                    outcome["captcha_detected"] = outcome["captcha_detected"] or bool(post_shape.get("captcha_signals"))
                    outcome["mfa_detected"] = outcome["mfa_detected"] or bool(post_shape.get("mfa_signals"))
                    outcome["human_context_detected"] = _has_control_term(post_shape, self.profile.human_context_terms)
                    outcome["context_detected"] = _contains_any_context(
                        post_shape,
                        [expected_context, *self.profile.expected_success_terms],
                    )
                    pages.append(_safe_page_snapshot("post-login landing", page, post_shape))

                    has_password_after = any(
                        field.get("type") == "password"
                        for form in post_shape.get("forms", [])
                        for field in form.get("inputs", [])
                    )
                    if outcome["captcha_detected"] or outcome["mfa_detected"]:
                        outcome["login_status"] = "human_action_required_after_login"
                    elif outcome["human_context_detected"]:
                        outcome["login_status"] = "human_action_required_context_selection"
                    elif has_password_after:
                        outcome["login_status"] = "login_not_confirmed_password_form_still_present"
                    elif outcome["context_detected"]:
                        outcome["login_status"] = "login_likely_success"
                    else:
                        outcome["login_status"] = "login_likely_success_context_unconfirmed"

                    if outcome["login_status"].startswith("login_likely_success"):
                        for readonly_path in self.profile.readonly_paths:
                            action = _goto_readonly_path(page, entry_url=entry_url, readonly_path=readonly_path)
                            navigation_actions.append(action)
                            if not action["ok"]:
                                continue
                            _wait_soft(page)
                            navigation_shape = _collect_shape(page)
                            pages.append(_safe_page_snapshot(f"readonly {readonly_path}", page, navigation_shape))
                            outcome["readonly_pages_visited"] += 1
                            outcome["captcha_detected"] = outcome["captcha_detected"] or bool(
                                navigation_shape.get("captcha_signals")
                            )
                            outcome["mfa_detected"] = outcome["mfa_detected"] or bool(
                                navigation_shape.get("mfa_signals")
                            )
                            if outcome["captcha_detected"] or outcome["mfa_detected"]:
                                outcome["login_status"] = "human_action_required_after_navigation"
                                break

            outcome["final_title"] = _safe_title(page)
            outcome["final_url_sanitized"] = _sanitize_url(page.url)
            context.close()
            browser.close()

        return ReadonlyReviewResult(
            status=_status_from_login(outcome["login_status"]),
            result_status=outcome["login_status"],
            result_summary=_summary_from_outcome(self.profile.display_name, outcome),
            evidence={
                "connector_key": self.connector_key,
                "platform_slug": self.platform_slug,
                "entry_url_sanitized": _sanitize_url(entry_url),
                "safe_mode": {
                    "read_only": True,
                    "dry_run": True,
                    "manual_approval_required": True,
                    "max_credential_submissions": 1,
                    "captcha_bypass": False,
                    "mfa_bypass": False,
                    "row_values_persisted": False,
                    "sensitive_data_scope": self.profile.sensitive_data_scope,
                },
                "outcome": outcome,
                "navigation_actions": navigation_actions,
                "network_summary": _network_summary(requests, responses),
                "external_status_summary": _external_status_summary(pages),
                "pages": pages,
            },
        )


def _click_submit(page: Any, selectors: list[str]) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.count() > 0 and locator.is_visible():
            locator.click(timeout=10_000)
            return
    page.keyboard.press("Enter")


def _goto_readonly_path(page: Any, *, entry_url: str, readonly_path: str) -> dict[str, Any]:
    if not readonly_path.startswith("/"):
        return {"ok": False, "reason": "readonly_path_not_absolute", "path": readonly_path}
    lower_path = readonly_path.lower()
    if any(word in lower_path for word in BLOCKED_READONLY_PATH_WORDS):
        return {"ok": False, "reason": "blocked_readonly_path_word", "path": readonly_path}
    target_url = urljoin(f"{urlparse(entry_url).scheme}://{urlparse(entry_url).netloc}", readonly_path)
    if urlparse(target_url).netloc != urlparse(entry_url).netloc:
        return {"ok": False, "reason": "cross_host_readonly_path_blocked", "path": readonly_path}
    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=15_000)
    except Exception as exc:
        return {
            "ok": False,
            "reason": "navigation_failed",
            "path": readonly_path,
            "error": _redact_text(f"{type(exc).__name__}: {exc}"),
        }
    return {"ok": True, "method": "direct_get_readonly_path", "path": readonly_path, "url_sanitized": _sanitize_url(target_url)}


def _wait_soft(page: Any) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(1_500)
    except Exception:
        pass


def _safe_page_snapshot(label: str, page: Any, shape: dict[str, Any]) -> dict[str, Any]:
    snapshot = _page_snapshot(label, page, shape)
    snapshot["forms"] = [_safe_form(form) for form in snapshot.get("forms", [])]
    snapshot["navigation_labels"] = _navigation_labels(page)
    return snapshot


def _safe_form(form: dict[str, Any]) -> dict[str, Any]:
    safe = dict(form)
    if isinstance(safe.get("action"), str):
        safe["action"] = _sanitize_url(safe["action"])
    safe["inputs"] = [
        {
            **field,
            "name": _redact_text(field.get("name", "")),
            "id": _redact_text(field.get("id", "")),
            "placeholder": _redact_text(field.get("placeholder", "")),
            "ariaLabel": _redact_text(field.get("ariaLabel", "")),
        }
        for field in safe.get("inputs", [])
    ]
    safe["buttons"] = [
        {
            **button,
            "text": _redact_text(button.get("text", "")),
            "id": _redact_text(button.get("id", "")),
            "name": _redact_text(button.get("name", "")),
        }
        for button in safe.get("buttons", [])
    ]
    return safe


def _navigation_labels(page: Any) -> list[str]:
    try:
        labels = page.evaluate(
            """() => {
              const clean = (value) => (value || '').toString().replace(/\\s+/g, ' ').trim().slice(0, 80);
              return Array.from(document.querySelectorAll('nav a, aside a, [role=menuitem], [role=tab]'))
                .slice(0, 40)
                .map((item) => clean(item.innerText || item.textContent || item.getAttribute('aria-label') || ''))
                .filter(Boolean);
            }"""
        )
    except Exception:
        return []
    if not isinstance(labels, list):
        return []
    return [_redact_text(label) for label in labels[:40]]


def _has_control_term(shape: dict[str, Any], extra_terms: tuple[str, ...]) -> bool:
    return _contains_any_context(shape, [*CONTROL_TERMS, *extra_terms])


def _contains_any_context(shape: dict[str, Any], terms: list[str] | tuple[str, ...]) -> bool:
    normalized_terms = [term.strip().lower() for term in terms if term and term.strip()]
    if not normalized_terms:
        return False
    haystack = " ".join(
        [
            *[str(item) for item in shape.get("headings", [])],
            str(shape.get("body_text", "")),
        ]
    ).lower()
    return any(term in haystack for term in normalized_terms)


def _status_from_login(login_status: str) -> str:
    if login_status == "login_likely_success":
        return "completed"
    if login_status.startswith("human_action_required"):
        return "human_action_required"
    if login_status.startswith("login_likely_success"):
        return "completed_with_warnings"
    return "failed"


def _summary_from_outcome(display_name: str, outcome: dict[str, Any]) -> str:
    login_status = str(outcome.get("login_status", "unknown"))
    if login_status == "login_likely_success":
        visited = int(outcome.get("readonly_pages_visited") or 0)
        suffix = f" y {visited} vistas de solo lectura" if visited else ""
        return f"Login {display_name} confirmado{suffix}; no se han escrito datos externos."
    if login_status == "human_action_required_context_selection":
        return f"{display_name} requiere seleccion/confirmacion humana de empresa o contexto antes de leer."
    if login_status.startswith("human_action_required"):
        return f"{display_name} requiere accion humana para captcha, MFA, aviso o control no determinista."
    if login_status == "login_likely_success_context_unconfirmed":
        return f"Login {display_name} probable, pero el contexto esperado no se confirmo de forma estable."
    return f"Revision {display_name} no completada: {login_status}."
