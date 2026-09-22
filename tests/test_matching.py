from __future__ import annotations

from datetime import UTC, datetime, timedelta

from candidatador.matching import passes_filters, score_job
from candidatador.sources import JobPosting, SearchQuery


def make_job(**kw) -> JobPosting:
    base = {
        "source": "t",
        "external_id": "1",
        "title": "Desenvolvedor Backend Pleno",
        "company": "ACME",
        "url": "https://x",
        "remote": True,
        "description": "Python, Django, PostgreSQL e Docker.",
    }
    base.update(kw)
    return JobPosting(**base)


def test_good_match_scores_high(profile):
    result = score_job(make_job(), profile)
    assert result.score >= 70
    assert any("python" in r for r in result.reasons)


def test_wrong_seniority_and_skills_scores_low(profile):
    job = make_job(title="Gerente de Vendas Sênior", description="Metas comerciais", remote=False)
    assert score_job(job, profile).score < 20


def test_filters(profile):
    query = SearchQuery()
    assert passes_filters(make_job(), profile, query)[0]
    # profile template excludes "php" in the title
    assert not passes_filters(make_job(title="Dev PHP"), profile, query)[0]
    old = make_job(posted_at=datetime.now(UTC) - timedelta(days=30))
    assert not passes_filters(old, profile, SearchQuery(posted_within_days=7))[0]
    assert not passes_filters(make_job(remote=False), profile, SearchQuery(remote_only=True))[0]


def test_fingerprint_dedupes_across_sources():
    a = make_job(source="gupy", title="Dev Backend", company="ACME S.A.")
    b = make_job(source="jobspy-linkedin", title="dev  backend", company="acme s a")
    assert a.fingerprint == b.fingerprint and a.id != b.id
