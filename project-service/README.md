# Projects service — `project-service/`

| Owner | Port | Contract |
|---|---|---|
| Ali (Student 1) | 8001 (internal) | `contracts/openapi/project-service.yaml` |

## What it must do
Identity and projects: create a project, list and read projects, add members, and say who is logged in.
It is also the **membership check** for every other service: only members can read or use a project.

## Endpoints
**Public** (through the gateway, `/api/v1` + path):
- `POST /projects` → 201 (honours `Idempotency-Key`)
- `GET /projects`
- `GET /projects/{project_id}`
- `POST /projects/{project_id}/members` → 201 (owners only)
- `GET /users/me`

**Used internally by other services:** `GET /projects/{project_id}` with the user's `X-User-Id`
→ 200 member, 403 not a member, 404 no such project.

Plus `GET /health`, `GET /metrics`.

## Reads and writes
- Writes: PostgreSQL schema `projects` (projects, members, idempotency keys). Migrations with Alembic.
- Calls: nobody.

## Acceptance test
A logged-in user creates "Image Classification" through the gateway and gets 201 `project-01`.
A repeated request with the same `Idempotency-Key` returns the same project.
A user who is not a member gets 403.
