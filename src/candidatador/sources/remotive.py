from __future__ import annotations

from collections.abc import Iterable

from candidatador.sources.base import JobPosting, JobSource, SearchQuery, parse_datetime, strip_html

API = "https://remotive.com/api/remote-jobs"


class RemotiveSource(JobSource):
    """Remotive: vagas 100% remotas (global)."""

    name = "remotive"
    display_name = "Remotive"
    regions = ("global",)
    terms_note = (
        "A API do Remotive pede atribuição e proíbe republicar vagas em outros sites. "
        "O candidatador só usa as vagas localmente e sempre mantém o link original."
    )

    def search(self, query: SearchQuery) -> Iterable[JobPosting]:
        limit = self.max_results(query)
        terms = query.keywords or [""]
        seen: set[str] = set()
        for term in terms:
            resp = self.client.get(API, params={"search": term, "limit": limit})
            resp.raise_for_status()
            for item in resp.json().get("jobs") or []:
                posting = JobPosting(
                    source=self.name,
                    external_id=str(item["id"]),
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("candidate_required_location", ""),
                    remote=True,
                    url=item.get("url", ""),
                    apply_url=item.get("url", ""),
                    description=strip_html(item.get("description")),
                    employment_type=item.get("job_type", ""),
                    salary=item.get("salary", ""),
                    posted_at=parse_datetime(item.get("publication_date")),
                    raw={k: v for k, v in item.items() if k != "description"},
                )
                if posting.external_id not in seen:
                    seen.add(posting.external_id)
                    yield posting
