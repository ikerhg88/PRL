"use client";

import {
  AlertTriangle,
  CheckCircle2,
  FileUp,
  GripVertical,
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
  work_position: string | null;
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
  const [selectedWorkerId, setSelectedWorkerId] = useState<number | null>(null);
  const [workerFilter, setWorkerFilter] = useState("");
  const [message, setMessage] = useState("Cargando trabajadores y plataformas.");
  const [busy, setBusy] = useState(false);
  const [hoverTargetKey, setHoverTargetKey] = useState<string | null>(null);

  useEffect(() => {
    void loadData();
  }, []);

  async function loadData() {
    setBusy(true);
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
    try {
      let created = 0;
      const docs = workerDocuments(documents, workerId);
      for (const target of enabledTargets) {
        await createWorkerTransfer(workerId, target);
        created += 1;
        for (const document of docs) {
          if (document.current_version_id) {
            await createDocumentTransfer(document.current_version_id, target);
            created += 1;
          }
        }
      }
      const skipped = targetRows.length - enabledTargets.length;
      setMessage(`${workerName(worker)} enviado a ${enabledTargets.length} plataforma(s): ${created} job(s) preparados. ${skipped ? `${skipped} destino(s) omitidos por existente/desactivado/sin conector.` : "Sin duplicados detectados."}`);
      await refreshWorkerRegistrations(worker.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo preparar la asignacion.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshWorkerRegistrations(workerId: number) {
    const rows = await apiJson<WorkerPlatformRegistration[]>(`/api/v1/workers/${workerId}/platform-registrations`);
    setRegistrationsByWorker((current) => ({ ...current, [workerId]: rows }));
  }

  async function createWorkerTransfer(workerId: number, target: PlatformTarget) {
    await apiJson<Transfer>("/api/v1/transfers", {
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
    await apiJson<Transfer>("/api/v1/transfers", {
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
  return message.startsWith("HTTP") || message.startsWith("No se") || message.startsWith("Invalid") || message.includes("error") || message.includes("token");
}
