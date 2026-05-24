"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  ExternalLink,
  KeyRound,
  ListChecks,
  PlayCircle,
  RefreshCw,
  ShieldCheck
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { readAuthSession } from "../../lib/authClient";
import { apiJson, jsonHeaders } from "../../lib/apiClient";

type GatewayAction = {
  action_key: string;
  label: string;
  description: string;
  enabled: boolean;
  writes_external_system: boolean;
};

type GatewaySchedule = {
  schedule_id: number;
  manifest_id: number;
  platform_slug: string;
  platform_name: string;
  enabled: boolean;
  dry_run: boolean;
  manual_approval_required: boolean;
  last_result_status: string | null;
  next_run_at: string | null;
  human_assisted_supported: boolean;
};

type GatewayOptions = {
  actions: GatewayAction[];
  schedules: GatewaySchedule[];
  policy: Record<string, boolean>;
};

type GuidedFlow = {
  title?: string;
  objective?: string;
  target_detail?: string | null;
  account_context?: string | null;
  read_only_boundary?: string;
  steps?: string[];
  cannot_automate?: string[];
};

type GatewayRun = {
  id: number;
  platform_slug: string;
  platform_name: string;
  operation: string;
  trigger_source: string;
  status: string;
  result_status: string | null;
  result_summary: string | null;
  dry_run: boolean;
  manual_approval_required: boolean;
  started_at: string | null;
  finished_at: string | null;
  evidence_json: {
    gateway?: {
      requested_action_label?: string;
      ui_boundary?: string;
      request_comment?: string;
      operator_steps?: string[];
      planned_external_changes?: unknown[];
      changes_applied?: unknown[];
      last_human_decision?: string;
      next_step?: string;
      allowed_external_host?: string | null;
      allowed_external_url?: string | null;
      external_account?: string | null;
      external_company_name?: string | null;
      external_browser_authorized?: boolean;
      browser_launch?: BrowserLaunch;
      guided_flow?: GuidedFlow;
    };
  };
};

type BrowserLaunch = {
  run_id: number;
  launched: boolean;
  status: string;
  message: string;
  pid: number | null;
  credential_available: boolean;
  entry_url: string | null;
  status_artifact: string | null;
  session_persistence?: SessionPersistence | null;
};

type SessionPersistence = {
  enabled?: boolean;
  profile_key?: string | null;
  profile_reused?: boolean;
  raw_cookies_exported?: boolean;
  stores_raw_cookies_in_status?: boolean;
};

type BrowserStatus = {
  run_id: number;
  available: boolean;
  state: string;
  message: string;
  updated_at_utc: string | null;
  platform_label: string | null;
  entry_url: string | null;
  selected_login_variant?: string | null;
  login_variant_policy?: Record<string, unknown> | null;
  session_persistence?: SessionPersistence | null;
  capture_summary?: {
    pages_captured?: number;
    status_counts?: unknown[];
    persisted_row_level?: boolean;
    row_level_blocker?: string;
    target_signals?: Record<string, boolean>;
  } | null;
};

type CaptureSync = {
  run_id: number;
  synced: boolean;
  status: string;
  message: string;
  pages_captured: number;
  status_counts: unknown[];
  persisted_row_level: boolean;
  row_level_blocker: string | null;
};

type FlowStep = {
  label: string;
  detail: string;
  state: "done" | "active" | "pending" | "blocked";
};

export default function RpaGatewayPage() {
  const [options, setOptions] = useState<GatewayOptions | null>(null);
  const [requests, setRequests] = useState<GatewayRun[]>([]);
  const [selectedScheduleId, setSelectedScheduleId] = useState<number | null>(null);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState("Cargando asistente de plataforma.");
  const [browserStatus, setBrowserStatus] = useState<BrowserStatus | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const session = useMemo(() => readAuthSession(), []);

  const selectedSchedule = useMemo(
    () => options?.schedules.find((schedule) => schedule.schedule_id === selectedScheduleId) ?? null,
    [options, selectedScheduleId]
  );
  const activeRun = useMemo(
    () => requests.find((request) => request.id === activeRunId) ?? null,
    [activeRunId, requests]
  );

  useEffect(() => {
    void loadGateway();
  }, []);

  useEffect(() => {
    if (!activeRun?.evidence_json.gateway?.browser_launch?.status_artifact) {
      setBrowserStatus(null);
      return;
    }
    let cancelled = false;
    async function pollStatus() {
      if (!activeRun || cancelled) {
        return;
      }
      await readBrowserStatus(activeRun.id, false);
    }
    void pollStatus();
    const interval = window.setInterval(() => void pollStatus(), 4000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [activeRun?.id, activeRun?.evidence_json.gateway?.browser_launch?.status_artifact]);

  async function loadGateway() {
    setIsBusy(true);
    try {
      await apiJson<unknown>("/api/v1/platform-review-schedules/ensure", { method: "POST" });
      const [optionPayload, requestRows] = await Promise.all([
        apiJson<GatewayOptions>("/api/v1/rpa-gateway/options"),
        apiJson<GatewayRun[]>("/api/v1/rpa-gateway/requests")
      ]);
      setOptions(optionPayload);
      setRequests(requestRows);
      setSelectedScheduleId((current) => current ?? preferredScheduleId(optionPayload.schedules));
      const requestedRunId = queryRequestId();
      const requestedRun = requestRows.find((request) => request.id === requestedRunId) ?? null;
      if (requestedRun) {
        setActiveRunId(requestedRun.id);
        setMessage(`${requestedRun.platform_name}: flujo guiado cargado.`);
      } else {
        setMessage(
          `Asistente listo: selecciona plataforma y genera el flujo guiado en un solo paso.`
        );
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo cargar la pasarela.");
    } finally {
      setIsBusy(false);
    }
  }

  async function createGuidedFlow() {
    if (!selectedScheduleId) {
      setMessage("Selecciona una plataforma antes de generar el flujo guiado.");
      return;
    }
    setIsBusy(true);
    try {
      const requestComment =
        comment || `Flujo guiado de revision de estado para ${selectedSchedule?.platform_name ?? "plataforma seleccionada"}.`;
      const run = await apiJson<GatewayRun>("/api/v1/rpa-gateway/requests", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          schedule_id: selectedScheduleId,
          action_key: "read_external_status",
          request_comment: requestComment
        })
      });
      upsertRun(run);
      activateRun(run.id);
      setComment("");
      setMessage(`${run.platform_name}: flujo generado. Registrando autorizacion y abriendo navegador guiado.`);
      await authorizeAndLaunch(run, false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo generar el flujo guiado.");
    } finally {
      setIsBusy(false);
    }
  }

  async function authorizeAndLaunch(run: GatewayRun, manageBusy = true) {
    if (manageBusy) {
      setIsBusy(true);
    }
    try {
      const authorized = await apiJson<GatewayRun>(`/api/v1/rpa-gateway/requests/${run.id}/decision`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          decision: "authorize_enter_page",
          notes: `Autorizar entrada y lanzar navegador guiado por ${session?.user.email ?? "operador"}.`
        })
      });
      upsertRun(authorized);
      activateRun(authorized.id);
      await launchVisibleBrowser(authorized, false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo registrar la decision.");
    } finally {
      if (manageBusy) {
        setIsBusy(false);
      }
    }
  }

  async function decide(run: GatewayRun, decision: "human_control_resolved" | "cancel") {
    setIsBusy(true);
    try {
      const updated = await apiJson<GatewayRun>(`/api/v1/rpa-gateway/requests/${run.id}/decision`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ decision, notes: `Decision registrada por ${session?.user.email ?? "operador"}.` })
      });
      upsertRun(updated);
      activateRun(updated.id);
      setMessage(`${updated.platform_name}: ${updated.result_summary ?? updated.status}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo registrar la decision.");
    } finally {
      setIsBusy(false);
    }
  }

  async function launchVisibleBrowser(run: GatewayRun, manageBusy = true) {
    if (manageBusy) {
      setIsBusy(true);
    }
    try {
      const launch = await apiJson<BrowserLaunch>(`/api/v1/rpa-gateway/requests/${run.id}/launch-visible-browser`, {
        method: "POST"
      });
      const updatedRun = withBrowserLaunch(run, launch);
      upsertRun(updatedRun);
      activateRun(run.id);
      setBrowserStatus({
        run_id: run.id,
        available: launch.launched,
        state: launch.status,
        message: launch.message,
        updated_at_utc: null,
        platform_label: run.platform_name,
        entry_url: launch.entry_url
      });
      if (launch.launched) {
        setMessage(`${run.platform_name}: navegador visible lanzado. Sigue el estado del flujo en esta pantalla.`);
        await readBrowserStatus(run.id, false);
      } else {
        setMessage(`${run.platform_name}: ${launch.message}`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo lanzar el navegador guiado.");
    } finally {
      if (manageBusy) {
        setIsBusy(false);
      }
    }
  }

  async function readBrowserStatus(runId: number, showError = true) {
    try {
      const statusPayload = await apiJson<BrowserStatus>(`/api/v1/rpa-gateway/requests/${runId}/browser-status`);
      setBrowserStatus(statusPayload);
    } catch (error) {
      if (showError) {
        setMessage(error instanceof Error ? error.message : "No se pudo leer el estado del navegador.");
      }
    }
  }

  async function syncReadonlyCapture(run: GatewayRun) {
    setIsBusy(true);
    try {
      const syncResult = await apiJson<CaptureSync>(`/api/v1/rpa-gateway/requests/${run.id}/sync-readonly-capture`, {
        method: "POST"
      });
      setMessage(`${run.platform_name}: ${syncResult.message}`);
      await loadGateway();
      activateRun(run.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo sincronizar la lectura con el Hub.");
    } finally {
      setIsBusy(false);
    }
  }

  function upsertRun(run: GatewayRun) {
    setRequests((current) => [run, ...current.filter((item) => item.id !== run.id)]);
  }

  function activateRun(runId: number) {
    setActiveRunId(runId);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `/rpa-gateway?request=${runId}`);
    }
  }

  const recentRequests = activeRun ? requests.filter((request) => request.id !== activeRun.id) : requests;

  return (
    <main className="workspace full">
      <header className="topbar">
        <div>
          <p className="eyebrow">RPA asistida</p>
          <h2>Asistente de plataforma</h2>
        </div>
        <button className="iconButton" type="button" aria-label="Actualizar pasarela" onClick={() => void loadGateway()} disabled={isBusy}>
          <RefreshCw aria-hidden="true" size={18} />
        </button>
      </header>

      <div className={`messageBar ${message.includes("No se") || message.startsWith("HTTP") ? "error" : "ok"}`}>
        <span>{message}</span>
      </div>

      <section className="gatewayHero">
        <ShieldCheck aria-hidden="true" size={24} />
        <div>
          <p className="eyebrow">Separacion visual</p>
          <h3>Esta pantalla guia el flujo; la plataforma externa se abre en navegador visible</h3>
          <p>
            El Hub genera la revision, registra autorizacion humana, abre la web externa y muestra el estado
            del asistente. Captcha, MFA y avisos se resuelven manualmente; no hay bypass ni escrituras.
          </p>
        </div>
        <span className="statusBadge orange">human_action_required</span>
      </section>

      {activeRun ? (
        <ActiveFlowPanel
          browserStatus={browserStatus}
          isBusy={isBusy}
          onAuthorizeAndLaunch={() => void authorizeAndLaunch(activeRun)}
          onCancel={() => void decide(activeRun, "cancel")}
          onLaunchAgain={() => void launchVisibleBrowser(activeRun)}
          onResolve={() => void decide(activeRun, "human_control_resolved")}
          onSyncCapture={() => void syncReadonlyCapture(activeRun)}
          run={activeRun}
        />
      ) : (
        <section className="gatewayGrid">
          <article className="panel gatewayStartPanel">
            <div className="sectionTitle">
              <div>
                <p className="eyebrow">Inicio guiado</p>
                <h3>Selecciona plataforma y arranca el flujo completo</h3>
              </div>
              <PlayCircle aria-hidden="true" size={20} />
            </div>

            <label className="formField">
              <span>Plataforma</span>
              <select
                value={selectedScheduleId ?? ""}
                onChange={(event) => setSelectedScheduleId(Number(event.target.value))}
                disabled={isBusy}
              >
                {options?.schedules.map((schedule) => (
                  <option value={schedule.schedule_id} key={schedule.schedule_id}>
                    {schedule.platform_name} - {schedule.platform_slug}
                  </option>
                ))}
              </select>
            </label>

            <div className="gatewaySelectedPlatform">
              <strong>{selectedSchedule?.platform_name ?? "Sin plataforma seleccionada"}</strong>
              <span>{selectedSchedule?.platform_slug ?? "Selecciona una plataforma configurada."}</span>
              <small>
                Operacion fija: revisar estado documental en solo lectura. Credenciales configuradas en servidor.
              </small>
            </div>

            <label className="formField">
              <span>Nota opcional para auditoria</span>
              <textarea
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                placeholder="Ejemplo: revisar CTAIMA/SOFIDEL y verificar pendiente de EPIs sin modificar datos."
                rows={3}
              />
            </label>

            <button className="primaryButton" type="button" onClick={() => void createGuidedFlow()} disabled={isBusy || !selectedScheduleId}>
              Generar flujo y abrir navegador guiado
              <ExternalLink aria-hidden="true" size={15} />
            </button>
          </article>

          <OperatorPanel sessionName={session?.user.name} sessionEmail={session?.user.email} />
        </section>
      )}

      <section className="panel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Trazabilidad</p>
            <h3>Peticiones recientes</h3>
          </div>
          <span className="muted">{requests.length} registradas</span>
        </div>
        {recentRequests.length > 0 ? (
          <div className="gatewayRequestList compact">
            {recentRequests.slice(0, 10).map((run) => (
              <article className="gatewayRequest" key={run.id}>
                <div className="gatewayRequestHeader">
                  <div>
                    <strong>{run.platform_name}</strong>
                    <small>{run.platform_slug} / #{run.id}</small>
                  </div>
                  <span className={`statusBadge ${run.status}`}>{run.status}</span>
                </div>
                <div className="gatewayRequestBody">
                  <p>{run.result_summary ?? "Sin resumen"}</p>
                  <small>Cuenta: {run.evidence_json.gateway?.external_company_name ?? run.evidence_json.gateway?.external_account ?? "pendiente"}</small>
                  <small>Credenciales: configuradas en el servidor; no se piden al operador.</small>
                </div>
                <div className="scheduleActions">
                  <button className="secondaryButton" type="button" onClick={() => activateRun(run.id)}>
                    Abrir flujo
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="muted">No hay otras peticiones asistidas.</p>
        )}
      </section>
    </main>
  );
}

function ActiveFlowPanel({
  browserStatus,
  isBusy,
  onAuthorizeAndLaunch,
  onCancel,
  onLaunchAgain,
  onResolve,
  onSyncCapture,
  run
}: {
  browserStatus: BrowserStatus | null;
  isBusy: boolean;
  onAuthorizeAndLaunch: () => void;
  onCancel: () => void;
  onLaunchAgain: () => void;
  onResolve: () => void;
  onSyncCapture: () => void;
  run: GatewayRun;
}) {
  const gateway = run.evidence_json.gateway;
  const flow = gateway?.guided_flow;
  const browserLaunch = gateway?.browser_launch;
  const timeline = flowTimeline(run, browserStatus);
  const terminal = isTerminalRun(run);

  return (
    <section className="panel gatewayActivePanel">
      <div className="sectionTitle">
        <div>
          <p className="eyebrow">Flujo guiado actual</p>
          <h3>{flow?.title ?? run.platform_name}</h3>
        </div>
        <span className={`statusBadge ${run.status}`}>{run.status}</span>
      </div>

      <div className="gatewayActiveGrid">
        <div className="gatewayObjective">
          <ListChecks aria-hidden="true" size={20} />
          <div>
            <strong>Objetivo</strong>
            <p>{flow?.objective ?? "Revisar estado documental externo en solo lectura."}</p>
            {flow?.target_detail ? <small>{flow.target_detail}</small> : null}
          </div>
        </div>

        <div className="gatewayRuntime">
          <KeyRound aria-hidden="true" size={20} />
          <div>
            <strong>Cuenta y credenciales</strong>
            <span>{gateway?.external_company_name ?? gateway?.external_account ?? "Cuenta pendiente"}</span>
            <small>Credenciales: configuradas en el servidor; no se piden al operador.</small>
            <small>Host autorizado: {gateway?.allowed_external_host ?? "pendiente"}</small>
          </div>
        </div>
      </div>

      <div className="gatewayBrowserStatus">
        <Clock3 aria-hidden="true" size={18} />
        <div>
          <strong>Estado del navegador</strong>
          <span>{browserStatus?.message ?? browserLaunch?.message ?? "El navegador guiado aun no se ha lanzado."}</span>
          <small>{browserStatus?.state ?? browserLaunch?.status ?? "browser_not_started"}</small>
          {browserStatus?.selected_login_variant ? (
            <small>Variante login: {browserStatus.selected_login_variant}</small>
          ) : null}
          {sessionPersistence(browserStatus, browserLaunch)?.enabled ? (
            <small>{sessionPersistenceLabel(sessionPersistence(browserStatus, browserLaunch))}</small>
          ) : null}
        </div>
      </div>

      {browserStatus?.capture_summary ? (
        <div className="gatewayCaptureSummary">
          <strong>Lectura recogida</strong>
          <span>{browserStatus.capture_summary.pages_captured ?? 0} pantallas leidas en solo lectura.</span>
          <small>
            {browserStatus.capture_summary.persisted_row_level
              ? "Filas persistidas por entidad."
              : browserStatus.capture_summary.row_level_blocker ?? "Pendiente de mapeo para persistir filas por entidad."}
          </small>
          <small>{formatStatusCounts(browserStatus.capture_summary.status_counts)}</small>
        </div>
      ) : null}

      <div className="gatewayTimeline">
        {timeline.map((step) => (
          <div className={`gatewayTimelineStep ${step.state}`} key={step.label}>
            <span>{step.state === "done" ? <CheckCircle2 aria-hidden="true" size={15} /> : <Clock3 aria-hidden="true" size={15} />}</span>
            <div>
              <strong>{step.label}</strong>
              <small>{step.detail}</small>
            </div>
          </div>
        ))}
      </div>

      <div className="gatewayGuardrails">
        {(flow?.cannot_automate ?? []).map((item) => (
          <span key={item}>
            <AlertTriangle aria-hidden="true" size={13} />
            {item}
          </span>
        ))}
      </div>

      <div className="scheduleActions">
        {!gateway?.external_browser_authorized ? (
          <button className="primaryButton" type="button" onClick={onAuthorizeAndLaunch} disabled={isBusy || terminal}>
            Autorizar entrada y lanzar navegador guiado
            <ExternalLink aria-hidden="true" size={15} />
          </button>
        ) : (
          <button className="primaryButton" type="button" onClick={onLaunchAgain} disabled={isBusy || terminal}>
            Lanzar navegador guiado
            <ExternalLink aria-hidden="true" size={15} />
          </button>
        )}
        <button className="secondaryButton" type="button" onClick={onResolve} disabled={isBusy || terminal}>
          Marcar revision finalizada
        </button>
        <button className="secondaryButton" type="button" onClick={onSyncCapture} disabled={isBusy || !browserStatus?.capture_summary}>
          Sincronizar lectura con Hub
        </button>
        <button className="secondaryButton" type="button" onClick={onCancel} disabled={isBusy || terminal}>
          Cancelar flujo
        </button>
      </div>
    </section>
  );
}

function OperatorPanel({ sessionName, sessionEmail }: { sessionName?: string; sessionEmail?: string }) {
  return (
    <article className="panel">
      <div className="sectionTitle">
        <div>
          <p className="eyebrow">Operador</p>
          <h3>Validacion humana</h3>
        </div>
        <AlertTriangle aria-hidden="true" size={20} />
      </div>
      <div className="gatewayOperator">
        <strong>{sessionName ?? "Sesion no identificada"}</strong>
        <span>{sessionEmail ?? "El operador debe iniciar sesion."}</span>
        <small>El usuario que pulse los botones queda en auditoria del backend.</small>
      </div>
      <ul className="gatewayChecklist">
        <li>El flujo abre solo la plataforma y cuenta seleccionadas.</li>
        <li>Resolver captcha/MFA manualmente, delante de pantalla.</li>
        <li>No subir ficheros ni cambiar datos en una revision de estado.</li>
        <li>Volver al Hub y registrar el resultado.</li>
      </ul>
    </article>
  );
}

function flowTimeline(run: GatewayRun, browserStatus: BrowserStatus | null): FlowStep[] {
  const gateway = run.evidence_json.gateway;
  const browserLaunched = Boolean(gateway?.browser_launch?.launched);
  const authorized = Boolean(gateway?.external_browser_authorized);
  const terminal = isTerminalRun(run);
  const humanControlActive =
    browserStatus?.state === "human_control_required" ||
    browserStatus?.state === "waiting_for_login_form" ||
    browserStatus?.state === "credentials_submitted" ||
    browserStatus?.state === "browser_open_for_operator";

  return [
    {
      label: "Flujo generado",
      detail: `Peticion #${run.id} creada en el Hub.`,
      state: "done"
    },
    {
      label: "Cuenta confirmada",
      detail: gateway?.external_company_name ?? gateway?.external_account ?? "Cuenta pendiente.",
      state: gateway?.allowed_external_url ? "done" : "blocked"
    },
    {
      label: "Autorizar entrada",
      detail: "La autorizacion queda registrada antes de abrir la web externa.",
      state: authorized ? "done" : "active"
    },
    {
      label: "Abrir navegador visible",
      detail: gateway?.allowed_external_url ?? "URL pendiente.",
      state: browserLaunched ? "done" : authorized ? "active" : "pending"
    },
    {
      label: "Validacion humana",
      detail: browserStatus?.message ?? "Captcha, MFA o avisos se resuelven manualmente si aparecen.",
      state: terminal ? "done" : humanControlActive ? "active" : browserLaunched ? "active" : "pending"
    },
    {
      label: "Registrar resultado",
      detail: run.result_summary ?? "Cuando termines en la plataforma, marca la revision finalizada.",
      state: terminal ? "done" : "pending"
    }
  ];
}

function preferredScheduleId(schedules: GatewaySchedule[]) {
  return schedules.find((schedule) => schedule.platform_slug === "ctaima")?.schedule_id ?? schedules[0]?.schedule_id ?? null;
}

function queryRequestId() {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = new URLSearchParams(window.location.search).get("request");
  if (!raw) {
    return null;
  }
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
}

function isTerminalRun(run: GatewayRun) {
  return run.status === "completed_with_warnings" || run.status === "completed" || run.status === "cancelled";
}

function withBrowserLaunch(run: GatewayRun, launch: BrowserLaunch): GatewayRun {
  return {
    ...run,
    evidence_json: {
      ...run.evidence_json,
      gateway: {
        ...(run.evidence_json.gateway ?? {}),
        browser_launch: launch,
        external_browser_authorized: run.evidence_json.gateway?.external_browser_authorized || launch.launched
      }
    }
  };
}

function formatStatusCounts(items: unknown[] | undefined) {
  if (!Array.isArray(items) || items.length === 0) {
    return "Sin conteos de estado detectados todavia.";
  }
  return items
    .map((item) => {
      if (!Array.isArray(item) || item.length < 2) {
        return null;
      }
      return `${String(item[0])}: ${String(item[1])}`;
    })
    .filter((item): item is string => Boolean(item))
    .join(" · ");
}

function sessionPersistence(status: BrowserStatus | null, launch: BrowserLaunch | undefined) {
  return status?.session_persistence ?? launch?.session_persistence ?? null;
}

function sessionPersistenceLabel(session: SessionPersistence | null) {
  if (!session?.enabled) {
    return "Sesion no persistente.";
  }
  return session.profile_reused
    ? "Sesion local reutilizada para esta cuenta."
    : "Sesion local creada para reutilizar esta cuenta.";
}
