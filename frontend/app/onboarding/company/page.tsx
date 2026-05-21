"use client";

import { Building2, Save } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { apiJson, jsonHeaders } from "../../../lib/apiClient";
import { readAuthSession } from "../../../lib/authClient";

type Company = {
  id: number;
  tenant_id: number;
  name: string;
  tax_id: string | null;
  company_type: string;
  address: string | null;
  status: string;
};

export default function CompanyOnboardingPage() {
  const [name, setName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [address, setAddress] = useState("");
  const [companyType, setCompanyType] = useState("own");
  const [message, setMessage] = useState("Completa los datos de la empresa.");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const session = readAuthSession();
    if (!session) {
      window.location.href = "/login";
      return;
    }
    const firstCompany = session.company_access[0];
    if (firstCompany) {
      setName(firstCompany.company_name);
      setCompanyType(firstCompany.company_type);
    }
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("Guardando empresa.");
    try {
      const company = await apiJson<Company>("/api/v1/auth/companies/onboarding", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          name,
          tax_id: taxId || null,
          company_type: companyType,
          address: address || null
        })
      });
      setMessage(`Empresa ${company.name} creada.`);
      window.location.href = "/select-company";
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo guardar la empresa.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="authShell narrow">
      <form className="panel authPanel" onSubmit={handleSubmit}>
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Onboarding</p>
            <h1>Datos de empresa</h1>
          </div>
          <Building2 aria-hidden="true" size={22} />
        </div>
        <div className={`messageBar ${message.startsWith("No ") || message.startsWith("HTTP") ? "error" : "ok"}`}>
          <span>{message}</span>
        </div>
        <label className="field">
          <span>Nombre legal</span>
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label className="field">
          <span>CIF/NIF</span>
          <input value={taxId} onChange={(event) => setTaxId(event.target.value)} />
        </label>
        <label className="field">
          <span>Tipo</span>
          <select value={companyType} onChange={(event) => setCompanyType(event.target.value)}>
            <option value="own">Empresa propia</option>
            <option value="client">Cliente</option>
            <option value="contractor">Contrata</option>
            <option value="subcontractor">Subcontrata</option>
          </select>
        </label>
        <label className="field">
          <span>Direccion</span>
          <textarea value={address} onChange={(event) => setAddress(event.target.value)} rows={4} />
        </label>
        <button className="primaryButton inlineButton" type="submit" disabled={busy}>
          <Save aria-hidden="true" size={16} />
          Guardar empresa
        </button>
      </form>
    </main>
  );
}
