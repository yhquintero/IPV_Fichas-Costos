const { test, expect } = require('@playwright/test');

test('administra una licencia PX desde el Creador web', async ({ page }) => {
  const email = process.env.IPV_ADMIN_EMAIL;
  const password = process.env.IPV_ADMIN_PASSWORD;
  const requestCode = process.env.IPV_E2E_REQUEST_CODE;
  expect(email, 'IPV_ADMIN_EMAIL debe apuntar al administrador temporal de pruebas').toBeTruthy();
  expect(password, 'IPV_ADMIN_PASSWORD debe apuntar a una contraseña temporal de pruebas').toBeTruthy();
  expect(requestCode, 'IPV_E2E_REQUEST_CODE debe ser un código web válido de pruebas').toMatch(/^IPVW-/);

  await page.goto('/');
  const login = page.locator('form.login-card');
  await expect(login).toBeVisible();
  await login.locator('[name="email"]').fill(email);
  await login.locator('[name="password"]').fill(password);
  await login.getByRole('button', { name: 'Iniciar sesión' }).click();
  await expect(login).toBeHidden();

  await page.locator('#nav-creator').click();
  await expect(page.getByRole('heading', { name: 'Creador de Licencias' })).toBeVisible();
  await expect(page.locator('#creator-body')).toContainText('Licencias desactivadas');

  // Crear una clave efímera de CI; el servidor y el checkout de este job se descartan al terminar.
  await page.locator('#creator-pass2').fill('E2E-clave-firma-solo-CI-2026');
  await page.locator('#creator-pass2b').fill('E2E-clave-firma-solo-CI-2026');
  await page.locator('#creator-init2-btn').click();
  await expect(page.locator('#creator-body')).toContainText('Licencias activadas', { timeout: 30_000 });

  await page.locator('#creator-user').fill('Cliente de prueba E2E');
  await page.locator('#creator-code').fill(requestCode);
  await page.locator('#creator-pass').fill('E2E-clave-firma-solo-CI-2026');
  await page.locator('#creator-plan').selectOption('PX');
  await expect(page.locator('#creator-custom-fields')).toBeVisible();

  const start = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10);
  const end = new Date(Date.now() + 12 * 86_400_000).toISOString().slice(0, 10);
  const invalidEnd = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
  await page.locator('#creator-start-date').fill(start);
  await page.locator('#creator-end-date').fill(invalidEnd);
  await page.locator('#creator-custom-price').fill('22.75');
  await page.locator('#creator-emit-btn').click();
  await expect(page.locator('#creator-emit-msg')).toContainText('Hasta debe ser una fecha válida');
  await expect(page.locator('#creator-result')).toHaveCount(0);

  await page.locator('#creator-end-date').fill(end);
  await page.locator('#creator-emit-btn').click();
  await expect(page.locator('#creator-result')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('#creator-result')).toContainText('22.75 USD');
  await expect(page.locator('#creator-result')).toContainText(`vigencia ${start} a ${end} (UTC)`);

  const token = await page.locator('#creator-token').inputValue();
  await page.locator('#creator-verify-token').fill(token);
  await page.locator('#creator-verify-btn').click();
  await expect(page.locator('#creator-verify-msg')).toContainText(`vigencia ${start} a ${end} UTC`);

  await page.locator('[data-action="creator-ledger"]').click();
  await expect(page.locator('#creator-ledger tbody')).toContainText('PX');
  await expect(page.locator('#creator-ledger tbody')).toContainText(start);
  await expect(page.locator('#creator-ledger tbody')).toContainText(end);
});
