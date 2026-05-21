"use client";

import { Building2, CheckCircle2, LogIn } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { apiJson, jsonHeaders } from "../../lib/apiClient";
import {
  type AuthCompanyAccess,
  type AuthSession,
  clearAuthSession,
  readAuthSession,
  writeAuthSession,
  writeSelectedCompany
} from "../../lib/authClient";

type AuthMe = Pick<AuthSession, "tenant_id" | "user" | "company_access">;

function safeNextPath(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/arm";
  }
  if (value.startsWith("/login") || value.startsWith("/select-company")) {
    return "/arm";
  }
  return value;
}

export default function SelectCompanyPage() {
  const [companies, setCompanies] = useState<AuthCompanyAccess[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(null);
  const [message, setMessage] = useState("Selecciona empresa antes de operar.");
  const [busy, setBusy] = useState(false);
  const nextPath = useMemo(() => {
    if (typeof window === "undefined") {
      return "/arm";
    }
    return safeNextPath(new URLSearchParams(window.location.search).get("next"));
  }, []);

  useEffect(() => {
    void loadSession();
  }, []);

  function applyCompanies(nextCompanies: AuthCompanyAccess[]) {
    setCompanies(nextCompanies);
    setSelectedCompanyId(nextCompanies[0]?.company_id ?? null);
    if (nextCompanies.length === 1) {
      setMessage(`Solo esta disponible ${nextCompanies[0].company_name}.`);
    } else if (nextCompanies.length > 1) {
      setMessage("Selecciona empresa antes de operar.");
    } else {
      setMessage("Tu sesion no tiene empresas asignadas. Puedes reiniciar con la demo ARM.");
    }
  }

  async function loadSession() {
    const session = readAuthSession();
    if (!session) {
      window.location.href = "/login";
      return;
    }
    applyCompanies(session.company_access);
    if (session.company_access.length === 0) {
      try {
        const fresh = await apiJson<AuthMe>("/api/v1/auth/me");
        const refreshedSession: AuthSession = {
          ...session,
          tenant_id: fresh.tenant_id,
          user: fresh.user,
          company_access: fresh.company_access
        };
        writeAuthSession(refreshedSession);
        applyCompanies(refreshedSession.company_access);
      } catch {
        setMessage("La sesion actual no tiene empresa asignada. Entra con demo/ARM para probar.");
      }
    }
  }

  function confirmCompany() {
    const company = companies.find((item) => item.company_id === selectedCompanyId);
    if (!company) {
      setMessage("No hay empresa autorizada para esta sesion.");
      return;
    }
    writeSelectedCompany(company);
    window.location.href = nextPath;
  }

  async function enterDemoArm() {
    setBusy(true);
    setMessage("Reiniciando sesion demo ARM.");
    try {
      clearAuthSession();
      const session = await apiJson<AuthSession>("/api/v1/auth/login", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          email: "demo",
          password: "demo",
          tenant_id: null
        })
      });
      writeAuthSession(session);
      const company = session.company_access[0];
      if (!company) {
        setMessage("La cuenta demo no tiene ARM asignada en el backend.");
        return;
      }
      writeSelectedCompany(company);
      window.location.href = nextPath;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo iniciar la demo ARM.");
    } finally {
      setBusy(false);
    }
  }

  function changeUser() {
    clearAuthSession();
    window.location.href = "/login";
  }

  const selectedCompany = companies.find((item) => item.company_id === selectedCompanyId) ?? null;

  return (
    <main className="authShell narrow">
      <section className="authIntro">
        <p className="eyebrow">Contexto obligatorio</p>
        <h1>Selecciona empresa</h1>
        <p>Esta confirmacion evita operar sobre una empresa equivocada.</p>
        <div className={`messageBar ${companies.length ? "ok" : "error"}`}>
          <span>{companies.length ? message : "Tu usuario no tiene empresas asignadas."}</span>
        </div>
      </section>

      <section className="panel authPanel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Empresa activa</p>
            <h2>{selectedCompany?.company_name ?? "Sin empresa"}</h2>
          </div>
          <Building2 aria-hidden="true" size={20} />
        </div>

        <div className="companyChoiceList" role="radiogroup" aria-label="Empresa activa">
          {companies.map((company) => {
            const selected = company.company_id === selectedCompanyId;
            return (
              <button
                className={`roleBox selectableCard ${selected ? "selectedCard" : ""}`}
                type="button"
                role="radio"
                aria-checked={selected}
                key={company.company_id}
                onClick={() => setSelectedCompanyId(company.company_id)}
              >
                <div className="inlineTitle">
                  <Building2 aria-hidden="true" size={18} />
                  <h3>{company.company_name}</h3>
                </div>
                <p>{company.company_type} / {company.access_level}</p>
              </button>
            );
          })}
        </div>

        <button className="primaryButton inlineButton" type="button" disabled={!selectedCompany || busy} onClick={confirmCompany}>
          <CheckCircle2 aria-hidden="true" size={16} />
          Confirmar empresa
        </button>
        {!selectedCompany ? (
          <button className="primaryButton inlineButton" type="button" disabled={busy} onClick={() => void enterDemoArm()}>
            <CheckCircle2 aria-hidden="true" size={16} />
            Entrar demo/ARM
          </button>
        ) : null}
        <button className="secondaryButton inlineButton" type="button" disabled={busy} onClick={changeUser}>
          <LogIn aria-hidden="true" size={16} />
          Cambiar usuario
        </button>
      </section>
    </main>
  );
}
