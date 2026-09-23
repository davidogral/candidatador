"""Application use-case shared by the CLI and the web UI.

The caller supplies the interaction hooks (confirm / ask_user / log), so the same flow
works in a terminal prompt or in the browser UI.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from sqlmodel import Session

from candidatador.apply import AnswerProvider, ApplyContext, find_applier
from candidatador.apply.answers import ResolvedAnswer
from candidatador.config import Paths, load_config, load_profile
from candidatador.db import submitted_since
from candidatador.documents import pick_resume
from candidatador.models import Application, ApplicationStatus, Document, Job, JobStatus, utcnow
from candidatador.pipeline import job_to_posting


@dataclass
class ApplyOptions:
    doc_id: int | None = None
    mode: Literal["review", "auto"] | None = None  # None -> config.apply.mode
    dry_run: bool = False
    ai: bool | None = None  # None -> config.matching.use_ai
    cover_letter: bool = False


@dataclass
class ApplyHooks:
    confirm: Callable[[str], bool]
    ask_user: Callable[[str, list[str] | None], str | None]
    log: Callable[[str], None] = lambda _msg: None


@dataclass
class ApplyResult:
    status: ApplicationStatus | None  # None: nothing happened (limit reached / manual pending)
    applier: str | None = None
    url: str = ""
    resume: Document | None = None
    notes: list[str] = field(default_factory=list)
    error: str = ""
    manual_required: bool = False
    answers: dict[str, ResolvedAnswer] = field(default_factory=dict)


def apply_to_job(
    s: Session, paths: Paths, job: Job, options: ApplyOptions, hooks: ApplyHooks
) -> ApplyResult:
    config, profile = load_config(paths), load_profile(paths)
    mode = options.mode or config.apply.mode
    url = job.apply_url or job.url

    if not options.dry_run and submitted_since(s) >= config.apply.max_per_day:
        return ApplyResult(
            None, url=url, error=f"Limite diário de {config.apply.max_per_day} atingido."
        )

    resume = (
        s.get(Document, options.doc_id)
        if options.doc_id
        else pick_resume(s, f"{job.title}\n{job.description}")
    )
    applier_cls = find_applier(url)
    if applier_cls is None:
        return ApplyResult(None, url=url, resume=resume, manual_required=True)

    posting = job_to_posting(job)
    use_ai = config.matching.use_ai if options.ai is None else options.ai
    assistant = None
    if use_ai or options.cover_letter:
        from candidatador.llm import AIAssistant, AIUnavailableError

        try:
            assistant = AIAssistant(config.ai)
            hooks.log(f"IA: {assistant.backend.name}")
        except AIUnavailableError as exc:
            hooks.log(f"IA desativada: {exc}")

    answers = AnswerProvider(
        profile, posting, resume, assistant if use_ai else None, hooks.ask_user
    )
    letter = None
    if options.cover_letter and assistant:
        hooks.log("Gerando carta de apresentação com IA...")
        try:
            letter = assistant.cover_letter(profile, resume, posting)
        except Exception as exc:
            hooks.log(f"Carta não gerada: {exc}")

    ctx = ApplyContext(
        profile=profile,
        job=posting,
        resume=resume,
        answers=answers,
        confirm=hooks.confirm,
        mode=mode,
        dry_run=options.dry_run,
        headless=config.apply.headless and mode == "auto",
        browser_state=paths.browser_state,
        cover_letter=letter,
    )
    hooks.log(
        f"Via {applier_cls.display_name} · modo {mode}{' · dry-run' if options.dry_run else ''}"
        f" · currículo: {resume.title if resume else 'nenhum'}"
    )
    result = ApplyResult(None, applier=applier_cls.name, url=url, resume=resume)
    try:
        outcome = applier_cls().apply(ctx)
        result.status, result.notes, result.error = outcome.status, outcome.notes, outcome.error
    except Exception as exc:
        result.status, result.error = ApplicationStatus.FAILED, f"{type(exc).__name__}: {exc}"

    result.answers = answers.log
    record_application(
        s,
        job,
        resume,
        applier_cls.name,
        mode,
        result.status,
        answers.log,
        result.error,
        "\n".join(result.notes),
    )
    return result


def record_application(
    s: Session,
    job: Job,
    resume: Document | None,
    applier: str,
    mode: str,
    status: ApplicationStatus,
    answers: dict[str, ResolvedAnswer],
    error: str = "",
    notes: str = "",
) -> Application:
    application = Application(
        job_id=job.id,
        document_id=resume.id if resume else None,
        applier=applier,
        mode=mode,
        status=status,
        answers_json=json.dumps({q: vars(a) for q, a in answers.items()}, ensure_ascii=False),
        error=error,
        notes=notes,
        submitted_at=utcnow() if status == ApplicationStatus.SUBMITTED else None,
    )
    s.add(application)
    if status in (ApplicationStatus.SUBMITTED, ApplicationStatus.MANUAL):
        job.status = JobStatus.APPLIED
        s.add(job)
    s.commit()
    return application
