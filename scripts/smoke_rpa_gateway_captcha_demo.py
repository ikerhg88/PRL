from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("IPRL_CAE_CONFIG_FILE", str(ROOT / "config" / "iprl-cae.local.example.toml"))
os.environ.setdefault("IPRL_CAE_ENVIRONMENT", "local")
os.environ.setdefault("IPRL_CAE_DATABASE_URL", f"sqlite:///{(ROOT / 'storage' / 'demo.db').as_posix()}")
os.environ.setdefault("IPRL_CAE_DOCUMENT_STORAGE_PATH", str(ROOT / "storage" / "documents"))
os.environ.setdefault("IPRL_CAE_SECRET_KEY", "local-demo-secret-key-for-development-only-32")

from sqlalchemy import select

from app.connectors.rpa.e_coordina.readonly import _collect_shape, _find_local_chromium
from app.db.demo_seed import create_demo_database
from app.db.models import PlatformReviewSchedule, PlatformRpaManifest, User
from app.db.session import get_session_factory
from app.services.platform_contracts import (
    DEFAULT_CONTRACT_BUNDLE,
    import_first_priority_arm_contracts,
)
from app.services.platform_review_schedules import ensure_review_schedules
from app.services.rpa_gateway import apply_gateway_decision, create_gateway_request

CAPTCHA_DEMO_HTML = """<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>Demo control humano CAE</title>
  </head>
  <body>
    <main>
      <h1>Portal CAE demo</h1>
      <p>Esta pagina local simula captcha y codigo de verificacion.</p>
      <form>
        <label>Usuario <input name="user" autocomplete="username" /></label>
        <label>Clave <input name="password" type="password" /></label>
        <iframe title="captcha demo" src="about:blank?captcha=recaptcha"></iframe>
        <label>Codigo de verificacion <input name="otp" placeholder="codigo de verificacion" /></label>
        <button type="submit">Entrar</button>
      </form>
    </main>
  </body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke local de deteccion captcha/MFA y pasarela humana sin tocar terceros."
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--out-dir", default=str(ROOT / "artifacts" / "rpa-gateway"))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    detection = _run_local_captcha_detection(out_dir)
    gateway = _run_gateway_flow(tenant_id=args.tenant_id)
    result = {
        "local_page": detection,
        "gateway": gateway,
        "safety": {
            "external_pages_contacted": False,
            "captcha_bypass_attempted": False,
            "mfa_bypass_attempted": False,
            "external_writes": 0,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def _run_local_captcha_detection(out_dir: Path) -> dict[str, Any]:
    html_path = out_dir / "captcha_human_control_demo.html"
    html_path.write_text(CAPTCHA_DEMO_HTML, encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {
            "status": "playwright_missing",
            "html_path": str(html_path),
            "error": str(exc),
        }

    try:
        with sync_playwright() as playwright:
            launch_kwargs: dict[str, Any] = {"headless": True}
            executable_path = _find_local_chromium()
            if executable_path is not None:
                launch_kwargs["executable_path"] = str(executable_path)
            browser = playwright.chromium.launch(**launch_kwargs)
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="domcontentloaded")
            shape = _collect_shape(page)
            browser.close()
    except Exception as exc:
        fallback = _static_control_detection(CAPTCHA_DEMO_HTML)
        return {
            "status": "browser_unavailable_static_fallback",
            "html_path": str(html_path),
            "error": f"{type(exc).__name__}: {exc}",
            "captcha_detected": fallback["captcha_detected"],
            "mfa_detected": fallback["mfa_detected"],
            "expected_gateway_status": "human_action_required",
        }
    return {
        "status": "completed",
        "html_path": str(html_path),
        "captcha_detected": bool(shape["captcha_signals"]),
        "mfa_detected": bool(shape["mfa_signals"]),
        "expected_gateway_status": "human_action_required",
    }


def _static_control_detection(html: str) -> dict[str, bool]:
    lower = html.lower()
    return {
        "captcha_detected": "captcha" in lower or "recaptcha" in lower or "hcaptcha" in lower,
        "mfa_detected": "codigo de verificacion" in lower or "otp" in lower or "2fa" in lower,
    }


def _run_gateway_flow(*, tenant_id: int) -> dict[str, Any]:
    create_demo_database()
    session_factory = get_session_factory()
    with session_factory() as session:
        actor = session.scalar(
            select(User).where(User.tenant_id == tenant_id, User.email == "demo@demo.invalid")
        )
        actor_user_id = actor.id if actor is not None else None
        import_first_priority_arm_contracts(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            source_root=DEFAULT_CONTRACT_BUNDLE,
        )
        ensure_review_schedules(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            priority_group="arm_first_priority",
        )
        schedule = session.scalar(
            select(PlatformReviewSchedule)
            .join(PlatformRpaManifest, PlatformRpaManifest.id == PlatformReviewSchedule.manifest_id)
            .where(
                PlatformReviewSchedule.tenant_id == tenant_id,
                PlatformRpaManifest.platform_slug == "e_coordina",
            )
        )
        if schedule is None:
            raise RuntimeError("No se encontro schedule e-coordina para la pasarela.")
        run = create_gateway_request(
            session,
            tenant_id=tenant_id,
            schedule_id=schedule.id,
            action_key="read_external_status",
            actor_user_id=actor_user_id,
            request_comment="Smoke local captcha/MFA: revisar estado sin modificar datos.",
        )
        if run is None:
            raise RuntimeError("No se pudo crear peticion de pasarela.")
        initial_status = run.status
        authorized = apply_gateway_decision(
            session,
            tenant_id=tenant_id,
            run_id=run.id,
            decision="authorize_enter_page",
            actor_user_id=actor_user_id,
            notes="Operador autoriza entrada en navegador visible.",
        )
        authorized_result_status = authorized.result_status if authorized is not None else None
        resolved = apply_gateway_decision(
            session,
            tenant_id=tenant_id,
            run_id=run.id,
            decision="human_control_resolved",
            actor_user_id=actor_user_id,
            notes="Control humano marcado como resuelto en smoke local.",
        )
        session.commit()
        gateway = resolved.evidence_json["gateway"] if resolved is not None else {}
        return {
            "request_id": run.id,
            "initial_status": initial_status,
            "authorized_result_status": authorized_result_status,
            "final_status": resolved.status if resolved is not None else None,
            "final_result_status": resolved.result_status if resolved is not None else None,
            "changes_applied": len(gateway.get("changes_applied") or []),
            "planned_external_changes": len(gateway.get("planned_external_changes") or []),
        }


if __name__ == "__main__":
    main()
