const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { expect } = require('playwright/test');

test('pending dataset and version uploads keep project and retry identity alive', async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROME_EXECUTABLE });
  try {
    const page = await browser.newPage();
    let release;
    let started;
    let version = 1;
    let keys = [];
    const dataset = { dataset_id: 'fixture-data', project_id: 'fixture-a', name: 'Fixture data', format: 'csv', latest_version: 1 };
    await page.route('**/api/v1/**', async route => {
      const request = route.request();
      assert.ok(request.headers()["authorization"]?.startsWith("Bearer "), "local page must send the dev session token");
      const url = new URL(request.url());
      let body;
      if (request.method() === 'POST') {
        keys.push(request.headers()['idempotency-key']);
        started();
        await new Promise(resolve => { release = resolve; });
        if (url.pathname.endsWith('/versions')) { version = 2; body = { dataset_id: dataset.dataset_id, version, size_bytes: 8, checksum_sha256: 'a'.repeat(64), created_at: '2026-11-22T00:00:00Z' }; }
        else body = dataset;
      } else if (url.pathname.endsWith('/projects')) body = { items: ['a', 'b'].map(id => ({ project_id: `fixture-${id}`, name: `Fixture ${id}` })) };
      else if (url.pathname.endsWith('/events')) body = { items: [] };
      else if (/\/versions\/\d+$/.test(url.pathname)) body = { dataset_id: dataset.dataset_id, version, size_bytes: 8, checksum_sha256: 'a'.repeat(64), created_at: '2026-11-22T00:00:00Z' };
      else body = { items: [] };
      await route.fulfill({ status: request.method() === 'POST' ? 201 : 200, json: body });
    });
    await page.goto(process.env.PORTAL_TEST_URL || 'http://localhost:3000');
    await page.getByRole('button', { name: /Fixture a/ }).click();
    await expect(page.getByRole('button', { name: 'Upload dataset', exact: true })).toBeEnabled();
    await page.getByLabel('Dataset name').fill('Fixture data');
    await page.locator('#dataset-file').setInputFiles({ name: 'fixture.csv', mimeType: 'text/csv', buffer: Buffer.from('x,y\n1,0\n') });
    for (const kind of ['dataset', 'version']) {
      if (kind === 'version') await page.locator('#version-file').setInputFiles({ name: 'fixture.csv', mimeType: 'text/csv', buffer: Buffer.from('x,y\n2,1\n') });
      const pending = new Promise(resolve => { started = resolve; });
      await page.getByRole('button', { name: kind === 'dataset' ? 'Upload dataset' : 'Upload version', exact: true }).click();
      await pending;
      await expect(page.getByRole('button', { name: /Fixture b/ })).toBeDisabled();
      await expect(page.getByRole('button', { name: 'Create project', exact: true })).toBeDisabled();
      await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeDisabled();
      await expect(page.getByText('Upload in progress.', { exact: false })).toBeVisible();
      release();
      await expect(page.getByRole('button', { name: /Fixture b/ })).toBeEnabled();
      await expect(page.getByLabel('Dataset version')).toHaveValue(kind === 'dataset' ? '1' : '2');
    }
    assert.equal(keys.length, 2);
    assert.ok(keys.every(Boolean));
    await page.getByRole('button', { name: /Fixture b/ }).click();
    await expect(page.getByRole('button', { name: /Fixture b/ })).toHaveAttribute('aria-pressed', 'true');
  } finally { await browser.close(); }
});
