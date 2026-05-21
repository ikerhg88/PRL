"use client";

import {
  ArrowLeft,
  Building2,
  CalendarDays,
  Download,
  FileText,
  RefreshCw,
  Save,
  Search,
  Upload,
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

const ARM_TAX_ID = "B95868543";

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
  cae_notes: ""
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
  const [companyForm, setCompanyForm] = useState(emptyCompanyForm);
  const [workerForm, setWorkerForm] = useState(emptyWorkerForm);
  const [companyDocumentTypeId, setCompanyDocumentTypeId] = useState("");
  const [workerDocumentTypeId, setWorkerDocumentTypeId] = useState("");
  const [documentSearch, setDocumentSearch] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [issuedAt, setIssuedAt] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [platformExpiresAt, setPlatformExpiresAt] = useState("");
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
  const pendingDocuments = armDocuments.filter((row) => row.document.status_internal === "pending_internal_review").length;
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
  const filteredWorkers = armWorkers.filter((worker) => fullName(worker).toLowerCase().includes(search.trim().toLowerCase()));

  useEffect(() => {
    setCompanyForm(companyToForm(armCompany));
  }, [armCompany?.id]);

  useEffect(() => {
    setWorkerForm(workerToForm(selectedWorker));
  }, [selectedWorker?.id]);

  useEffect(() => {
    if (!companyDocumentTypeId && companyDocumentTypes[0]) {
      setCompanyDocumentTypeId(String(companyDocumentTypes[0].id));
    }
    if (!workerDocumentTypeId && workerDocumentTypes[0]) {
      setWorkerDocumentTypeId(String(workerDocumentTypes[0].id));
    }
  }, [companyDocumentTypeId, companyDocumentTypes, workerDocumentTypeId, workerDocumentTypes]);

  async function loadData(nextWorkerId?: number) {
    setBusy(true);
    try {
      const [companyRows, workerRows, typeRows, documentRows] = await Promise.all([
        apiJson<Company[]>("/api/v1/companies"),
        apiJson<Worker[]>("/api/v1/workers"),
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
        body: JSON.stringify({
          company_id: Number(workerForm.company_id),
          first_name: nullable(workerForm.first_name),
          last_name: nullable(workerForm.last_name),
          identifier_type: nullable(workerForm.identifier_type),
          identifier_value: nullable(workerForm.identifier_value),
          identifier_expires_at: workerForm.identifier_expires_at || null,
          nationality: nullable(workerForm.nationality),
          email: nullable(workerForm.email),
          phone: nullable(workerForm.phone),
          social_security_number: nullable(workerForm.social_security_number),
          contract_type: nullable(workerForm.contract_type),
          starts_at: workerForm.starts_at || null,
          ends_at: workerForm.ends_at || null,
          work_position: nullable(workerForm.work_position),
          work_center_name: nullable(workerForm.work_center_name),
          risk_profile: nullable(workerForm.risk_profile),
          employment_status: nullable(workerForm.employment_status),
          medical_fitness_status: nullable(workerForm.medical_fitness_status),
          medical_fitness_issued_at: workerForm.medical_fitness_issued_at || null,
          medical_fitness_expires_at: workerForm.medical_fitness_expires_at || null,
          medical_fitness_provider: nullable(workerForm.medical_fitness_provider),
          medical_fitness_restrictions: nullable(workerForm.medical_fitness_restrictions),
          cae_notes: nullable(workerForm.cae_notes)
        })
      });
      await loadData(updated.id);
      setMessage(`Trabajador actualizado: ${fullName(updated)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo actualizar el trabajador.");
    } finally {
      setBusy(false);
    }
  }

  async function uploadDocument(event: FormEvent<HTMLFormElement>, entityType: DocumentTarget) {
    event.preventDefault();
    if (!uploadFile) {
      setMessage("Selecciona un fichero antes de subir.");
      return;
    }
    const entityId = entityType === "company" ? armCompany?.id : selectedWorker?.id;
    const documentTypeId = Number(entityType === "company" ? companyDocumentTypeId : workerDocumentTypeId);
    if (!entityId || !documentTypeId) {
      setMessage("Selecciona entidad y tipo documental normalizado.");
      return;
    }
    setBusy(true);
    try {
      const existingDocument = documents.find(
        (row) =>
          row.document.entity_type === entityType &&
          row.document.entity_id === entityId &&
          row.document.document_type_id === documentTypeId
      )?.document;
      const documentRecord =
        existingDocument ??
        (await apiJson<DocumentRecord>("/api/v1/documents", {
          method: "POST",
          headers: jsonHeaders(),
          body: JSON.stringify({
            document_type_id: documentTypeId,
            entity_type: entityType,
            entity_id: entityId,
            status_internal: "draft"
          })
        }));
      const formData = new FormData();
      formData.append("file", uploadFile);
      formData.append("source", "manual");
      if (issuedAt) {
        formData.append("issued_at", issuedAt);
      }
      if (expiresAt) {
        formData.append("expires_at", expiresAt);
      }
      if (platformExpiresAt) {
        formData.append("platform_expires_at", platformExpiresAt);
        formData.append("platform_expiry_source", "manual");
      }
      const version = await apiJson<DocumentVersion>(`/api/v1/documents/${documentRecord.id}/upload`, {
        method: "POST",
        body: formData
      });
      resetUploadForm();
      await loadData(selectedWorker?.id);
      setMessage(`Nueva version documental cargada: ${version.filename}. SHA-256 ${version.sha256.slice(0, 12)}...`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo subir el documento.");
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
    resetUploadForm();
  }

  function openCompanyView() {
    setActiveView("company");
    setWorkerDetailOpen(false);
    setDocumentSearch("");
    resetUploadForm();
  }

  function openWorkersView() {
    setActiveView("workers");
    setWorkerDetailOpen(false);
    setDocumentSearch("");
    resetUploadForm();
  }

  function resetUploadForm() {
    setUploadFile(null);
    setIssuedAt("");
    setExpiresAt("");
    setPlatformExpiresAt("");
  }

  function renderUploadForm(entityType: DocumentTarget) {
    const typeOptions = entityType === "company" ? companyDocumentTypes : workerDocumentTypes;
    const typeId = entityType === "company" ? companyDocumentTypeId : workerDocumentTypeId;
    const title = entityType === "company" ? "Subir documento de empresa" : "Subir documento de trabajador";
    const subtitle = entityType === "company" ? armCompany?.name : selectedWorker ? fullName(selectedWorker) : null;

    return (
      <section className="panel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Nueva version</p>
            <h3>{title}</h3>
            <small className="muted">{subtitle ?? "Selecciona una entidad antes de subir."}</small>
          </div>
          <Upload aria-hidden="true" size={20} />
        </div>
        <form className="armUploadGrid" onSubmit={(event) => void uploadDocument(event, entityType)}>
          <label>
            <span>Tipo normalizado</span>
            <select
              value={typeId}
              onChange={(event) =>
                entityType === "company"
                  ? setCompanyDocumentTypeId(event.target.value)
                  : setWorkerDocumentTypeId(event.target.value)
              }
            >
              {typeOptions.map((type) => (
                <option value={type.id} key={type.id}>{type.name} / {type.code}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Fichero</span>
            <input type="file" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
          </label>
          <label>
            <span>Emision</span>
            <input type="date" value={issuedAt} onChange={(event) => setIssuedAt(event.target.value)} />
          </label>
          <label>
            <span>Cad. empresa</span>
            <input type="date" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} />
          </label>
          <label>
            <span>Cad. plataforma</span>
            <input type="date" value={platformExpiresAt} onChange={(event) => setPlatformExpiresAt(event.target.value)} />
          </label>
          <button className="primaryButton" type="submit" disabled={busy || !typeOptions.length}>
            <Upload aria-hidden="true" size={16} />
            Subir version
          </button>
        </form>
      </section>
    );
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
        <Metric icon={UsersRound} label="Trabajadores" value={String(armWorkers.length)} />
        <Metric icon={FileText} label="Documentos" value={String(armDocuments.length)} />
        <Metric icon={CalendarDays} label="Pendientes / caducados" value={`${pendingDocuments} / ${expiredDocuments}`} />
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

          {renderUploadForm("company")}
          <DocumentTable
            title="Documentos de empresa"
            rows={visibleCompanyDocuments}
            totalRows={companyDocuments.length}
            query={documentSearch}
            onQueryChange={setDocumentSearch}
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
          </div>

          <section className="armCompanyGrid" aria-label="Resumen documental del trabajador">
            <InfoBox label="Estado laboral" value={selectedWorker.employment_status} badgeClass={selectedWorker.employment_status} />
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

          {renderUploadForm("worker")}
          <DocumentTable
            title={`Documentos de ${fullName(selectedWorker)}`}
            rows={visibleWorkerDocuments}
            totalRows={selectedWorkerDocuments.length}
            query={documentSearch}
            onQueryChange={setDocumentSearch}
            onDownload={(row) => void downloadDocument(row)}
          />
        </section>
      ) : (
        <section className="armScreen" aria-label="Listado de trabajadores ARM">
          <section className="panel">
            <div className="sectionTitle">
              <div>
                <p className="eyebrow">Trabajadores ARM</p>
                <h3>Listado de trabajadores</h3>
              </div>
              <label className="compactSearch">
                <span>Buscar</span>
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Nombre o apellido" />
              </label>
            </div>
            <div className="armDirectoryGrid" aria-label="Trabajadores ARM">
              {filteredWorkers.map((worker) => {
                const stats = workerDocumentStatus(worker.id, documents);
                return (
                  <button className="workerDirectoryItem" type="button" onClick={() => openWorker(worker.id)} key={worker.id}>
                    <span>
                      <strong>{fullName(worker)}</strong>
                      <small>{worker.work_position ?? "Puesto pendiente"} / {worker.work_center_name ?? "Centro pendiente"}</small>
                      <small>
                        {workerDocumentCounts.get(worker.id) ?? 0} documentos · {stats.pending} pendientes · {stats.expired} caducados
                      </small>
                    </span>
                    <span>
                      <span className={`statusBadge ${worker.status}`}>{worker.status}</span>
                      <small>Aptitud: {worker.medical_fitness_status ?? "pendiente"}</small>
                    </span>
                  </button>
                );
              })}
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
  title,
  rows,
  totalRows,
  query,
  onQueryChange,
  onDownload
}: {
  title: string;
  rows: DocumentRow[];
  totalRows: number;
  query: string;
  onQueryChange: (value: string) => void;
  onDownload: (row: DocumentRow) => void;
}) {
  return (
    <section className="panel">
      <div className="sectionTitle">
        <div>
          <p className="eyebrow">Repositorio ARM</p>
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
      <div className="table" role="table" aria-label={title}>
        <div className="tableRow armDocumentHead" role="row">
          <span role="columnheader">Documento</span>
          <span role="columnheader">Estado</span>
          <span role="columnheader">Ultima subida</span>
          <span role="columnheader">Caducidad</span>
          <span role="columnheader">Fichero</span>
          <span role="columnheader">Accion</span>
        </div>
        {rows.map((row) => (
          <div className="tableRow armDocumentRow" role="row" key={row.document.id}>
            <span role="cell">
              <strong>{row.type?.name ?? "Tipo no localizado"}</strong>
              <small>{row.type?.code ?? `type:${row.document.document_type_id}`}</small>
            </span>
            <span role="cell"><span className={`statusBadge ${row.document.status_internal}`}>{row.document.status_internal}</span></span>
            <span role="cell">
              {row.currentVersion ? formatDateTime(row.currentVersion.created_at) : "Sin version"}
              <small>
                {row.currentVersion ? `${row.versions.length} version(es) / actual v${row.currentVersion.version_number} / ${row.currentVersion.source}` : "Crea una version"}
              </small>
            </span>
            <span role="cell">
              Empresa: {formatDate(row.currentVersion?.expires_at)}
              <small>Plataforma: {formatDate(row.currentVersion?.platform_expires_at)}</small>
            </span>
            <span role="cell">
              {row.currentVersion?.filename ?? "Sin fichero"}
              <small>{row.currentVersion ? `${formatBytes(row.currentVersion.size_bytes)} / SHA ${row.currentVersion.sha256.slice(0, 10)}` : "Pendiente"}</small>
            </span>
            <span role="cell">
              <button className="secondaryButton inlineButton" type="button" disabled={!row.currentVersion} onClick={() => onDownload(row)}>
                <Download aria-hidden="true" size={14} />
                Descargar
              </button>
            </span>
          </div>
        ))}
        {rows.length === 0 ? (
          <div className="tableRow armDocumentRow" role="row">
            <span role="cell">Sin documentos cargados.</span>
            <span role="cell"><span className="statusBadge missing">missing</span></span>
            <span role="cell">Pendiente</span>
            <span role="cell">Pendiente</span>
            <span role="cell">Sube un fichero normalizado.</span>
            <span role="cell">-</span>
          </div>
        ) : null}
      </div>
    </section>
  );
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
    pending: workerRows.filter((row) => row.document.status_internal === "pending_internal_review").length,
    expired: workerRows.filter((row) => row.document.status_internal === "expired").length
  };
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
    cae_notes: worker.cae_notes ?? ""
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
