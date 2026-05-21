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
  await expect(page.getByLabel("Trabajadores ARM").getByText("Alicia Gomez Moreno")).toBeVisible();
  await page.getByLabel("Trabajadores ARM").getByText("Alicia Gomez Moreno").click();
  await expect(page.getByRole("button", { name: "Volver al listado" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Documentos de Alicia Gomez Moreno" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Subir documento de trabajador" })).toBeVisible();
  await expect(page.getByText("CAE.WORKER.FORKLIFT_TRAINING", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Descargar" }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidencias pendientes de validacion" })).toHaveCount(0);

  await page.getByRole("link", { name: "Plataformas" }).click();
  await expect(page).toHaveURL(/\/platforms/);
  await expect(page.getByRole("heading", { name: "Plataformas", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Contextos de plataforma/ })).toBeVisible();
  await expect(page.getByText("Preview escritura")).toBeVisible();
  await expect(page.getByText("Escritura").first()).toBeVisible();
  await expect(page.getByText("Conectar plataforma autorizada")).toBeVisible();
  await expect(page.getByRole("table", { name: "Plataformas activas" }).getByText("CTAIMA / CTAIMA CAE").first()).toBeVisible();

  await page.getByRole("link", { name: "Anadir trabajador" }).click();
  await expect(page).toHaveURL(/\/assign-worker/);
  await expect(page.getByRole("heading", { name: "Anadir trabajador a plataforma" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Anadir a todas/ })).toBeVisible();

  await page.getByRole("link", { name: "Notificaciones" }).click();
  await expect(page).toHaveURL(/\/notifications/);
  await expect(page.getByRole("heading", { name: "Notificaciones" })).toBeVisible();
  await expect(page.getByText("Solo plataformas activas")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidencias pendientes de validacion" })).toBeVisible();
});
