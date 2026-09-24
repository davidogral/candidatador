from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from candidatador.sources.base import (
    JobPosting,
    JobSource,
    SearchQuery,
    SourceError,
    matches_keywords,
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

        # Without a location LinkedIn answers with US jobs; use the searched country instead.
        country = ENGLISH_COUNTRY_NAMES.get((query.countries or [""])[0], "")
        kwargs: dict[str, Any] = {
            "site_name": self.settings.get("sites") or ["linkedin", "indeed", "google"],
            "search_term": " OR ".join(query.keywords) if query.keywords else None,
            "location": query.location or country or None,
            "results_wanted": self.max_results(query),
            "country_indeed": self.settings.get("country_indeed") or country.lower() or "brazil",
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
            remote=_is_remote(row, clean),
            url=clean(row.get("job_url")),
            apply_url=clean(row.get("job_url_direct")) or clean(row.get("job_url")),
            description=clean(row.get("description")),
            employment_type=clean(row.get("job_type")),
            salary=salary.strip(),
            posted_at=parse_datetime(posted) if clean(posted) else None,
            raw={"site": site, "job_level": clean(row.get("job_level"))},
        )


#: country code -> name JobSpy/LinkedIn/Indeed understand
ENGLISH_COUNTRY_NAMES = {
    "BR": "Brazil",
    "AR": "Argentina",
    "CL": "Chile",
    "CO": "Colombia",
    "PE": "Peru",
    "UY": "Uruguay",
    "MX": "Mexico",
    "US": "USA",
    "CA": "Canada",
    "GB": "UK",
    "IE": "Ireland",
    "PT": "Portugal",
    "ES": "Spain",
    "DE": "Germany",
    "FR": "France",
    "NL": "Netherlands",
    "PL": "Poland",
    "IN": "India",
    "IL": "Israel",
}

_REMOTE_WORDS = ["remoto", "remota", "remote", "home office", "trabalho remoto", "100 remoto"]
_HYBRID_WORDS = ["hibrido", "hibrida", "hybrid", "presencial", "on site", "onsite"]


def _is_remote(row: dict[str, Any], clean: Any) -> bool:
    """LinkedIn's is_remote flag is unreliable (and its remote filter has no effect), so
    decide from the title/location/description: hybrid or on-site wording wins."""
    if str(clean(row.get("is_remote"))).lower() == "true":
        return True
    head = f"{clean(row.get('title'))} {clean(row.get('location'))}"
    text = f"{head} {clean(row.get('description'))[:3000]}"
    if matches_keywords(head, ["100 remoto", "remote", "remoto", "remota"]):
        return True
    if matches_keywords(text, _HYBRID_WORDS):
        return False
    return matches_keywords(text, _REMOTE_WORDS)
