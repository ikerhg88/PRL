"use client";

import { useEffect, useState } from "react";

import { apiJson, jsonHeaders } from "../../../../lib/apiClient";
import { type AuthSession, writeAuthSession } from "../../../../lib/authClient";

export default function GoogleCallbackPage() {
  const [message, setMessage] = useState("Completando Google SSO.");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const state = params.get("state");
    const code = params.get("code");
    if (!state || !code) {
      setMessage("Google no devolvio state y code.");
      return;
    }
    void complete(state, code);
  }, []);

  async function complete(state: string, code: string) {
    try {
      const session = await apiJson<AuthSession>("/api/v1/auth/google/signup/callback", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({ state, code })
      });
      writeAuthSession(session);
      window.location.href = session.company_access.length ? "/select-company" : "/onboarding/company";
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo completar Google SSO.");
    }
  }

  return (
    <main className="authShell narrow">
      <section className="panel authPanel">
        <p className="eyebrow">Google SSO</p>
        <h1>Callback</h1>
        <div className={`messageBar ${message.startsWith("No ") || message.includes("no ") ? "error" : "ok"}`}>
          <span>{message}</span>
        </div>
        <a className="secondaryButton inlineButton" href="/login">
          Volver al login
        </a>
      </section>
    </main>
  );
}
