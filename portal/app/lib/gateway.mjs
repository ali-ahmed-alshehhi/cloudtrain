// Shared browser client: all platform requests go through the gateway.
export class GatewayError extends Error {
  constructor(message, status, code, requestId) {
    super(message);
    this.name = "GatewayError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export function createGatewayClient({ gatewayUrl, getToken = () => "", fetchImpl = fetch }) {
  const base = gatewayUrl.replace(/\/+$/, "");
  async function request(path, { body, headers, ...options } = {}) {
    if (path !== "/health" && !path.startsWith("/api/v1/")) {
      throw new Error("Use a public gateway API path.");
    }
    const requestHeaders = new Headers(headers);
    const token = getToken();
    if (token) requestHeaders.set("Authorization", `Bearer ${token}`);
    const isJson = body !== undefined && !(body instanceof FormData);
    if (isJson) requestHeaders.set("Content-Type", "application/json");
    let response;
    try {
      response = await fetchImpl(`${base}${path}`, {
        ...options,
        headers: requestHeaders,
        body: isJson ? JSON.stringify(body) : body,
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new GatewayError("Cannot reach CloudTrain. Check your connection and try again.", 0, "NETWORK_ERROR");
    }
    let data;
    try {
      data = await response.json();
    } catch (error) {
      if (error.name === "AbortError") throw error;
      data = null;
    }
    if (!response.ok) {
      throw new GatewayError(
        data?.error?.message || `CloudTrain could not complete the request (${response.status}).`,
        response.status,
        data?.error?.code,
        data?.error?.request_id || response.headers.get("X-Request-Id"),
      );
    }
    if (data === null && response.status !== 204) {
      throw new GatewayError("CloudTrain returned an unreadable response. Please try again.", response.status, "INVALID_RESPONSE");
    }
    return data;
  }
  return {
    request,
    listProjects: (signal) => request("/api/v1/projects", { signal }),
    listDatasets: (projectId, signal) => request(`/api/v1/datasets?${new URLSearchParams({ project_id: projectId })}`, { signal }),
    uploadDataset: (form, idempotencyKey, signal) => request("/api/v1/datasets", {
      method: "POST", body: form, headers: { "Idempotency-Key": idempotencyKey }, signal,
    }),
    uploadDatasetVersion: (datasetId, form, idempotencyKey, signal) => request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/versions`, {
      method: "POST", body: form, headers: { "Idempotency-Key": idempotencyKey }, signal,
    }),
    getDatasetVersion: (datasetId, version, signal) => request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/versions/${version}`, { signal }),
    createProject: (project, idempotencyKey) => request("/api/v1/projects", {
      method: "POST", body: project, headers: { "Idempotency-Key": idempotencyKey },
    }),
  };
}
