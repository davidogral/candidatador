"""Search pipeline: fetch from every enabled source -> filter -> dedupe -> score -> store."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, col, select

from candidatador.config import Config, Profile
from candidatador.matching import Filters, passes_filters, score_job
from candidatador.models import Document, DocumentKind, Job, JobStatus, utcnow
from candidatador.sources import JobPosting, SearchQuery, available_sources

AI_WORKERS = 4
UPSERT_BATCH = 200


@dataclass
class SearchReport:
    fetched: int = 0
    filtered_out: int = 0
    duplicates: int = 0
    ai_evaluated: int = 0
    #: why jobs were discarded: {"senioridade": 120, "país": 40, ...}
    filtered_reasons: dict[str, int] = field(default_factory=dict)
    stored: list[Job] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


@dataclass
class _Scored:
    posting: JobPosting
    score: float
    reasons: list[str]


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
    """Fetch -> filter/dedupe/score -> (AI, in parallel) -> one short write at the end.

    Nothing is written while sources or the AI are being called, so a long search never
    holds a database lock (the UI keeps working and a second search can't hit "locked").
    """
    report = SearchReport()

    # 1) fetch — network only, every source at the same time. Sources see the resolved
    #    filters (e.g. JobSpy searches LinkedIn in the chosen country).
    filters = Filters.resolve(query, profile)
    source_query = query.model_copy(update={"countries": filters.countries})
    postings = _fetch_all(config, source_query, only_sources, report, on_progress)

    # 2) filter, dedupe and local score — reads only
    known_ids = set(s.exec(select(Job.id)).all())
    seen_fingerprints = set(s.exec(select(Job.fingerprint)).all())
    scored: list[_Scored] = []
    seen_ids: set[str] = set()
    for posting in postings:
        ok, reason = passes_filters(posting, profile, query, filters)
        if not ok:
            report.filtered_out += 1
            report.filtered_reasons[reason] = report.filtered_reasons.get(reason, 0) + 1
            continue
        if posting.id in seen_ids or (
            posting.id not in known_ids and posting.fingerprint in seen_fingerprints
        ):
            report.duplicates += 1
            continue
        seen_ids.add(posting.id)
        seen_fingerprints.add(posting.fingerprint)
        match = score_job(posting, profile)
        scored.append(_Scored(posting, match.score, match.reasons))

    # 3) optional AI refinement — best local scores first, capped, in parallel
    if use_ai and scored:
        _refine_with_ai(s, config, profile, scored, report, on_progress)

    # 4) one short, atomic write (upsert keeps the status the user gave: shortlisted, applied...)
    on_progress("Salvando...")
    report.stored = _upsert_all(s, scored)
    report.stored.sort(key=lambda j: j.score or 0, reverse=True)
    return report


def _fetch_all(
    config: Config,
    query: SearchQuery,
    only_sources: list[str] | None,
    report: SearchReport,
    on_progress: Callable[[str], None],
) -> list[JobPosting]:
    registry = available_sources()
    names = []
    for name in only_sources or config.enabled_sources():
        if name in registry:
            names.append(name)
        else:
            report.errors[name] = "fonte desconhecida"
    if not names:
        return []

    on_progress("Buscando em " + ", ".join(registry[n].display_name.split(" (")[0] for n in names))
    postings: list[JobPosting] = []
    pending = {registry[n].display_name for n in names}
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        futures = {
            pool.submit(lambda n: list(registry[n](config.source_settings(n)).search(query)), n): n
            for n in names
        }
        for future in as_completed(futures):
            name = futures[future]
            label = registry[name].display_name
            pending.discard(label)
            try:
                found = future.result()
            except Exception as exc:  # one failing site must not abort the search
                report.errors[name] = f"{type(exc).__name__}: {exc}"
                found = []
            report.fetched += len(found)
            postings.extend(found)
            waiting = f" · aguardando {', '.join(sorted(pending))}" if pending else ""
            on_progress(f"{label}: {len(found)} vagas{waiting}")
    return postings


def _refine_with_ai(
    s: Session,
    config: Config,
    profile: Profile,
    scored: list[_Scored],
    report: SearchReport,
    on_progress: Callable[[str], None],
) -> None:
    from candidatador.llm import AIAssistant, AIUnavailableError

    try:
        assistant = AIAssistant(config.ai)
    except AIUnavailableError as exc:
        report.errors["ia"] = str(exc)
        return
    resumes = list(s.exec(select(Document).where(Document.kind == DocumentKind.RESUME)))

    threshold = config.matching.min_score / 2
    candidates = sorted(
        (item for item in scored if item.score >= threshold), key=lambda i: i.score, reverse=True
    )[: config.matching.ai_max_jobs]
    if not candidates:
        return

    total = len(candidates)
    on_progress(f"Analisando {total} vagas com IA ({AI_WORKERS} por vez)...")
    with ThreadPoolExecutor(max_workers=AI_WORKERS) as pool:
        futures = {
            pool.submit(assistant.evaluate_job, profile, resumes, item.posting): item
            for item in candidates
        }
        for done, future in enumerate(as_completed(futures), start=1):
            item = futures[future]
            if future.cancelled():
                continue
            try:
                evaluation = future.result()
            except AIUnavailableError as exc:
                # limit reached, logged out...: stop calling it, keep the local scores
                report.errors.setdefault("ia", str(exc))
                for pending in futures:
                    pending.cancel()
                on_progress(f"IA indisponível, mantendo as notas locais: {exc}")
                continue
            except Exception as exc:  # one bad answer: keep this job's local score
                report.errors.setdefault("ia", f"{type(exc).__name__}: {exc}")
            else:
                item.score = float(evaluation.score)
                item.reasons = [f"IA: {r}" for r in evaluation.reasons]
                report.ai_evaluated += 1
            on_progress(f"IA {done}/{total}: {item.posting.title[:60]}")


def _upsert_all(s: Session, scored: list[_Scored]) -> list[Job]:
    if not scored:
        return []
    now = utcnow()
    rows = [
        {
            "id": item.posting.id,
            "source": item.posting.source,
            "external_id": item.posting.external_id,
            "title": item.posting.title,
            "company": item.posting.company,
            "location": item.posting.location,
            "remote": item.posting.remote,
            "url": item.posting.url,
            "apply_url": item.posting.apply_url,
            "description": item.posting.description,
            "employment_type": item.posting.employment_type,
            "salary": item.posting.salary,
            "posted_at": item.posting.posted_at,
            "fetched_at": now,
            "fingerprint": item.posting.fingerprint,
            "score": item.score,
            "score_reasons_json": json.dumps(item.reasons, ensure_ascii=False),
            "status": JobStatus.NEW,
            "raw_json": json.dumps(item.posting.raw, ensure_ascii=False, default=str),
        }
        for item in scored
    ]
    keep = {"id", "source", "external_id", "status"}  # never overwritten on conflict
    for start in range(0, len(rows), UPSERT_BATCH):
        stmt = sqlite_insert(Job).values(rows[start : start + UPSERT_BATCH])
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={c: getattr(stmt.excluded, c) for c in rows[0] if c not in keep},
        )
        s.exec(stmt)
    s.commit()
    ids = [row["id"] for row in rows]
    return list(
        s.exec(select(Job).where(col(Job.id).in_(ids)).execution_options(populate_existing=True))
    )


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
