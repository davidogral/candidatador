from __future__ import annotations

from candidatador.apply import AnswerProvider
from candidatador.sources import JobPosting

JOB = JobPosting(source="t", external_id="1", title="Dev", url="https://x")


def test_resolution_order(profile):
    asked = []
    provider = AnswerProvider(profile, JOB, ask_user=lambda q, o: asked.append(q) or "resposta")
    assert provider.resolve("First Name").value == "Seu"
    assert provider.resolve("Nome completo").value == "Seu Nome Completo"
    assert provider.resolve("Nome").value == "Seu Nome Completo"
    assert provider.resolve("E-mail").origin == "profile"
    assert provider.resolve("Current location").value == "São Paulo, SP, Brasil"
    assert provider.resolve("Qual sua pretensão salarial?").value == "R$ 10.000"
    assert provider.resolve("Are you legally authorized to work?").origin == "answers"
    assert provider.resolve("Qual seu time do coração?").origin == "user"
    assert asked == ["Qual seu time do coração?"]
    assert len(provider.log) == 8


def test_company_name_is_not_the_candidate_name(profile):
    provider = AnswerProvider(profile, JOB)
    assert provider.resolve("Nome da empresa atual") is None
