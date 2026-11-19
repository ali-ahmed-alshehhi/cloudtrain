"""Ask the Projects service whether a user is a member of a project.

GET /projects/{id} with X-User-Id → 200 member, 403 not a member, 404 no project.
"""

from __future__ import annotations

import os

import httpx

from app.errors import ApiError


class ProjectsClient:
    def __init__(self, base_url: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        url = base_url or os.environ.get("PROJECT_SERVICE_URL", "http://project-service:8001")
        self._client = httpx.Client(base_url=url, transport=transport, timeout=5)

    def require_member(self, project_id: str, user_id: str, request_id: str) -> None:
        try:
            answer = self._client.get(
                f"/projects/{project_id}",
                headers={"X-User-Id": user_id, "X-Request-Id": request_id},
            )
        except httpx.HTTPError:
            raise ApiError(503, "SERVICE_UNAVAILABLE", "The Projects service is not reachable") from None
        if answer.status_code == 200:
            return
        if answer.status_code == 403:
            raise ApiError(403, "NOT_A_MEMBER", f"You are not a member of {project_id}")
        if answer.status_code == 404:
            raise ApiError(404, "PROJECT_NOT_FOUND", f"Project {project_id} does not exist")
        raise ApiError(503, "SERVICE_UNAVAILABLE", "The Projects service could not check membership")


class AllowAllProjects:
    """Test double: every user is treated as a member."""

    def require_member(self, project_id: str, user_id: str, request_id: str) -> None:
        return None
