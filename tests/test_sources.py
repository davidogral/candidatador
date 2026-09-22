from __future__ import annotations

import httpx
import respx

from candidatador.sources import SearchQuery, available_sources
from candidatador.sources.ats import AshbySource, GreenhouseSource, LeverSource
from candidatador.sources.base import matches_keywords, strip_html
from candidatador.sources.gupy import GupySource
from candidatador.sources.remotive import RemotiveSource


def test_builtin_sources_registered():
    assert {"gupy", "remotive", "greenhouse", "lever", "ashby", "jobspy"} <= set(
        available_sources()
    )


def test_helpers():
    assert strip_html("<p>Olá&nbsp;<b>mundo</b></p><p>linha 2</p>") == "Olá mundo\nlinha 2"
    assert matches_keywords("Desenvolvedor Back-end Sênior", ["senior"])
    assert not matches_keywords("Javascript developer", ["java"])


@respx.mock
def test_gupy_parses_and_paginates():
    route = respx.get("https://employability-portal.gupy.io/api/v1/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "name": "Dev Python",
                        "careerPageName": "ACME",
                        "city": "São Paulo",
                        "state": "SP",
                        "workplaceType": "remote",
                        "isRemoteWork": True,
                        "jobUrl": "https://acme.gupy.io/job/1",
                        "publishedDate": "2026-09-21T19:43:38.546Z",
                        "description": "<p>Python</p>",
                    }
                ]
            },
        )
    )
    jobs = list(GupySource().search(SearchQuery(keywords=["python"], remote_only=True)))
    assert route.calls[0].request.url.params["workplaceType"] == "remote"
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "gupy:1"
    assert job.company == "ACME"
    assert job.remote is True
    assert job.description == "Python"
    assert job.posted_at is not None


@respx.mock
def test_remotive():
    respx.get("https://remotive.com/api/remote-jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 7,
                        "url": "https://remotive.com/x",
                        "title": "Backend Engineer",
                        "company_name": "Foo",
                        "candidate_required_location": "Worldwide",
                        "publication_date": "2026-09-18T16:43:22",
                        "description": "<b>Go</b>",
                    }
                ]
            },
        )
    )
    [job] = RemotiveSource().search(SearchQuery(keywords=["backend"]))
    assert job.remote is True and job.company == "Foo" and job.description == "Go"


@respx.mock
def test_greenhouse_filters_locally_and_skips_missing_boards():
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 1,
                        "title": "Python Engineer",
                        "absolute_url": "https://gh/1",
                        "location": {"name": "Remote, Brazil"},
                        "content": "&lt;p&gt;Django&lt;/p&gt;",
                    },
                    {
                        "id": 2,
                        "title": "Account Executive",
                        "absolute_url": "https://gh/2",
                        "location": {"name": "NYC"},
                        "content": "Sales",
                    },
                ]
            },
        )
    )
    respx.get("https://boards-api.greenhouse.io/v1/boards/gone/jobs").mock(
        return_value=httpx.Response(404)
    )
    source = GreenhouseSource({"boards": ["acme", "gone"]})
    jobs = list(source.search(SearchQuery(keywords=["python"])))
    assert [j.title for j in jobs] == ["Python Engineer"]
    assert jobs[0].remote is True
    assert jobs[0].description == "Django"


@respx.mock
def test_lever_and_ashby():
    respx.get("https://api.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "abc",
                    "text": "Data Engineer",
                    "hostedUrl": "https://jobs.lever.co/acme/abc",
                    "applyUrl": "https://jobs.lever.co/acme/abc/apply",
                    "workplaceType": "remote",
                    "categories": {"location": "Brazil", "commitment": "Full-time"},
                    "descriptionPlain": "Python and SQL",
                    "createdAt": 1711403416463,
                }
            ],
        )
    )
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "x",
                        "title": "Python Dev",
                        "location": "Remote",
                        "isRemote": True,
                        "jobUrl": "https://jobs.ashbyhq.com/acme/x",
                        "applyUrl": "https://a/x/apply",
                        "descriptionPlain": "Python",
                        "isListed": True,
                    },
                    {"id": "y", "title": "Hidden Python", "isListed": False, "jobUrl": "u"},
                ]
            },
        )
    )
    [lever] = LeverSource({"companies": ["acme"]}).search(SearchQuery(keywords=["python"]))
    assert lever.remote is True and lever.posted_at.year == 2024
    [ashby] = AshbySource({"organizations": ["acme"]}).search(SearchQuery(keywords=["python"]))
    assert ashby.title == "Python Dev"


def test_parse_datetime_is_always_timezone_aware():
    from datetime import date

    from candidatador.sources.base import parse_datetime

    for value in (
        "2026-09-18T16:43:22",
        "2026-09-21T19:43:38.546Z",
        1711403416463,
        date(2026, 1, 2),
    ):
        parsed = parse_datetime(value)
        assert parsed is not None and parsed.tzinfo is not None
    assert parse_datetime("não é data") is None
