from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from candidatador.sources.base import (
    JobPosting,
    JobSource,
    SearchQuery,
    SourceError,
    parse_datetime,
)


class JobSpySource(JobSource):
    """LinkedIn, Indeed, Glassdoor, Google Jobs e ZipRecruiter via python-jobspy.

    Esses sites não oferecem API pública; a coleta é feita por scraping, o que pode
    violar os termos de uso deles e gerar bloqueios. Desativado por padrão.
    """

    name = "jobspy"
    display_name = "LinkedIn / Indeed / Glassdoor / Google (JobSpy)"
    regions = ("global", "BR")
    terms_note = (
        "LinkedIn, Indeed e Glassdoor proíbem coleta automatizada nos termos de uso. "
        "Use por sua conta e risco, com volumes baixos. Veja docs/uso-responsavel.md."
    )

    def search(self, query: SearchQuery) -> Iterable[JobPosting]:
        try:
            from jobspy import scrape_jobs
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise SourceError('Instale o extra: pip install "candidatador[jobspy]"') from exc

        kwargs: dict[str, Any] = {
            "site_name": self.settings.get("sites") or ["linkedin", "indeed", "google"],
            "search_term": " OR ".join(query.keywords) if query.keywords else None,
            "location": query.location,
            "results_wanted": self.max_results(query),
            "country_indeed": self.settings.get("country_indeed", "brazil"),
            "is_remote": query.remote_only,
            "linkedin_fetch_description": True,
        }
        if query.posted_within_days:
            kwargs["hours_old"] = query.posted_within_days * 24

        frame = scrape_jobs(**kwargs)
        for row in frame.to_dict(orient="records"):
            yield self._parse(row)

    def _parse(self, row: dict[str, Any]) -> JobPosting:
        def clean(value: Any) -> str:
            return "" if value is None or value != value else str(value)  # NaN != NaN

        site = clean(row.get("site")) or "jobspy"
        salary = ""
        if clean(row.get("min_amount")) or clean(row.get("max_amount")):
            salary = f"{clean(row.get('min_amount'))}-{clean(row.get('max_amount'))} "
            salary += f"{clean(row.get('currency'))}/{clean(row.get('interval'))}"
        posted = row.get("date_posted")
        return JobPosting(
            source=f"{self.name}-{site}",
            external_id=clean(row.get("id")) or clean(row.get("job_url")),
            title=clean(row.get("title")),
            company=clean(row.get("company")),
            location=clean(row.get("location")),
            remote=bool(row["is_remote"]) if clean(row.get("is_remote")) else None,
            url=clean(row.get("job_url")),
            apply_url=clean(row.get("job_url_direct")) or clean(row.get("job_url")),
            description=clean(row.get("description")),
            employment_type=clean(row.get("job_type")),
            salary=salary.strip(),
            posted_at=parse_datetime(posted) if clean(posted) else None,
            raw={"site": site},
        )
