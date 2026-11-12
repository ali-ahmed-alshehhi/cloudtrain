"""The five public endpoints of the Projects service.

Membership rule: only members of a project may read or use it. Other services ask
GET /projects/{project_id} with the user's X-User-Id: 200 = member, 403 = not a member, 404 = no project.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import Member, Project
from app.errors import ApiError
from app.idempotency import create_once, fingerprint
from app.schemas import PROJECT_ID_PATTERN, MemberAdd, ProjectCreate, member_json, project_json

router = APIRouter()


def get_session(request: Request):
    """One database session per request, closed afterwards."""
    with request.app.state.sessions() as session:
        yield session


def current_user(x_user_id: Annotated[str | None, Header(max_length=128)] = None) -> str:
    """The gateway sets X-User-Id after checking the login token. No header means not logged in."""
    if not x_user_id:
        raise ApiError(401, "NOT_AUTHENTICATED", "Missing X-User-Id (requests must come through the gateway)")
    return x_user_id


SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[str, Depends(current_user)]
ProjectIdPath = Annotated[str, Path(pattern=PROJECT_ID_PATTERN)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def load_project(session: Session, project_id: str) -> Project:
    number = int(project_id.removeprefix("project-"))
    project = session.get(Project, number)
    if project is None:
        raise ApiError(404, "PROJECT_NOT_FOUND", f"Project {project_id} does not exist")
    return project


def role_of(project: Project, user_id: str) -> str | None:
    for member in project.members:
        if member.user_id == user_id:
            return member.role
    return None


@router.post("/projects", status_code=201)
def create_project(
    body: ProjectCreate, session: SessionDep, user_id: UserDep, idempotency_key: IdempotencyKey = None
) -> JSONResponse:
    def create() -> tuple[int, dict]:
        project = Project(name=body.name, description=body.description, owner_id=user_id)
        project.members.append(Member(user_id=user_id, role="owner"))
        session.add(project)
        session.flush()  # gives the project its number
        return 201, project_json(project)

    request_fingerprint = fingerprint("POST", "/projects", body.model_dump())
    status_code, answer = create_once(session, user_id, idempotency_key, request_fingerprint, create)
    return JSONResponse(status_code=status_code, content=answer)


@router.get("/projects")
def list_projects(session: SessionDep, user_id: UserDep) -> dict:
    query = (
        select(Project)
        .join(Member)
        .where(Member.user_id == user_id)
        .options(selectinload(Project.members))
        .order_by(Project.id)
    )
    return {"items": [project_json(project) for project in session.scalars(query)]}


@router.get("/projects/{project_id}")
def get_project(project_id: ProjectIdPath, session: SessionDep, user_id: UserDep) -> dict:
    project = load_project(session, project_id)
    if role_of(project, user_id) is None:
        raise ApiError(403, "NOT_A_MEMBER", f"You are not a member of {project_id}")
    return project_json(project)


@router.post("/projects/{project_id}/members", status_code=201)
def add_member(
    project_id: ProjectIdPath,
    body: MemberAdd,
    session: SessionDep,
    user_id: UserDep,
    idempotency_key: IdempotencyKey = None,
) -> JSONResponse:
    def create() -> tuple[int, dict]:
        project = load_project(session, project_id)
        if role_of(project, user_id) != "owner":
            raise ApiError(403, "NOT_PROJECT_OWNER", f"Only owners of {project_id} can add members")
        if role_of(project, body.user_id) is not None:
            raise ApiError(409, "ALREADY_A_MEMBER", f"{body.user_id} is already a member of {project_id}")
        member = Member(user_id=body.user_id, role=body.role)
        project.members.append(member)
        session.flush()
        return 201, member_json(member, project)

    request_fingerprint = fingerprint("POST", f"/projects/{project_id}/members", body.model_dump())
    status_code, answer = create_once(session, user_id, idempotency_key, request_fingerprint, create)
    return JSONResponse(status_code=status_code, content=answer)


@router.get("/users/me")
def current_user_info(session: SessionDep, user_id: UserDep) -> dict:
    numbers = session.scalars(
        select(Member.project_id).where(Member.user_id == user_id).order_by(Member.project_id)
    )
    return {"user_id": user_id, "project_ids": [f"project-{number:02d}" for number in numbers]}
