from __future__ import annotations

import json
import stat
import sys
from types import SimpleNamespace

import pytest

from candidatador.config import AIConfig
from candidatador.llm import AIAssistant, AIUnavailableError, FormAnswer, JobEvaluation
from candidatador.llm.backends import (
    AnthropicAPIBackend,
    ClaudeCLIBackend,
    CodexCLIBackend,
    create_backend,
    strict_schema,
)
from candidatador.sources import JobPosting

JOB = JobPosting(source="t", external_id="1", title="Dev", url="https://x", description="Python")


# --------------------------------------------------------------------------- API backend


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


def test_api_backend_sends_schema_and_hides_contact_data(profile):
    parsed = FormAnswer(answer="Sim", confident=True)
    client, messages = fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))
    assistant = AIAssistant(AIConfig(), backend=AnthropicAPIBackend(AIConfig(), client=client))

    result = assistant.answer_question(profile, None, JOB, "Aceita PJ?", ["Sim", "Não"])

    assert result.answer == "Sim"
    call = messages.calls[0]
    assert call["output_format"] is FormAnswer
    assert call["model"] == "claude-opus-5"
    prompt = call["messages"][0]["content"]
    assert "Aceita PJ?" in prompt and "- Não" in prompt
    assert profile.personal.email not in prompt
    assert profile.personal.phone not in prompt


def test_api_refusal_raises(profile):
    client, _ = fake_client(SimpleNamespace(stop_reason="refusal", parsed_output=None))
    backend = AnthropicAPIBackend(AIConfig(), client=client)
    with pytest.raises(AIUnavailableError):
        AIAssistant(AIConfig(), backend=backend).answer_question(profile, None, JOB, "?")


# --------------------------------------------------------------------------- CLI backends


def fake_cli(tmp_path, name: str, body: str):
    """Create an executable that records its argv/stdin and runs `body`."""
    script = tmp_path / name
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, pathlib\n"
        "stdin = sys.stdin.read()\n"
        f"pathlib.Path({str(tmp_path / 'call.json')!r}).write_text("
        "json.dumps({'argv': sys.argv[1:], 'stdin': stdin}))\n" + body
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def last_call(tmp_path) -> dict:
    return json.loads((tmp_path / "call.json").read_text())


@pytest.mark.skipif(sys.platform == "win32", reason="shebang scripts")
def test_claude_cli_runs_without_tools_and_parses_structured_output(tmp_path, profile):
    exe = fake_cli(
        tmp_path,
        "claude",
        "print(json.dumps({'is_error': False, 'result': '', "
        "'structured_output': {'answer': 'Sim', 'confident': True}}))\n",
    )
    backend = ClaudeCLIBackend(AIConfig(effort="low"), executable=str(exe))
    result = AIAssistant(AIConfig(), backend=backend).answer_question(profile, None, JOB, "PJ?")

    assert result == FormAnswer(answer="Sim", confident=True)
    call = last_call(tmp_path)
    argv = call["argv"]
    assert argv[argv.index("--tools") + 1] == ""  # every tool disabled
    assert "--strict-mcp-config" in argv and "--no-session-persistence" in argv
    assert "--model" not in argv  # empty model -> CLI default
    assert json.loads(argv[argv.index("--json-schema") + 1])["additionalProperties"] is False
    assert "PJ?" in call["stdin"]


@pytest.mark.skipif(sys.platform == "win32", reason="shebang scripts")
def test_claude_cli_error_is_reported(tmp_path, profile):
    exe = fake_cli(tmp_path, "claude", "print('not logged in', file=sys.stderr); sys.exit(1)\n")
    backend = ClaudeCLIBackend(AIConfig(), executable=str(exe))
    with pytest.raises(AIUnavailableError, match="not logged in"):
        backend.text("sys", "oi")


@pytest.mark.skipif(sys.platform == "win32", reason="shebang scripts")
def test_codex_answers_are_always_flagged_for_review(tmp_path, profile):
    exe = fake_cli(
        tmp_path,
        "codex",
        "out = sys.argv[sys.argv.index('-o') + 1]\n"
        "pathlib.Path(out).write_text(json.dumps({'answer': 'Sim', 'confident': True}))\n",
    )
    backend = CodexCLIBackend(AIConfig(model="claude-opus-5"), executable=str(exe))
    result = AIAssistant(AIConfig(), backend=backend).answer_question(profile, None, JOB, "PJ?")

    assert result.answer == "Sim" and result.confident is False
    argv = last_call(tmp_path)["argv"]
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--model" not in argv  # a Claude model name is never passed to codex


def test_strict_schema_requires_every_field():
    schema = strict_schema(JobEvaluation)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_create_backend_auto_and_unavailable(monkeypatch):
    monkeypatch.setattr(
        "candidatador.llm.backends.available_providers",
        lambda: {"claude-cli": False, "codex-cli": True, "api": False},
    )
    assert create_backend(AIConfig()).name == "codex-cli"
    with pytest.raises(AIUnavailableError):
        create_backend(AIConfig(provider="claude-cli"))
