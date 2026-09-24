from __future__ import annotations

import httpx
import pytest
import respx

from candidatador.config import Profile, Target, load_config
from candidatador.db import session
from candidatador.matching import Filters, passes_filters
from candidatador.matching.location import accepts, where
from candidatador.pipeline import run_search
from candidatador.sources import JobPosting, SearchQuery
from candidatador.sources.gupy import GupySource


def job(title="Analista de Dados Júnior", location="Brasil", **kw) -> JobPosting:
    base = {
        "source": "t",
        "external_id": "1",
        "title": title,
        "url": "https://x",
        "location": location,
        "remote": True,
        "description": "dados",
    }
    base.update(kw)
    return JobPosting(**base)


@pytest.mark.parametrize(
    ("location", "raw", "br"),
    [
        ("Brasil", {}, True),
        ("Toledo, Paraná, Brasil", {}, True),
        ("São Paulo, SP", {}, True),
        ("Porto Alegre, RS", {}, True),
        ("Worldwide", {}, True),
        ("Northern America, LATAM, Europe, APAC", {}, True),
        ("Intermediate Backend Engineer, AMER", {}, True),
        ("Remote, United States", {}, False),
        ("Remote, Canada; Remote, US", {}, False),
        ("USA, Canada, Argentina, Mexico, Peru", {}, False),
        ("Remote - European Union", {}, False),
        ("New York, NY", {"country_code": "US"}, False),
        ("El Salvador", {}, False),
    ],
)
def test_country_detection_for_remote_jobs(location, raw, br):
    assert accepts(job(location=location, raw=raw), ["BR"], include_unknown=False) is br


def test_unknown_location_follows_include_unknown():
    remote = job(location="Remote")
    assert not where(remote).known
    assert accepts(remote, ["BR"], include_unknown=True)
    assert not accepts(remote, ["BR"], include_unknown=False)


def reason(posting, target: Target | None = None, **query) -> str:
    profile = Profile(target=target or Target())
    return passes_filters(posting, profile, SearchQuery(**query))[1]


def test_search_time_filters_and_their_reasons():
    assert reason(job(), seniority=["junior"]) == ""
    assert reason(job("Analista de Dados Sênior"), seniority=["junior"]) == "senioridade"
    assert reason(job("Analista de Dados"), seniority=["junior"]) == ""
    assert (
        reason(job("Analista de Dados"), seniority=["junior"], include_unknown_seniority=False)
        == "senioridade não informada"
    )
    assert reason(job(location="Remote, United States"), countries=["BR"]) == "país"
    assert reason(job(title="Banco de Talentos - Dados")) == "banco de talentos"
    assert reason(job(employment_type="banco_de_talentos")) == "banco de talentos"
    assert reason(job(employment_type="banco_de_talentos"), exclude_talent_pool=False) == ""
    assert (
        reason(job(employment_type="estagio"), contract_types=["clt", "pj"]) == "tipo de contrato"
    )
    assert reason(job(employment_type=""), contract_types=["clt"]) == ""  # unknown is kept
    assert (
        reason(job("Analista de Riscos"), keywords=["analista de dados"], title_must_match=True)
        == "título fora do cargo buscado"
    )


def test_query_overrides_profile_defaults():
    profile = Profile(target=Target(seniority_levels=["senior"], countries=["US"]))
    assert Filters.resolve(SearchQuery(), profile).seniority == ["senior"]
    resolved = Filters.resolve(SearchQuery(seniority=[], countries=["BR"]), profile)
    assert resolved.seniority == [] and resolved.countries == ["BR"]  # [] = any level


GUPY = "https://employability-portal.gupy.io/api/v1/jobs"


def gupy_item(i, name, country="Brasil", city="", type_="vacancy_type_effective"):
    return {
        "id": i,
        "name": name,
        "careerPageName": f"E{i}",
        "workplaceType": "remote",
        "isRemoteWork": True,
        "jobUrl": f"https://a/{i}",
        "description": "dados python",
        "country": country,
        "city": city,
        "state": "",
        "type": type_,
    }


@respx.mock
def test_gupy_country_contract_and_parallel_keywords():
    calls = []

    def reply(request):
        term = request.url.params["jobName"]
        calls.append(term)
        items = {
            "dados": [
                gupy_item(1, "Analista de Dados Jr"),
                gupy_item(2, "Analista de Dados", country="Argentina"),
            ],
            "data": [
                gupy_item(1, "Analista de Dados Jr"),  # same job again
                gupy_item(3, "Banco de talentos", type_="vacancy_type_talent_pool"),
            ],
        }[term]
        return httpx.Response(200, json={"data": items})

    respx.get(GUPY).mock(side_effect=reply)
    jobs = GupySource().search(SearchQuery(keywords=["dados", "data"]))
    assert sorted(calls) == ["dados", "data"]
    by_id = {j.external_id: j for j in jobs}
    assert set(by_id) == {"1", "2", "3"}  # merged without repeats
    assert by_id["1"].employment_type == "clt" and by_id["1"].location == "Brasil"
    assert by_id["2"].location == "Argentina"
    assert by_id["3"].employment_type == "banco_de_talentos"


def test_search_reports_why_jobs_were_discarded(paths):
    items = [
        gupy_item(1, "Analista de Dados Júnior"),
        gupy_item(2, "Analista de Dados Sênior"),
        gupy_item(3, "Analista de Dados Jr", country="Argentina"),
        gupy_item(4, "Banco de talentos Dados", type_="vacancy_type_talent_pool"),
        gupy_item(5, "Programa de Dados", type_="vacancy_type_internship"),
    ]
    profile = Profile(target=Target(contract_types=["clt", "pj"]))
    with respx.mock:
        respx.get(GUPY).mock(return_value=httpx.Response(200, json={"data": items}))
        with session(paths) as s:
            report = run_search(
                s,
                load_config(paths),
                profile,
                SearchQuery(keywords=["dados"], seniority=["junior"], countries=["BR"]),
                only_sources=["gupy"],
            )
    assert [j.external_id for j in report.stored] == ["1"]
    assert report.filtered_reasons == {
        "senioridade": 1,
        "país": 1,
        "banco de talentos": 1,
        "tipo de contrato": 1,
    }


ROLES = [
    "Analista de dados",
    "Cientista de dados",
    "Engenheiro de dados",
    "Data Analyst",
    "Machine Learning",
]


@pytest.mark.parametrize(
    ("title", "ok"),
    [
        ("ANALISTA DADOS JR", True),  # without "de"
        ("Engenheiro(a) de Dados", True),  # gender mark
        ("CAS | Engenharia de Dados - Asset", True),  # word form
        ("Ciência de Dados Jr", True),
        ("Machine Learning Engineer", True),
        ("Analista de Riscos e Controles Internos Júnior", False),
        ("Administrador de Dados Sênior", False),
        ("Engenheiro de Software", False),
        ("Scrum Master / Product Owner - Dados", False),
    ],
)
def test_title_matching_is_tolerant_but_relevant(title, ok):
    from candidatador.matching.filters import title_matches

    assert title_matches(title, ROLES) is ok


@pytest.mark.parametrize(
    ("location", "countries"),
    [
        ("Denver, CO", {"US"}),
        ("Toledo, PR", {"BR"}),
        ("Belém, PA", {"BR"}),  # city decides
        ("Pittsburgh, PA", set()),  # PA exists in both countries
    ],
)
def test_state_codes(location, countries):
    assert where(job(location=location)).countries == countries


def test_site_reported_level_is_used_when_the_title_is_silent():
    from candidatador.matching import job_seniority

    assert job_seniority("Data Analyst", {"job_level": "Entry level"}) == ["junior"]
    assert job_seniority("Data Analyst", {"job_level": "Mid-Senior level"}) == ["pleno", "senior"]
    assert job_seniority("Senior Data Analyst", {"job_level": "Entry level"}) == ["senior"]
    posting = job("Data Analyst", raw={"job_level": "Mid-Senior level"})
    assert reason(posting, seniority=["junior"]) == "senioridade"


def test_jobspy_searches_the_chosen_country_and_detects_remote(monkeypatch):
    """Runs without the jobspy/pandas extras (CI installs only [ai])."""
    import sys
    from types import SimpleNamespace

    from candidatador.sources.jobspy import JobSpySource

    rows = [
        {
            "id": "1",
            "site": "linkedin",
            "title": "Analista de Dados",
            "is_remote": False,
            "location": "São Paulo, São Paulo, Brazil",
            "job_url": "u1",
            "description": "Vaga 100% remota, trabalho remoto.",
            "job_level": "Entry level",
        },
        {
            "id": "2",
            "site": "linkedin",
            "title": "Analista de Dados",
            "is_remote": False,
            "location": "Curitiba, Paraná, Brazil",
            "job_url": "u2",
            "description": "Modelo híbrido, 3 dias no escritório.",
            "job_level": "",
        },
    ]
    seen = {}

    def fake_scrape(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(to_dict=lambda orient: rows)  # same shape as a DataFrame

    monkeypatch.setitem(sys.modules, "jobspy", SimpleNamespace(scrape_jobs=fake_scrape))
    jobs = list(JobSpySource({}).search(SearchQuery(keywords=["dados"], countries=["BR"])))
    assert seen["location"] == "Brazil" and seen["country_indeed"] == "brazil"
    assert [j.remote for j in jobs] == [True, False]
    assert jobs[0].raw["job_level"] == "Entry level"
