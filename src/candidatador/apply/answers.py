"""Resolve answers for application-form questions.

Order: profile fields -> profile.answers -> AI (if enabled) -> ask the user.
Every answer records where it came from so the user can audit what was sent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from candidatador.config import Profile
from candidatador.sources.base import JobPosting, normalize

if TYPE_CHECKING:
    from candidatador.llm import AIAssistant
    from candidatador.models import Document

# Keys in profile.answers -> phrases that identify the question (pt/en, normalized)
QUESTION_HINTS: dict[str, list[str]] = {
    "authorized_to_work": [
        "authorized to work",
        "autorizado a trabalhar",
        "work authorization",
        "legally authorized",
        "permissao de trabalho",
    ],
    "requires_sponsorship": ["sponsorship", "patrocinio", "visa", "visto"],
    "notice_period": [
        "notice period",
        "aviso previo",
        "disponibilidade para inicio",
        "start date",
        "when can you start",
        "quando pode comecar",
    ],
    "salary_expectation": [
        "salary",
        "salarial",
        "pretensao",
        "compensation expectation",
        "remuneracao",
    ],
    "available_to_relocate": ["relocate", "relocation", "mudanca de cidade", "realocacao"],
    "how_did_you_hear": ["how did you hear", "como soube", "como conheceu", "como ficou sabendo"],
}

# Questions starting like this expect yes/no (or a sentence), never a profile field value
YES_NO_OPENERS = (
    "are you",
    "do you",
    "will you",
    "have you",
    "would you",
    "can you",
    "did you",
    "is your",
    "voce ",
    "vc ",
    "possui",
    "tem ",
    "aceita",
    "estaria",
    "esta disposto",
    "ja trabalhou",
)


@dataclass
class ResolvedAnswer:
    value: str
    origin: str  # profile | answers | ai | user
    needs_review: bool = False


@dataclass
class AnswerProvider:
    profile: Profile
    job: JobPosting
    resume: Document | None = None
    assistant: AIAssistant | None = None
    ask_user: Callable[[str, list[str] | None], str | None] | None = None
    log: dict[str, ResolvedAnswer] = field(default_factory=dict)

    def resolve(self, question: str, options: list[str] | None = None) -> ResolvedAnswer | None:
        answer = (
            self._from_answers(question)
            or self._from_profile(question)
            or self._from_ai(question, options)
            or self._from_user(question, options)
        )
        if answer is not None:
            self.log[question] = answer
        return answer

    def _from_profile(self, question: str) -> ResolvedAnswer | None:
        p = self.profile.personal
        q = f" {normalize(question)} "
        if q.lstrip().startswith(YES_NO_OPENERS):
            return None  # "Will you require sponsorship to work in this country?" is not "Brasil"
        table = [
            (["full name", "nome completo"], p.full_name),
            (["first name", "primeiro nome"], p.first_name),
            (["last name", "sobrenome", "surname"], p.last_name),
            # a bare "Nome"/"Name" field, but not "company name", "nome da empresa"...
            (["name", "nome"] if len(q.split()) <= 2 else [], p.full_name),
            (["email", "e mail"], p.email),
            (["phone", "telefone", "celular", "whatsapp"], p.phone),
            (["linkedin"], p.linkedin),
            (["github"], p.github),
            (["portfolio", "website", "site pessoal"], p.portfolio),
            (["city", "cidade"], p.city),
            (
                ["location", "localizacao", "onde voce mora"],
                ", ".join(part for part in (p.city, p.state, p.country) if part),
            ),
            (["country", "pais "], p.country),
        ]
        for needles, value in table:
            if value and any(f" {n.strip()} " in q for n in needles):
                return ResolvedAnswer(value, "profile")
        return None

    def _from_answers(self, question: str) -> ResolvedAnswer | None:
        q = normalize(question)
        for key, value in self.profile.answers.items():
            hints = [*QUESTION_HINTS.get(key, []), key.replace("_", " ")]
            if any(normalize(h) in q for h in hints):
                return ResolvedAnswer(str(value), "answers")
        return None

    def _from_ai(self, question: str, options: list[str] | None) -> ResolvedAnswer | None:
        if self.assistant is None:
            return None
        try:
            result = self.assistant.answer_question(
                self.profile, self.resume, self.job, question, options
            )
        except Exception:
            return None  # AI failed: fall back to asking the user
        if not result.answer:
            return None
        return ResolvedAnswer(result.answer, "ai", needs_review=not result.confident)

    def _from_user(self, question: str, options: list[str] | None) -> ResolvedAnswer | None:
        if self.ask_user is None:
            return None
        value = self.ask_user(question, options)
        return ResolvedAnswer(value, "user") if value else None
