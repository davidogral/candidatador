from __future__ import annotations

from collections.abc import Iterable

from candidatador.sources.base import JobPosting, JobSource, SearchQuery, parse_datetime, strip_html

API = "https://employability-portal.gupy.io/api/v1/jobs"

#: Gupy "type" -> contract type used by the filters (see matching/filters.py)
CONTRACT_TYPES = {
    "vacancy_type_effective": "clt",
    "vacancy_legal_entity": "pj",
    "vacancy_type_legal_entity": "pj",
    "vacancy_type_internship": "estagio",
    "vacancy_type_apprentice": "aprendiz",
    "vacancy_type_temporary": "temporario",
    "vacancy_type_autonomous": "autonomo",
    "vacancy_type_associate": "cooperado",
    "vacancy_type_talent_pool": "banco_de_talentos",
}
PAGE_SIZE = 50


class GupySource(JobSource):
    """Gupy: maior plataforma de recrutamento do Brasil (portal público de vagas)."""

    name = "gupy"
    display_name = "Gupy"
    regions = ("BR",)

    def search(self, query: SearchQuery) -> Iterable[JobPosting]:
        limit = self.max_results(query)

        def fetch(term: str) -> list[JobPosting]:
            found: list[JobPosting] = []
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
                found.extend(self._parse(item) for item in data)
                if len(data) < int(params["limit"]):
                    break
                offset += len(data)
            return found

        return self.per_keyword(query, fetch)

    def _parse(self, item: dict) -> JobPosting:
        # country is always kept: remote Gupy jobs also come from Argentina, Chile, Mexico...
        location = ", ".join(
            p for p in (item.get("city"), item.get("state"), item.get("country")) if p
        )
        workplace = (item.get("workplaceType") or "").lower()
        return JobPosting(
            source=self.name,
            external_id=str(item["id"]),
            title=item.get("name", ""),
            company=item.get("careerPageName", ""),
            location=location,
            remote=bool(item.get("isRemoteWork")) or workplace == "remote",
            url=item.get("jobUrl", ""),
            apply_url=item.get("jobUrl", ""),
            description=strip_html(item.get("description")),
            employment_type=CONTRACT_TYPES.get(item.get("type") or "", ""),
            posted_at=parse_datetime(item.get("publishedDate")),
            raw=item,
        )
