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
from candidatador.sources.base import JobPosting

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
