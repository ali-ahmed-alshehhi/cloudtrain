const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

const baseURL = process.env.PORTAL_TEST_URL || 'http://localhost:3000';
const launchOptions = process.env.PLAYWRIGHT_CHROME_EXECUTABLE
  ? { executablePath: process.env.PLAYWRIGHT_CHROME_EXECUTABLE }
  : {};

test('projects: create, refresh, select, validate and recover from a network error', async () => {
  const browser = await chromium.launch({ headless: true, ...launchOptions });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(baseURL);
    await page.getByRole('button', { name: 'Refresh', exact: true }).waitFor();
    await page.waitForFunction(() => !document.querySelector('#project-name').disabled);
    const name = `Portal test ${Date.now()}`;
    const input = page.getByLabel('Project name');
    await input.fill('   ');
    await page.getByRole('button', { name: 'Create project', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Enter a project name.' }).waitFor();
    await input.fill(name);
    await page.getByLabel('Description (optional)').fill('Browser integration test');
    const responsePromise = page.waitForResponse(r => r.url().endsWith('/api/v1/projects') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Create project', exact: true }).click();
    const response = await responsePromise;
    assert.equal(response.status(), 201);
    const created = await response.json();
    await page.getByRole('button', { name: new RegExp(name) }).waitFor();
    assert.equal(await page.getByRole('button', { name: new RegExp(name) }).getAttribute('aria-pressed'), 'true');
    const refreshed = page.waitForResponse(r => r.url().endsWith('/api/v1/projects') && r.request().method() === 'GET');
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await refreshed;
    await page.getByRole('button', { name: new RegExp(name) }).click();
    assert.equal(await page.getByRole('button', { name: new RegExp(name) }).getAttribute('aria-pressed'), 'true');
    // A failed read must show an error, then recover when the connection returns.
    await page.route('**/api/v1/projects', route => route.request().method() === 'GET' ? route.abort() : route.continue());
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Cannot reach CloudTrain' }).waitFor();
    await page.unroute('**/api/v1/projects');
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await page.getByRole('button', { name: new RegExp(name) }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    console.log(`Verified project ${created.project_id} through the live gateway.`);
  } finally {
    await browser.close();
  }
});
