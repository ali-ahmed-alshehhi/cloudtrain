"""Request bodies and answers, exactly as in contracts/openapi/project-service.yaml."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db import Member, Project

PROJECT_ID_PATTERN = r"^project-[0-9]+$"


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields are refused, as the contract says

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class MemberAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=128)
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
