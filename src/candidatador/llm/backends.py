"""Ways of reaching a model. Every backend offers the same two calls:

- structured(system, prompt, schema) -> instance of the pydantic schema
- text(system, prompt) -> str

Backends:
- claude-cli: the Claude Code CLI (`claude -p`), using your existing login/subscription.
  Runs with every tool disabled and no MCP servers, so job text can't make it act.
- codex-cli: the OpenAI Codex CLI (`codex exec`), read-only sandbox in an empty folder.
  Codex can't have its shell fully disabled, so its form answers are always flagged for review.
- api: the Anthropic API via the official SDK (needs ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from candidatador.config import AIConfig

T = TypeVar("T", bound=BaseModel)

CLI_TIMEOUT_SECONDS = 300
FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_API_MODEL = "claude-opus-5"


class AIUnavailableError(RuntimeError):
    pass


class Backend(Protocol):
    name: str
    #: True when the backend can't be fully isolated from tools (answers need human review)
    untrusted_tools: bool

    def structured(self, system: str, prompt: str, schema: type[T]) -> T: ...

    def text(self, system: str, prompt: str) -> str: ...


def strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with additionalProperties=false and every property required (CLIs want it)."""

    def fix(node: Any) -> Any:
        if isinstance(node, dict):
            node = {k: fix(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            return node
        if isinstance(node, list):
            return [fix(v) for v in node]
        return node

    return dict(fix(copy.deepcopy(schema.model_json_schema())))


def _run(cmd: list[str], stdin: str, cwd: str | None = None) -> str:
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_SECONDS,
            cwd=cwd,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise AIUnavailableError(f"Comando não encontrado: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AIUnavailableError(f"{cmd[0]} demorou mais de {CLI_TIMEOUT_SECONDS}s") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()[-500:]
        raise AIUnavailableError(f"{cmd[0]} falhou (código {proc.returncode}): {detail}")
    return proc.stdout


# --------------------------------------------------------------------------- Claude Code CLI


class ClaudeCLIBackend:
    name = "claude-cli"
    untrusted_tools = False

    def __init__(self, config: AIConfig, executable: str = "claude") -> None:
        self.config = config
        self.executable = executable

    def _cmd(self, system: str, extra: list[str]) -> list[str]:
        cmd = [
            self.executable,
            "-p",
            "--output-format",
            "json",
            "--tools",
            "",  # no tools at all: job descriptions are untrusted input
            "--strict-mcp-config",  # ...and no MCP servers/connectors
            "--no-session-persistence",
            "--system-prompt",
            system,
            "--effort",
            self.config.effort,
            *extra,
        ]
        if self.config.model:
            cmd += ["--model", self.config.model]
        return cmd

    def _call(self, system: str, prompt: str, extra: list[str]) -> dict[str, Any]:
        # Empty working dir so no project CLAUDE.md or settings leak into the prompt.
        with tempfile.TemporaryDirectory() as cwd:
            out = _run(self._cmd(system, extra), prompt, cwd=cwd)
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            raise AIUnavailableError(f"Saída inesperada do claude: {out[:300]}") from exc
        if data.get("is_error"):
            raise AIUnavailableError(f"claude retornou erro: {data.get('result', '')[:300]}")
        return dict(data)

    def structured(self, system: str, prompt: str, schema: type[T]) -> T:
        data = self._call(system, prompt, ["--json-schema", json.dumps(strict_schema(schema))])
        payload = data.get("structured_output")
        if payload is None:  # older CLIs: JSON comes back as text
            payload = json.loads(data.get("result") or "null")
        return schema.model_validate(payload)

    def text(self, system: str, prompt: str) -> str:
        return str(self._call(system, prompt, []).get("result", "")).strip()


# --------------------------------------------------------------------------- Codex CLI


class CodexCLIBackend:
    name = "codex-cli"
    untrusted_tools = True

    def __init__(self, config: AIConfig, executable: str = "codex") -> None:
        self.config = config
        self.executable = executable

    def _exec(self, system: str, prompt: str, schema: dict[str, Any] | None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "out.txt"
            cmd = [
                self.executable,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "-C",
                tmp,
                "-o",
                str(out_file),
                "-c",
                f"model_reasoning_effort={self.config.effort}",
            ]
            model = self.config.model
            if model and not model.startswith("claude"):
                cmd += ["--model", model]
            if schema is not None:
                schema_file = Path(tmp) / "schema.json"
                schema_file.write_text(json.dumps(schema), encoding="utf-8")
                cmd += ["--output-schema", str(schema_file)]
            instructions = (
                f"{system}\n\nNão execute comandos nem leia arquivos: responda só com base no "
                f"texto abaixo.\n\n{prompt}"
            )
            _run([*cmd, "-"], instructions, cwd=tmp)
            return out_file.read_text(encoding="utf-8").strip()

    def structured(self, system: str, prompt: str, schema: type[T]) -> T:
        raw = self._exec(system, prompt, strict_schema(schema))
        try:
            return schema.model_validate_json(raw)
        except ValueError as exc:
            raise AIUnavailableError(f"Resposta inválida do codex: {raw[:300]}") from exc

    def text(self, system: str, prompt: str) -> str:
        return self._exec(system, prompt, None)


# --------------------------------------------------------------------------- Anthropic API


class AnthropicAPIBackend:
    name = "api"
    untrusted_tools = False

    def __init__(self, config: AIConfig, client: Any | None = None) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise AIUnavailableError('Instale o extra: pip install "candidatador[ai]"') from exc
            client = anthropic.Anthropic()
        self.client = client
        self.config = config
        self.model = config.model or DEFAULT_API_MODEL

    def structured(self, system: str, prompt: str, schema: type[T]) -> T:
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.config.effort},
            output_format=schema,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        _check_refusal(response)
        if response.parsed_output is None:
            reason = response.stop_reason
            raise AIUnavailableError(f"Resposta inválida da IA (stop_reason={reason})")
        parsed: T = response.parsed_output
        return parsed

    def text(self, system: str, prompt: str) -> str:
        from anthropic.types.beta import BetaTextBlock

        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.config.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        _check_refusal(response)
        return "".join(b.text for b in response.content if isinstance(b, BetaTextBlock)).strip()


def _check_refusal(response: Any) -> None:
    if response.stop_reason == "refusal":
        raise AIUnavailableError("A IA recusou esta solicitação.")


# --------------------------------------------------------------------------- selection


def available_providers() -> dict[str, bool]:
    import importlib.util
    import os

    return {
        "claude-cli": shutil.which("claude") is not None,
        "codex-cli": shutil.which("codex") is not None,
        "api": importlib.util.find_spec("anthropic") is not None
        and bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


def resolve_provider(config: AIConfig) -> str | None:
    """'auto' picks the first available: claude-cli, codex-cli, api."""
    available = available_providers()
    if config.provider != "auto":
        return config.provider if available.get(config.provider) else None
    return next((name for name, ok in available.items() if ok), None)


def create_backend(config: AIConfig) -> Backend:
    provider = resolve_provider(config)
    if provider == "claude-cli":
        return ClaudeCLIBackend(config)
    if provider == "codex-cli":
        return CodexCLIBackend(config)
    if provider == "api":
        return AnthropicAPIBackend(config)
    wanted = "nenhum provedor" if config.provider == "auto" else config.provider
    raise AIUnavailableError(
        f"IA indisponível ({wanted}). Instale o Claude Code (`claude`) ou o Codex (`codex`) e faça "
        "login, ou defina ANTHROPIC_API_KEY com o extra [ai]."
    )
