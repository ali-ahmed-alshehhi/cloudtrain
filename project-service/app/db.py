"""Database tables of the Projects service. They all live in the PostgreSQL schema `projects`."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SCHEMA = "projects"


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(1000))
    owner_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    members: Mapped[list["Member"]] = relationship(
        back_populates="project", order_by="Member.added_at", cascade="all, delete-orphan"
    )

    @property
    def public_id(self) -> str:
        """The ID the outside world sees, e.g. 7 -> "project-07"."""
        return f"project-{self.id:02d}"


class Member(Base):
    __tablename__ = "members"

    project_id: Mapped[int] = mapped_column(ForeignKey(f"{SCHEMA}.projects.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))  # "owner" or "member"
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    project: Mapped[Project] = relationship(back_populates="members")


class IdempotencyRecord(Base):
    """The first answer to a create request, kept so a repeat with the same key gets the same answer."""

    __tablename__ = "idempotency_keys"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
