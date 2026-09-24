from __future__ import annotations

import pytest

from candidatador.apply import AnswerProvider, ApplyContext
from candidatador.config import PersonalInfo, Profile
from candidatador.db import session
from candidatador.documents import add_document, pick_resume
from candidatador.matching import detect_seniority, score_job
from candidatador.models import Document, DocumentKind
from candidatador.sources import JobPosting


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Analista de Dados Sênior - RevOps | Remoto", ["senior"]),
        ("Desenvolvedor Pleno/Sênior", ["pleno", "senior"]),
        ("Data Scientist II", ["pleno"]),
        ("Engenheiro(a) de Machine Learning Júnior", ["junior"]),
        ("Analista de Dados SR", ["senior"]),
        ("Analista de BI PL", ["pleno"]),
        ("Data Engineer I", ["junior"]),
        ("Analista de Domínio III (Diretoria de Dados)", ["senior"]),
        ("Estágio em Dados", ["estagio"]),
        ("Programa Trainee de Dados", ["estagio"]),
        ("Tech Lead de Dados", ["lideranca"]),
        ("Head of Data", ["lideranca"]),
        ("Mid-level Data Analyst", ["pleno"]),
        ("CAS | Cientista de Dados - Foco em Crédito", []),
        ("Machine Learning Engineer (PLN)", []),  # PLN is NLP, not "pleno"
        ("Especialista I em Dados Financeiros - Crédito PJ", ["especialista"]),
        ("[Ambev Tech] Gerente de Dados I", ["lideranca"]),
    ],
)
def test_detect_seniority(title, expected):
    assert detect_seniority(title) == expected


def job(title="Analista de Dados", description="") -> JobPosting:
    return JobPosting(
        source="t",
        external_id="1",
        title=title,
        url="https://x",
        description=description,
        remote=True,
    )


def test_long_skill_lists_are_not_penalized_and_variants_count_once():
    many = [f"skill{i}" for i in range(30)] + [
        "Python",
        "SQL",
        "pandas",
        "Power BI",
        "PowerBI",
        "Airflow",
        "Databricks",
    ]
    profile = Profile(skills=many)
    posting = job(description="Python, SQL, pandas, Power BI, Airflow e Databricks.")
    result = score_job(posting, profile)
    assert "habilidades: Python, SQL, pandas, Power BI, Airflow, Databricks" in result.reasons
    assert result.score >= 40  # all 40 skill points with 6 matches
    assert "PowerBI" not in result.missing_skills  # variant of an already counted skill


def test_seniority_score_uses_detection():
    profile = Profile(seniority="junior")
    assert "senioridade júnior" in score_job(job("Analista de Dados Jr"), profile).reasons
    assert any("diferente" in r for r in score_job(job("Analista de Dados III"), profile).reasons)


def test_pick_resume_matches_whole_words(paths, tmp_path):
    def add(name, tags):
        f = tmp_path / name
        f.write_text(name)
        with session(paths) as s:
            add_document(s, paths, f, kind=DocumentKind.RESUME, title=name, tags=tags)

    add("bi.txt", ["bi", "power bi"])
    add("eng.txt", ["engenharia de dados", "airflow"])
    text = "Engenheiro de Dados. Ambiente com Airflow e muitas habilidades."
    with session(paths) as s:
        assert pick_resume(s, text).title == "eng.txt"  # "bi" must not match "ambiente"
        add("ml.txt", ["machine learning", "python", "sql"])
        bi_job = "Analista de BI Sênior\nPython, SQL, machine learning, modelos e Power BI."
        assert pick_resume(s, bi_job).title == "bi.txt"  # the title outweighs the description


def test_resume_is_uploaded_with_a_friendly_name():
    resume = Document(
        kind=DocumentKind.RESUME,
        title="cv",
        path="/vault/resume/3fa2b1c9d4e5.pdf",
        original_name="davi_analise.pdf",
        sha256="x",
    )
    profile = Profile(personal=PersonalInfo(full_name="Davi Specia"))
    posting = JobPosting(
        source="t", external_id="1", title="Dev", url="https://x", company="Banco Ágil S.A."
    )
    ctx = ApplyContext(
        profile=profile,
        job=posting,
        resume=resume,
        answers=AnswerProvider(profile, posting),
        confirm=lambda _q: True,
    )
    assert ctx.resume_upload_name() == "davi-specia-banco-agil-s-a.pdf"
