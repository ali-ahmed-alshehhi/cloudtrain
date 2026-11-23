"""Only project members can read a project's MLflow runs (#107).

The MLflow route (/api/v1/experiments/*) used to check only the login, so any user could read
every project's runs. MLflow has no projects of its own: the training worker tags every run with
`project_id`. So the gateway:

  - lets through only the read endpoints the portal uses (anything else: 404);
  - passes experiments through as they are (an experiment holds no project data);
  - on runs/search, returns only the runs of the caller's projects;
  - on runs/get and metrics/get-history, answers 404 for a run of another project, the same as
    MLflow does for a run that does not exist, so nothing is revealed.

The caller's projects come from the Projects service (GET /projects with X-User-Id).
MLflow can't filter a tag by a list of values, so runs/search is filtered here; a page can
therefore hold fewer runs than max_results.
"""

from urllib.parse import urlencode

import httpx
from fastapi import Request
from starlette.responses import JSONResponse, Response

from app import proxy
from app.errors import error_response
from app.routing import Route

PREFIX = "/api/v1/experiments/"
EXPERIMENT_PATHS = {"experiments/get", "experiments/get-by-name", "experiments/search"}
RUN_PATHS = {"runs/get", "metrics/get-history"}
SEARCH_PATH = "runs/search"
# metrics/get-history is sent to MLflow with only the checked run_id and these parameters.
METRIC_PARAMS = ("metric_key", "max_results", "page_token")


class Unavailable(Exception):
    """A service the check needs did not answer."""


def run_project(run: dict) -> str | None:
    tags = run.get("data", {}).get("tags", [])
    return next((tag.get("value") for tag in tags if tag.get("key") == "project_id"), None)


async def caller_projects(
    client: httpx.AsyncClient, projects_url: str, user_id: str, request_id: str, timeout: float
) -> set[str]:
    try:
        answer = await client.get(
            projects_url.rstrip("/") + "/projects",
            headers={"X-User-Id": user_id, "X-Request-Id": request_id},
            timeout=timeout,
        )
    except httpx.HTTPError as error:
        raise Unavailable("projects") from error
    if answer.status_code != 200:
        raise Unavailable("projects")
    return {item["project_id"] for item in answer.json().get("items", []) if "project_id" in item}


async def read_mlflow(
    client: httpx.AsyncClient, method: str, url: str, request_id: str, timeout: float, body=None
):
    try:
        return await client.request(
            method,
            url,
            content=body,
            headers={"X-Request-Id": request_id, "Content-Type": "application/json"},
            timeout=timeout,
        )
    except httpx.HTTPError as error:
        raise Unavailable("experiments") from error


def not_found(run_id: str, request_id: str) -> Response:
    return error_response(404, "RESOURCE_DOES_NOT_EXIST", f"Run '{run_id}' not found.", request_id)


async def forward(
    client: httpx.AsyncClient,
    request: Request,
    route: Route,
    projects_url: str,
    user_id: str,
    request_id: str,
    timeout: float,
) -> Response:
    path = request.url.path
    endpoint = path[len(PREFIX) :] if path.startswith(PREFIX) else ""
    if endpoint in EXPERIMENT_PATHS:
        return await proxy.forward(client, request, route, user_id, request_id, timeout)
    if endpoint not in RUN_PATHS and endpoint != SEARCH_PATH:
        return error_response(404, "NOT_FOUND", f"No route for {path}", request_id)

    try:
        projects = await caller_projects(client, projects_url, user_id, request_id, timeout)
        if endpoint == SEARCH_PATH:
            url = route.upstream_url(path, request.url.query)
            answer = await read_mlflow(client, "POST", url, request_id, timeout, await request.body())
            if answer.status_code >= 400:
                return await proxy.mlflow_error(answer, request_id)
            found = answer.json()
            found["runs"] = [run for run in found.get("runs", []) if run_project(run) in projects]
            return JSONResponse(found)

        # Exactly one run id: Starlette reads the last of a repeated parameter and MLflow the first,
        # so a repeated or mixed run_id/run_uuid could pass the check on one run and read another.
        ids = request.query_params.getlist("run_id") + request.query_params.getlist("run_uuid")
        if len(ids) != 1 or not ids[0]:
            message = "Give exactly one run_id."
            return error_response(400, "INVALID_PARAMETER_VALUE", message, request_id)
        run_id = ids[0]
        run_url = route.upstream_url(PREFIX + "runs/get", urlencode({"run_id": run_id}))
        answer = await read_mlflow(client, "GET", run_url, request_id, timeout)
        if answer.status_code >= 400:
            return await proxy.mlflow_error(answer, request_id)
        run = answer.json().get("run", {})
        if run_project(run) not in projects:
            return not_found(run_id, request_id)
        if endpoint == "runs/get":
            return JSONResponse(answer.json())
        # Never forward the caller's query: rebuild it from the run that was checked.
        params = {"run_id": run_id}
        params.update({n: request.query_params[n] for n in METRIC_PARAMS if n in request.query_params})
        url = route.upstream_url(path, urlencode(params))
        answer = await read_mlflow(client, "GET", url, request_id, timeout)
        if answer.status_code >= 400:
            return await proxy.mlflow_error(answer, request_id)
        return JSONResponse(answer.json())
    except Unavailable as error:
        return error_response(503, "SERVICE_UNAVAILABLE", f"{error} is not reachable", request_id)
    except ValueError:
        return error_response(
            503, "SERVICE_UNAVAILABLE", "experiments returned an unreadable answer", request_id
        )
