"""Optional AI features. The model is reached through a backend (see backends.py): the
Claude Code CLI or Codex CLI you already use, or the Anthropic API.

- evaluate_job: deeper match analysis + which resume version to send
- answer_question: answers open/closed questions found in application forms
- cover_letter: tailored cover letter for a given job

Everything here is opt-in and only sends the data needed for the task.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, Field

from candidatador.config import AIConfig, Profile
from candidatador.llm.backends import AIUnavailableError, Backend, create_backend

if TYPE_CHECKING:
    from candidatador.models import Document
    from candidatador.sources.base import JobPosting

T = TypeVar("T", bound=BaseModel)
MAX_DOC_CHARS = 20_000

SYSTEM_PROMPT = """\
Você é o assistente de candidaturas do projeto open source "candidatador". Você ajuda \
uma pessoa candidata a avaliar vagas e preencher formulários de candidatura.

Regras:
- Use apenas fatos presentes no perfil e nos documentos da pessoa. Nunca invente \
experiências, diplomas, certificações, empresas ou números.
- Se uma pergunta exigir informação que não existe no perfil, diga isso claramente \
em vez de inventar.
- Responda no idioma da vaga (português ou inglês), de forma objetiva e profissional.
"""


class JobEvaluation(BaseModel):
    score: int = Field(description="0-100: quão boa é a vaga para esta pessoa")
    should_apply: bool
    reasons: list[str] = Field(description="Até 5 motivos curtos, positivos ou negativos")
    missing_skills: list[str] = Field(description="Requisitos da vaga que a pessoa não tem")
    best_resume_id: int | None = Field(description="id do currículo mais adequado, ou null")


class FormAnswer(BaseModel):
    answer: str = Field(description="Resposta a ser enviada no formulário")
    confident: bool = Field(
        description="false se faltou informação no perfil e a pessoa deve revisar"
    )


class AIAssistant:
    def __init__(self, config: AIConfig, backend: Backend | None = None) -> None:
        self.config = config
        self.backend = backend or create_backend(config)

    # ------------------------------------------------------------------ public API

    def evaluate_job(
        self, profile: Profile, resumes: list[Document], job: JobPosting
    ) -> JobEvaluation:
        prompt = (
            f"{_profile_block(profile)}\n\n{_resumes_block(resumes)}\n\n{_job_block(job)}\n\n"
            "Avalie o quanto esta vaga combina com a pessoa (requisitos, senioridade, local, "
            "idioma, preferências) e escolha o currículo mais adequado para enviar."
        )
        return self._parse(prompt, JobEvaluation)

    def answer_question(
        self,
        profile: Profile,
        resume: Document | None,
        job: JobPosting,
        question: str,
        options: list[str] | None = None,
    ) -> FormAnswer:
        opts = ""
        if options:
            opts = "\nOpções válidas (responda exatamente uma delas):\n" + "\n".join(
                f"- {o}" for o in options
            )
        prompt = (
            f"{_profile_block(profile)}\n\n{_resumes_block([resume] if resume else [])}\n\n"
            f"{_job_block(job)}\n\nPergunta do formulário de candidatura:\n{question}{opts}"
        )
        answer = self._parse(prompt, FormAnswer)
        if self.backend.untrusted_tools:
            answer.confident = False  # always reviewed by a human (see backends.CodexCLIBackend)
        return answer

    def cover_letter(self, profile: Profile, resume: Document | None, job: JobPosting) -> str:
        prompt = (
            f"{_profile_block(profile)}\n\n{_resumes_block([resume] if resume else [])}\n\n"
            f"{_job_block(job)}\n\nEscreva uma carta de apresentação curta (até 250 palavras), "
            "específica para esta vaga. Devolva apenas o texto da carta."
        )
        return self.backend.text(SYSTEM_PROMPT, prompt)

    # ------------------------------------------------------------------ internals

    def _parse(self, prompt: str, schema: type[T]) -> T:
        return self.backend.structured(SYSTEM_PROMPT, prompt, schema)


def _profile_block(profile: Profile) -> str:
    data = profile.model_dump(exclude={"personal": {"phone", "email"}})
    return f"<perfil>\n{data}\n</perfil>"


def _resumes_block(resumes: list[Document]) -> str:
    parts = [
        f'<curriculo id="{r.id}" titulo="{r.title}" idioma="{r.language}">\n'
        f"{r.text[:MAX_DOC_CHARS]}\n</curriculo>"
        for r in resumes
    ]
    return "\n".join(parts) or "<curriculo>(nenhum currículo cadastrado)</curriculo>"


def _job_block(job: JobPosting) -> str:
    return (
        f"<vaga>\nTítulo: {job.title}\nEmpresa: {job.company}\nLocal: {job.location}\n"
        f"Remota: {job.remote}\n\n{job.description[:MAX_DOC_CHARS]}\n</vaga>"
    )


__all__ = ["AIAssistant", "AIUnavailableError", "FormAnswer", "JobEvaluation"]
