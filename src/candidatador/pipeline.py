"""Search pipeline: fetch from every enabled source -> filter -> dedupe -> score -> store."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlmodel import Session, select

from candidatador.config import Config, Profile
from candidatador.matching import passes_filters, score_job
from candidatador.models import Document, DocumentKind, Job
from candidatador.sources import JobPosting, SearchQuery, available_sources


@dataclass
class SearchReport:
    fetched: int = 0
    filtered_out: int = 0
    duplicates: int = 0
    stored: list[Job] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


def run_search(
    s: Session,
    config: Config,
    profile: Profile,
    query: SearchQuery,
    *,
    only_sources: list[str] | None = None,
    use_ai: bool = False,
    on_progress: Callable[[str], None] = lambda _msg: None,
) -> SearchReport:
    report = SearchReport()
    registry = available_sources()
    names = only_sources or config.enabled_sources()

    postings: list[JobPosting] = []
    for name in names:
        cls = registry.get(name)
        if cls is None:
            report.errors[name] = "fonte desconhecida"
            continue
        on_progress(f"Buscando em {cls.display_name}...")
        try:
            found = list(cls(config.source_settings(name)).search(query))
        except Exception as exc:  # one failing site must not abort the search
            report.errors[name] = f"{type(exc).__name__}: {exc}"
            continue
        report.fetched += len(found)
        postings.extend(found)

    assistant = None
    resumes: list[Document] = []
    if use_ai:
        from candidatador.llm import ClaudeAssistant

        assistant = ClaudeAssistant(config.ai)
        resumes = list(s.exec(select(Document).where(Document.kind == DocumentKind.RESUME)))

    seen_fingerprints = set(s.exec(select(Job.fingerprint)).all())
    for posting in postings:
        ok, _reason = passes_filters(posting, profile, query)
        if not ok:
            report.filtered_out += 1
            continue

        existing = s.get(Job, posting.id)
        if existing is None and posting.fingerprint in seen_fingerprints:
            report.duplicates += 1
            continue
        seen_fingerprints.add(posting.fingerprint)

        match = score_job(posting, profile)
        score, reasons = match.score, match.reasons
        if assistant is not None and score >= config.matching.min_score / 2:
            on_progress(f"Analisando com IA: {posting.title} @ {posting.company}")
            evaluation = assistant.evaluate_job(profile, resumes, posting)
            score, reasons = float(evaluation.score), evaluation.reasons

        job = existing or Job(
            id=posting.id,
            source=posting.source,
            external_id=posting.external_id,
            title=posting.title,
            url=posting.url,
            fingerprint=posting.fingerprint,
        )
        job.company = posting.company
        job.location = posting.location
        job.remote = posting.remote
        job.apply_url = posting.apply_url
        job.description = posting.description
        job.employment_type = posting.employment_type
        job.salary = posting.salary
        job.posted_at = posting.posted_at
        job.score = score
        job.score_reasons_json = json.dumps(reasons, ensure_ascii=False)
        job.raw_json = json.dumps(posting.raw, ensure_ascii=False, default=str)
        s.add(job)
        report.stored.append(job)

    s.commit()
    report.stored.sort(key=lambda j: j.score or 0, reverse=True)
    return report


def job_to_posting(job: Job) -> JobPosting:
    return JobPosting(
        source=job.source,
        external_id=job.external_id,
        title=job.title,
        company=job.company,
        location=job.location,
        remote=job.remote,
        url=job.url,
        apply_url=job.apply_url,
        description=job.description,
        employment_type=job.employment_type,
        salary=job.salary,
        posted_at=job.posted_at,
        raw=job.raw,
    )
