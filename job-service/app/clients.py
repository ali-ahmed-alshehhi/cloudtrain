"""Calls to the two services Training Jobs asks before it accepts or shows a job.

- Projects (Ali): GET /projects/{id} with the user's X-User-Id is the membership check
  (200 member, 403 not a member, 404 no such project); GET /projects lists the user's projects.
- Datasets (Faisal): GET /datasets/{id} (which project owns it) and
  GET /datasets/{id}/versions/{v} (does this version exist).

These are internal calls: never through the gateway. Each forwards X-User-Id and X-Request-Id, so
one request can be followed across services in the logs. A service that is down means 503.
"""

import httpx

from app.common import ApiError


class Services:
    def __init__(
        self, project_url: str, dataset_url: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.projects = httpx.Client(base_url=project_url, transport=transport, timeout=5)
        self.datasets = httpx.Client(base_url=dataset_url, transport=transport, timeout=5)

    @staticmethod
    def _get(client: httpx.Client, path: str, user_id: str, request_id: str, who: str) -> httpx.Response:
        try:
            return client.get(path, headers={"X-User-Id": user_id, "X-Request-Id": request_id})
        except httpx.HTTPError:
            raise ApiError(503, "SERVICE_UNAVAILABLE", f"The {who} service is not reachable") from None

    def check_member(self, project_id: str, user_id: str, request_id: str) -> None:
        answer = self._get(self.projects, f"/projects/{project_id}", user_id, request_id, "Projects")
        if answer.status_code == 200:
            return
        if answer.status_code == 403:
            raise ApiError(403, "NOT_A_MEMBER", f"You are not a member of {project_id}")
        if answer.status_code == 404:
            raise ApiError(404, "PROJECT_NOT_FOUND", f"Project {project_id} does not exist")
        raise ApiError(503, "SERVICE_UNAVAILABLE", "The Projects service could not check membership")

    def my_projects(self, user_id: str, request_id: str) -> list[str]:
        answer = self._get(self.projects, "/projects", user_id, request_id, "Projects")
        if answer.status_code != 200:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "The Projects service could not list your projects")
        return [project["project_id"] for project in answer.json().get("items", [])]

    def check_dataset(
        self, project_id: str, dataset_id: str, version: int, user_id: str, request_id: str
    ) -> None:
        """The dataset exists, belongs to the job's project, and has this version."""
        dataset = self._get(self.datasets, f"/datasets/{dataset_id}", user_id, request_id, "Datasets")
        if dataset.status_code == 404:
            raise ApiError(404, "DATASET_NOT_FOUND", f"Dataset {dataset_id} does not exist")
        if dataset.status_code == 403:
            raise ApiError(403, "NOT_A_MEMBER", f"You cannot use dataset {dataset_id}")
        if dataset.status_code != 200:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "The Datasets service could not find the dataset")
        if dataset.json().get("project_id") != project_id:
            # Otherwise a member of two projects could train project A's job on project B's data.
            raise ApiError(
                422, "DATASET_NOT_IN_PROJECT", f"Dataset {dataset_id} does not belong to {project_id}"
            )

        found = self._get(
            self.datasets, f"/datasets/{dataset_id}/versions/{version}", user_id, request_id, "Datasets"
        )
        if found.status_code == 404:
            raise ApiError(
                404, "DATASET_VERSION_NOT_FOUND", f"Dataset {dataset_id} version {version} does not exist"
            )
        if found.status_code != 200:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "The Datasets service could not confirm the version")
