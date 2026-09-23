from __future__ import annotations

import threading
import time

import httpx
import respx
from sqlmodel import select

from candidatador.config import load_config, load_profile
from candidatador.db import session
from candidatador.llm import JobEvaluation
from candidatador.matching import score_job
from candidatador.models import Job, JobStatus
from candidatador.pipeline import job_to_posting, run_search
from candidatador.sources import SearchQuery

GUPY = "https://employability-portal.gupy.io/api/v1/jobs"


class SlowAssistant:
    """Simulates CLI AI calls (seconds each) to reproduce long searches."""

    def __init__(self, *_args, **_kwargs):
        pass

    def evaluate_job(self, profile, resumes, posting):
        time.sleep(0.5)
        return JobEvaluation(
            score=70, should_apply=True, reasons=["ok"], missing_skills=[], best_resume_id=None
        )


def gupy_payload(n: int = 6) -> dict:
    return {
        "data": [
            {
                "id": i,
                "name": f"Desenvolvedor Backend Python Pleno {i}",
                "careerPageName": f"Empresa {i}",
                "isRemoteWork": True,
                "workplaceType": "remote",
                "jobUrl": f"https://a/{i}",
                "description": "Python Django PostgreSQL Docker AWS",
            }
            for i in range(n)
        ]
    }


def search_gupy(paths, profile, *, use_ai: bool = False) -> None:
    with session(paths) as s:
        run_search(
            s,
            load_config(paths),
            profile,
            SearchQuery(keywords=["python"], limit=6),
            only_sources=["gupy"],
            use_ai=use_ai,
        )


def test_two_concurrent_ai_searches_with_the_same_jobs(paths, monkeypatch):
    """Reproduces the UI bug: a second search during a slow AI search hit
    "database is locked"; two searches returning the same jobs hit UNIQUE errors."""
    monkeypatch.setattr("candidatador.llm.AIAssistant", SlowAssistant)
    profile = load_profile(paths)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            search_gupy(paths, profile, use_ai=True)
        except BaseException as exc:  # collected for the assertion
            errors.append(exc)

    with respx.mock:
        respx.get(GUPY).mock(return_value=httpx.Response(200, json=gupy_payload()))
        threads = [threading.Thread(target=worker) for _ in range(2)]
        started = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.monotonic() - started

    assert errors == []
    with session(paths) as s:
        jobs = s.exec(select(Job)).all()
    assert len(jobs) == 6
    assert all(j.score == 70 and j.score_reasons == ["IA: ok"] for j in jobs)
    # 6 jobs x 0.5 s run 4 at a time: well under the 3 s a sequential search would take
    assert elapsed < 2.5


def test_research_keeps_user_status_and_updates_score(paths):
    profile = load_profile(paths)
    with respx.mock:
        respx.get(GUPY).mock(return_value=httpx.Response(200, json=gupy_payload(1)))
        search_gupy(paths, profile)
        with session(paths) as s:
            job = s.get(Job, "gupy:0")
            job.status = JobStatus.APPLIED
            s.add(job)
            s.commit()
        profile.skills = ["python"]  # a different profile gives a different score
        search_gupy(paths, profile)

    with session(paths) as s:
        job = s.get(Job, "gupy:0")
    assert job.status == JobStatus.APPLIED
    assert job.score == score_job(job_to_posting(job), profile).score


def test_ai_unavailable_stops_further_calls_and_keeps_local_scores(paths, monkeypatch):
    from candidatador.llm import AIUnavailableError

    calls: list[str] = []

    class LimitedAssistant(SlowAssistant):
        def evaluate_job(self, profile, resumes, posting):
            calls.append(posting.id)
            time.sleep(0.05)
            raise AIUnavailableError("claude: You've hit your session limit")

    monkeypatch.setattr("candidatador.llm.AIAssistant", LimitedAssistant)
    config = load_config(paths)
    config.matching.ai_max_jobs = 50
    profile = load_profile(paths)
    with respx.mock:
        respx.get(GUPY).mock(return_value=httpx.Response(200, json=gupy_payload(30)))
        with session(paths) as s:
            report = run_search(
                s,
                config,
                profile,
                SearchQuery(keywords=["python"], limit=30),
                only_sources=["gupy"],
                use_ai=True,
            )

    assert report.errors["ia"] == "claude: You've hit your session limit"
    assert report.ai_evaluated == 0
    assert len(calls) < 30  # pending calls were cancelled
    assert len(report.stored) == 30 and all(j.score and j.score > 0 for j in report.stored)
