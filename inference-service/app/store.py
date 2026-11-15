"""Which model version is live, kept in step with the Model Registry.

- A version takes traffic only after it loaded and passed its health check.
- The registry sends a candidate BEFORE making it live (`stage`); it is loaded and checked here,
  and the registry promotes it only if that passed. Then the switch is instant.
- Every `refresh_seconds` (or when the registry says so) the store asks the registry which version
  is live. If that version cannot be loaded or fails its check, the old one keeps serving.
- If the registry is down, the loaded version keeps serving.
"""

import threading
import time
from collections.abc import Callable
from logging import Logger

import httpx

from app.model import Deployment, LoadedModel, ModelProblem


class NoModel(Exception):
    """Nothing can be served for this model right now (no live version, or the registry is down)."""


class RegistryDown(NoModel):
    """The registry could not be asked; a loaded version keeps serving."""


class UnknownModel(Exception):
    """The registry has no such model."""


class Registry:
    def __init__(self, http: httpx.Client, url: str) -> None:
        self.http = http
        self.url = url.rstrip("/")

    def production(self, model_id: str) -> Deployment:
        try:
            answer = self.http.get(f"{self.url}/models/{model_id}/production")
        except httpx.HTTPError:
            raise RegistryDown("The Model Registry is not reachable") from None
        if answer.status_code == 404:
            code = answer.json().get("error", {}).get("code")
            if code == "NO_PRODUCTION_VERSION":
                raise NoModel(f"Model {model_id} has no live version yet")
            raise UnknownModel(f"Model {model_id} does not exist")
        if answer.status_code != 200:
            raise RegistryDown(f"The Model Registry answered {answer.status_code}")
        body = answer.json()
        return Deployment(
            model_id=model_id,
            name=body["name"],
            version=body["version"],
            mlflow_run_id=body["mlflow_run_id"],
            artifact_uri=body["artifact_uri"],
        )


class ModelStore:
    def __init__(
        self,
        registry: Registry,
        loader: Callable[[Deployment], LoadedModel],
        refresh_seconds: float,
        logger: Logger,
    ) -> None:
        self.registry = registry
        self.loader = loader
        self.refresh_seconds = refresh_seconds
        self.logger = logger
        self.live: dict[str, LoadedModel] = {}
        self.candidates: dict[str, LoadedModel] = {}  # checked, waiting for the registry to promote them
        self.failed: dict[
            str, Deployment
        ] = {}  # the last version that failed, so it is not retried each time
        self.asked_at: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    def _lock(self, model_id: str) -> threading.Lock:
        with self._locks_lock:
            return self._locks.setdefault(model_id, threading.Lock())

    def stage(self, deployment: Deployment) -> LoadedModel:
        """Load and check a candidate the registry wants to promote. Raises ModelProblem."""
        with self._lock(deployment.model_id):
            live = self.live.get(deployment.model_id)
            if live and live.deployment.same_as(deployment):
                return live
            try:
                loaded = self.loader(deployment)
            except ModelProblem as problem:
                self.logger.warning(
                    f"candidate {deployment.model_id} v{deployment.version} failed: {problem}"
                )
                raise
            self.candidates[deployment.model_id] = loaded
            self.failed.pop(deployment.model_id, None)
            self.logger.info(f"candidate {deployment.model_id} v{deployment.version} passed its health check")
            return loaded

    def current(self, model_id: str, force: bool = False) -> LoadedModel:
        """The live model, after asking the registry if the last answer is older than refresh_seconds."""
        with self._lock(model_id):
            live = self.live.get(model_id)
            fresh = time.monotonic() - self.asked_at.get(model_id, -1e9) < self.refresh_seconds
            if live and fresh and not force:
                return live
            try:
                wanted = self.registry.production(model_id)
            except RegistryDown as reason:
                if live is None:
                    raise
                self.logger.warning(f"{reason}; still serving {model_id} v{live.deployment.version}")
                return live
            except (NoModel, UnknownModel):
                self.live.pop(model_id, None)
                raise
            self.asked_at[model_id] = time.monotonic()
            if live and live.deployment.same_as(wanted):
                return live
            new = self._ready(wanted)
            if new is None:
                if live:
                    return live
                raise NoModel(f"Version {wanted.version} of {model_id} failed its health check")
            self.live[model_id] = new
            self.logger.info(f"now serving {model_id} v{new.deployment.version}")
            return new

    def _ready(self, wanted: Deployment) -> LoadedModel | None:
        """The checked model for `wanted`: the staged candidate, or load it now. None if it fails."""
        candidate = self.candidates.get(wanted.model_id)
        if candidate and candidate.deployment.same_as(wanted):
            del self.candidates[wanted.model_id]
            return candidate
        failed = self.failed.get(wanted.model_id)
        if failed and failed.same_as(wanted):
            return None
        try:
            return self.loader(wanted)
        except ModelProblem as problem:
            self.failed[wanted.model_id] = wanted
            self.logger.warning(
                f"{wanted.model_id} v{wanted.version} failed, keeping the old version: {problem}"
            )
            return None

    def healthy(self, model_id: str) -> bool:
        """The health check of the live model (True when none is loaded yet: the service itself is up)."""
        live = self.live.get(model_id)
        if live is None:
            return True
        try:
            live.check()
            return True
        except ModelProblem as problem:
            self.logger.warning(f"{model_id} v{live.deployment.version} failed its health check: {problem}")
            return False
