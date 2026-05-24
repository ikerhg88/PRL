"use client";

import {
  AlertTriangle,
  CheckCircle2,
  FileUp,
  GripVertical,
  ExternalLink,
  RefreshCw,
  Send,
  UserPlus,
  UsersRound
} from "lucide-react";
import { DragEvent, useEffect, useMemo, useState } from "react";

import { apiJson, jsonHeaders } from "../../lib/apiClient";

type StatusColor = "green" | "orange" | "red";

type Worker = {
  id: number;
  company_id: number;
  first_name: string;
  last_name: string;
  identifier_last4: string | null;
  nationality: string | null;
  contract_type: string | null;
  work_position: string | null;
  email: string | null;
  phone: string | null;
  social_security_last4: string | null;
  status: string;
};

type DocumentRecord = {
  id: number;
  entity_type: string;
  entity_id: number;
  current_version_id: number | null;
  status_internal: string;
};

type PlatformRpaManifest = {
  id: number;
  external_platform_id: number | null;
  platform_slug: string;
  platform_name: string;
  hosts: string[];
};

type PlatformRpaAccountProposal = {
  id: number;
  manifest_id: number;
  external_platform_id: number | null;
  platform_account_id: number | null;
  external_company_name: string | null;
  host: string | null;
  status: string;
};

type PlatformReviewSchedule = {
  id: number;
  manifest_id: number;
  platform_slug: string;
  platform_name: string;
  enabled: boolean;
};

type PlatformDataCoverageContext = {
  manifest_id: number;
  account_proposal_id: number | null;
  platform_slug: string;
  platform_name: string;
  external_company_name: string | null;
  trace_label: string;
  host: string | null;
  pending_summary: {
    total: number;
    red: number;
    orange: number;
  };
};

type PlatformDataCoverage = {
  contexts: PlatformDataCoverageContext[];
};

type Transfer = {
  id: number;
  status: string;
  connector_key: string;
  operation: string;
  last_attempt_status?: string | null;
  last_attempt_message?: string | null;
  post_write_read_confirmed?: boolean | null;
  valid_external_write?: boolean | null;
};

type PlatformReviewRun = {
  id: number;
  platform_slug: string;
  platform_name: string;
  account_proposal_id: number | null;
  operation: string;
  result_status?: string | null;
};

type CaptureAction = {
  requestId: number;
  platformName: string;
  targetTitle: string;
  workerName: string;
  url: string;
};

type CreatedTransferRow = {
  target: PlatformTarget;
  transfer: Transfer;
  kind: "worker" | "document";
};

type WorkerPlatformRegistration = {
  id: number;
  worker_id: number;
  platform_account_id: number | null;
  external_platform_id: number | null;
  platform_name: string;
  registration_status: string;
  assignment_scope: string | null;
  source: string;
  last_synced_at: string | null;
  notes: string | null;
};

type MassUpdateActionBlocker = {
  kind: string;
  standard_key?: string;
  detail: string;
};

type MassUpdateAction = {
  action_id: string;
  operation: string;
  account_proposal_id: number;
  platform_slug: string;
  platform_name: string;
  external_company_name: string | null;
  live_adapter_status: string | null;
  preview_status: string;
  ready_for_submit: boolean;
  capture_recommended: boolean;
  blockers: MassUpdateActionBlocker[];
  next_action: string;
};

type MassUpdatePlan = {
  summary: {
    actions: number;
    ready_for_submit: number;
    blocked: number;
    capture_recommended: number;
    with_live_helper: number;
    by_preview_status: Record<string, number>;
  };
  actions: MassUpdateAction[];
};

type PlatformTarget = {
  key: string;
  manifest: PlatformRpaManifest;
  account: PlatformRpaAccountProposal | null;
  schedule: PlatformReviewSchedule | null;
  coverage: PlatformDataCoverageContext | null;
  title: string;
  subtitle: string;
  active: boolean;
  status: StatusColor;
};

type TargetAssignmentState = {
  kind: "available" | "existing" | "disabled" | "unsupported";
  label: string;
  detail: string;
  color: StatusColor;
  registration: WorkerPlatformRegistration | null;
};

const CONNECTOR_BY_SLUG: Record<string, string> = {
  ctaima: "connector_rpa_ctaima_write",
  e_coordina: "connector_rpa_e_coordina_write",
  nomio: "connector_rpa_nomio_write",
  seisconecta: "connector_rpa_seisconecta_write",
  timenet: "connector_rpa_timenet_write",
  validate: "connector_rpa_validate_write",
  vitaly_cae: "connector_rpa_vitaly_cae_write"
};

const PLATFORM_KEY_BY_SLUG: Record<string, string> = {
  ctaima: "ctaima_cae",
  e_coordina: "ecoordina",
  nomio: "nomio",
  seisconecta: "sixconecta",
  timenet: "timenet",
  validate: "validate",
  vitaly_cae: "vitaly_cae"
};

const BLOCKING_REGISTRATION_STATUSES = new Set([
  "accepted",
  "accepted_with_warnings",
  "confirmed",
  "submitted",
  "submitted_pending_readback",
  "pending_external_validation",
  "review_required",
  "missing_required_document"
]);

export default function AssignWorkerPage() {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [manifests, setManifests] = useState<PlatformRpaManifest[]>([]);
  const [accounts, setAccounts] = useState<PlatformRpaAccountProposal[]>([]);
  const [schedules, setSchedules] = useState<PlatformReviewSchedule[]>([]);
  const [coverage, setCoverage] = useState<PlatformDataCoverage | null>(null);
  const [registrationsByWorker, setRegistrationsByWorker] = useState<Record<number, WorkerPlatformRegistration[]>>({});
  const [writePlan, setWritePlan] = useState<MassUpdatePlan | null>(null);
  const [writePlanLoading, setWritePlanLoading] = useState(false);
  const [selectedWorkerId, setSelectedWorkerId] = useState<number | null>(null);
  const [workerFilter, setWorkerFilter] = useState("");
  const [message, setMessage] = useState("Cargando trabajadores y plataformas.");
  const [busy, setBusy] = useState(false);
  const [hoverTargetKey, setHoverTargetKey] = useState<string | null>(null);
  const [captureActions, setCaptureActions] = useState<CaptureAction[]>([]);

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    void loadSelectedWorkerWritePlan();
  }, [selectedWorkerId]);

  async function loadData() {
    setBusy(true);
    setCaptureActions([]);
    try {
      const scheduleRows = await apiJson<PlatformReviewSchedule[]>("/api/v1/platform-review-schedules/ensure?priority_group=all", {
        method: "POST"
      });
      const [workerRows, documentRows, manifestRows, accountRows, coverageRows] = await Promise.all([
        apiJson<Worker[]>("/api/v1/workers"),
        apiJson<DocumentRecord[]>("/api/v1/documents"),
        apiJson<PlatformRpaManifest[]>("/api/v1/platform-contracts/manifests"),
        apiJson<PlatformRpaAccountProposal[]>("/api/v1/platform-contracts/accounts"),
        apiJson<PlatformDataCoverage>("/api/v1/platform-maps/data-coverage?priority_group=all")
      ]);
      const registrationRows = await Promise.all(
        workerRows.map(async (worker) => [
          worker.id,
          await apiJson<WorkerPlatformRegistration[]>(`/api/v1/workers/${worker.id}/platform-registrations`)
        ] as const)
      );
      setWorkers(workerRows);
      setDocuments(documentRows);
      setManifests(manifestRows);
      setAccounts(accountRows);
      setSchedules(scheduleRows);
      setCoverage(coverageRows);
      setRegistrationsByWorker(Object.fromEntries(registrationRows));
      setSelectedWorkerId(workerRows[0]?.id ?? null);
      setMessage(`Listo: ${workerRows.length} trabajadores y ${scheduleRows.filter((item) => item.enabled).length} plataformas activas.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo cargar la pantalla.");
    } finally {
      setBusy(false);
    }
  }

  const targets = useMemo(
    () => buildTargets({ manifests, accounts, schedules, coverage }),
    [accounts, coverage, manifests, schedules]
  );
  const activeTargets = targets.filter((target) => target.active);
  const filteredWorkers = workers.filter((worker) => workerName(worker).toLowerCase().includes(workerFilter.toLowerCase().trim()));
  const selectedWorker = workers.find((worker) => worker.id === selectedWorkerId) ?? null;
  const selectedWorkerDocuments = selectedWorker ? workerDocuments(documents, selectedWorker.id) : [];
  const selectedTargetStates = selectedWorker
    ? targets.map((target) => targetStateForWorker(selectedWorker, target, registrationsByWorker[selectedWorker.id] ?? []))
    : [];
  const selectedAvailableCount = selectedTargetStates.filter((state) => state.kind === "available").length;
  const selectedExistingCount = selectedTargetStates.filter((state) => state.kind === "existing").length;
  const selectedWorkerMissingFields = selectedWorker ? missingProfileFields(selectedWorker) : [];

  function onWorkerDragStart(event: DragEvent<HTMLButtonElement>, worker: Worker) {
    event.dataTransfer.setData("text/plain", String(worker.id));
    setSelectedWorkerId(worker.id);
  }

  async function onDropWorker(event: DragEvent<HTMLElement>, target: PlatformTarget) {
    event.preventDefault();
    setHoverTargetKey(null);
    const workerId = Number(event.dataTransfer.getData("text/plain")) || selectedWorkerId;
    if (!workerId) {
      setMessage("Selecciona o arrastra un trabajador.");
      return;
    }
    const worker = workers.find((item) => item.id === workerId);
    if (worker) {
      const state = targetStateForWorker(worker, target, registrationsByWorker[worker.id] ?? []);
      if (state.kind !== "available") {
        setMessage(`${workerName(worker)} no se puede enviar a ${target.title}: ${state.detail}`);
        return;
      }
    }
    await assignWorkerToTargets(workerId, [target]);
  }

  async function assignSelectedToAll() {
    if (!selectedWorkerId) {
      setMessage("Selecciona un trabajador.");
      return;
    }
    const worker = workers.find((item) => item.id === selectedWorkerId);
    const availableTargets = worker
      ? activeTargets.filter((target) => targetStateForWorker(worker, target, registrationsByWorker[worker.id] ?? []).kind === "available")
      : activeTargets;
    await assignWorkerToTargets(selectedWorkerId, availableTargets);
  }

  async function assignWorkerToTargets(workerId: number, targetRows: PlatformTarget[]) {
    const worker = workers.find((item) => item.id === workerId);
    if (!worker) {
      setMessage("Trabajador no encontrado.");
      return;
    }
    const workerRegistrations = registrationsByWorker[worker.id] ?? [];
    const enabledTargets = targetRows.filter((target) => {
      const state = targetStateForWorker(worker, target, workerRegistrations);
      return state.kind === "available";
    });
    if (!enabledTargets.length) {
      const firstBlocked = targetRows[0] ? targetStateForWorker(worker, targetRows[0], workerRegistrations) : null;
      setMessage(firstBlocked ? `${workerName(worker)} no se puede enviar: ${firstBlocked.detail}` : "No hay plataformas activas disponibles para este envio.");
      return;
    }
    setBusy(true);
    setCaptureActions([]);
    try {
      const createdRows: CreatedTransferRow[] = [];
      const docs = workerDocuments(documents, workerId);
      for (const target of enabledTargets) {
        createdRows.push({ target, transfer: await createWorkerTransfer(workerId, target), kind: "worker" });
        for (const document of docs) {
          if (document.current_version_id) {
            createdRows.push({
              target,
              transfer: await createDocumentTransfer(document.current_version_id, target),
              kind: "document"
            });
          }
        }
      }
      const captureRows = await createCaptureRequestsForBlockedWorkerTransfers(createdRows, worker);
      setCaptureActions(captureRows);
      const skipped = targetRows.length - enabledTargets.length;
      setMessage(buildTransferOutcomeMessage(workerName(worker), enabledTargets.length, createdRows.map((row) => row.transfer), skipped, captureRows.length));
      await refreshWorkerRegistrations(worker.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo preparar la asignacion.");
    } finally {
      setBusy(false);
    }
  }

  async function createCaptureRequestsForBlockedWorkerTransfers(rows: CreatedTransferRow[], worker: Worker) {
    const blockedTargets = uniqueTargets(
      rows
        .filter((row) => row.kind === "worker" && isBlockedTransfer(row.transfer) && row.target.account)
        .map((row) => row.target)
    );
    const created: CaptureAction[] = [];
    for (const target of blockedTargets) {
      const accountId = target.account?.id;
      if (!accountId) {
        continue;
      }
      const run = await apiJson<PlatformReviewRun>(`/api/v1/exchange/${accountId}/capture-write-screen`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          operation: "upsert_worker",
          request_comment: `Mapear alta de ${workerName(worker)} en ${target.title}. No guardar cambios ni subir ficheros.`
        })
      });
      created.push({
        requestId: run.id,
        platformName: run.platform_name,
        targetTitle: target.title,
        workerName: workerName(worker),
        url: `/rpa-gateway?request=${run.id}`
      });
    }
    return created;
  }

  async function refreshWorkerRegistrations(workerId: number) {
    const rows = await apiJson<WorkerPlatformRegistration[]>(`/api/v1/workers/${workerId}/platform-registrations`);
    setRegistrationsByWorker((current) => ({ ...current, [workerId]: rows }));
  }

  async function loadSelectedWorkerWritePlan() {
    const worker = workers.find((item) => item.id === selectedWorkerId);
    if (!worker) {
      setWritePlan(null);
      return;
    }
    setWritePlanLoading(true);
    try {
      const plan = await apiJson<MassUpdatePlan>("/api/v1/exchange/mass-update/plan", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          company_id: worker.company_id,
          worker_ids: [worker.id],
          include_missing_workers: true,
          include_document_requests: false,
          only_active_contexts: true,
          limit: 100
        })
      });
      setWritePlan(plan);
    } catch {
      setWritePlan(null);
    } finally {
      setWritePlanLoading(false);
    }
  }

  async function createWorkerTransfer(workerId: number, target: PlatformTarget) {
    return apiJson<Transfer>("/api/v1/transfers", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({
        platform_key: PLATFORM_KEY_BY_SLUG[target.manifest.platform_slug],
        connector_key: CONNECTOR_BY_SLUG[target.manifest.platform_slug],
        operation: "upsert_worker",
        worker_id: workerId,
        account_proposal_id: target.account?.id ?? null,
        dry_run: true,
        manual_approval_required: true
      })
    });
  }

  async function createDocumentTransfer(documentVersionId: number, target: PlatformTarget) {
    return apiJson<Transfer>("/api/v1/transfers", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({
        platform_key: PLATFORM_KEY_BY_SLUG[target.manifest.platform_slug],
        connector_key: CONNECTOR_BY_SLUG[target.manifest.platform_slug],
        operation: "upload_worker_document",
        document_version_id: documentVersionId,
        account_proposal_id: target.account?.id ?? null,
        dry_run: true,
        manual_approval_required: true
      })
    });
  }

  return (
    <main className="workspace full">
      <header className="topbar">
        <div>
          <p className="eyebrow">Operacion</p>
          <h2>Anadir trabajador a plataforma</h2>
        </div>
        <button className="iconButton" type="button" aria-label="Actualizar" onClick={() => void loadData()} disabled={busy}>
          <RefreshCw aria-hidden="true" size={18} />
        </button>
      </header>

      <div className={`messageBar ${isErrorMessage(message) ? "error" : "ok"}`}>
        <span>{message}</span>
      </div>

      {captureActions.length > 0 ? (
        <section className="panel actionPanel">
          <div className="sectionTitle">
            <div>
              <p className="eyebrow">Siguiente paso</p>
              <h3>Pasarela de mapeo creada</h3>
            </div>
            <ExternalLink aria-hidden="true" size={18} />
          </div>
          <div className="platformDropList compact">
            {captureActions.map((action) => (
              <article className="platformDropTarget assignment-available" key={action.requestId}>
                <div>
                  <strong>{action.platformName} / {action.workerName}</strong>
                  <small>{action.targetTitle}</small>
                  <small>Abre la pasarela, entra con credenciales configuradas y captura la pantalla editable sin guardar cambios.</small>
                </div>
                <a className="secondaryButton inlineButton" href={action.url} target="_blank" rel="noreferrer">
                  <ExternalLink aria-hidden="true" size={14} />
                  Abrir pasarela #{action.requestId}
                </a>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="splitPanels platformAssignLayout">
        <div className="panel">
          <div className="sectionTitle">
            <div>
              <p className="eyebrow">Trabajadores</p>
              <h3>Selecciona o arrastra</h3>
            </div>
            <UsersRound aria-hidden="true" size={20} />
          </div>
          <label className="field">
            <span>Buscar trabajador</span>
            <input value={workerFilter} onChange={(event) => setWorkerFilter(event.target.value)} placeholder="Nombre o apellido" />
          </label>
          <div className="workerDragList">
            {filteredWorkers.map((worker) => {
              const selected = worker.id === selectedWorkerId;
              return (
                <button
                  className={`workerDragItem ${selected ? "selectedCard" : ""}`}
                  type="button"
                  draggable
                  onDragStart={(event) => onWorkerDragStart(event, worker)}
                  onClick={() => setSelectedWorkerId(worker.id)}
                  key={worker.id}
                >
                  <GripVertical aria-hidden="true" size={16} />
                  <span>
                    <strong>{workerName(worker)}</strong>
                    <small>{worker.work_position ?? "Sin puesto"} / {worker.identifier_last4 ? `****${worker.identifier_last4}` : "ID pendiente"}</small>
                    <span className="workerAssignmentMeta">
                      {workerAssignmentSummary(worker, targets, registrationsByWorker[worker.id] ?? [])}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="panel">
          <div className="sectionTitle">
            <div>
              <p className="eyebrow">Destino</p>
              <h3>Enviar a plataformas activas</h3>
            </div>
            <button className="primaryButton inlineButton" type="button" onClick={() => void assignSelectedToAll()} disabled={busy || !selectedWorker || activeTargets.length === 0}>
              <Send aria-hidden="true" size={16} />
              Anadir a todas
            </button>
          </div>
          <div className="selectedWorkerBand">
            <UserPlus aria-hidden="true" size={18} />
            <span>
              <strong>{selectedWorker ? workerName(selectedWorker) : "Sin trabajador seleccionado"}</strong>
              <small>
                {selectedWorkerDocuments.length} documento(s) con version actual. {selectedWorker ? `${selectedAvailableCount} destino(s) disponibles, ${selectedExistingCount} ya existentes.` : ""}
              </small>
            </span>
          </div>
          {selectedWorker ? (
            <section className="writeReadinessBox">
              <div>
                <strong>Preparacion escritura real</strong>
                <small>
                  {writePlanLoading
                    ? "Analizando previews por plataforma..."
                    : writePlan
                      ? `${writePlan.summary.ready_for_submit} listo(s), ${writePlan.summary.blocked} bloqueado(s), ${writePlan.summary.with_live_helper} con helper live.`
                      : "No se pudo calcular el plan de escritura."}
                </small>
              </div>
              {selectedWorkerMissingFields.length ? (
                <div className="readinessWarning">
                  <AlertTriangle aria-hidden="true" size={15} />
                  <span>
                    Ficha ARM incompleta: {selectedWorkerMissingFields.join(", ")}.
                    <a href={`/arm?worker=${selectedWorker.id}`}> Completar en ARM</a>
                  </span>
                </div>
              ) : null}
              {writePlan ? <WritePlanSummary plan={writePlan} /> : null}
            </section>
          ) : null}
          <div className="platformDropList">
            {targets.map((target) => {
              const state = selectedWorker
                ? targetStateForWorker(selectedWorker, target, registrationsByWorker[selectedWorker.id] ?? [])
                : emptySelectionState(target);
              const canAssign = Boolean(selectedWorkerId) && state.kind === "available";
              return (
                <article
                  className={`platformDropTarget assignment-${state.kind} ${hoverTargetKey === target.key ? "dropHover" : ""}`}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setHoverTargetKey(target.key);
                  }}
                  onDragLeave={() => setHoverTargetKey(null)}
                  onDrop={(event) => void onDropWorker(event, target)}
                  key={target.key}
                >
                  <div>
                    <strong>{target.title}</strong>
                    <small>{target.subtitle}</small>
                    <small>{state.detail}</small>
                  </div>
                  <div className="platformDropActions">
                    {renderStatus(state.color, state.label)}
                    <button className="secondaryButton inlineButton" type="button" onClick={() => selectedWorkerId && void assignWorkerToTargets(selectedWorkerId, [target])} disabled={busy || !canAssign}>
                      <FileUp aria-hidden="true" size={14} />
                      {state.kind === "existing" ? "Ya existe" : state.kind === "available" ? "Anadir aqui" : "No disponible"}
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      </section>
    </main>
  );
}

function buildTargets({
  manifests,
  accounts,
  schedules,
  coverage
}: {
  manifests: PlatformRpaManifest[];
  accounts: PlatformRpaAccountProposal[];
  schedules: PlatformReviewSchedule[];
  coverage: PlatformDataCoverage | null;
}): PlatformTarget[] {
  const accountsByManifest = new Map<number, PlatformRpaAccountProposal[]>();
  for (const account of accounts) {
    accountsByManifest.set(account.manifest_id, [...(accountsByManifest.get(account.manifest_id) ?? []), account]);
  }
  const scheduleByManifest = new Map(schedules.map((schedule) => [schedule.manifest_id, schedule]));
  const coverageByAccount = new Map((coverage?.contexts ?? []).map((context) => [`${context.manifest_id}:${context.account_proposal_id ?? "none"}`, context]));
  return manifests.flatMap((manifest) => {
    const manifestAccounts = accountsByManifest.get(manifest.id) ?? [null];
    return manifestAccounts.map((account) => {
      const schedule = scheduleByManifest.get(manifest.id) ?? null;
      const coverageContext = coverageByAccount.get(`${manifest.id}:${account?.id ?? "none"}`) ?? null;
      const active = Boolean(schedule?.enabled);
      const critical = coverageContext?.pending_summary.red ?? 0;
      const warnings = coverageContext?.pending_summary.orange ?? 0;
      return {
        key: `${manifest.id}:${account?.id ?? "none"}`,
        manifest,
        account,
        schedule,
        coverage: coverageContext,
        title: coverageContext?.trace_label ?? `${manifest.platform_name} / ${account?.external_company_name ?? "sin empresa externa"}`,
        subtitle: account?.host ?? coverageContext?.host ?? manifest.hosts[0] ?? "host pendiente",
        active,
        status: active ? (critical > 0 ? "red" : warnings > 0 ? "orange" : "green") : "orange"
      };
    });
  });
}

function workerDocuments(documents: DocumentRecord[], workerId: number) {
  return documents.filter((document) => document.entity_type === "worker" && document.entity_id === workerId && document.current_version_id);
}

function targetStateForWorker(worker: Worker, target: PlatformTarget, registrations: WorkerPlatformRegistration[]): TargetAssignmentState {
  if (!target.active) {
    return {
      kind: "disabled",
      label: "desactivada",
      detail: "No genera avisos ni se revisa; no se preparan altas.",
      color: "orange",
      registration: null
    };
  }
  if (!CONNECTOR_BY_SLUG[target.manifest.platform_slug]) {
    return {
      kind: "unsupported",
      label: "sin conector",
      detail: "Hay contexto activo, pero aun no hay conector de escritura para este flujo.",
      color: "orange",
      registration: null
    };
  }
  const registration = registrationForTarget(target, registrations);
  if (registration && BLOCKING_REGISTRATION_STATUSES.has(registration.registration_status)) {
    return {
      kind: "existing",
      label: "ya existe",
      detail: `Alta ya localizada para ${workerName(worker)}. Estado: ${registration.registration_status}${registration.assignment_scope ? ` / ${registration.assignment_scope}` : ""}.`,
      color: registrationStatusColor(registration.registration_status),
      registration
    };
  }
  return {
    kind: "available",
    label: "disponible",
    detail: "No consta alta previa para este trabajador en esta plataforma/cuenta.",
    color: "green",
    registration: null
  };
}

function emptySelectionState(target: PlatformTarget): TargetAssignmentState {
  if (!target.active) {
    return {
      kind: "disabled",
      label: "desactivada",
      detail: "Selecciona un trabajador; esta plataforma esta desactivada.",
      color: "orange",
      registration: null
    };
  }
  if (!CONNECTOR_BY_SLUG[target.manifest.platform_slug]) {
    return {
      kind: "unsupported",
      label: "sin conector",
      detail: "Selecciona un trabajador; este contexto aun no tiene conector de escritura.",
      color: "orange",
      registration: null
    };
  }
  return {
    kind: "available",
    label: "pendiente seleccionar",
    detail: "Selecciona un trabajador para comprobar si ya existe.",
    color: "orange",
    registration: null
  };
}

function registrationForTarget(target: PlatformTarget, registrations: WorkerPlatformRegistration[]) {
  const targetPlatformAccountId = target.account?.platform_account_id ?? null;
  if (targetPlatformAccountId !== null) {
    return registrations.find((registration) => registration.platform_account_id === targetPlatformAccountId) ?? null;
  }
  const externalPlatformId = target.account?.external_platform_id ?? target.manifest.external_platform_id ?? null;
  if (externalPlatformId !== null) {
    return registrations.find((registration) => registration.external_platform_id === externalPlatformId) ?? null;
  }
  return registrations.find((registration) => normalizePlatformName(registration.platform_name).includes(normalizePlatformName(target.manifest.platform_name))) ?? null;
}

function registrationStatusColor(status: string): StatusColor {
  const normalized = status.toLowerCase();
  if (/(accepted|active|valid|synced|ok|confirmed)/.test(normalized)) {
    return "green";
  }
  if (/(caduc|expired|reject|blocked|missing|deleted|inactive)/.test(normalized)) {
    return "red";
  }
  return "orange";
}

function normalizePlatformName(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function workerAssignmentSummary(worker: Worker, targets: PlatformTarget[], registrations: WorkerPlatformRegistration[]) {
  const supportedTargets = targets.filter((target) => target.active && CONNECTOR_BY_SLUG[target.manifest.platform_slug]);
  const states = supportedTargets.map((target) => targetStateForWorker(worker, target, registrations));
  const existing = states.filter((state) => state.kind === "existing").length;
  const available = states.filter((state) => state.kind === "available").length;
  return `${available} disponibles / ${existing} ya existentes`;
}

function uniqueTargets(targets: PlatformTarget[]) {
  const seen = new Set<string>();
  const rows: PlatformTarget[] = [];
  for (const target of targets) {
    if (seen.has(target.key)) {
      continue;
    }
    seen.add(target.key);
    rows.push(target);
  }
  return rows;
}

function missingProfileFields(worker: Worker) {
  const fields: string[] = [];
  if (!worker.identifier_last4) {
    fields.push("DNI/NIE");
  }
  if (!worker.nationality) {
    fields.push("nacionalidad");
  }
  if (!worker.contract_type) {
    fields.push("contrato");
  }
  if (!worker.work_position) {
    fields.push("puesto");
  }
  if (!worker.social_security_last4) {
    fields.push("numero SS");
  }
  return fields;
}

function WritePlanSummary({ plan }: { plan: MassUpdatePlan }) {
  const blockerCounts = new Map<string, number>();
  for (const action of plan.actions) {
    if (action.ready_for_submit) {
      continue;
    }
    const key = action.preview_status === "blocked_local_data_required"
      ? "faltan datos ARM"
      : action.preview_status === "blocked_mapping_review_required"
        ? "falta mapeo editable"
        : action.preview_status === "blocked_no_write_connector"
          ? "sin conector"
          : action.preview_status;
    blockerCounts.set(key, (blockerCounts.get(key) ?? 0) + 1);
  }
  const topBlockers = [...blockerCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
  const liveBlocked = plan.actions.find((action) => action.live_adapter_status === "specific_live_adapter_available" && !action.ready_for_submit);
  return (
    <div className="writePlanSummary">
      {topBlockers.map(([label, count]) => (
        <span className="statusBadge orange" key={label}>{count} {label}</span>
      ))}
      {liveBlocked ? (
        <small>
          Helper live bloqueado en {liveBlocked.platform_name}: {firstBlockerDetail(liveBlocked)}
        </small>
      ) : null}
    </div>
  );
}

function firstBlockerDetail(action: MassUpdateAction) {
  const first = action.blockers[0];
  if (!first) {
    return action.next_action;
  }
  if (first.standard_key) {
    return `${first.standard_key}: ${first.detail}`;
  }
  return first.detail;
}

function buildTransferOutcomeMessage(workerLabel: string, targetCount: number, jobs: Transfer[], skipped: number, captureRequestCount = 0) {
  const blockedJobs = jobs.filter(isBlockedTransfer);
  const confirmedJobs = jobs.filter(isConfirmedTransfer);
  const skippedText = skipped ? ` ${skipped} destino(s) omitidos por existente/desactivado/sin conector.` : "";
  const captureText = captureRequestCount ? ` Pasarela(s) de mapeo creadas: ${captureRequestCount}.` : "";
  if (blockedJobs.length) {
    const firstReason = blockedJobs.find((job) => job.last_attempt_message)?.last_attempt_message ?? blockedStatusReason(blockedJobs[0]);
    return `Bloqueado: ${workerLabel} tiene ${jobs.length} job(s) preparados para ${targetCount} plataforma(s), pero ${blockedJobs.length} no se han escrito fuera. ${firstReason}${captureText}${skippedText}`;
  }
  if (confirmedJobs.length) {
    return `${workerLabel} confirmado en ${targetCount} plataforma(s): ${confirmedJobs.length} escritura(s) con lectura posterior. ${jobs.length - confirmedJobs.length} job(s) restantes preparados.${skippedText}`;
  }
  return `${workerLabel} preparado para ${targetCount} plataforma(s): ${jobs.length} job(s) creados. Pendiente de ejecucion/confirmacion externa.${skippedText || " Sin duplicados detectados."}`;
}

function isBlockedTransfer(job: Transfer) {
  const status = `${job.status} ${job.last_attempt_status ?? ""}`.toLowerCase();
  return status.includes("blocked") || status.includes("mapping_review_required") || status.includes("live_adapter_missing");
}

function isConfirmedTransfer(job: Transfer) {
  const status = `${job.status} ${job.last_attempt_status ?? ""}`.toLowerCase();
  return status.includes("confirmed_external") || job.post_write_read_confirmed === true;
}

function blockedStatusReason(job: Transfer) {
  if (job.status.includes("mapping_review_required")) {
    return "Faltan mapeos/editable capture aprobados para poder ejecutar escritura real.";
  }
  if (job.status.includes("live_adapter_missing")) {
    return "Falta helper live especifico con lectura previa, submit y lectura posterior.";
  }
  return `Estado: ${job.status}.`;
}

function workerName(worker: Worker) {
  return `${worker.first_name} ${worker.last_name}`.trim();
}

function renderStatus(status: StatusColor, label: string) {
  const Icon = status === "green" ? CheckCircle2 : AlertTriangle;
  return (
    <span className={`statusBadge ${status}`}>
      <Icon aria-hidden="true" size={13} />
      {label}
    </span>
  );
}

function isErrorMessage(message: string) {
  return message.startsWith("HTTP") || message.startsWith("No se") || message.startsWith("Invalid") || message.startsWith("Bloqueado") || message.includes("error") || message.includes("token");
}
