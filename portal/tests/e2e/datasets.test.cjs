const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mkdir } = require('node:fs/promises');
const { chromium } = require('playwright');
const { expect } = require('playwright/test');
const { createHash } = require('node:crypto');
const path = require('node:path');

const baseURL = process.env.PORTAL_TEST_URL || 'http://localhost:3000';
const launchOptions = process.env.PLAYWRIGHT_CHROME_EXECUTABLE
  ? { executablePath: process.env.PLAYWRIGHT_CHROME_EXECUTABLE }
  : {};
const csv1 = 'feature,label\n1,0\n';
const csv2 = 'feature,label\n1,0\n2,1\n';
const checksum = text => createHash('sha256').update(text).digest('hex');

async function createProject(page, name) {
  await page.getByLabel('Project name').fill(name);
  await page.getByRole('button', { name: 'Create project', exact: true }).click();
  await expect(page.getByRole('button', { name: new RegExp(name) })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Upload dataset', exact: true })).toBeEnabled();
}

async function csvFile(page, selector, text) {
  await page.locator(selector).setInputFiles({ name: 'sample.csv', mimeType: 'text/csv', buffer: Buffer.from(text) });
}

test('datasets: live uploads, validation, retry, versions and project isolation', async () => {
  const browser = await chromium.launch({ headless: true, ...launchOptions });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(baseURL);
    await expect(page.getByText('Select a project to upload datasets and choose a version.')).toBeVisible();
    const suffix = Date.now();
    const projectName = `Dataset test ${suffix}`;
    const datasetName = `Training data ${suffix}`;
    await createProject(page, projectName);
    await expect(page.getByText('No datasets yet. Upload your first file.')).toBeVisible();

    // The server checks actual content, not just the filename extension.
    await page.getByLabel('Dataset name').fill(datasetName);
    await csvFile(page, '#dataset-file', 'not a CSV');
    await page.getByRole('button', { name: 'Upload dataset', exact: true }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'not a valid csv' })).toBeVisible();

    await csvFile(page, '#dataset-file', csv1);
    // Simulate a lost response AFTER the backend accepted the upload.
    // Retrying must reuse the same key and return the same dataset.
    let accepted;
    await page.route('**/api/v1/datasets', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      const response = await route.fetch();
      assert.equal(response.status(), 201);
      accepted = await response.json();
      await route.abort();
    });
    await page.getByRole('button', { name: 'Upload dataset', exact: true }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'Cannot reach CloudTrain' })).toBeVisible();
    await page.unroute('**/api/v1/datasets');
    const retryResponse = page.waitForResponse(r => r.url().endsWith('/api/v1/datasets') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Upload dataset', exact: true }).click();
    assert.equal((await (await retryResponse).json()).dataset_id, accepted.dataset_id);
    await expect(page.getByTestId('version-details')).toContainText(checksum(csv1));
    await expect(page.getByLabel('Dataset version')).toHaveValue('1');

    await page.getByLabel('Version note (optional)').fill('Added another row');
    await csvFile(page, '#version-file', csv2);
    await page.getByRole('button', { name: 'Upload version', exact: true }).click();
    await expect(page.getByLabel('Dataset version')).toHaveValue('2');
    await expect(page.getByTestId('version-details')).toContainText(checksum(csv2));
    await expect(page.getByTestId('version-details')).toContainText('Added another row');
    await page.getByRole('button', { name: new RegExp(datasetName) }).click();
    await expect(page.getByTestId('version-details')).toContainText(checksum(csv2));
    await page.getByLabel('Dataset version').selectOption('1');
    await expect(page.getByTestId('version-details')).toContainText(checksum(csv1));
    await expect(page.getByTestId('version-details')).not.toContainText(checksum(csv2));

    // A failed version read must hide stale metadata and offer retry.
    await page.route('**/api/v1/datasets/*/versions/2', route => route.fulfill({
      status: 503, contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'SERVICE_UNAVAILABLE', message: 'Version service temporarily unavailable', request_id: 'req-browser-test' } }),
    }));
    await page.getByLabel('Dataset version').selectOption('2');
    await expect(page.getByRole('alert').filter({ hasText: 'Version service temporarily unavailable' })).toBeVisible();
    await expect(page.getByTestId('version-details')).toHaveCount(0);
    await page.unroute('**/api/v1/datasets/*/versions/2');
    await page.getByRole('button', { name: 'Retry version' }).click();
    await expect(page.getByTestId('version-details')).toContainText(checksum(csv2));

    await page.getByRole('button', { name: 'Refresh datasets' }).click();
    await expect(page.getByRole('button', { name: new RegExp(datasetName) })).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Refresh datasets' })).toBeEnabled();
    await expect(page.getByTestId('version-details')).toContainText(checksum(csv2));

    await mkdir('test-results', { recursive: true });
    await page.getByLabel('Dataset version').scrollIntoViewIfNeeded();
    await page.screenshot({ path: 'test-results/datasets-desktop.png' });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('#datasets').scrollIntoViewIfNeeded();
    await page.screenshot({ path: 'test-results/datasets-mobile.png' });

    await createProject(page, `Empty project ${suffix}`);
    await expect(page.getByText('No datasets yet. Upload your first file.')).toBeVisible();
    await expect(page.getByLabel('Dataset version')).toHaveCount(0);
    await expect(page.getByRole('button', { name: new RegExp(datasetName) })).toHaveCount(0);
    await page.getByRole('button', { name: new RegExp(projectName) }).click();
    await expect(page.getByRole('button', { name: new RegExp(datasetName) })).toBeVisible();
    await page.getByRole('button', { name: new RegExp(datasetName) }).click();
    await expect(page.getByLabel('Dataset version')).toHaveValue('2');
    await expect(page.getByTestId('version-details')).toContainText(checksum(csv2));
    // Archive formats follow the same public multipart upload contract.
    for (const [format, filename] of [['zip', 'images.zip'], ['tar_gz', 'images.tar.gz']]) {
      const archiveName = `Archive ${format} ${suffix}`;
      await page.getByLabel('Dataset name').fill(archiveName);
      await page.getByLabel('File format').selectOption(format);
      await page.locator('#dataset-file').setInputFiles(path.join(__dirname, '../fixtures', filename));
      await page.getByRole('button', { name: 'Upload dataset', exact: true }).click();
      await expect(page.getByRole('button', { name: new RegExp(archiveName) })).toHaveAttribute('aria-pressed', 'true');
      await expect(page.getByTestId('version-details')).toBeVisible();
      await expect(page.getByLabel('Dataset version')).toHaveValue('1');
    }
    const unauthorized = await page.request.get('http://localhost:5810/api/v1/datasets?project_id=project-01');
    assert.equal(unauthorized.status(), 401);
    assert.deepEqual(errors, []);
    console.log(`Verified ${accepted.dataset_id}: real CSV uploads, versions 1/2, retry idempotency and project isolation.`);
  } finally { await browser.close(); }
});
