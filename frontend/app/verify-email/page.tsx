"use client";

import { CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";

import { apiJson, jsonHeaders } from "../../lib/apiClient";
import { type AuthSession, writeAuthSession } from "../../lib/authClient";

export default function VerifyEmailPage() {
  const [message, setMessage] = useState("Verificando email.");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      setMessage("Token no informado.");
      return;
    }
    void verify(token);
  }, []);

  async function verify(token: string) {
    try {
      const session = await apiJson<AuthSession>("/api/v1/auth/verify-email", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ token })
      });
      writeAuthSession(session);
      window.location.href = session.company_access.length ? "/select-company" : "/onboarding/company";
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo verificar el email.");
    }
  }

  return (
    <main className="authShell narrow">
      <section className="panel authPanel">
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Email</p>
            <h1>Verificacion</h1>
          </div>
          <CheckCircle2 aria-hidden="true" size={22} />
        </div>
        <div className={`messageBar ${message.startsWith("No ") || message.startsWith("Token") ? "error" : "ok"}`}>
          <span>{message}</span>
        </div>
        <a className="secondaryButton inlineButton" href="/login">
          Volver al login
        </a>
      </section>
    </main>
  );
}
