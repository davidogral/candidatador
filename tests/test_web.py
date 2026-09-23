from __future__ import annotations

import time

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from candidatador.apply.base import Applier, ApplyContext, ApplyOutcome
from candidatador.db import session
from candidatador.models import ApplicationStatus, Job
from candidatador.web import create_app

H = {"X-Candidatador": "1"}


@pytest.fixture
def client(paths):
    return TestClient(create_app(paths))


def add_job(paths, job_id="gupy:1", url="https://acme.gupy.io/job/1", score=80.0):
    source, ext = job_id.split(":")
    with session(paths) as s:
        s.add(
            Job(
                id=job_id,
                source=source,
                external_id=ext,
                title="Dev Python",
                company="ACME",
                url=url,
                fingerprint=job_id,
                score=score,
                description="<script>x</script>",
            )
        )
        s.commit()


def test_mutations_require_header_and_local_host(client):
    assert client.put("/api/profile", json={}).status_code == 403
    assert client.get("/api/status", headers={"Host": "evil.com"}).status_code == 403
    assert client.get("/").status_code == 200


def test_profile_and_config_roundtrip(client):
    profile = client.get("/api/profile").json()
    profile["skills"] = ["go", "rust"]
    profile["answers"]["aceita_pj"] = "Sim"
    assert client.put("/api/profile", json=profile, headers=H).status_code == 200
    assert client.get("/api/profile").json()["answers"]["aceita_pj"] == "Sim"

    config = client.get("/api/config").json()
    config["sources"]["greenhouse"] = {"enabled": True, "boards": ["acme"]}
    client.put("/api/config", json=config, headers=H)
    sources = {s["name"]: s for s in client.get("/api/sources").json()}
    assert sources["greenhouse"]["enabled"] and sources["greenhouse"]["list_setting"] == "boards"


def test_documents_crud(client):
    r = client.post(
        "/api/documents",
        headers=H,
        files={"file": ("cv.txt", b"Python Django", "text/plain")},
        data={"kind": "resume", "tags": "python, backend", "is_default": "true"},
    )
    doc = r.json()
    assert doc["tags"] == ["python", "backend"] and doc["is_default"] and doc["text_chars"] == 13
    assert client.get(f"/api/documents/{doc['id']}/file").content == b"Python Django"
    client.patch(f"/api/documents/{doc['id']}", json={"title": "Backend"}, headers=H)
    assert client.get("/api/documents").json()[0]["title"] == "Backend"
    client.delete(f"/api/documents/{doc['id']}", headers=H)
    assert client.get("/api/documents").json() == []


def test_search_and_job_filters(client, paths):
    with respx.mock:
        respx.get("https://employability-portal.gupy.io/api/v1/jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 9,
                            "name": "Desenvolvedor Backend Python Pleno",
                            "careerPageName": "ACME",
                            "isRemoteWork": True,
                            "workplaceType": "remote",
                            "jobUrl": "https://a/9",
                            "description": "Python Django PostgreSQL Docker AWS",
                        }
                    ]
                },
            )
        )
        r = client.post(
            "/api/search", json={"keywords": ["python"], "sources": ["gupy"]}, headers=H
        )
    assert r.json()["stored"] == 1
    add_job(
        paths, "greenhouse:acme-2", url="https://job-boards.greenhouse.io/acme/jobs/2", score=50
    )

    items = client.get("/api/jobs", params={"min_score": 0}).json()["items"]
    assert {j["id"] for j in items} == {"gupy:9", "greenhouse:acme-2"}
    auto = client.get("/api/jobs", params={"min_score": 0, "auto_apply": True}).json()
    assert [j["id"] for j in auto["items"]] == ["greenhouse:acme-2"]
    assert client.get("/api/jobs", params={"q": "backend", "min_score": 0}).json()["total"] == 1

    client.patch("/api/jobs/gupy:9", json={"status": "ignored"}, headers=H)
    active = client.get("/api/jobs", params={"status": "new,shortlisted", "min_score": 0}).json()
    assert [j["id"] for j in active["items"]] == ["greenhouse:acme-2"]


def test_manual_application(client, paths):
    add_job(paths)
    client.post("/api/jobs/gupy:1/manual", json={}, headers=H)
    [app] = client.get("/api/applications").json()
    assert app["status"] == "manual" and app["job"]["status"] == "applied"


class FakeApplier(Applier):
    name = "fake"
    display_name = "Fake"

    @classmethod
    def supports(cls, url: str) -> bool:
        return "fake.example" in url

    def apply(self, ctx: ApplyContext) -> ApplyOutcome:
        ctx.answers.resolve("Qual seu time do coração?")
        if not ctx.confirm("Enviar?"):
            return ApplyOutcome(ApplicationStatus.SKIPPED)
        return ApplyOutcome(ApplicationStatus.SUBMITTED, ["ok"])


def wait_for(client, sid, state):
    for _ in range(100):
        snap = client.get(f"/api/apply/{sid}").json()
        if snap["state"] == state:
            return snap
        time.sleep(0.02)
    raise AssertionError(f"session never reached {state}: {snap}")


def test_apply_session_asks_user_through_the_ui(client, paths, monkeypatch):
    monkeypatch.setattr("candidatador.service.find_applier", lambda url: FakeApplier)
    monkeypatch.setattr("candidatador.web.find_applier", lambda url: FakeApplier)
    add_job(paths, "lever:x-1", url="https://fake.example/1")

    sid = client.post("/api/jobs/lever:x-1/apply", json={"ai": False}, headers=H).json()["id"]
    assert client.post("/api/jobs/lever:x-1/apply", json={}, headers=H).status_code == 409

    snap = wait_for(client, sid, "waiting")
    assert snap["prompt"]["kind"] == "question"
    client.post(
        f"/api/apply/{sid}/respond",
        headers=H,
        json={"prompt_id": snap["prompt"]["id"], "value": "Corinthians"},
    )

    snap = wait_for(client, sid, "waiting")
    assert snap["prompt"]["kind"] == "confirm"
    client.post(
        f"/api/apply/{sid}/respond",
        headers=H,
        json={"prompt_id": snap["prompt"]["id"], "value": True},
    )

    result = wait_for(client, sid, "done")["result"]
    assert result["status"] == "submitted"
    assert result["answers"]["Qual seu time do coração?"]["origin"] == "user"
    assert client.get("/api/jobs/lever:x-1").json()["status"] == "applied"
