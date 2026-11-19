"""The services the registry calls: MLflow (REST API), the Projects service and Inference.

Each failure of another service becomes an ApiError in the shared error format: a dependency that
is down or answers 5xx -> 503, a run or project that does not exist -> 400 / 404.
"""

import math
from urllib.parse import urlsplit

import httpx

from app.common import ApiError

# The MLflow run tags the training worker may set. When present they must match the request.
LINK_TAGS = ("project_id", "job_id", "dataset_id", "dataset_version")
PRODUCTION_ALIAS = "production"


class MlflowError(Exception):
    """MLflow answered with an error (its `error_code`, e.g. RESOURCE_DOES_NOT_EXIST)."""

    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class Mlflow:
    """The few MLflow REST calls the registry needs (https://mlflow.org/docs/latest/rest-api.html)."""

    def __init__(self, http: httpx.Client, url: str, artifacts_destination: str) -> None:
        self.http = http
        self.api = url.rstrip("/") + "/api/2.0/mlflow"
        self.artifacts_destination = artifacts_destination.rstrip("/")

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            answer = self.http.request(method, self.api + path, **kwargs)
        except httpx.HTTPError as error:
            raise ApiError(
                503, "MLFLOW_UNAVAILABLE", f"MLflow is not reachable ({type(error).__name__})"
            ) from None
        if answer.status_code >= 500:
            raise ApiError(503, "MLFLOW_UNAVAILABLE", f"MLflow answered {answer.status_code}")
        try:
            body = answer.json()
        except ValueError:
            body = {}
        if answer.status_code >= 400:
            raise MlflowError(
                answer.status_code, body.get("error_code", ""), body.get("message", answer.text)
            )
        return body

    def get_run(self, run_id: str) -> dict:
        try:
            return self._call("GET", "/runs/get", params={"run_id": run_id})["run"]
        except MlflowError:
            raise ApiError(400, "RUN_NOT_FOUND", f"MLflow has no run {run_id}") from None

    def find_model(self, run: dict) -> tuple[str, str | None]:
        """Where the run's saved model is: (artifact location, MLflow logged-model ID or None).

        MLflow 3 keeps a model logged in a run as a "logged model" with its own folder; MLflow 2 kept
        it in the run's own artifacts under `model/`. Both are accepted.
        """
        outputs = (run.get("outputs") or {}).get("model_outputs") or []
        model_ids = [output["model_id"] for output in outputs if output.get("model_id")]
        if not model_ids:
            found = self._call(
                "POST",
                "/logged-models/search",
                json={
                    "experiment_ids": [run["info"]["experiment_id"]],
                    "filter": f"source_run_id = '{run['info']['run_id']}'",
                },
            )
            model_ids = [model["info"]["model_id"] for model in found.get("models", [])]
        if model_ids:
            model_id = model_ids[-1]  # the newest one when a run logged several
            model = self._call("GET", f"/logged-models/{model_id}")["model"]
            return model["info"]["artifact_uri"], model_id
        try:
            listed = self._call(
                "GET", "/artifacts/list", params={"run_id": run["info"]["run_id"], "path": "model"}
            )
        except MlflowError:
            listed = {}
        if any(item["path"].endswith("MLmodel") for item in listed.get("files", [])):
            return run["info"]["artifact_uri"].rstrip("/") + "/model", None
        raise ApiError(400, "MODEL_NOT_IN_RUN", f"MLflow run {run['info']['run_id']} has no saved model")

    def storage_uri(self, artifact_uri: str) -> str:
        """The real place of the files: MLflow's proxy address `mlflow-artifacts:/...` -> `s3://...`.

        Inference then reads the model straight from the bucket, without going through MLflow.
        """
        if artifact_uri.startswith("mlflow-artifacts:"):
            path = urlsplit(artifact_uri).path.lstrip("/")
            return f"{self.artifacts_destination}/{path}"
        return artifact_uri

    def register_version(self, name: str, source: str, run_id: str, model_id: str | None, tags: dict) -> str:
        """Add a version to MLflow's registered model `name` (made the first time). Returns its number."""
        try:
            self._call("POST", "/registered-models/create", json={"name": name, "tags": _tags(tags)})
        except MlflowError as error:
            if error.error_code != "RESOURCE_ALREADY_EXISTS":
                raise ApiError(503, "MLFLOW_UNAVAILABLE", f"MLflow refused the model: {error}") from None
        body = {"name": name, "source": source, "run_id": run_id, "tags": _tags(tags)}
        if model_id:
            body["model_id"] = model_id
        try:
            return str(self._call("POST", "/model-versions/create", json=body)["model_version"]["version"])
        except MlflowError as error:
            raise ApiError(503, "MLFLOW_UNAVAILABLE", f"MLflow refused the version: {error}") from None

    def set_production(self, name: str, mlflow_version: str) -> None:
        """Point MLflow's `production` alias at the live version, so MLflow shows the same thing."""
        try:
            self._call(
                "POST",
                "/registered-models/alias",
                json={"name": name, "alias": PRODUCTION_ALIAS, "version": mlflow_version},
            )
        except MlflowError as error:
            raise ApiError(503, "MLFLOW_UNAVAILABLE", f"MLflow refused the alias: {error}") from None


def run_metrics(run: dict) -> dict[str, float]:
    """The run's latest value of every metric (numbers only: JSON has no NaN or infinity)."""
    metrics = {}
    for metric in (run.get("data") or {}).get("metrics", []):
        value = float(metric["value"])
        if math.isfinite(value):
            metrics[metric["key"]] = value
    return metrics


def run_tags(run: dict) -> dict[str, str]:
    return {tag["key"]: tag["value"] for tag in (run.get("data") or {}).get("tags", [])}


def _tags(values: dict) -> list[dict]:
    return [{"key": key, "value": str(value)} for key, value in values.items()]


class Projects:
    """Membership check: GET /projects/{id} with the user's X-User-Id -> 200 member, 403 not, 404 none."""

    def __init__(self, http: httpx.Client, url: str) -> None:
        self.http = http
        self.url = url.rstrip("/")

    def status(self, project_id: str, user_id: str) -> int:
        try:
            answer = self.http.get(f"{self.url}/projects/{project_id}", headers={"X-User-Id": user_id})
        except httpx.HTTPError:
            raise ApiError(
                503, "PROJECT_SERVICE_UNAVAILABLE", "The Projects service is not reachable"
            ) from None
        if answer.status_code not in (200, 403, 404):
            raise ApiError(
                503, "PROJECT_SERVICE_UNAVAILABLE", f"The Projects service answered {answer.status_code}"
            )
        return answer.status_code

    def require_member(self, project_id: str, user_id: str) -> None:
        status = self.status(project_id, user_id)
        if status == 404:
            raise ApiError(404, "PROJECT_NOT_FOUND", f"Project {project_id} does not exist")
        if status == 403:
            raise ApiError(403, "NOT_A_MEMBER", f"You are not a member of {project_id}")


class DeploymentFailed(Exception):
    """The candidate version did not pass the inference health check (or Inference was unreachable)."""


class Inference:
    """Health-gated deployment: Inference loads and checks a candidate before it may take traffic."""

    def __init__(self, http: httpx.Client, url: str, deploy_timeout: float) -> None:
        self.http = http
        self.url = url.rstrip("/")
        self.deploy_timeout = deploy_timeout

    def check_candidate(self, model_id: str, candidate: dict) -> None:
        """Ask Inference to load `candidate` and pass its health check. Raises DeploymentFailed."""
        try:
            answer = self.http.post(
                f"{self.url}/internal/models/{model_id}/candidates",
                json=candidate,
                timeout=self.deploy_timeout,
            )
        except httpx.HTTPError as error:
            raise DeploymentFailed(f"Inference is not reachable ({type(error).__name__})") from None
        if answer.status_code != 200:
            try:
                reason = answer.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                reason = f"Inference answered {answer.status_code}"
            raise DeploymentFailed(reason)

    def switch(self, model_id: str) -> bool:
        """Tell Inference the live version changed, so it switches now instead of at its next check."""
        try:
            return self.http.post(f"{self.url}/internal/models/{model_id}/refresh").status_code == 200
        except httpx.HTTPError:
            return False
