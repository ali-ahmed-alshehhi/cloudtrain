import { test } from "node:test";
import assert from "node:assert/strict";
import { createGatewayClient, GatewayError } from "../app/lib/gateway.mjs";

function client(fetchImpl) {
  return createGatewayClient({ gatewayUrl: "http://localhost:5810/", getToken: () => "test-token", fetchImpl });
}

test("project reads go through the gateway with the current token", async () => {
  const api = client(async (url, options) => {
    assert.equal(url, "http://localhost:5810/api/v1/projects");
    assert.equal(options.headers.get("Authorization"), "Bearer test-token");
    return Response.json({ items: [] });
  });
  assert.deepEqual(await api.listProjects(), { items: [] });
});

test("project creation preserves JSON and the retry key", async () => {
  const project = { name: "Image classification", description: null };
  const keys = [];
  const api = client(async (url, options) => {
    assert.equal(options.method, "POST");
    assert.equal(options.headers.get("Content-Type"), "application/json");
    assert.deepEqual(JSON.parse(options.body), project);
    keys.push(options.headers.get("Idempotency-Key"));
    return Response.json({ ...project, project_id: "project-1" }, { status: 201 });
  });
  await api.createProject(project, "retry-key");
  await api.createProject(project, "retry-key");
  assert.deepEqual(keys, ["retry-key", "retry-key"]);
});

for (const status of [401, 403, 422, 503]) {
  test(`preserves shared errors and request references for ${status}`, async () => {
    const api = client(async () => Response.json({ error: { code: "TEST_ERROR", message: "Try later", request_id: "req-1" } }, { status }));
    await assert.rejects(api.listProjects(), (error) => error instanceof GatewayError && error.status === status && error.requestId === "req-1" && error.message === "Try later");
  });
}

test("network errors give an actionable message", async () => {
  const api = client(async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(api.listProjects(), (error) => error.code === "NETWORK_ERROR");
});

test("cancellation is preserved so stale requests do not update the page", async () => {
  const api = client(async () => { throw new DOMException("Cancelled", "AbortError"); });
  await assert.rejects(api.listProjects(), { name: "AbortError" });
});

test("file uploads let the browser set the multipart boundary", async () => {
  const form = new FormData();
  form.set("project_id", "project-1");
  const api = client(async (url, options) => {
    assert.equal(options.headers.has("Content-Type"), false);
    assert.equal(options.body, form);
    return Response.json({}, { status: 201 });
  });
  await api.request("/api/v1/datasets", { method: "POST", body: form });
});

test("rejects direct service paths and malformed responses", async () => {
  const api = client(async () => new Response("not json"));
  await assert.rejects(api.request("/internal/run"), /public gateway/);
  await assert.rejects(api.listProjects(), (error) => error.code === "INVALID_RESPONSE");
});

test("dataset listing is project-scoped and version selection uses the public endpoint", async () => {
  const paths = [];
  const api = client(async (url) => {
    paths.push(url);
    return Response.json(url.includes("/versions/") ? { dataset_id: "dataset-07", version: 2 } : { items: [] });
  });
  await api.listDatasets("project-01");
  const version = await api.getDatasetVersion("dataset-07", 2);
  assert.equal(version.version, 2);
  assert.deepEqual(paths, ["http://localhost:5810/api/v1/datasets?project_id=project-01", "http://localhost:5810/api/v1/datasets/dataset-07/versions/2"]);
});

test("dataset and version uploads retain files, idempotency keys and cancellation", async () => {
  const controller = new AbortController();
  const calls = [];
  const api = client(async (url, options) => {
    calls.push(url);
    assert.equal(options.method, "POST");
    assert.equal(options.headers.get("Idempotency-Key"), "upload-key");
    assert.equal(options.headers.has("Content-Type"), false);
    assert.equal(options.signal, controller.signal);
    assert.equal(await options.body.get("file").text(), "x,y\n1,2\n");
    return Response.json({}, { status: 201 });
  });
  const form = new FormData();
  form.set("file", new File(["x,y\n1,2\n"], "sample.csv"));
  await api.uploadDataset(form, "upload-key", controller.signal);
  await api.uploadDatasetVersion("dataset-07", form, "upload-key", controller.signal);
  assert.deepEqual(calls, ["http://localhost:5810/api/v1/datasets", "http://localhost:5810/api/v1/datasets/dataset-07/versions"]);
});


test("cancellation while reading a response body remains an abort", async () => {
  const api = client(async () => ({
    ok: true,
    status: 200,
    json: async () => { throw new DOMException("Cancelled", "AbortError"); },
  }));
  await assert.rejects(api.listProjects(), { name: "AbortError" });
});
