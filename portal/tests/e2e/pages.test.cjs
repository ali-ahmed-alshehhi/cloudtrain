// Comparison (/compare) and usage & cost (/usage) pages, against the running local stack (owner: Adel).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { expect } = require('playwright/test');

const baseURL = process.env.PORTAL_TEST_URL || 'http://localhost:3000';
const gatewayURL = process.env.GATEWAY_TEST_URL || 'http://localhost:5810';
const launchOptions = process.env.PLAYWRIGHT_CHROME_EXECUTABLE
  ? { executablePath: process.env.PLAYWRIGHT_CHROME_EXECUTABLE }
  : {};

async function ensureProject(page) {
  await page.goto(`${baseURL}/usage`);
  const picker = page.getByLabel('Project', { exact: true });
  const none = page.getByText('No projects yet.');
  await expect(picker.or(none)).toBeVisible();
  if (await none.isVisible()) {
    await page.goto(baseURL);
    await page.getByLabel('Project name').fill(`Pages test ${Date.now()}`);
    await page.getByRole('button', { name: 'Create project', exact: true }).click();
    await expect(page.getByText(/Pages test/).first()).toBeVisible();
  }
}

test('compare and usage pages: project in the address, honest results, gateway only', async () => {
  const browser = await chromium.launch({ headless: true, ...launchOptions });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    const origins = new Set();
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('request', (request) => origins.add(new URL(request.url()).origin));
    await ensureProject(page);

    for (const [path, heading, box] of [
      ['/usage', 'Usage & cost', /Usage and cost/],
      ['/compare', 'Compare runs', /1 GPU vs multi-GPU/],
    ]) {
      // An unknown project in the address is ignored: the first project is shown, never the unknown one.
      await page.goto(`${baseURL}${path}?project=project-does-not-exist`);
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
      await expect(page.getByRole('link', { name: heading })).toHaveAttribute('aria-current', 'page');
      const picker = page.getByLabel('Project', { exact: true });
      await expect(picker).toBeVisible();
      const chosen = await picker.inputValue();
      assert.ok(chosen && chosen !== 'project-does-not-exist');
      await expect(page).toHaveURL(new RegExp(`${path}\\?project=${chosen}$`));
      // The box answers: a table, or a plain message (no runs / no jobs / not logged), never a blank page.
      await expect(page.getByRole('heading', { name: box })).toBeVisible();
      await expect(page.getByText(/Loading/)).toHaveCount(0, { timeout: 15000 });

      // A reload keeps the chosen project.
      await page.reload();
      await expect(page.getByLabel('Project', { exact: true })).toHaveValue(chosen);
    }

    // The sidebar links carry the project from page to page.
    const chosen = await page.getByLabel('Project', { exact: true }).inputValue();
    await page.getByRole('link', { name: 'Usage & cost' }).click();
    await expect(page).toHaveURL(`${baseURL}/usage?project=${chosen}`);

    // The browser talks to the portal and the gateway only (no MLflow, no AWS, no other service).
    const allowed = new Set([new URL(baseURL).origin, new URL(gatewayURL).origin]);
    assert.deepEqual([...origins].filter((origin) => !allowed.has(origin)), []);
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
});
