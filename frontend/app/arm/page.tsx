"use client";

import {
  ArrowLeft,
  Building2,
  CalendarDays,
  Download,
  FileText,
  Pencil,
  PlusCircle,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Upload,
  UserMinus,
  UserPlus,
  UserRoundCheck,
  UsersRound,
  type LucideIcon
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { apiBlob, apiJson, jsonHeaders } from "../../lib/apiClient";

type Company = {
  id: number;
  name: string;
  tax_id: string | null;
  company_type: string;
  address: string | null;
  status: string;
};

type Worker = {
  id: number;
  company_id: number;
  first_name: string;
  last_name: string;
  identifier_type: string | null;
  identifier_value: string | null;
  identifier_last4: string | null;
  identifier_expires_at: string | null;
  nationality: string | null;
  email: string | null;
  phone: string | null;
  social_security_number: string | null;
  social_security_last4: string | null;
  contract_type: string | null;
  starts_at: string | null;
  ends_at: string | null;
  work_position: string | null;
  work_center_name: string | null;
  risk_profile: string | null;
  employment_status: string;
  medical_fitness_status: string | null;
  medical_fitness_issued_at: string | null;
  medical_fitness_expires_at: string | null;
  medical_fitness_provider: string | null;
  medical_fitness_restrictions: string | null;
  cae_notes: string | null;
  status: string;
};

type DocumentType = {
  id: number;
  code: string;
  name: string;
  entity_scope: string;
  requires_expiration: boolean;
  default_validity_days: number | null;
};

type DocumentRecord = {
  id: number;
  document_type_id: number;
  entity_type: string;
  entity_id: number;
  current_version_id: number | null;
  status_internal: string;
};

type DocumentVersion = {
  id: number;
  document_id: number;
  version_number: number;
  file_storage_key: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  issued_at: string | null;
  expires_at: string | null;
  platform_expires_at: string | null;
  expiry_review_status: string;
  platform_expiry_source: string | null;
  source: string;
  created_at: string | null;
};

type DocumentRow = {
  document: DocumentRecord;
  type: DocumentType | null;
  versions: DocumentVersion[];
  currentVersion: DocumentVersion | null;
};

type ArmView = "company" | "workers";
type DocumentTarget = "company" | "worker";
type WorkerStatusFilter = "active" | "inactive" | "all";
type WorkerDocumentFilter = "all" | "hub_review" | "expired";

const ARM_TAX_ID = "B95868543";

type DocumentEditDraft = {
  file: File | null;
  issuedAt: string;
  expiresAt: string;
  platformExpiresAt: string;
};

type NewDocumentTypeForm = {
  code: string;
  name: string;
  requiresExpiration: boolean;
  defaultValidityDays: string;
};

const emptyDocumentDraft: DocumentEditDraft = {
  file: null,
  issuedAt: "",
  expiresAt: "",
  platformExpiresAt: ""
};

const emptyNewDocumentTypeForm: NewDocumentTypeForm = {
  code: "",
  name: "",
  requiresExpiration: true,
  defaultValidityDays: ""
};

const emptyCompanyForm = {
  name: "",
  tax_id: "",
  company_type: "own",
  address: "",
  status: "active"
};

const emptyWorkerForm = {
  company_id: "",
  first_name: "",
  last_name: "",
  identifier_type: "dni",
  identifier_value: "",
  identifier_expires_at: "",
  nationality: "",
  email: "",
  phone: "",
  social_security_number: "",
  contract_type: "",
  starts_at: "",
  ends_at: "",
  work_position: "",
  work_center_name: "",
  risk_profile: "",
  employment_status: "active",
  medical_fitness_status: "",
  medical_fitness_issued_at: "",
  medical_fitness_expires_at: "",
  medical_fitness_provider: "",
  medical_fitness_restrictions: "",
  cae_notes: "",
  status: "active"
};

export default function ArmPage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [documentTypes, setDocumentTypes] = useState<DocumentType[]>([]);
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [activeView, setActiveView] = useState<ArmView>("company");
  const [selectedWorkerId, setSelectedWorkerId] = useState<number | null>(null);
  const [workerDetailOpen, setWorkerDetailOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [workerStatusFilter, setWorkerStatusFilter] = useState<WorkerStatusFilter>("active");
  const [workerDocumentFilter, setWorkerDocumentFilter] = useState<WorkerDocumentFilter>("all");
  const [workerCreateOpen, setWorkerCreateOpen] = useState(false);
  const [companyForm, setCompanyForm] = useState(emptyCompanyForm);
  const [workerForm, setWorkerForm] = useState(emptyWorkerForm);
  const [newWorkerForm, setNewWorkerForm] = useState(emptyWorkerForm);
  const [documentSearch, setDocumentSearch] = useState("");
  const [editingDocumentId, setEditingDocumentId] = useState<number | null>(null);
  const [documentDrafts, setDocumentDrafts] = useState<Record<number, DocumentEditDraft>>({});
  const [newDocumentTypeForms, setNewDocumentTypeForms] = useState<Record<DocumentTarget, NewDocumentTypeForm>>({
    company: emptyNewDocumentTypeForm,
    worker: emptyNewDocumentTypeForm
  });
  const [message, setMessage] = useState("Cargando datos propios ARM.");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void loadData();
  }, []);

  const armCompany = companies.find((company) => company.tax_id === ARM_TAX_ID) ?? companies[0] ?? null;
  const armWorkers = useMemo(
    () => workers.filter((worker) => armCompany && worker.company_id === armCompany.id),
    [armCompany, workers]
  );
  const armWorkerIds = useMemo(() => new Set(armWorkers.map((worker) => worker.id)), [armWorkers]);
  const selectedWorker = useMemo(
    () => armWorkers.find((worker) => worker.id === selectedWorkerId) ?? null,
    [armWorkers, selectedWorkerId]
  );
  const companyDocumentTypes = useMemo(
    () => documentTypes.filter((type) => type.entity_scope === "company"),
    [documentTypes]
  );
  const workerDocumentTypes = useMemo(
    () => documentTypes.filter((type) => type.entity_scope === "worker"),
    [documentTypes]
  );
  const companyDocuments = useMemo(
    () => sortDocuments(documents.filter((row) => armCompany && row.document.entity_type === "company" && row.document.entity_id === armCompany.id)),
    [armCompany, documents]
  );
  const selectedWorkerDocuments = useMemo(
    () => sortDocuments(documents.filter((row) => selectedWorker && row.document.entity_type === "worker" && row.document.entity_id === selectedWorker.id)),
    [documents, selectedWorker]
  );
  const armDocuments = useMemo(
    () =>
      documents.filter(
        (row) =>
          (armCompany && row.document.entity_type === "company" && row.document.entity_id === armCompany.id) ||
          (row.document.entity_type === "worker" && armWorkerIds.has(row.document.entity_id))
      ),
    [armCompany, armWorkerIds, documents]
  );
  const visibleCompanyDocuments = useMemo(
    () => filterDocuments(companyDocuments, documentSearch),
    [companyDocuments, documentSearch]
  );
  const visibleWorkerDocuments = useMemo(
    () => filterDocuments(selectedWorkerDocuments, documentSearch),
    [documentSearch, selectedWorkerDocuments]
  );
  const reviewDocuments = armDocuments.filter((row) => row.document.status_internal === "pending_internal_review").length;
  const expiredDocuments = armDocuments.filter((row) => row.document.status_internal === "expired").length;
  const latestCompanyUpload = latestUpload(companyDocuments);
  const latestWorkerUpload = latestUpload(selectedWorkerDocuments);
  const workerDocumentCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const row of documents) {
      if (row.document.entity_type === "worker") {
        counts.set(row.document.entity_id, (counts.get(row.document.entity_id) ?? 0) + 1);
      }
    }
    return counts;
  }, [documents]);
  const activeWorkerCount = useMemo(() => armWorkers.filter((worker) => !isWorkerInactive(worker)).length, [armWorkers]);
  const inactiveWorkerCount = armWorkers.length - activeWorkerCount;
  const filteredWorkers = useMemo(() => {
    const query = normalizeSearch(search);
    return armWorkers.filter((worker) => {
      const workerInactive = isWorkerInactive(worker);
      if (workerStatusFilter === "active" && workerInactive) {
        return false;
      }
      if (workerStatusFilter === "inactive" && !workerInactive) {
        return false;
      }
      const stats = workerDocumentStatus(worker.id, documents);
      if (workerDocumentFilter === "hub_review" && stats.review === 0) {
        return false;
      }
      if (workerDocumentFilter === "expired" && stats.expired === 0) {
        return false;
      }
      if (!query) {
        return true;
      }
      const haystack = normalizeSearch(
        [
          fullName(worker),
          worker.identifier_value,
          worker.identifier_last4,
          worker.work_position,
          worker.work_center_name,
          worker.email,
          worker.phone
        ]
          .filter(Boolean)
          .join(" ")
      );
      return haystack.includes(query);
    });
  }, [armWorkers, documents, search, workerDocumentFilter, workerStatusFilter]);

  useEffect(() => {
    setCompanyForm(companyToForm(armCompany));
  }, [armCompany?.id]);

  useEffect(() => {
    setWorkerForm(workerToForm(selectedWorker));
  }, [selectedWorker?.id]);

  async function loadData(nextWorkerId?: number) {
    setBusy(true);
    try {
      const [companyRows, workerRows, typeRows, documentRows] = await Promise.all([
        apiJson<Company[]>("/api/v1/companies"),
        apiJson<Worker[]>("/api/v1/workers?include_deleted=true"),
        apiJson<DocumentType[]>("/api/v1/document-types"),
        apiJson<DocumentRecord[]>("/api/v1/documents")
      ]);
      const hydratedDocuments = await hydrateDocuments(documentRows, typeRows);
      const nextArmCompany = companyRows.find((company) => company.tax_id === ARM_TAX_ID) ?? companyRows[0] ?? null;
      const nextArmWorkers = workerRows.filter((worker) => nextArmCompany && worker.company_id === nextArmCompany.id);
      const nextArmWorkerIds = new Set(nextArmWorkers.map((worker) => worker.id));
      const nextArmDocuments = hydratedDocuments.filter(
        (row) =>
          (nextArmCompany && row.document.entity_type === "company" && row.document.entity_id === nextArmCompany.id) ||
          (row.document.entity_type === "worker" && nextArmWorkerIds.has(row.document.entity_id))
      );
      const candidateWorkerId = nextWorkerId ?? selectedWorkerId ?? null;
      const nextSelectedWorkerId =
        candidateWorkerId && nextArmWorkers.some((worker) => worker.id === candidateWorkerId)
          ? candidateWorkerId
          : nextArmWorkers[0]?.id ?? null;
      setCompanies(companyRows);
      setWorkers(workerRows);
      setDocumentTypes(typeRows);
      setDocuments(hydratedDocuments);
      setSelectedWorkerId(nextSelectedWorkerId);
      setMessage(`ARM actualizado: ${nextArmWorkers.length} trabajadores y ${nextArmDocuments.length} documentos normalizados.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudieron cargar datos ARM.");
    } finally {
      setBusy(false);
    }
  }

  async function saveCompany(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!armCompany) {
      return;
    }
    setBusy(true);
    try {
      const updated = await apiJson<Company>(`/api/v1/companies/${armCompany.id}`, {
        method: "PUT",
        headers: jsonHeaders(),
        body: JSON.stringify({
          name: companyForm.name.trim(),
          tax_id: nullable(companyForm.tax_id),
          company_type: companyForm.company_type,
          address: nullable(companyForm.address),
          status: companyForm.status
        })
      });
      await loadData(selectedWorker?.id);
      setMessage(`Empresa actualizada: ${updated.name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo actualizar la empresa.");
    } finally {
      setBusy(false);
    }
  }

  async function saveWorker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedWorker) {
      return;
    }
    setBusy(true);
    try {
      const updated = await apiJson<Worker>(`/api/v1/workers/${selectedWorker.id}`, {
        method: "PUT",
        headers: jsonHeaders(),
        body: JSON.stringify(workerPayloadFromForm(workerForm, { includeStatus: true }))
      });
      await loadData(updated.id);
      setMessage(`Trabajador actualizado: ${fullName(updated)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo actualizar el trabajador.");
    } finally {
      setBusy(false);
    }
  }

  async function createWorker(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!armCompany) {
      setMessage("No hay empresa ARM activa para crear el trabajador.");
      return;
    }
    if (!newWorkerForm.first_name.trim() || !newWorkerForm.last_name.trim()) {
      setMessage("Nombre y apellidos son obligatorios.");
      return;
    }
    setBusy(true);
    try {
      const created = await apiJson<Worker>("/api/v1/workers", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify(
          workerPayloadFromForm(
            {
              ...newWorkerForm,
              company_id: String(armCompany.id),
              status: "active",
              employment_status: newWorkerForm.employment_status || "active"
            },
            { includeStatus: false }
          )
        )
      });
      setWorkerCreateOpen(false);
      setNewWorkerForm({ ...emptyWorkerForm, company_id: String(armCompany.id) });
      setActiveView("workers");
      setWorkerDetailOpen(true);
      await loadData(created.id);
      setMessage(`Trabajador creado en ARM: ${fullName(created)}. No se ha enviado a plataformas externas.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo crear el trabajador.");
    } finally {
      setBusy(false);
    }
  }

  async function setWorkerLifecycle(worker: Worker, nextStatus: "active" | "inactive") {
    const isReactivation = nextStatus === "active";
    setBusy(true);
    try {
      const updated =
        isReactivation && worker.status === "deleted"
          ? await apiJson<Worker>(`/api/v1/workers/${worker.id}/restore`, { method: "POST" })
          : await apiJson<Worker>(`/api/v1/workers/${worker.id}`, {
              method: "PUT",
              headers: jsonHeaders(),
              body: JSON.stringify({
                status: nextStatus,
                employment_status: isReactivation ? "active" : "inactive",
                ends_at: isReactivation ? null : worker.ends_at ?? todayIsoDate()
              })
            });
      await loadData(updated.id);
      if (isReactivation) {
        setWorkerStatusFilter("active");
        setMessage(`Trabajador reactivado: ${fullName(updated)}.`);
      } else {
        setWorkerStatusFilter("inactive");
        setMessage(`Trabajador dado de baja: ${fullName(updated)}. Se conserva su historico y sus documentos.`);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo cambiar el estado del trabajador.");
    } finally {
      setBusy(false);
    }
  }

  function openDocumentEditor(row: DocumentRow) {
    setEditingDocumentId(row.document.id);
    setDocumentDrafts((current) => ({
      ...current,
      [row.document.id]: current[row.document.id] ?? draftFromCurrentVersion(row)
    }));
  }

  function updateDocumentDraft(row: DocumentRow, changes: Partial<DocumentEditDraft>) {
    setDocumentDrafts((current) => ({
      ...current,
      [row.document.id]: {
        ...(current[row.document.id] ?? draftFromCurrentVersion(row)),
        ...changes
      }
    }));
  }

  async function uploadDocumentForRow(row: DocumentRow) {
    const draft = documentDrafts[row.document.id] ?? draftFromCurrentVersion(row);
    if (!draft.file) {
      setMessage("Selecciona un fichero en la fila del documento.");
      return;
    }
    setBusy(true);
    try {
      const formData = new FormData();
      formData.append("file", draft.file);
      formData.append("source", "manual");
      if (draft.issuedAt) {
        formData.append("issued_at", draft.issuedAt);
      }
      if (draft.expiresAt) {
        formData.append("expires_at", draft.expiresAt);
      }
      if (draft.platformExpiresAt) {
        formData.append("platform_expires_at", draft.platformExpiresAt);
        formData.append("platform_expiry_source", "manual");
      }
      const version = await apiJson<DocumentVersion>(`/api/v1/documents/${row.document.id}/upload`, {
        method: "POST",
        body: formData
      });
      setDocumentDrafts((current) => ({ ...current, [row.document.id]: draftFromVersion(version) }));
      setEditingDocumentId(row.document.id);
      await loadData(selectedWorker?.id);
      setMessage(`Nueva version en HUB: ${version.filename}. SHA-256 ${version.sha256.slice(0, 12)}...`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo subir el documento.");
    } finally {
      setBusy(false);
    }
  }

  async function saveDocumentDates(row: DocumentRow) {
    if (!row.currentVersion) {
      setMessage("Sube primero un fichero para poder versionar fechas.");
      return;
    }
    const draft = documentDrafts[row.document.id] ?? draftFromCurrentVersion(row);
    const currentVersion = row.currentVersion;
    setBusy(true);
    try {
      const version = await apiJson<DocumentVersion>(`/api/v1/documents/${row.document.id}/versions`, {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          file_storage_key: currentVersion.file_storage_key,
          sha256: currentVersion.sha256,
          filename: currentVersion.filename,
          mime_type: currentVersion.mime_type,
          size_bytes: currentVersion.size_bytes,
          issued_at: draft.issuedAt || null,
          expires_at: draft.expiresAt || null,
          platform_expires_at: draft.platformExpiresAt || null,
          expiry_review_status: expiryReviewStatus(draft.expiresAt, draft.platformExpiresAt),
          platform_expiry_source: draft.platformExpiresAt ? "manual" : currentVersion.platform_expiry_source,
          source: currentVersion.source,
          created_by: null
        })
      });
      setDocumentDrafts((current) => ({ ...current, [row.document.id]: draftFromVersion(version) }));
      await loadData(selectedWorker?.id);
      setMessage(`Fechas guardadas en HUB como version v${version.version_number} de ${version.filename}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudieron guardar las fechas.");
    } finally {
      setBusy(false);
    }
  }

  async function createDocumentTypeForTarget(event: FormEvent<HTMLFormElement>, entityType: DocumentTarget) {
    event.preventDefault();
    const form = newDocumentTypeForms[entityType];
    const entityId = entityType === "company" ? armCompany?.id : selectedWorker?.id;
    if (!entityId) {
      setMessage("Selecciona primero la empresa o el trabajador.");
      return;
    }
    if (!form.name.trim() || !form.code.trim()) {
      setMessage("Indica nombre y codigo del nuevo tipo documental.");
      return;
    }
    setBusy(true);
    try {
      const documentType = await apiJson<DocumentType>("/api/v1/document-types", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          code: form.code.trim().toUpperCase(),
          name: form.name.trim(),
          entity_scope: entityType,
          is_common_cae_type: true,
          requires_expiration: form.requiresExpiration,
          default_validity_days: form.defaultValidityDays ? Number(form.defaultValidityDays) : null
        })
      });
      await apiJson<DocumentRecord>("/api/v1/documents", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          document_type_id: documentType.id,
          entity_type: entityType,
          entity_id: entityId,
          status_internal: "draft"
        })
      });
      setNewDocumentTypeForms((current) => ({ ...current, [entityType]: emptyNewDocumentTypeForm }));
      await loadData(selectedWorker?.id);
      setMessage(`Tipo documental creado en HUB: ${documentType.name}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo crear el tipo documental.");
    } finally {
      setBusy(false);
    }
  }

  async function downloadDocument(row: DocumentRow) {
    if (!row.currentVersion) {
      setMessage("Este documento no tiene fichero cargado.");
      return;
    }
    setBusy(true);
    try {
      const { blob } = await apiBlob(`/api/v1/documents/${row.document.id}/versions/${row.currentVersion.id}/download`);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = row.currentVersion.filename || "documento.pdf";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setMessage(`Descarga preparada: ${row.currentVersion.filename}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo descargar el documento.");
    } finally {
      setBusy(false);
    }
  }

  function openWorker(workerId: number) {
    setSelectedWorkerId(workerId);
    setWorkerDetailOpen(true);
    setActiveView("workers");
    setEditingDocumentId(null);
  }

  function openCompanyView() {
    setActiveView("company");
    setWorkerDetailOpen(false);
    setDocumentSearch("");
    setEditingDocumentId(null);
  }

  function openWorkersView() {
    setActiveView("workers");
    setWorkerDetailOpen(false);
    setDocumentSearch("");
    setEditingDocumentId(null);
  }

  function openCreateWorker() {
    setNewWorkerForm({ ...emptyWorkerForm, company_id: armCompany ? String(armCompany.id) : "" });
    setWorkerCreateOpen(true);
    setActiveView("workers");
    setWorkerDetailOpen(false);
  }

  return (
    <main className="workspace full">
      <header className="topbar">
        <div>
          <p className="eyebrow">ARM</p>
          <h2>Empresa y trabajadores</h2>
        </div>
        <div className="toolbar">
          <div className="armViewSwitch" role="tablist" aria-label="Vista ARM">
            <button className={activeView === "company" ? "active" : ""} type="button" onClick={openCompanyView}>
              <Building2 aria-hidden="true" size={16} />
              Empresa ARM
            </button>
            <button className={activeView === "workers" ? "active" : ""} type="button" onClick={openWorkersView}>
              <UsersRound aria-hidden="true" size={16} />
              Trabajadores
            </button>
          </div>
          <button className="iconButton" type="button" aria-label="Actualizar ARM" onClick={() => void loadData()} disabled={busy}>
            <RefreshCw aria-hidden="true" size={18} />
          </button>
        </div>
      </header>

      <div className={`messageBar ${isErrorMessage(message) ? "error" : "ok"}`}>
        <span>{message}</span>
      </div>

      <section className="metricGrid" aria-label="Resumen ARM">
        <Metric icon={Building2} label="Empresa ARM" value={armCompany ? "1" : "0"} />
        <Metric icon={UsersRound} label="Trabajadores activos / total" value={`${activeWorkerCount} / ${armWorkers.length}`} />
        <Metric icon={FileText} label="Documentos" value={String(armDocuments.length)} />
        <Metric icon={CalendarDays} label="Revisar HUB / caducados" value={`${reviewDocuments} / ${expiredDocuments}`} />
      </section>

      {activeView === "company" ? (
        <section className="armScreen" aria-label="Ficha empresa ARM">
          <section className="armCompanyGrid" aria-label="Resumen documental de empresa">
            <InfoBox label="CIF" value={armCompany?.tax_id ?? "Pendiente"} />
            <InfoBox label="Estado" value={armCompany?.status ?? "Sin empresa"} badgeClass={armCompany?.status ?? "missing"} />
            <InfoBox label="Documentos empresa" value={String(companyDocuments.length)} />
            <InfoBox label="Ultima subida" value={formatDateTime(latestCompanyUpload)} />
          </section>

          <section className="panel">
            <div className="sectionTitle">
              <div>
                <p className="eyebrow">Ficha empresa</p>
                <h3>{armCompany?.name ?? "Sin empresa ARM cargada"}</h3>
              </div>
              <Building2 aria-hidden="true" size={20} />
            </div>
            <form className="armEditGrid" onSubmit={(event) => void saveCompany(event)}>
              <label>
                <span>Nombre</span>
                <input value={companyForm.name} onChange={(event) => setCompanyForm({ ...companyForm, name: event.target.value })} required />
              </label>
              <label>
                <span>CIF</span>
                <input value={companyForm.tax_id} onChange={(event) => setCompanyForm({ ...companyForm, tax_id: event.target.value })} />
              </label>
              <label>
                <span>Tipo</span>
                <select value={companyForm.company_type} onChange={(event) => setCompanyForm({ ...companyForm, company_type: event.target.value })}>
                  <option value="own">Propia</option>
                  <option value="client">Cliente</option>
                  <option value="contractor">Contrata</option>
                  <option value="subcontractor">Subcontrata</option>
                </select>
              </label>
              <label>
                <span>Estado</span>
                <select value={companyForm.status} onChange={(event) => setCompanyForm({ ...companyForm, status: event.target.value })}>
                  <option value="active">Activa</option>
                  <option value="inactive">Inactiva</option>
                </select>
              </label>
              <label className="wideField">
                <span>Direccion</span>
                <input value={companyForm.address} onChange={(event) => setCompanyForm({ ...companyForm, address: event.target.value })} />
              </label>
              <button className="primaryButton" type="submit" disabled={busy || !armCompany}>
                <Save aria-hidden="true" size={16} />
                Guardar empresa
              </button>
            </form>
          </section>

          <DocumentTable
            entityType="company"
            title="Documentos de empresa"
            rows={visibleCompanyDocuments}
            totalRows={companyDocuments.length}
            query={documentSearch}
            onQueryChange={setDocumentSearch}
            editingDocumentId={editingDocumentId}
            drafts={documentDrafts}
            busy={busy}
            newTypeForm={newDocumentTypeForms.company}
            onNewTypeFormChange={(changes) =>
              setNewDocumentTypeForms((current) => ({ ...current, company: { ...current.company, ...changes } }))
            }
            onCreateDocumentType={(event) => void createDocumentTypeForTarget(event, "company")}
            onEdit={openDocumentEditor}
            onDraftChange={updateDocumentDraft}
            onUploadVersion={(row) => void uploadDocumentForRow(row)}
            onSaveDates={(row) => void saveDocumentDates(row)}
            onDownload={(row) => void downloadDocument(row)}
          />
        </section>
      ) : workerDetailOpen && selectedWorker ? (
        <section className="armScreen" aria-label="Ficha trabajador ARM">
          <div className="armDetailHeader">
            <button className="secondaryButton inlineButton" type="button" onClick={openWorkersView}>
              <ArrowLeft aria-hidden="true" size={16} />
              Volver al listado
            </button>
            <div>
              <p className="eyebrow">Ficha trabajador</p>
              <h3>{fullName(selectedWorker)}</h3>
            </div>
            <div className="workerLifecycleActions" aria-label="Acciones de estado del trabajador">
              {isWorkerInactive(selectedWorker) ? (
                <button className="primaryButton inlineButton" type="button" disabled={busy} onClick={() => void setWorkerLifecycle(selectedWorker, "active")}>
                  <RotateCcw aria-hidden="true" size={16} />
                  Reactivar
                </button>
              ) : (
                <button className="secondaryButton inlineButton" type="button" disabled={busy} onClick={() => void setWorkerLifecycle(selectedWorker, "inactive")}>
                  <UserMinus aria-hidden="true" size={16} />
                  Dar de baja
                </button>
              )}
            </div>
          </div>

          <section className="armCompanyGrid" aria-label="Resumen documental del trabajador">
            <InfoBox label="Estado ficha" value={workerStatusLabel(selectedWorker)} badgeClass={workerStatusClass(selectedWorker)} />
            <InfoBox label="Aptitud" value={selectedWorker.medical_fitness_status ?? "Pendiente"} />
            <InfoBox label="Documentos" value={String(selectedWorkerDocuments.length)} />
            <InfoBox label="Ultima subida" value={formatDateTime(latestWorkerUpload)} />
          </section>

          <section className="panel">
            <div className="sectionTitle">
              <div>
                <p className="eyebrow">Datos ARM</p>
                <h3>{fullName(selectedWorker)}</h3>
              </div>
              <UserRoundCheck aria-hidden="true" size={20} />
            </div>
            <form className="armEditGrid" onSubmit={(event) => void saveWorker(event)}>
              <input type="hidden" value={workerForm.company_id} readOnly />
              <label>
                <span>Nombre</span>
                <input value={workerForm.first_name} onChange={(event) => setWorkerForm({ ...workerForm, first_name: event.target.value })} required />
              </label>
              <label>
                <span>Apellidos</span>
                <input value={workerForm.last_name} onChange={(event) => setWorkerForm({ ...workerForm, last_name: event.target.value })} required />
              </label>
              <label>
                <span>Tipo ID</span>
                <input value={workerForm.identifier_type} onChange={(event) => setWorkerForm({ ...workerForm, identifier_type: event.target.value })} />
              </label>
              <label>
                <span>DNI/NIE único</span>
                <input value={workerForm.identifier_value} onChange={(event) => setWorkerForm({ ...workerForm, identifier_value: event.target.value })} />
              </label>
              <label>
                <span>Caducidad ID</span>
                <input type="date" value={workerForm.identifier_expires_at} onChange={(event) => setWorkerForm({ ...workerForm, identifier_expires_at: event.target.value })} />
              </label>
              <label>
                <span>Nacionalidad</span>
                <input value={workerForm.nationality} onChange={(event) => setWorkerForm({ ...workerForm, nationality: event.target.value })} />
              </label>
              <label>
                <span>Email</span>
                <input type="email" value={workerForm.email} onChange={(event) => setWorkerForm({ ...workerForm, email: event.target.value })} />
              </label>
              <label>
                <span>Telefono</span>
                <input value={workerForm.phone} onChange={(event) => setWorkerForm({ ...workerForm, phone: event.target.value })} />
              </label>
              <label>
                <span>NAF / SS</span>
                <input value={workerForm.social_security_number} onChange={(event) => setWorkerForm({ ...workerForm, social_security_number: event.target.value })} />
              </label>
              <label>
                <span>Contrato</span>
                <input value={workerForm.contract_type} onChange={(event) => setWorkerForm({ ...workerForm, contract_type: event.target.value })} />
              </label>
              <label>
                <span>Alta</span>
                <input type="date" value={workerForm.starts_at} onChange={(event) => setWorkerForm({ ...workerForm, starts_at: event.target.value })} />
              </label>
              <label>
                <span>Baja</span>
                <input type="date" value={workerForm.ends_at} onChange={(event) => setWorkerForm({ ...workerForm, ends_at: event.target.value })} />
              </label>
              <label>
                <span>Puesto</span>
                <input value={workerForm.work_position} onChange={(event) => setWorkerForm({ ...workerForm, work_position: event.target.value })} />
              </label>
              <label>
                <span>Centro</span>
                <input value={workerForm.work_center_name} onChange={(event) => setWorkerForm({ ...workerForm, work_center_name: event.target.value })} />
              </label>
              <label>
                <span>Riesgo</span>
                <input value={workerForm.risk_profile} onChange={(event) => setWorkerForm({ ...workerForm, risk_profile: event.target.value })} />
              </label>
              <label>
                <span>Estado laboral</span>
                <select value={workerForm.employment_status} onChange={(event) => setWorkerForm({ ...workerForm, employment_status: event.target.value })}>
                  <option value="active">Activo</option>
                  <option value="inactive">Inactivo</option>
                  <option value="pending">Pendiente</option>
                </select>
              </label>
              <label>
                <span>Estado ficha</span>
                <select value={workerForm.status} onChange={(event) => setWorkerForm({ ...workerForm, status: event.target.value })}>
                  <option value="active">Activa</option>
                  <option value="inactive">Baja</option>
                </select>
              </label>
              <label>
                <span>Aptitud</span>
                <input value={workerForm.medical_fitness_status} onChange={(event) => setWorkerForm({ ...workerForm, medical_fitness_status: event.target.value })} placeholder="apto, pendiente..." />
              </label>
              <label>
                <span>Emision aptitud</span>
                <input type="date" value={workerForm.medical_fitness_issued_at} onChange={(event) => setWorkerForm({ ...workerForm, medical_fitness_issued_at: event.target.value })} />
              </label>
              <label>
                <span>Caducidad aptitud</span>
                <input type="date" value={workerForm.medical_fitness_expires_at} onChange={(event) => setWorkerForm({ ...workerForm, medical_fitness_expires_at: event.target.value })} />
              </label>
              <label>
                <span>Proveedor aptitud</span>
                <input value={workerForm.medical_fitness_provider} onChange={(event) => setWorkerForm({ ...workerForm, medical_fitness_provider: event.target.value })} />
              </label>
              <label className="wideField">
                <span>Restricciones preventivas</span>
                <input value={workerForm.medical_fitness_restrictions} onChange={(event) => setWorkerForm({ ...workerForm, medical_fitness_restrictions: event.target.value })} />
              </label>
              <label className="wideField">
                <span>Notas CAE</span>
                <textarea value={workerForm.cae_notes} onChange={(event) => setWorkerForm({ ...workerForm, cae_notes: event.target.value })} />
              </label>
              <button className="primaryButton" type="submit" disabled={busy || !selectedWorker}>
                <Save aria-hidden="true" size={16} />
                Guardar trabajador
              </button>
            </form>
          </section>

          <DocumentTable
            entityType="worker"
            title={`Documentos de ${fullName(selectedWorker)}`}
            rows={visibleWorkerDocuments}
            totalRows={selectedWorkerDocuments.length}
            query={documentSearch}
            onQueryChange={setDocumentSearch}
            editingDocumentId={editingDocumentId}
            drafts={documentDrafts}
            busy={busy}
            newTypeForm={newDocumentTypeForms.worker}
            onNewTypeFormChange={(changes) =>
              setNewDocumentTypeForms((current) => ({ ...current, worker: { ...current.worker, ...changes } }))
            }
            onCreateDocumentType={(event) => void createDocumentTypeForTarget(event, "worker")}
            onEdit={openDocumentEditor}
            onDraftChange={updateDocumentDraft}
            onUploadVersion={(row) => void uploadDocumentForRow(row)}
            onSaveDates={(row) => void saveDocumentDates(row)}
            onDownload={(row) => void downloadDocument(row)}
          />
        </section>
      ) : (
        <section className="armScreen" aria-label="Listado de trabajadores ARM">
          <section className="panel">
            <div className="sectionTitle workerListTitle">
              <div>
                <p className="eyebrow">Trabajadores ARM</p>
                <h3>Listado de trabajadores</h3>
                <p className="muted">{activeWorkerCount} activos, {inactiveWorkerCount} de baja, {armWorkers.length} fichas conservadas.</p>
              </div>
              <button className="primaryButton inlineButton" type="button" onClick={openCreateWorker} disabled={busy || !armCompany}>
                <UserPlus aria-hidden="true" size={16} />
                Crear trabajador
              </button>
            </div>
            <div className="workerFilters" aria-label="Filtros de trabajadores">
              <label className="compactSearch">
                <span>Buscar</span>
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nombre, DNI, puesto o centro" />
              </label>
              <label>
                <span>Estado trabajador</span>
                <select value={workerStatusFilter} onChange={(event) => setWorkerStatusFilter(event.target.value as WorkerStatusFilter)}>
                  <option value="active">Activos</option>
                  <option value="inactive">Baja</option>
                  <option value="all">Todos</option>
                </select>
              </label>
              <label>
                <span>Documentos</span>
                <select value={workerDocumentFilter} onChange={(event) => setWorkerDocumentFilter(event.target.value as WorkerDocumentFilter)}>
                  <option value="all">Todos</option>
                  <option value="hub_review">Revisar HUB</option>
                  <option value="expired">Caducados HUB</option>
                </select>
              </label>
            </div>
            {workerCreateOpen ? (
              <form className="workerCreatePanel" onSubmit={(event) => void createWorker(event)} aria-label="Crear trabajador ARM">
                <div className="sectionTitle">
                  <div>
                    <p className="eyebrow">Nueva ficha ARM</p>
                    <h3>Crear trabajador</h3>
                    <p className="muted">El trabajador queda en ARM. No se envia a ninguna plataforma hasta usar operativa.</p>
                  </div>
                  <UserPlus aria-hidden="true" size={20} />
                </div>
                <div className="armEditGrid">
                  <label>
                    <span>Nombre</span>
                    <input value={newWorkerForm.first_name} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, first_name: event.target.value })} required />
                  </label>
                  <label>
                    <span>Apellidos</span>
                    <input value={newWorkerForm.last_name} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, last_name: event.target.value })} required />
                  </label>
                  <label>
                    <span>Tipo ID</span>
                    <input value={newWorkerForm.identifier_type} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, identifier_type: event.target.value })} />
                  </label>
                  <label>
                    <span>DNI/NIE unico</span>
                    <input value={newWorkerForm.identifier_value} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, identifier_value: event.target.value })} />
                  </label>
                  <label>
                    <span>Puesto</span>
                    <input value={newWorkerForm.work_position} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, work_position: event.target.value })} />
                  </label>
                  <label>
                    <span>Centro</span>
                    <input value={newWorkerForm.work_center_name} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, work_center_name: event.target.value })} />
                  </label>
                  <label>
                    <span>Email</span>
                    <input type="email" value={newWorkerForm.email} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, email: event.target.value })} />
                  </label>
                  <label>
                    <span>Telefono</span>
                    <input value={newWorkerForm.phone} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, phone: event.target.value })} />
                  </label>
                  <label>
                    <span>NAF / SS</span>
                    <input value={newWorkerForm.social_security_number} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, social_security_number: event.target.value })} />
                  </label>
                  <label>
                    <span>Alta</span>
                    <input type="date" value={newWorkerForm.starts_at} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, starts_at: event.target.value })} />
                  </label>
                  <label>
                    <span>Aptitud</span>
                    <input value={newWorkerForm.medical_fitness_status} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, medical_fitness_status: event.target.value })} placeholder="apto, pendiente..." />
                  </label>
                  <label>
                    <span>Estado laboral</span>
                    <select value={newWorkerForm.employment_status} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, employment_status: event.target.value })}>
                      <option value="active">Activo</option>
                      <option value="inactive">Inactivo</option>
                      <option value="pending">Pendiente</option>
                    </select>
                  </label>
                  <label className="wideField">
                    <span>Notas CAE</span>
                    <textarea value={newWorkerForm.cae_notes} onChange={(event) => setNewWorkerForm({ ...newWorkerForm, cae_notes: event.target.value })} />
                  </label>
                </div>
                <div className="workerCreateActions">
                  <button className="primaryButton inlineButton" type="submit" disabled={busy || !armCompany}>
                    <Save aria-hidden="true" size={16} />
                    Crear trabajador
                  </button>
                  <button className="secondaryButton inlineButton" type="button" disabled={busy} onClick={() => setWorkerCreateOpen(false)}>
                    Cancelar
                  </button>
                </div>
              </form>
            ) : null}
            <div className="armDirectoryGrid" aria-label="Trabajadores ARM">
              {filteredWorkers.length ? (
                filteredWorkers.map((worker) => {
                  const stats = workerDocumentStatus(worker.id, documents);
                  return (
                    <button className="workerDirectoryItem" type="button" onClick={() => openWorker(worker.id)} key={worker.id}>
                      <span>
                        <strong>{fullName(worker)}</strong>
                        <small>{worker.work_position ?? "Puesto pendiente"} / {worker.work_center_name ?? "Centro pendiente"}</small>
                        <small>
                          {workerDocumentCounts.get(worker.id) ?? 0} documentos / {stats.review} revisar HUB / {stats.expired} caducados
                        </small>
                      </span>
                      <span>
                        <span className={`statusBadge ${workerStatusClass(worker)}`}>{workerStatusLabel(worker)}</span>
                        <small>Aptitud: {worker.medical_fitness_status ?? "pendiente"}</small>
                      </span>
                    </button>
                  );
                })
              ) : (
                <div className="notice workerEmptyState">
                  <strong>No hay trabajadores con este filtro.</strong>
                  <p>Ajusta busqueda, estado o filtro documental para ver otras fichas conservadas.</p>
                </div>
              )}
            </div>
          </section>
        </section>
      )}
    </main>
  );
}

function Metric({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <article className="metric">
      <Icon aria-hidden="true" size={20} />
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function InfoBox({ label, value, badgeClass }: { label: string; value: string; badgeClass?: string }) {
  return (
    <article className="infoBox">
      <span>{label}</span>
      {badgeClass ? <strong><span className={`statusBadge ${badgeClass}`}>{value}</span></strong> : <strong>{value}</strong>}
    </article>
  );
}

function DocumentTable({
  entityType,
  title,
  rows,
  totalRows,
  query,
  onQueryChange,
  editingDocumentId,
  drafts,
  busy,
  newTypeForm,
  onNewTypeFormChange,
  onCreateDocumentType,
  onEdit,
  onDraftChange,
  onUploadVersion,
  onSaveDates,
  onDownload
}: {
  entityType: DocumentTarget;
  title: string;
  rows: DocumentRow[];
  totalRows: number;
  query: string;
  onQueryChange: (value: string) => void;
  editingDocumentId: number | null;
  drafts: Record<number, DocumentEditDraft>;
  busy: boolean;
  newTypeForm: NewDocumentTypeForm;
  onNewTypeFormChange: (changes: Partial<NewDocumentTypeForm>) => void;
  onCreateDocumentType: (event: FormEvent<HTMLFormElement>) => void;
  onEdit: (row: DocumentRow) => void;
  onDraftChange: (row: DocumentRow, changes: Partial<DocumentEditDraft>) => void;
  onUploadVersion: (row: DocumentRow) => void;
  onSaveDates: (row: DocumentRow) => void;
  onDownload: (row: DocumentRow) => void;
}) {
  return (
    <section className="panel">
      <div className="sectionTitle">
        <div>
          <p className="eyebrow">Zona HUB</p>
          <h3>{title}</h3>
          <small className="muted">{rows.length} visibles de {totalRows} documento(s) normalizados.</small>
        </div>
        <label className="compactSearch">
          <span>Filtrar documentos</span>
          <div className="searchControl">
            <Search aria-hidden="true" size={16} />
            <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Tipo, fichero o estado" />
          </div>
        </label>
        <FileText aria-hidden="true" size={20} />
      </div>
      <DocumentStatusLegend />
      <form className="armDocumentTypeCreate" onSubmit={onCreateDocumentType}>
        <div>
          <p className="eyebrow">Nuevo tipo documental HUB</p>
          <strong>Crear tipo para {entityType === "company" ? "empresa" : "trabajador"}</strong>
        </div>
        <label>
          <span>Codigo</span>
          <input
            value={newTypeForm.code}
            onChange={(event) => onNewTypeFormChange({ code: event.target.value })}
            placeholder={entityType === "company" ? "ARM.COMPANY.NUEVO" : "ARM.WORKER.NUEVO"}
          />
        </label>
        <label>
          <span>Nombre</span>
          <input
            value={newTypeForm.name}
            onChange={(event) => onNewTypeFormChange({ name: event.target.value })}
            placeholder="Nombre visible del documento"
          />
        </label>
        <label>
          <span>Validez dias</span>
          <input
            type="number"
            min="1"
            value={newTypeForm.defaultValidityDays}
            onChange={(event) => onNewTypeFormChange({ defaultValidityDays: event.target.value })}
            placeholder="Opcional"
          />
        </label>
        <label className="checkboxField">
          <input
            type="checkbox"
            checked={newTypeForm.requiresExpiration}
            onChange={(event) => onNewTypeFormChange({ requiresExpiration: event.target.checked })}
          />
          <span>Controla caducidad</span>
        </label>
        <button className="secondaryButton inlineButton" type="submit" disabled={busy}>
          <PlusCircle aria-hidden="true" size={14} />
          Crear tipo
        </button>
      </form>
      <div className="table" role="table" aria-label={title}>
        <div className="tableRow armDocumentHead" role="row">
          <span role="columnheader">Documento</span>
          <span role="columnheader">Estado HUB</span>
          <span role="columnheader">Ultima subida</span>
          <span role="columnheader">Caducidad HUB</span>
          <span role="columnheader">Plataformas</span>
          <span role="columnheader">Fichero</span>
          <span role="columnheader">Accion</span>
        </div>
        {rows.map((row) => {
          const hubStatus = hubStatusFor(row);
          const draft = drafts[row.document.id] ?? draftFromCurrentVersion(row);
          const isEditing = editingDocumentId === row.document.id;
          return (
            <div className="armDocumentRowGroup" key={row.document.id}>
              <div className="tableRow armDocumentRow" role="row">
                <span role="cell">
                  <strong>{row.type?.name ?? "Tipo no localizado"}</strong>
                  <small>{row.type?.code ?? `type:${row.document.document_type_id}`}</small>
                </span>
                <span role="cell">
                  <span className={`statusBadge ${hubStatus.className}`}>{hubStatus.label}</span>
                  <small>{hubStatus.detail}</small>
                </span>
                <span role="cell">
                  {row.currentVersion ? formatDateTime(row.currentVersion.created_at) : "Sin version"}
                  <small>
                    {row.currentVersion ? `${row.versions.length} version(es) / actual v${row.currentVersion.version_number} / ${row.currentVersion.source}` : "Sube el primer fichero"}
                  </small>
                </span>
                <span role="cell">
                  {formatDate(row.currentVersion?.expires_at)}
                  <small>Emision: {formatDate(row.currentVersion?.issued_at)}</small>
                </span>
                <span role="cell">
                  {formatDate(row.currentVersion?.platform_expires_at)}
                  <small>{row.currentVersion?.platform_expiry_source ? `Fuente: ${row.currentVersion.platform_expiry_source}` : "Sin dato externo"}</small>
                </span>
                <span role="cell">
                  {row.currentVersion?.filename ?? "Sin fichero"}
                  <small>{row.currentVersion ? `${formatBytes(row.currentVersion.size_bytes)} / SHA ${row.currentVersion.sha256.slice(0, 10)}` : "Pendiente de subida HUB"}</small>
                </span>
                <span role="cell" className="documentActionCell">
                  <button className="secondaryButton inlineButton" type="button" onClick={() => onEdit(row)}>
                    <Pencil aria-hidden="true" size={14} />
                    Editar
                  </button>
                  <button className="secondaryButton inlineButton" type="button" disabled={!row.currentVersion} onClick={() => onDownload(row)}>
                    <Download aria-hidden="true" size={14} />
                    Descargar
                  </button>
                </span>
              </div>
              {isEditing ? (
                <div className="armDocumentEditPanel">
                  <div>
                    <p className="eyebrow">Editar documento HUB</p>
                    <strong>{row.type?.name ?? "Tipo no localizado"}</strong>
                    <small className="muted">Guardar fechas crea una nueva version de metadatos con el mismo fichero. Subir version reemplaza el fichero actual.</small>
                  </div>
                  <div className="armInlineDocumentForm">
                    <label>
                      <span>Fichero nuevo</span>
                      <input type="file" onChange={(event) => onDraftChange(row, { file: event.target.files?.[0] ?? null })} />
                    </label>
                    <label>
                      <span>Emision HUB</span>
                      <input type="date" value={draft.issuedAt} onChange={(event) => onDraftChange(row, { issuedAt: event.target.value })} />
                    </label>
                    <label>
                      <span>Caducidad HUB</span>
                      <input type="date" value={draft.expiresAt} onChange={(event) => onDraftChange(row, { expiresAt: event.target.value })} />
                    </label>
                    <label>
                      <span>Caducidad plataformas</span>
                      <input type="date" value={draft.platformExpiresAt} onChange={(event) => onDraftChange(row, { platformExpiresAt: event.target.value })} />
                    </label>
                    <button className="secondaryButton inlineButton" type="button" disabled={busy || !row.currentVersion} onClick={() => onSaveDates(row)}>
                      <Save aria-hidden="true" size={14} />
                      Guardar fechas
                    </button>
                    <button className="primaryButton inlineButton" type="button" disabled={busy} onClick={() => onUploadVersion(row)}>
                      <Upload aria-hidden="true" size={14} />
                      Subir version
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
        {rows.length === 0 ? (
          <div className="tableRow armDocumentRow" role="row">
            <span role="cell">Sin documentos cargados.</span>
            <span role="cell"><span className="statusBadge hub_missing">Falta en HUB</span></span>
            <span role="cell">Sin version</span>
            <span role="cell">Sin fecha</span>
            <span role="cell">Sin dato externo</span>
            <span role="cell">Crea un tipo documental o sube un fichero normalizado.</span>
            <span role="cell">-</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function DocumentStatusLegend() {
  return (
    <div className="documentLegend" aria-label="Leyenda de estados documentales">
      <span className="legendItem"><span className="statusBadge hub_uploaded">En HUB</span> Fichero propio subido y vigente en el Hub.</span>
      <span className="legendItem"><span className="statusBadge hub_review">Revisar HUB</span> Requiere revisar fechas o criterio interno, no es estado de plataforma.</span>
      <span className="legendItem"><span className="statusBadge hub_expired">Caducado HUB</span> La caducidad declarada por ARM ha vencido.</span>
      <span className="legendItem"><span className="statusBadge hub_missing">Falta en HUB</span> Existe el tipo documental, pero todavia no hay fichero.</span>
      <span className="legendItem"><span className="statusBadge neutral">Zona plataformas</span> Fechas/avisos leidos fuera se muestran aparte y no cambian el fichero HUB sin revision.</span>
    </div>
  );
}

function hubStatusFor(row: DocumentRow) {
  if (!row.currentVersion || row.document.status_internal === "draft" || row.document.status_internal === "missing") {
    return {
      label: "Falta en HUB",
      className: "hub_missing",
      detail: "Tipo documental creado sin fichero subido."
    };
  }
  if (row.document.status_internal === "expired") {
    return {
      label: "Caducado HUB",
      className: "hub_expired",
      detail: "La fecha declarada por ARM ha vencido."
    };
  }
  if (row.document.status_internal === "pending_internal_review") {
    return {
      label: "Revisar HUB",
      className: "hub_review",
      detail: "Hay diferencia o criterio interno a revisar."
    };
  }
  if (row.document.status_internal === "rejected_internal") {
    return {
      label: "Rechazado HUB",
      className: "hub_expired",
      detail: "Rechazo interno registrado en el Hub."
    };
  }
  return {
    label: "En HUB",
    className: "hub_uploaded",
    detail: "Fichero propio subido al Hub."
  };
}

function draftFromCurrentVersion(row: DocumentRow): DocumentEditDraft {
  return row.currentVersion ? draftFromVersion(row.currentVersion) : emptyDocumentDraft;
}

function draftFromVersion(version: DocumentVersion): DocumentEditDraft {
  return {
    file: null,
    issuedAt: version.issued_at ?? "",
    expiresAt: version.expires_at ?? "",
    platformExpiresAt: version.platform_expires_at ?? ""
  };
}

function expiryReviewStatus(expiresAt: string, platformExpiresAt: string) {
  if (!platformExpiresAt) {
    return "ok";
  }
  return expiresAt === platformExpiresAt ? "ok" : "review_required";
}

async function hydrateDocuments(documentRows: DocumentRecord[], documentTypes: DocumentType[]) {
  const rows = await Promise.all(
    documentRows.map(async (documentRecord) => {
      const versions = await apiJson<DocumentVersion[]>(`/api/v1/documents/${documentRecord.id}/versions`);
      return {
        document: documentRecord,
        versions,
        type: documentTypes.find((type) => type.id === documentRecord.document_type_id) ?? null,
        currentVersion: versions.find((version) => version.id === documentRecord.current_version_id) ?? versions.at(-1) ?? null
      };
    })
  );
  return sortDocuments(rows);
}

function sortDocuments(rows: DocumentRow[]) {
  return [...rows].sort((left, right) => {
    const leftName = `${left.type?.name ?? ""} ${left.currentVersion?.filename ?? ""}`;
    const rightName = `${right.type?.name ?? ""} ${right.currentVersion?.filename ?? ""}`;
    return leftName.localeCompare(rightName, "es");
  });
}

function filterDocuments(rows: DocumentRow[], query: string) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    return rows;
  }
  return rows.filter((row) => {
    const haystack = [
      row.type?.name,
      row.type?.code,
      row.document.status_internal,
      row.currentVersion?.filename,
      row.currentVersion?.source,
      row.currentVersion?.sha256
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(normalized);
  });
}

function latestUpload(rows: DocumentRow[]) {
  const timestamps = rows
    .map((row) => row.currentVersion?.created_at)
    .filter((value): value is string => Boolean(value))
    .map((value) => new Date(value).getTime())
    .filter((value) => Number.isFinite(value));
  if (!timestamps.length) {
    return null;
  }
  return new Date(Math.max(...timestamps)).toISOString();
}

function workerDocumentStatus(workerId: number, rows: DocumentRow[]) {
  const workerRows = rows.filter((row) => row.document.entity_type === "worker" && row.document.entity_id === workerId);
  return {
    review: workerRows.filter((row) => row.document.status_internal === "pending_internal_review").length,
    expired: workerRows.filter((row) => row.document.status_internal === "expired").length
  };
}

function workerPayloadFromForm(form: typeof emptyWorkerForm, options: { includeStatus: boolean }) {
  const payload: Record<string, string | number | null> = {
    company_id: Number(form.company_id),
    first_name: form.first_name.trim(),
    last_name: form.last_name.trim(),
    identifier_type: nullable(form.identifier_type),
    identifier_value: nullable(form.identifier_value),
    identifier_expires_at: form.identifier_expires_at || null,
    nationality: nullable(form.nationality),
    email: nullable(form.email),
    phone: nullable(form.phone),
    social_security_number: nullable(form.social_security_number),
    contract_type: nullable(form.contract_type),
    starts_at: form.starts_at || null,
    ends_at: form.ends_at || null,
    work_position: nullable(form.work_position),
    work_center_name: nullable(form.work_center_name),
    risk_profile: nullable(form.risk_profile),
    employment_status: nullable(form.employment_status),
    medical_fitness_status: nullable(form.medical_fitness_status),
    medical_fitness_issued_at: form.medical_fitness_issued_at || null,
    medical_fitness_expires_at: form.medical_fitness_expires_at || null,
    medical_fitness_provider: nullable(form.medical_fitness_provider),
    medical_fitness_restrictions: nullable(form.medical_fitness_restrictions),
    cae_notes: nullable(form.cae_notes)
  };
  if (options.includeStatus) {
    payload.status = form.status === "inactive" ? "inactive" : "active";
  }
  return payload;
}

function isWorkerInactive(worker: Worker) {
  return worker.status === "inactive" || worker.status === "deleted" || worker.employment_status === "inactive";
}

function workerStatusLabel(worker: Worker) {
  return isWorkerInactive(worker) ? "Baja" : "Activo";
}

function workerStatusClass(worker: Worker) {
  return isWorkerInactive(worker) ? "baja" : "active";
}

function normalizeSearch(value: string) {
  return value.trim().toLowerCase();
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function companyToForm(company: Company | null) {
  if (!company) {
    return emptyCompanyForm;
  }
  return {
    name: company.name,
    tax_id: company.tax_id ?? "",
    company_type: company.company_type,
    address: company.address ?? "",
    status: company.status
  };
}

function workerToForm(worker: Worker | null) {
  if (!worker) {
    return emptyWorkerForm;
  }
  return {
    company_id: String(worker.company_id),
    first_name: worker.first_name,
    last_name: worker.last_name,
    identifier_type: worker.identifier_type ?? "dni",
    identifier_value: worker.identifier_value ?? "",
    identifier_expires_at: worker.identifier_expires_at ?? "",
    nationality: worker.nationality ?? "",
    email: worker.email ?? "",
    phone: worker.phone ?? "",
    social_security_number: worker.social_security_number ?? "",
    contract_type: worker.contract_type ?? "",
    starts_at: worker.starts_at ?? "",
    ends_at: worker.ends_at ?? "",
    work_position: worker.work_position ?? "",
    work_center_name: worker.work_center_name ?? "",
    risk_profile: worker.risk_profile ?? "",
    employment_status: worker.employment_status,
    medical_fitness_status: worker.medical_fitness_status ?? "",
    medical_fitness_issued_at: worker.medical_fitness_issued_at ?? "",
    medical_fitness_expires_at: worker.medical_fitness_expires_at ?? "",
    medical_fitness_provider: worker.medical_fitness_provider ?? "",
    medical_fitness_restrictions: worker.medical_fitness_restrictions ?? "",
    cae_notes: worker.cae_notes ?? "",
    status: isWorkerInactive(worker) ? "inactive" : "active"
  };
}

function nullable(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function fullName(worker: Worker) {
  return `${worker.first_name} ${worker.last_name}`.trim();
}

function formatBytes(size: number) {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${Math.round(size / 102.4) / 10} KB`;
  }
  return `${Math.round(size / 1024 / 102.4) / 10} MB`;
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Sin fecha";
  }
  return value;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "Sin fecha";
  }
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date(value));
}

function isErrorMessage(message: string) {
  return message.startsWith("HTTP") || message.startsWith("No se") || message.startsWith("Invalid") || message.includes("token");
}
