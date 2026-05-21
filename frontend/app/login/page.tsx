"use client";

import { LogIn, ShieldCheck } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import { apiJson, jsonHeaders } from "../../lib/apiClient";
import { clearSelectedCompany, type AuthSession, writeAuthSession } from "../../lib/authClient";

export default function LoginPage() {
  const [loginEmail, setLoginEmail] = useState("demo");
  const [loginPassword, setLoginPassword] = useState("demo");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const nextPath = useMemo(() => {
    if (typeof window === "undefined") {
      return "/arm";
    }
    const raw = new URLSearchParams(window.location.search).get("next");
    if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) {
      return "/arm";
    }
    return raw;
  }, []);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("Validando acceso local.");
    try {
      const session = await apiJson<AuthSession>("/api/v1/auth/login", {
        method: "POST",
        headers: jsonHeaders(),
        body: JSON.stringify({
          email: loginEmail,
          password: loginPassword,
          tenant_id: null
        })
      });
      clearSelectedCompany();
      writeAuthSession(session);
      window.location.href = `/select-company?next=${encodeURIComponent(nextPath)}`;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No se pudo iniciar sesion.");
    } finally {
      setBusy(false);
    }
  }

  const isError = message.startsWith("No ") || message.startsWith("HTTP") || message.startsWith("Invalid");

  return (
    <main className="authShell narrow">
      <section className="authIntro">
        <p className="eyebrow">IPRL/CAE Hub</p>
        <h1>Acceso a la aplicacion</h1>
        <p>Alta SaaS, verificacion de email y Google signup quedan fuera de la pantalla mientras probamos la aplicacion local.</p>
        <div className={`messageBar ${isError ? "error" : "ok"}`}>
          <span>{message || "Usa demo/demo para entrar al entorno de trabajo actual."}</span>
        </div>
      </section>

      <form className="panel authPanel" onSubmit={handleLogin}>
        <div className="sectionTitle">
          <div>
            <p className="eyebrow">Sesion local</p>
            <h2>Entrar</h2>
          </div>
          <LogIn aria-hidden="true" size={20} />
        </div>
        <label className="field">
          <span>Usuario o email</span>
          <input value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} autoComplete="username" required />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            value={loginPassword}
            onChange={(event) => setLoginPassword(event.target.value)}
            type="password"
            autoComplete="current-password"
            required
          />
        </label>
        <button className="primaryButton" type="submit" disabled={busy}>
          Entrar
        </button>
        <p className="smallText">
          <ShieldCheck aria-hidden="true" size={15} />
          La prueba de captcha es asistida por humano: no se saltan controles y no se escriben datos en terceros.
        </p>
      </form>
    </main>
  );
}
