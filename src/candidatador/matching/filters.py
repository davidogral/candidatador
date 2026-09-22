"""Hard filters: a job that fails any of them is discarded before scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from candidatador.config import Profile
from candidatador.sources.base import JobPosting, SearchQuery, matches_keywords, normalize


def passes_filters(job: JobPosting, profile: Profile, query: SearchQuery) -> tuple[bool, str]:
    """Return (ok, reason_if_rejected)."""
    target = profile.target
    text = f"{job.title}\n{job.description}"

    excluded_companies = {normalize(c) for c in target.companies_excluded}
    if normalize(job.company) in excluded_companies:
        return False, "empresa excluída"

    if target.keywords_excluded and matches_keywords(job.title, target.keywords_excluded):
        return False, "palavra-chave excluída no título"

    if target.keywords_required and not matches_keywords(text, target.keywords_required):
        return False, "sem palavras-chave obrigatórias"

    remote_only = query.remote_only or target.remote == "only"
    if remote_only and job.remote is False:
        return False, "não é remota"
    if target.remote == "no" and job.remote is True:
        return False, "é remota"

    if query.posted_within_days and job.posted_at:
        posted = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=UTC)
        if posted < datetime.now(UTC) - timedelta(days=query.posted_within_days):
            return False, "vaga antiga"

    return True, ""
