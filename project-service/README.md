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

## Files

| File | What it does |
|---|---|
| `app/routes.py` | The five endpoints and the membership rule |
| `app/db.py` | The tables (`projects`, `members`, `idempotency_keys`) in the `projects` schema |
| `app/schemas.py` | Request bodies and answers, as in the contract |
| `app/idempotency.py` | Same `Idempotency-Key` → same answer, created only once |
| `app/errors.py` | The shared error format (and 503 when the database is down) |
| `app/main.py` | Builds the app: request IDs, JSON logs, metrics, `/health` (checks the database) |
| `migrations/` | Alembic migrations; the container runs `alembic upgrade head` on start |

Table details: `docs/database/projects.md`.

## Run the tests
Unit tests use an in-memory database, so nothing else needs to run:
```bash
cd project-service
python3.11 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Acceptance test
A logged-in user creates "Image Classification" through the gateway and gets 201 `project-01`.
A repeated request with the same `Idempotency-Key` returns the same project.
A user who is not a member gets 403.
