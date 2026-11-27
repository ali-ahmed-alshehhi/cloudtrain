// Alert delay (EVALUATION.md section 1): how long after a job event happens does its alert appear in the
// portal? Owner: Adel.
//
// It submits a few small CPU jobs through the gateway (the walk-through's job form), keeps the Projects page
// open on that project in a headless Chrome, and notes the moment each alert line appears on the page.
// Two numbers per event:
//   delay       = alert visible (browser clock) - event occurred_at (job-service clock, in Docker)
//   from submit = alert visible - the moment this script sent POST /jobs (both on the laptop's clock)
// The first depends on Docker's clock matching the laptop's; the second needs no second clock.
//
// Needs the local stack (make up) and one finished walk-through job to copy the dataset from (make e2e).
// Run from portal/, which has Playwright:
//   export DEV_AUTH_TOKEN=$(grep '^DEV_AUTH_TOKEN=' ../.env | cut -d= -f2)
//   node ../docs/evaluation/alert-delay.cjs 5          # 5 jobs (default)
// Optional: PORTAL_URL (http://localhost:3000), GATEWAY_URL (http://localhost:5810),
// PLAYWRIGHT_CHROME_EXECUTABLE (your Chrome, if `npx playwright install chromium` was not run).
// Reads and submits only; it changes nothing else. The raw results also go to /tmp/alert-delay.json.

const { randomUUID } = require("node:crypto");
const { writeFileSync } = require("node:fs");
const { chromium } = require(require.resolve("playwright", { paths: [process.cwd()] }));

const PORTAL = (process.env.PORTAL_URL || "http://localhost:3000").replace(/\/+$/, "");
const GATEWAY = (process.env.GATEWAY_URL || "http://localhost:5810").replace(/\/+$/, "");
const TOKEN = process.env.DEV_AUTH_TOKEN || "";
const JOBS = Number(process.argv[2] || 5);
const DONE = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
// The words the portal puts after the job id (portal/lib/alerts/describe.mjs).
const WORDS = {
  "job.queued": "is queued",
  "job.scheduled": "was placed on a machine",
  "job.running": "started training",
  "job.succeeded": "succeeded",
  "job.failed": "failed",
  "job.cancelled": "was cancelled",
  "job.retrying": "is being retried",
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function api(path, { method = "GET", body, headers = {} } = {}) {
  const answer = await fetch(GATEWAY + path, {
    method,
    headers: { Authorization: `Bearer ${TOKEN}`, ...(body ? { "Content-Type": "application/json" } : {}), ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await answer.text();
  if (!answer.ok) throw new Error(`${method} ${path} -> ${answer.status} ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
}

/** The newest finished walk-through job (tabular_mlp): its project and dataset are reused. */
async function templateJob() {
  const jobs = [];
  for (const project of (await api("/api/v1/projects")).items) {
    const query = new URLSearchParams({ project_id: project.project_id });
    jobs.push(...(await api(`/api/v1/jobs?${query}`)).items);
  }
  const done = jobs.filter((j) => j.status === "SUCCEEDED" && j.spec?.model === "tabular_mlp");
  done.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  if (!done[0]) throw new Error("No finished tabular_mlp job yet: run `make e2e` once, then try again.");
  return done[0];
}

/** The walk-through's small CPU job (tests/integration/conftest.py small_job), on the template's dataset. */
function jobForm(template) {
  return {
    project_id: template.project_id,
    dataset_id: template.spec.dataset_id,
    dataset_version: template.spec.dataset_version,
    model: "tabular_mlp",
    hyperparameters: { epochs: 1, batch_size: 4, learning_rate: 0.05, seed: 7, hidden_size: 8 },
    resources: { gpu_count: 0, cpu_cores: 2, memory_gb: 4 },
    parallelism: { strategy: "single", world_size: 1 },
    execution: { max_runtime_minutes: 10, retry_limit: 2 },
  };
}

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : null;
};
const sec = (ms) => (ms === null || ms === undefined ? "-" : (ms / 1000).toFixed(2));

async function main() {
  if (!TOKEN) throw new Error("Set DEV_AUTH_TOKEN first (see the top of this file).");
  const template = await templateJob();
  const projectId = template.project_id;
  console.log(`Project ${projectId}, dataset ${template.spec.dataset_id} v${template.spec.dataset_version}, ${JOBS} jobs`);

  const launch = process.env.PLAYWRIGHT_CHROME_EXECUTABLE ? { executablePath: process.env.PLAYWRIGHT_CHROME_EXECUTABLE } : {};
  const browser = await chromium.launch({ headless: true, ...launch });
  const rows = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.goto(PORTAL);
    const exactId = new RegExp(`^${projectId}$`);
    await page.locator("button.project-card").filter({ has: page.locator("small", { hasText: exactId }) }).click();
    await page.locator('[data-testid="job-alerts"][data-phase="ready"]').waitFor({ timeout: 30000 });
    // Note the first moment each alert line is on the page (lines already there count as "before").
    await page.evaluate(() => {
      const seen = (window.__alertSeen = {});
      const scan = (stamp) => {
        for (const li of document.querySelectorAll('[data-testid="job-alerts"] li')) {
          // Each line starts with a <time> ("2026-11-22 08:14 UTC"), then, on the poll that brought it, a
          // "New:" label, then "job-17 started training". Only the "job-…" part is kept.
          const time = li.querySelector("time");
          const text = li.textContent.slice(time ? time.textContent.length : 0).trim().replace(/^New:\s*/, "");
          if (!(text in seen)) seen[text] = stamp;
        }
      };
      scan(-1);
      new MutationObserver(() => scan(Date.now())).observe(document.body, { childList: true, subtree: true, characterData: true });
      setInterval(() => scan(Date.now()), 100);
    });

    for (let i = 1; i <= JOBS; i += 1) {
      // A random pause, so the jobs start at different points of the portal's 5 s polling cycle.
      await sleep(Math.random() * 5000);
      const sentAt = Date.now();
      const job = await api("/api/v1/jobs", { method: "POST", body: jobForm(template), headers: { "Idempotency-Key": randomUUID() } });
      let status = job.status;
      for (let waited = 0; !DONE.has(status) && waited < 180000; waited += 1000) {
        await sleep(1000);
        status = (await api(`/api/v1/jobs/${encodeURIComponent(job.job_id)}`)).status;
      }
      await sleep(12000); // two more polls of the portal (every 5 s) so the last alert is on the page
      const seen = await page.evaluate(() => window.__alertSeen);
      const events = (await api(`/api/v1/jobs/${encodeURIComponent(job.job_id)}/events`)).items;
      for (const event of events) {
        const title = `${event.job_id} ${WORDS[event.event_type] ?? event.event_type}`;
        const key = Object.keys(seen).find((text) => text.startsWith(title) && seen[text] > 0);
        const visibleAt = key ? seen[key] : null;
        const occurredAt = Date.parse(event.occurred_at);
        rows.push({
          run: i, job_id: event.job_id, status, event_type: event.event_type, occurred_at: event.occurred_at,
          visible_at: visibleAt ? new Date(visibleAt).toISOString() : null,
          delay_ms: visibleAt ? visibleAt - occurredAt : null,
          from_submit_ms: visibleAt ? visibleAt - sentAt : null,
        });
      }
      console.log(`run ${i}: ${job.job_id} ${status}`);
    }
  } finally {
    await browser.close();
  }

  console.log("\nrun  job      event          occurred_at (UTC)          delay s  from submit s");
  for (const r of rows) {
    console.log(`${String(r.run).padEnd(4)} ${r.job_id.padEnd(8)} ${r.event_type.padEnd(14)} ${r.occurred_at.padEnd(26)} ${sec(r.delay_ms).padStart(7)}  ${sec(r.from_submit_ms).padStart(13)}`);
  }
  const shown = rows.filter((r) => r.delay_ms !== null);
  const delays = shown.map((r) => r.delay_ms);
  console.log(`\n${shown.length} of ${rows.length} events shown as alerts; ${rows.length - shown.length} not seen`);
  if (delays.length) {
    console.log(`delay: median ${sec(median(delays))} s, min ${sec(Math.min(...delays))} s, max ${sec(Math.max(...delays))} s`);
    for (const type of [...new Set(shown.map((r) => r.event_type))]) {
      const d = shown.filter((r) => r.event_type === type).map((r) => r.delay_ms);
      console.log(`  ${type.padEnd(14)} median ${sec(median(d))} s (n=${d.length})`);
    }
    const queued = shown.filter((r) => r.event_type === "job.queued").map((r) => r.from_submit_ms);
    if (queued.length) console.log(`submit -> "is queued" alert (one clock): median ${sec(median(queued))} s, max ${sec(Math.max(...queued))} s`);
  }
  writeFileSync("/tmp/alert-delay.json", JSON.stringify(rows, null, 2));
  console.log("raw rows: /tmp/alert-delay.json");
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
