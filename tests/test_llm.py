from __future__ import annotations

from types import SimpleNamespace

import pytest

from candidatador.config import AIConfig
from candidatador.llm import AIUnavailableError, ClaudeAssistant, FormAnswer
from candidatador.sources import JobPosting

JOB = JobPosting(source="t", external_id="1", title="Dev", url="https://x", description="Python")


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def fake_client(response):
    messages = FakeMessages(response)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_answer_question_sends_schema_and_hides_contact_data(profile):
    parsed = FormAnswer(answer="Sim", confident=True)
    client, messages = fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))
    assistant = ClaudeAssistant(AIConfig(), client=client)

    result = assistant.answer_question(profile, None, JOB, "Aceita PJ?", ["Sim", "Não"])

    assert result.answer == "Sim"
    call = messages.calls[0]
    assert call["output_format"] is FormAnswer
    assert call["model"] == "claude-opus-5"
    prompt = call["messages"][0]["content"]
    assert "Aceita PJ?" in prompt and "- Não" in prompt
    assert profile.personal.email not in prompt
    assert profile.personal.phone not in prompt


def test_refusal_raises(profile):
    client, _ = fake_client(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    with pytest.raises(AIUnavailableError):
        ClaudeAssistant(AIConfig(), client=client).answer_question(profile, None, JOB, "?")
