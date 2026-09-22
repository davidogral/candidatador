"""Database models: documents, jobs and applications."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class DocumentKind(StrEnum):
    RESUME = "resume"
    COVER_LETTER = "cover_letter"
    CERTIFICATE = "certificate"
    COURSE = "course"
    DIPLOMA = "diploma"
    PORTFOLIO = "portfolio"
    OTHER = "other"


class JobStatus(StrEnum):
    NEW = "new"
    SHORTLISTED = "shortlisted"
    IGNORED = "ignored"
    APPLIED = "applied"


class ApplicationStatus(StrEnum):
    FILLED = "filled"  # form filled, waiting for user confirmation
    SUBMITTED = "submitted"
    SKIPPED = "skipped"  # user declined at review time
    FAILED = "failed"
    MANUAL = "manual"  # no applier available; user applied by hand


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: DocumentKind = Field(index=True)
    title: str
    language: str = "pt"
    tags_json: str = "[]"
    path: str  # absolute path inside the vault
    original_name: str
    sha256: str = Field(index=True)
    text: str = ""  # extracted text, used for matching and AI prompts
    is_default: bool = False
    issued_by: str = ""  # certificates/courses: institution
    issued_at: str = ""  # certificates/courses: date (free text)
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def tags(self) -> list[str]:
        return list(json.loads(self.tags_json or "[]"))


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)  # "<source>:<external_id>"
    source: str = Field(index=True)
    external_id: str
    title: str
    company: str = ""
    location: str = ""
    remote: bool | None = None
    url: str
    apply_url: str = ""
    description: str = ""
    employment_type: str = ""
    salary: str = ""
    posted_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=utcnow)
    fingerprint: str = Field(index=True)  # used to dedupe the same job across sources
    score: float | None = Field(default=None, index=True)
    score_reasons_json: str = "[]"
    status: JobStatus = Field(default=JobStatus.NEW, index=True)
    raw_json: str = "{}"

    @property
    def score_reasons(self) -> list[str]:
        return list(json.loads(self.score_reasons_json or "[]"))

    @property
    def raw(self) -> dict[str, Any]:
        return dict(json.loads(self.raw_json or "{}"))


class Application(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="job.id", index=True)
    document_id: int | None = Field(default=None, foreign_key="document.id")
    applier: str = ""
    mode: str = "review"
    status: ApplicationStatus
    answers_json: str = "{}"  # question -> answer actually sent
    error: str = ""
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    submitted_at: datetime | None = None
