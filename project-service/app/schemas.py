"""Request bodies and answers, exactly as in contracts/openapi/project-service.yaml."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.db import Member, Project

PROJECT_ID_PATTERN = r"^project-[0-9]+$"


def _no_nul(value: str | None) -> str | None:
    """PostgreSQL text cannot hold the NUL character: refuse it here (422), not in the database (500)."""
    if value is not None and "\x00" in value:
        raise ValueError("must not contain the NUL character (\\u0000)")
    return value


NoNul = AfterValidator(_no_nul)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are refused, as the contract says

    name: Annotated[str, Field(min_length=1, max_length=100), NoNul]
    description: Annotated[str | None, Field(max_length=1000), NoNul] = None


class MemberAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: Annotated[str, Field(min_length=1, max_length=128), NoNul]
    role: Literal["owner", "member"] = "member"


def iso_utc(moment: datetime) -> str:
    """ISO 8601 in UTC, e.g. 2026-11-14T09:30:00Z (the shared naming rule)."""
    if moment.tzinfo is None:  # the test database forgets the time zone; we only ever store UTC
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def member_json(member: Member, project: Project) -> dict:
    return {
        "project_id": project.public_id,
        "user_id": member.user_id,
        "role": member.role,
        "added_at": iso_utc(member.added_at),
    }


def project_json(project: Project) -> dict:
    return {
        "project_id": project.public_id,
        "name": project.name,
        "description": project.description,
        "owner_id": project.owner_id,
        "created_at": iso_utc(project.created_at),
        "members": [member_json(member, project) for member in project.members],
    }
