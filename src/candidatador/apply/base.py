"""Contract for appliers: components that fill and submit application forms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Literal

from candidatador.apply.answers import AnswerProvider
from candidatador.config import Profile
from candidatador.models import ApplicationStatus
from candidatador.sources.base import JobPosting, normalize

if TYPE_CHECKING:
    from candidatador.models import Document


@dataclass
class ApplyContext:
    profile: Profile
    job: JobPosting
    resume: Document | None
    answers: AnswerProvider
    confirm: Callable[[str], bool]
    mode: Literal["review", "auto"] = "review"
    dry_run: bool = False
    headless: bool = False
    browser_state: Path | None = None
    cover_letter: str | None = None

    def resume_upload_name(self) -> str | None:
        """File name the employer sees: "<name>-<company>.pdf" (not the vault's hash name)."""
        if self.resume is None:
            return None
        suffix = Path(self.resume.original_name or self.resume.path).suffix or ".pdf"
        parts = [slugify(self.profile.personal.full_name), slugify(self.job.company)]
        stem = "-".join(p for p in parts if p)
        return f"{stem}{suffix}" if stem else self.resume.original_name


def slugify(value: str) -> str:
    return normalize(value).replace(" ", "-")


@dataclass
class ApplyOutcome:
    status: ApplicationStatus
    notes: list[str] = field(default_factory=list)
    error: str = ""


class Applier(ABC):
    name: ClassVar[str]
    display_name: ClassVar[str]

    @classmethod
    @abstractmethod
    def supports(cls, url: str) -> bool:
        """True if this applier knows how to handle the given application URL."""

    @abstractmethod
    def apply(self, ctx: ApplyContext) -> ApplyOutcome: ...
