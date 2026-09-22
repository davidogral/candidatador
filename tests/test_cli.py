from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from candidatador.cli import app
from candidatador.db import session
from candidatador.models import Job

runner = CliRunner()


def test_init_docs_and_search(paths, tmp_path):
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output

    resume = tmp_path / "cv.md"
    resume.write_text("Python Django AWS", encoding="utf-8")
    result = runner.invoke(
        app, ["docs", "add", str(resume), "--kind", "resume", "--tags", "python", "--default"]
    )
    assert result.exit_code == 0, result.output
    assert "17 caracteres" in result.output
    # same file twice -> no duplicate
    runner.invoke(app, ["docs", "add", str(resume)])
    assert runner.invoke(app, ["docs", "list"]).output.count("cv.md") == 1

    with respx.mock:
        respx.get("https://employability-portal.gupy.io/api/v1/jobs").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 1,
                            "name": "Desenvolvedor Backend Python Pleno",
                            "careerPageName": "ACME",
                            "workplaceType": "remote",
                            "isRemoteWork": True,
                            "jobUrl": "https://a/1",
                            "description": "Python Django PostgreSQL Docker AWS",
                        }
                    ]
                },
            )
        )
        respx.get("https://remotive.com/api/remote-jobs").mock(return_value=httpx.Response(500))
        result = runner.invoke(app, ["search", "-k", "python"])
    assert result.exit_code == 0, result.output
    assert "remotive" in result.output  # error reported, search continues
    with session(paths) as s:
        job = s.get(Job, "gupy:1")
    assert job is not None and job.score and job.score > 50
