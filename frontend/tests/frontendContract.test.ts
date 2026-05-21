import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { apiBaseUrl, tenantHeaders } from "../lib/apiClient";

describe("frontend contract", () => {
  it("uses the backend API instead of local fixture data", () => {
    expect(apiBaseUrl).toMatch(/^http:\/\/127\.0\.0\.1:8001|^http:\/\/localhost:8001|^https?:\/\//);
    expect(tenantHeaders).toEqual({});
  });

  it("removes old UI routes that no longer belong to the new platform centre", () => {
    const removedRoutes = [
      "admin",
      "audit",
      "authorizations",
      "documents",
      "intake",
      "requirements",
      "system",
      "transfers",
      "workers"
    ];

    for (const route of removedRoutes) {
      expect(existsSync(join(process.cwd(), "app", route, "page.tsx"))).toBe(false);
    }
    expect(existsSync(join(process.cwd(), "app", "components", "DashboardClient.tsx"))).toBe(false);
    expect(existsSync(join(process.cwd(), "lib", "i18n.ts"))).toBe(false);
  });

  it("keeps navigation global and grouped for every operational page", () => {
    const layout = readFileSync(join(process.cwd(), "app", "layout.tsx"), "utf-8");
    const appShell = readFileSync(join(process.cwd(), "app", "components", "AppShell.tsx"), "utf-8");
    const platformsPage = readFileSync(join(process.cwd(), "app", "platforms", "page.tsx"), "utf-8");
    const loginPage = readFileSync(join(process.cwd(), "app", "login", "page.tsx"), "utf-8");
    const selectCompanyPage = readFileSync(join(process.cwd(), "app", "select-company", "page.tsx"), "utf-8");
    expect(layout).toContain("<AppShell>{children}</AppShell>");
    expect(appShell).toContain("ARM");
    expect(appShell).toContain("Empresa y trabajadores");
    expect(appShell).toContain("Operativa");
    expect(appShell).toContain("Plataformas");
    expect(appShell).toContain("Anadir trabajador");
    expect(appShell).toContain("Notificaciones");
    expect(appShell).toContain('"/select-company"');
    expect(appShell).toContain("readSelectedCompany");
    expect(loginPage).toContain("nextPath");
    expect(loginPage).toContain("return \"/arm\"");
    expect(selectCompanyPage).toContain("Selecciona empresa");
    expect(selectCompanyPage).toContain("Confirmar empresa");
    expect(selectCompanyPage).toContain("Entrar demo/ARM");
    expect(selectCompanyPage).toContain("clearAuthSession");
    expect(appShell).toContain('href: "/arm"');
    expect(appShell).toContain('href: "/platforms"');
    expect(appShell).toContain('href: "/assign-worker"');
    expect(appShell).toContain('href: "/notifications"');
    expect(platformsPage).not.toContain('className="shell"');
    expect(platformsPage).not.toContain('className="sidebar"');
  });

  it("provides a dedicated ARM area separated from platform operations", () => {
    const armPage = readFileSync(join(process.cwd(), "app", "arm", "page.tsx"), "utf-8");
    const homePage = readFileSync(join(process.cwd(), "app", "page.tsx"), "utf-8");
    expect(homePage).toContain('redirect("/arm" as Route)');
    expect(armPage).toContain("Empresa y trabajadores");
    expect(armPage).toContain("Ficha empresa");
    expect(armPage).toContain("Empresa ARM");
    expect(armPage).toContain("Listado de trabajadores");
    expect(armPage).toContain("Volver al listado");
    expect(armPage).toContain("Guardar empresa");
    expect(armPage).toContain("Guardar trabajador");
    expect(armPage).toContain("Subir documento de empresa");
    expect(armPage).toContain("Subir documento de trabajador");
    expect(armPage).toContain("Documentos de empresa");
    expect(armPage).toContain("Ultima subida");
    expect(armPage).toContain("Descargar");
    expect(armPage).toContain("Documentos de ${fullName(selectedWorker)}");
    expect(armPage).toContain("hydrateDocuments");
    expect(armPage).toContain("/api/v1/document-types");
    expect(armPage).toContain("/api/v1/companies");
    expect(armPage).toContain("/api/v1/workers");
    expect(armPage).toContain("/api/v1/documents");
    expect(armPage).toContain("method: \"PUT\"");
    expect(armPage).toContain("source\", \"manual\"");
    expect(armPage).not.toContain("Evidencias pendientes de validacion");
    expect(armPage).not.toContain("/api/v1/document-intake");
    expect(armPage).not.toContain("/api/v1/platform-contracts/manifests");
  });

  it("uses the new platform operations page instead of the old technical catalog", () => {
    const platformsPage = readFileSync(join(process.cwd(), "app", "platforms", "page.tsx"), "utf-8");
    expect(platformsPage).toContain("Contextos de plataforma");
    expect(platformsPage).toContain("Conectar plataforma autorizada");
    expect(platformsPage).toContain("/api/v1/platform-contracts/manifests");
    expect(platformsPage).toContain("/api/v1/platform-contracts/accounts");
    expect(platformsPage).toContain("/api/v1/platform-review-schedules");
    expect(platformsPage).toContain("/api/v1/platform-maps/edit-methods");
    expect(platformsPage).toContain("/api/v1/rpa-gateway/requests");
    expect(platformsPage).toContain("Desactivar");
    expect(platformsPage).toContain("Activar");
    expect(platformsPage).toContain("plataforma + empresa + centro");
    expect(platformsPage).toContain("Preview escritura");
    expect(platformsPage).toContain("Escritura");
    expect(platformsPage).toContain("writeStatusLabel");
    expect(platformsPage).not.toContain("/api/v1/platforms/catalog");
    expect(platformsPage).not.toContain("API oficial");
    expect(platformsPage).not.toContain("Investigacion tecnica");
  });

  it("provides worker-to-platform assignment and active-platform notifications", () => {
    const assignWorkerPage = readFileSync(join(process.cwd(), "app", "assign-worker", "page.tsx"), "utf-8");
    const notificationsPage = readFileSync(join(process.cwd(), "app", "notifications", "page.tsx"), "utf-8");
    expect(assignWorkerPage).toContain("Anadir trabajador a plataforma");
    expect(assignWorkerPage).toContain("draggable");
    expect(assignWorkerPage).toContain("onDropWorker");
    expect(assignWorkerPage).toContain("Anadir a todas");
    expect(assignWorkerPage).toContain("platform-registrations");
    expect(assignWorkerPage).toContain("targetStateForWorker");
    expect(assignWorkerPage).toContain("ya existe");
    expect(assignWorkerPage).toContain("disponible");
    expect(assignWorkerPage).toContain("BLOCKING_REGISTRATION_STATUSES");
    expect(assignWorkerPage).toContain("upload_worker_document");
    expect(assignWorkerPage).toContain("upsert_worker");
    expect(notificationsPage).toContain("Solo plataformas activas");
    expect(notificationsPage).toContain("buildNotificationRows");
    expect(notificationsPage).toContain("schedule.enabled");
    expect(notificationsPage).toContain("Revisar ahora");
    expect(notificationsPage).toContain("/api/v1/platform-maps/validation-surfaces");
    expect(notificationsPage).toContain("Evidencias pendientes de validacion");
    expect(notificationsPage).toContain("buildEvidenceNotificationRows");
    expect(notificationsPage).toContain("/api/v1/document-intake");
  });

  it("keeps the RPA gateway human-assisted before opening external pages", () => {
    const gatewayPage = readFileSync(join(process.cwd(), "app", "rpa-gateway", "page.tsx"), "utf-8");
    expect(gatewayPage).toContain("Autorizar entrada");
    expect(gatewayPage).toContain("launch-visible-browser");
    expect(gatewayPage).toContain("Lanzar navegador guiado");
    expect(gatewayPage).toContain("Generar flujo y abrir navegador guiado");
    expect(gatewayPage).toContain("Flujo guiado actual");
    expect(gatewayPage).toContain("Estado del navegador");
    expect(gatewayPage).toContain("browser-status");
    expect(gatewayPage).toContain("selected_login_variant");
    expect(gatewayPage).toContain("Variante login");
    expect(gatewayPage).toContain("Sincronizar lectura con Hub");
    expect(gatewayPage).toContain("sync-readonly-capture");
    expect(gatewayPage).toContain("Credenciales: configuradas en el servidor");
    expect(gatewayPage).toContain("No se pudo registrar la decision");
    expect(gatewayPage).not.toContain("Crear peticion de revision");
  });
});
