"""Public job-board APIs from ATSs used by thousands of companies.

These APIs list *all* jobs of a given company, so the user configures which companies
to follow and keyword filtering happens locally.
"""

from __future__ import annotations

from collections.abc import Iterable

import httpx

from candidatador.sources.base import (
    JobPosting,
    JobSource,
    SearchQuery,
    matches_keywords,
    parse_datetime,
    strip_html,
)


class _CompanyBoardSource(JobSource):
    settings_key: str

    def companies(self) -> list[str]:
        return [str(c) for c in self.settings.get(self.settings_key) or []]

    def search(self, query: SearchQuery) -> Iterable[JobPosting]:
        for company in self.companies():
            try:
                postings = list(self.fetch_company(company))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    continue  # company slug no longer exists; don't fail the whole run
                raise
            for posting in postings:
                if query.remote_only and posting.remote is False:
                    continue
                if matches_keywords(f"{posting.title}\n{posting.description}", query.keywords):
                    yield posting

    def fetch_company(self, company: str) -> Iterable[JobPosting]:
        raise NotImplementedError


class GreenhouseSource(_CompanyBoardSource):
    name = "greenhouse"
    display_name = "Greenhouse"
    settings_key = "boards"

    def fetch_company(self, company: str) -> Iterable[JobPosting]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
        resp = self.client.get(url, params={"content": "true"})
        resp.raise_for_status()
        for item in resp.json().get("jobs") or []:
            location = (item.get("location") or {}).get("name", "")
            yield JobPosting(
                source=self.name,
                external_id=f"{company}-{item['id']}",
                title=item.get("title", ""),
                company=item.get("company_name") or company,
                location=location,
                remote="remote" in location.lower() or None,
                url=item.get("absolute_url", ""),
                apply_url=item.get("absolute_url", ""),
                description=strip_html(item.get("content")),
                posted_at=parse_datetime(item.get("first_published") or item.get("updated_at")),
                raw={"board": company, "id": item["id"]},
            )


class LeverSource(_CompanyBoardSource):
    name = "lever"
    display_name = "Lever"
    settings_key = "companies"

    def fetch_company(self, company: str) -> Iterable[JobPosting]:
        resp = self.client.get(
            f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"}
        )
        resp.raise_for_status()
        for item in resp.json() or []:
            cats = item.get("categories") or {}
            workplace = (item.get("workplaceType") or "").lower()
            yield JobPosting(
                source=self.name,
                external_id=f"{company}-{item['id']}",
                title=item.get("text", ""),
                company=company,
                location=cats.get("location", ""),
                remote=workplace == "remote" if workplace else None,
                url=item.get("hostedUrl", ""),
                apply_url=item.get("applyUrl", ""),
                description=item.get("descriptionPlain") or strip_html(item.get("description")),
                employment_type=cats.get("commitment", ""),
                posted_at=parse_datetime(item.get("createdAt")),
                raw={"company": company, "id": item["id"], "country_code": item.get("country")},
            )


class AshbySource(_CompanyBoardSource):
    name = "ashby"
    display_name = "Ashby"
    settings_key = "organizations"

    def fetch_company(self, company: str) -> Iterable[JobPosting]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
        resp = self.client.get(url, params={"includeCompensation": "true"})
        resp.raise_for_status()
        for item in resp.json().get("jobs") or []:
            if item.get("isListed") is False:
                continue
            comp = (item.get("compensation") or {}).get("compensationTierSummary", "")
            yield JobPosting(
                source=self.name,
                external_id=f"{company}-{item['id']}",
                title=item.get("title", ""),
                company=company,
                location=item.get("location", ""),
                remote=item.get("isRemote"),
                url=item.get("jobUrl", ""),
                apply_url=item.get("applyUrl", ""),
                description=item.get("descriptionPlain") or strip_html(item.get("descriptionHtml")),
                employment_type=item.get("employmentType", ""),
                salary=comp or "",
                posted_at=parse_datetime(item.get("publishedAt")),
                raw={
                    "organization": company,
                    "id": item["id"],
                    "country_code": _ashby_country(item),
                    "candidate_required_location": "; ".join(
                        loc.get("location", "") for loc in item.get("secondaryLocations") or []
                    ),
                },
            )


def _ashby_country(item: dict) -> str:
    """Ashby gives a country *name* in the postal address; map it to an ISO code."""
    from candidatador.matching.location import COUNTRIES
    from candidatador.sources.base import normalize

    name = normalize(
        ((item.get("address") or {}).get("postalAddress") or {}).get("addressCountry") or ""
    )
    return next((c.code for c in COUNTRIES.values() if name and name in c.terms), "")
