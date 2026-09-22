from __future__ import annotations

from collections.abc import Iterable

from candidatador.sources.base import JobPosting, JobSource, SearchQuery, parse_datetime, strip_html

API = "https://employability-portal.gupy.io/api/v1/jobs"
PAGE_SIZE = 50


class GupySource(JobSource):
    """Gupy: maior plataforma de recrutamento do Brasil (portal público de vagas)."""

    name = "gupy"
    display_name = "Gupy"
    regions = ("BR",)

    def search(self, query: SearchQuery) -> Iterable[JobPosting]:
        limit = self.max_results(query)
        terms = query.keywords or [""]
        seen: set[str] = set()
        for term in terms:
            offset = 0
            while offset < limit:
                params: dict[str, str | int] = {
                    "jobName": term,
                    "limit": min(PAGE_SIZE, limit - offset),
                    "offset": offset,
                }
                if query.remote_only:
                    params["workplaceType"] = "remote"
                if query.location and not query.remote_only:
                    params["city"] = query.location
                resp = self.client.get(API, params=params)
                resp.raise_for_status()
                data = resp.json().get("data") or []
                for item in data:
                    posting = self._parse(item)
                    if posting.external_id not in seen:
                        seen.add(posting.external_id)
                        yield posting
                if len(data) < int(params["limit"]):
                    break
                offset += len(data)

    def _parse(self, item: dict) -> JobPosting:
        location = ", ".join(p for p in (item.get("city"), item.get("state")) if p)
        workplace = (item.get("workplaceType") or "").lower()
        return JobPosting(
            source=self.name,
            external_id=str(item["id"]),
            title=item.get("name", ""),
            company=item.get("careerPageName", ""),
            location=location or item.get("country", ""),
            remote=bool(item.get("isRemoteWork")) or workplace == "remote",
            url=item.get("jobUrl", ""),
            apply_url=item.get("jobUrl", ""),
            description=strip_html(item.get("description")),
            employment_type=workplace,
            posted_at=parse_datetime(item.get("publishedDate")),
            raw=item,
        )
