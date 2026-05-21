"use client";

import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  MapPinned,
  Network,
  Plus,
  Power,
  PowerOff,
  RefreshCw,
  Search,
  ShieldCheck
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { apiJson, jsonHeaders } from "../../lib/apiClient";

type StatusColor = "green" | "orange" | "red";

type PlatformRpaManifest = {
  id: number;
  external_platform_id: number | null;
  platform_slug: string;
  platform_name: string;
  status: string;
  priority_group: string | null;
  hosts: string[];
  entry_urls: string[];
  allowed_operations: string[];
};

type PlatformRpaAccountProposal = {
  id: number;
  manifest_id: number;
  platform_account_id: number | null;
  external_company_name: string | null;
  entry_url: string | null;
  host: string | null;
  user_hint_masked: string | null;
  account_status: string;
  status: string;
  dry_run: boolean;
  manual_approval_required: boolean;
  allowed_operations: string[];
};

type PlatformReviewSchedule = {
  id: number;
  manifest_id: number;
  platform_slug: string;
  platform_name: string;
  enabled: boolean;
  interval_minutes: number;
  review_scope: string[];
  status: string;
  dry_run: boolean;
  manual_approval_required: boolean;
  next_run_at: string | null;
  last_result_status: string | null;
  last_result_summary: string | null;
};

type PlatformDataCoveragePendingItem = {
  id: string;
  kind: string;
  severity: StatusColor;
  title: string;
  detail: string;
  suggested_action: string;
};

type PlatformDataCoverageContext = {
  manifest_id: number;
  platform_slug: string;
  platform_name: string;
  account_proposal_id: number | null;
  external_company_name: string | null;
  trace_label: string;
  host: string | null;
  entry_url_configured: boolean;
  pending_items: PlatformDataCoveragePendingItem[];
  pending_summary: {
    total: number;
    red: number;
    orange: number;
  };
  next_action: string;
};

type PlatformDataCoverage = {
  totals: {
    platforms: number;
    contexts: number;
    pending_items: number;
    pending_red: number;
    pending_orange: number;
  };
  contexts: PlatformDataCoverageContext[];
};

type ValidationSurfacePlatform = {
  platform_slug: string;
  summary: Record<string, number>;
  readback_plan: Array<{ use: string; label: string; evidence_count: number }>;
};

type ValidationSurfaceMap = {
  totals: { platforms: number; surfaces: number };
  platforms: ValidationSurfacePlatform[];
};

type PlatformEditOperation = {
  operation: string;
  status: string;
  next_action: string;
  ready_keys: string[];
  missing_or_unreviewed_keys: string[];
  needs_editable_capture_keys: string[];
};

type PlatformEditContext = {
  manifest_id: number;
  account_proposal_id: number | null;
  operations: PlatformEditOperation[];
};

type PlatformEditMethods = {
  totals: {
    operations_ready_for_preview: number;
  };
  contexts: PlatformEditContext[];
};

type GatewayRequest = {
  id: number;
  platform_name: string;
  status: string;
  result_summary: string | null;
};

type PlatformContextRow = {
  key: string;
  manifest: PlatformRpaManifest;
  account: PlatformRpaAccountProposal | null;
  schedule: PlatformReviewSchedule | null;
  coverage: PlatformDataCoverageContext | null;
  active: boolean;
  platformName: string;
  platformSlug: string;
  externalCompany: string;
  centers: string[];
  host: string;
  entryReady: boolean;
  pendingTotal: number;
  critical: number;
  warnings: number;
  status: StatusColor;
  nextAction: string;
  validationSurfaceCount: number;
  writeReadyOps: number;
  upsertStatus: string;
  writeStatus: StatusColor;
  writeNextAction: string;
};

type ActiveFilter = "all" | "active" | "inactive";

export default function PlatformsPage() {
  const [manifests, setManifests] = useState<PlatformRpaManifest[]>([]);
  const [accounts, setAccounts] = useState<PlatformRpaAccountProposal[]>([]);
  const [schedules, setSchedules] = useState<PlatformReviewSchedule[]>([]);
  const [coverage, setCoverage] = useState<PlatformDataCoverage | null>(null);
  const [surfaces, setSurfaces] = useState<ValidationSurfaceMap | null>(null);
  const [editMethods, setEditMethods] = useState<PlatformEditMethods | null>(null);
  const [search, setSearch] = useState("");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [companyFilter, setCompanyFilter] = useState("all");
  const [centerFilter, setCenterFilter] = useState("all");
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("active");
  const [addManifestId, setAddManifestId] = useState("");
  const [addAccountId, setAddAccountId] = useState("");
  const [loginUser, setLoginUser] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [message, setMessage] = useState("Cargando plataformas.");
  const [busy, setBusy] = useState(false);
  const [updatingScheduleId, setUpdatingScheduleId] = useState<number | null>(null);

  useEffect(() => {
    void loadData();
  }, []);

  async function loadData() {
    setBusy(true);
    try {
      const scheduleRows = await apiJson<PlatformReviewSchedule[]>("/api/v1/platform-review-schedules/ensure?priority_group=all", {
        method: "POST"
      });
      const [manifestRows, accountRows, coverageRows, surfaceRows, editRows] = await Promise.all([
        apiJson<PlatformRpaManifest[]>("/api/v1/platform-contracts/manifests"),
        apiJson<PlatformRpaAccountProposal[]>("/api/v1/platform-contracts/accounts"),
        apiJson<PlatformDataCoverage>("/api/v1/platform-maps/data-coverage?priority_group=all"),
        apiJson<ValidationSurfaceMap>("/api/v1/platform-maps/validation-surfaces"),
        apiJson<PlatformEditMethods>("/api/v1/platform-maps/edit-methods?priority_group=all")
      ]);
      setSchedules(scheduleRows);
      setManifests(manifestRows);
      setAccounts(accountRows);
      setCoverage(coverageRows);
      setSurfaces(surfaceRows);
      setEditMethods(editRows);
      setAddManifestId(String(manifestRows[0]?.id ?? ""));
      setAddAccountId(String(accountRows[0]?.id ?? ""));
      setMessage(`Plataformas cargadas: ${coverageRows.totals.contexts} contextos operativos, ${surfaceRows.totals.surfaces} superficies de validacion, ${editRows.totals.operations_ready_for_preview} operaciones listas para preview.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudieron cargar plataformas.");
    } finally {
      setBusy(false);
    }
  }

  const rows = useMemo(
    () => buildPlatformRows({ manifests, accounts, schedules, coverage, surfaces, editMethods }),
    [accounts, coverage, editMethods, manifests, schedules, surfaces]
  );

  const filteredRows = useMemo(
    () =>
      rows.filter((row) => {
        const haystack = `${row.platformName} ${row.externalCompany} ${row.centers.join(" ")} ${row.host}`.toLowerCase();
        if (search.trim() && !haystack.includes(search.trim().toLowerCase())) {
          return false;
        }
        if (platformFilter !== "all" && row.platformSlug !== platformFilter) {
          return false;
        }
        if (companyFilter !== "all" && row.externalCompany !== companyFilter) {
          return false;
        }
        if (centerFilter !== "all" && !row.centers.includes(centerFilter)) {
          return false;
        }
        if (activeFilter === "active" && !row.active) {
          return false;
        }
        if (activeFilter === "inactive" && row.active) {
          return false;
        }
        return true;
      }),
    [activeFilter, centerFilter, companyFilter, platformFilter, rows, search]
  );

  const platformOptions = unique(rows.map((row) => row.platformSlug));
  const companyOptions = unique(rows.map((row) => row.externalCompany));
  const centerOptions = unique(rows.flatMap((row) => row.centers));
  const activeCount = rows.filter((row) => row.active).length;
  const inactiveCount = rows.length - activeCount;
  const previewReadyCount = rows.filter((row) => row.writeReadyOps > 0).length;

  async function updatePlatformActive(row: PlatformContextRow, enabled: boolean) {
    if (!row.schedule) {
      setMessage("No existe controlador de revision para esta plataforma.");
      return;
    }
    setUpdatingScheduleId(row.schedule.id);
    try {
      const updated = await apiJson<PlatformReviewSchedule>(`/api/v1/platform-review-schedules/${row.schedule.id}`, {
        method: "PATCH",
        headers: jsonHeaders(),
        body: JSON.stringify({
          enabled,
          status: enabled ? "scheduled" : "disabled",
          review_scope: row.schedule.review_scope.length ? row.schedule.review_scope : ["company", "workers", "documents", "incidents", "mappings"]
        })
      });
      setSchedules((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setMessage(`${row.platformName}: ${enabled ? "activada para revision" : "desactivada; no generara avisos operativos"}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo actualizar la plataforma.");
    } finally {
      setUpdatingScheduleId(null);
    }
  }

  async function createConnectionRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const manifest = manifests.find((item) => String(item.id) === addManifestId);
    const account = accounts.find((item) => String(item.id) === addAccountId && item.manifest_id === manifest?.id) ?? null;
    if (!manifest) {
      setMessage("Selecciona una plataforma autorizada del Hub.");
      return;
    }
    setBusy(true);
    try {
      const request = await apiJson<GatewayRequest>("/api/v1/rpa-gateway/requests", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          manifest_id: manifest.id,
          account_proposal_id: account?.id ?? null,
          action_key: "read_external_status",
          request_comment: `Conexion solicitada desde nueva UI. Usuario visible: ${loginUser ? "[redacted]" : "no aportado"}. Clave no transmitida por front; usar almacen seguro configurado.`
        })
      });
      setLoginPassword("");
      setMessage(`Peticion #${request.id} creada para ${request.platform_name}. Abrela en /rpa-gateway?request=${request.id} para validar acceso y captcha si aparece.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo crear la peticion de conexion.");
    } finally {
      setBusy(false);
    }
  }

  const availableAccounts = accounts.filter((account) => String(account.manifest_id) === addManifestId);

  return (
    <main className="workspace full">
      <header className="topbar">
        <div>
          <p className="eyebrow">Operacion</p>
          <h2>Plataformas</h2>
        </div>
        <button className="iconButton" type="button" aria-label="Actualizar plataformas" onClick={() => void loadData()} disabled={busy}>
          <RefreshCw aria-hidden="true" size={18} />
        </button>
      </header>

      <div className={`messageBar ${isErrorMessage(message) ? "error" : "ok"}`}>
        <span>{message}</span>
      </div>

      <section className="metricGrid" aria-label="Resumen de plataformas">
        <Metric icon={Network} label="Contextos" value={String(rows.length)} />
        <Metric icon={Power} label="Activas" value={String(activeCount)} />
        <Metric icon={PowerOff} label="Desactivadas" value={String(inactiveCount)} />
        <Metric icon={ShieldCheck} label="Preview escritura" value={String(previewReadyCount)} />
        <Metric icon={AlertTriangle} label="Avisos activos" value={String(filteredRows.reduce((total, row) => total + (row.active ? row.pendingTotal : 0), 0))} />
      </section>

      <section className="panel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Filtro</p>
            <h3>Plataforma, empresa y centro de trabajo</h3>
          </div>
          <Search aria-hidden="true" size={20} />
        </div>
        <div className="formGrid">
          <label>
            <span>Buscar</span>
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nombre, empresa, centro o host" />
          </label>
          <label>
            <span>Plataforma</span>
            <select value={platformFilter} onChange={(event) => setPlatformFilter(event.target.value)}>
              <option value="all">Todas</option>
              {platformOptions.map((slug) => (
                <option value={slug} key={slug}>{platformNameForSlug(rows, slug)}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Empresa externa</span>
            <select value={companyFilter} onChange={(event) => setCompanyFilter(event.target.value)}>
              <option value="all">Todas</option>
              {companyOptions.map((company) => (
                <option value={company} key={company}>{company}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Centro / trabajo</span>
            <select value={centerFilter} onChange={(event) => setCenterFilter(event.target.value)}>
              <option value="all">Todos</option>
              {centerOptions.map((center) => (
                <option value={center} key={center}>{center}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Estado operativo</span>
            <select value={activeFilter} onChange={(event) => setActiveFilter(event.target.value as ActiveFilter)}>
              <option value="active">Solo activas</option>
              <option value="inactive">Solo desactivadas</option>
              <option value="all">Todas</option>
            </select>
          </label>
        </div>
      </section>

      <section className="panel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Listado</p>
            <h3>Contextos de plataforma + empresa + centro</h3>
          </div>
          <span className="apiPill online">{filteredRows.length} visibles</span>
        </div>
        <div className="table" role="table" aria-label="Plataformas activas">
          <div className="tableRow newPlatformHead" role="row">
            <span role="columnheader">Plataforma</span>
            <span role="columnheader">Empresa y centro</span>
            <span role="columnheader">Conexion</span>
            <span role="columnheader">Avisos</span>
            <span role="columnheader">Verificacion</span>
            <span role="columnheader">Escritura</span>
            <span role="columnheader">Accion</span>
          </div>
          {filteredRows.map((row) => (
            <div className={`tableRow newPlatformRow ${row.active ? "" : "mutedRow"}`} role="row" key={row.key}>
              <span role="cell">
                <strong>{row.platformName}</strong>
                <small>{row.platformSlug} / {row.host}</small>
              </span>
              <span role="cell">
                <strong>{row.externalCompany}</strong>
                <small>{row.centers.join(", ")}</small>
              </span>
              <span role="cell">
                {renderStatus(row.status, row.active ? "activa" : "desactivada")}
                <small>{row.entryReady ? "URL disponible" : "Falta URL/host"}</small>
              </span>
              <span role="cell">
                {row.active ? `${row.critical} criticas / ${row.warnings} warnings` : "Silenciada"}
                <small>{row.active ? row.nextAction : "No se revisa y no genera avisos."}</small>
              </span>
              <span role="cell">
                {row.validationSurfaceCount} superficies
                <small>{row.schedule?.last_result_summary ?? row.schedule?.last_result_status ?? "Sin lectura reciente"}</small>
              </span>
              <span role="cell">
                {renderStatus(row.writeStatus, writeStatusLabel(row.upsertStatus))}
                <small>{row.writeNextAction}</small>
              </span>
              <span role="cell">
                <button
                  className={row.active ? "secondaryButton" : "primaryButton"}
                  type="button"
                  onClick={() => void updatePlatformActive(row, !row.active)}
                  disabled={!row.schedule || updatingScheduleId === row.schedule.id}
                >
                  {row.active ? "Desactivar" : "Activar"}
                </button>
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Anadir</p>
            <h3>Conectar plataforma autorizada</h3>
          </div>
          <Plus aria-hidden="true" size={20} />
        </div>
        <form className="actionPanel" onSubmit={(event) => void createConnectionRequest(event)}>
          <div className="formGrid">
            <label>
              <span>Plataforma del Hub</span>
              <select value={addManifestId} onChange={(event) => {
                setAddManifestId(event.target.value);
                const firstAccount = accounts.find((account) => String(account.manifest_id) === event.target.value);
                setAddAccountId(String(firstAccount?.id ?? ""));
              }}>
                {manifests.map((manifest) => (
                  <option value={manifest.id} key={manifest.id}>{manifest.platform_name}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Empresa / centro</span>
              <select value={addAccountId} onChange={(event) => setAddAccountId(event.target.value)}>
                <option value="">Sin cuenta concreta</option>
                {availableAccounts.map((account) => (
                  <option value={account.id} key={account.id}>{account.external_company_name ?? account.host ?? `Cuenta ${account.id}`}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Usuario</span>
              <input value={loginUser} onChange={(event) => setLoginUser(event.target.value)} autoComplete="username" placeholder="Usuario de la plataforma" />
            </label>
            <label>
              <span>Clave</span>
              <input value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} type="password" autoComplete="current-password" placeholder="No se guarda en el navegador" />
            </label>
          </div>
          <div className="notice">
            <KeyRound aria-hidden="true" size={18} />
            <p>Por seguridad, esta pantalla crea la peticion de conexion y usa el almacen seguro configurado en servidor. La clave escrita aqui no se guarda ni se envia en comentarios o auditoria.</p>
          </div>
          <div className="actionControls">
            <button className="primaryButton inlineButton" type="submit" disabled={busy}>
              <ShieldCheck aria-hidden="true" size={16} />
              Validar y conectar
            </button>
            <a className="secondaryButton inlineButton" href="/rpa-gateway">
              Abrir pasarela
              <ExternalLink aria-hidden="true" size={14} />
            </a>
          </div>
        </form>
      </section>
    </main>
  );
}

function Metric({ icon: Icon, label, value }: { icon: typeof Network; label: string; value: string }) {
  return (
    <article className="metric">
      <Icon aria-hidden="true" size={20} />
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function buildPlatformRows({
  manifests,
  accounts,
  schedules,
  coverage,
  surfaces,
  editMethods
}: {
  manifests: PlatformRpaManifest[];
  accounts: PlatformRpaAccountProposal[];
  schedules: PlatformReviewSchedule[];
  coverage: PlatformDataCoverage | null;
  surfaces: ValidationSurfaceMap | null;
  editMethods: PlatformEditMethods | null;
}): PlatformContextRow[] {
  const accountsByManifest = new Map<number, PlatformRpaAccountProposal[]>();
  for (const account of accounts) {
    accountsByManifest.set(account.manifest_id, [...(accountsByManifest.get(account.manifest_id) ?? []), account]);
  }
  const scheduleByManifest = new Map(schedules.map((schedule) => [schedule.manifest_id, schedule]));
  const coverageByAccount = new Map((coverage?.contexts ?? []).map((context) => [`${context.manifest_id}:${context.account_proposal_id ?? "none"}`, context]));
  const surfaceBySlug = new Map((surfaces?.platforms ?? []).map((platform) => [platform.platform_slug, platform]));
  const editByAccount = new Map((editMethods?.contexts ?? []).map((context) => [`${context.manifest_id}:${context.account_proposal_id ?? "none"}`, context]));

  return manifests.flatMap((manifest) => {
    const manifestAccounts = accountsByManifest.get(manifest.id) ?? [null];
    return manifestAccounts.map((account) => {
      const coverageContext = coverageByAccount.get(`${manifest.id}:${account?.id ?? "none"}`) ?? null;
      const editContext = editByAccount.get(`${manifest.id}:${account?.id ?? "none"}`) ?? null;
      const schedule = scheduleByManifest.get(manifest.id) ?? null;
      const active = Boolean(schedule?.enabled && account?.status === "active");
      const externalCompany = coverageContext?.external_company_name ?? account?.external_company_name ?? "Empresa externa sin nombre";
      const centers = centersFrom(externalCompany, coverageContext?.trace_label ?? "");
      const pendingTotal = coverageContext?.pending_summary.total ?? 0;
      const critical = coverageContext?.pending_summary.red ?? 0;
      const warnings = coverageContext?.pending_summary.orange ?? 0;
      const platformSurface = surfaceBySlug.get(manifest.platform_slug);
      const upsertOperation = editContext?.operations.find((operation) => operation.operation === "upsert_worker") ?? null;
      const writeReadyOps = editContext?.operations.filter((operation) => operation.status === "ready_for_preview").length ?? 0;
      return {
        key: `${manifest.id}:${account?.id ?? "no-account"}`,
        manifest,
        account,
        schedule,
        coverage: coverageContext,
        active,
        platformName: manifest.platform_name,
        platformSlug: manifest.platform_slug,
        externalCompany,
        centers,
        host: coverageContext?.host ?? account?.host ?? manifest.hosts[0] ?? "host pendiente",
        entryReady: Boolean(coverageContext?.entry_url_configured || account?.entry_url || manifest.entry_urls.length),
        pendingTotal,
        critical,
        warnings,
        status: active ? (critical > 0 ? "red" : warnings > 0 ? "orange" : "green") : "red",
        nextAction: active
          ? coverageContext?.next_action ?? "Revisar configuracion de cuenta."
          : "Cuenta baja/inactiva; no se revisa ni genera avisos.",
        validationSurfaceCount: platformSurface ? Object.values(platformSurface.summary).reduce((total, count) => total + count, 0) : 0,
        writeReadyOps,
        upsertStatus: upsertOperation?.status ?? "needs_mapping",
        writeStatus: writeStatusColor(upsertOperation?.status, writeReadyOps),
        writeNextAction: upsertOperation?.next_action ?? "Completar mapeo de escritura para este contexto."
      };
    });
  });
}

function centersFrom(externalCompany: string, traceLabel: string) {
  const raw = externalCompany && externalCompany !== "Empresa externa sin nombre" ? externalCompany : traceLabel;
  const centers = raw
    .split(/[,/|]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => !/^arm\b/i.test(item) && !/^ctaima\b/i.test(item));
  return centers.length ? unique(centers) : ["Centro no informado"];
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((left, right) => left.localeCompare(right));
}

function platformNameForSlug(rows: PlatformContextRow[], slug: string) {
  return rows.find((row) => row.platformSlug === slug)?.platformName ?? slug;
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

function writeStatusColor(status: string | undefined, readyOps: number): StatusColor {
  if (status === "ready_for_preview") {
    return "green";
  }
  if (status === "needs_editable_capture" || readyOps > 0) {
    return "orange";
  }
  return "red";
}

function writeStatusLabel(status: string) {
  if (status === "ready_for_preview") {
    return "preview listo";
  }
  if (status === "needs_editable_capture") {
    return "falta captura";
  }
  if (status === "needs_mapping_review") {
    return "revisar mapeo";
  }
  return "sin mapeo";
}

function isErrorMessage(message: string) {
  return message.startsWith("HTTP") || message.startsWith("No se") || message.startsWith("Invalid") || message.includes("error") || message.includes("token");
}
