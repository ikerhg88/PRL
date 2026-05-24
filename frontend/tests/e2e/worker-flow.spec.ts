import { expect, test } from "@playwright/test";

test("login and navigate the new platform operations UX", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Usuario o email").first().fill("demo");
  await page.getByLabel("Password").first().fill("demo");
  await page.getByRole("button", { name: "Entrar", exact: true }).click();
  await expect(page).toHaveURL(/\/select-company/);
  await page.getByRole("button", { name: "Confirmar empresa" }).click();

  await expect(page).toHaveURL(/\/arm/);
  await expect(page.getByRole("heading", { name: "Empresa y trabajadores" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Empresa ARM/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Trabajadores" })).toBeVisible();
  await expect(page.getByText(/ARM actualizado: \d+ trabajadores/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Documentos de empresa" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Ultima subida" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Trabajadores" })).toBeVisible();
  await page.getByRole("button", { name: "Trabajadores" }).click();
  await expect(page.getByRole("heading", { name: "Listado de trabajadores" })).toBeVisible();
  await expect(page.getByLabel("Filtros de trabajadores").getByLabel("Estado trabajador")).toBeVisible();
  await expect(page.getByLabel("Filtros de trabajadores").getByLabel("Documentos")).toBeVisible();
  await expect(page.getByRole("button", { name: "Crear trabajador" })).toBeVisible();
  await page.getByRole("button", { name: "Crear trabajador" }).click();
  await expect(page.getByLabel("Crear trabajador ARM")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancelar" })).toBeVisible();
  await page.getByRole("button", { name: "Cancelar" }).click();
  await expect(page.getByLabel("Trabajadores ARM").getByText("Eleder Bilbao Egusquiza")).toBeVisible();
  await page.getByLabel("Trabajadores ARM").getByText("Eleder Bilbao Egusquiza").click();
  await expect(page.getByRole("button", { name: "Volver al listado" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Dar de baja" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Documentos de Eleder Bilbao Egusquiza" })).toBeVisible();
  await expect(page.getByText(/zona hub/i).first()).toBeVisible();
  await expect(page.getByText(/nuevo tipo documental hub/i).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Crear tipo" }).first()).toBeVisible();
  await expect(page.getByText("CAE.WORKER.FORKLIFT_TRAINING", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Editar" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Editar" }).first().click();
  await expect(page.getByText(/fichero nuevo/i).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Guardar fechas" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Subir version" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Descargar" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidencias pendientes de validacion" })).toHaveCount(0);

  await page.getByRole("link", { name: "Plataformas" }).click();
  await expect(page).toHaveURL(/\/platforms/);
  await expect(page.getByRole("heading", { name: "Plataformas", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Contextos de plataforma/ })).toBeVisible();
  await expect(page.getByText("Verificacion y superficies")).toBeVisible();
  await expect(page.getByText("Las superficies son pantallas, tablas o exports")).toBeVisible();
  await expect(page.getByLabel("Filtro").getByLabel("Que les pasa")).toBeVisible();
  await expect(page.getByLabel("Filtro").getByLabel("Verificacion")).toBeVisible();
  await expect(page.getByLabel("Filtro").getByLabel("Escritura")).toBeVisible();
  await expect(page.getByLabel("Filtro").getByLabel("Operativa completa")).toBeVisible();
  await expect(page.getByText("Preview escritura")).toBeVisible();
  await expect(page.getByText("Escritura").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Analizar ahora" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Preparar 100%" }).first()).toBeVisible();
  await expect(page.getByText("Conectar plataforma autorizada")).toBeVisible();
  await expect(page.getByRole("table", { name: "Plataformas activas" }).getByText("CTAIMA / CTAIMA CAE").first()).toBeVisible();

  await page.getByRole("link", { name: "Anadir trabajador" }).click();
  await expect(page).toHaveURL(/\/assign-worker/);
  await expect(page.getByRole("heading", { name: "Anadir trabajador a plataforma" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Anadir a todas/ })).toBeVisible();
  await expect(page.getByText("Preparacion escritura real")).toBeVisible();

  await page.getByRole("link", { name: "Notificaciones" }).click();
  await expect(page).toHaveURL(/\/notifications/);
  await expect(page.getByRole("heading", { name: "Notificaciones" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Preparar cambios desde el Hub" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Preparar actualizaciones" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Madurar mapeos" })).toBeVisible();
  await expect(page.getByText("Solo plataformas activas")).toBeVisible();
  await expect(page.getByLabel("Filtros de notificaciones").getByLabel("Buscar")).toBeVisible();
  await expect(page.getByLabel("Filtros de notificaciones").getByLabel("Origen")).toBeVisible();
  await expect(page.getByLabel("Filtros de notificaciones").getByLabel("Visibilidad")).toBeVisible();
  await expect(page.getByLabel("Filtros de notificaciones").getByLabel("Ocultar anteriores a")).toBeVisible();
  const notificationsTable = page.getByRole("table", { name: "Notificaciones activas" });
  await expect(notificationsTable).toBeVisible();
  const dismissButtons = notificationsTable.getByRole("button", { name: "Anular" });
  if ((await dismissButtons.count()) > 0) {
    await expect(dismissButtons.first()).toBeVisible();
  } else {
    await expect(notificationsTable.getByText("Sin avisos para plataformas activas.")).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "Evidencias pendientes de validacion" })).toBeVisible();
});
