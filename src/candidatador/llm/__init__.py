"""Optional AI features powered by Claude (install with: pip install "candidatador[ai]").

- evaluate_job: deeper match analysis + which resume version to send
- answer_question: answers open/closed questions found in application forms
- cover_letter: tailored cover letter for a given job

Everything here is opt-in and only sends the data needed for the task.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from candidatador.config import AIConfig, Profile

if TYPE_CHECKING:
    from candidatador.models import Document
    from candidatador.sources.base import JobPosting

FALLBACK_BETA = "server-side-fallback-2026-07-01"
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


class AIUnavailableError(RuntimeError):
    pass


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


class ClaudeAssistant:
    def __init__(self, config: AIConfig, client: Any | None = None) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise AIUnavailableError('Instale o extra: pip install "candidatador[ai]"') from exc
            client = anthropic.Anthropic()
        self.client = client
        self.config = config

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
        return self._parse(prompt, FormAnswer)

    def cover_letter(self, profile: Profile, resume: Document | None, job: JobPosting) -> str:
        prompt = (
            f"{_profile_block(profile)}\n\n{_resumes_block([resume] if resume else [])}\n\n"
            f"{_job_block(job)}\n\nEscreva uma carta de apresentação curta (até 250 palavras), "
            "específica para esta vaga. Devolva apenas o texto da carta."
        )
        response = self.client.beta.messages.create(
            model=self.config.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.config.effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        _check_refusal(response)
        from anthropic.types.beta import BetaTextBlock

        text = "".join(b.text for b in response.content if isinstance(b, BetaTextBlock))
        return text.strip()

    # ------------------------------------------------------------------ internals

    def _parse(self, prompt: str, schema: type[BaseModel]) -> Any:
        response = self.client.beta.messages.parse(
            model=self.config.model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": self.config.effort},
            output_format=schema,
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        _check_refusal(response)
        if response.parsed_output is None:
            raise AIUnavailableError(
                f"Resposta inválida da IA (stop_reason={response.stop_reason})"
            )
        return response.parsed_output


def _check_refusal(response: Any) -> None:
    if response.stop_reason == "refusal":
        raise AIUnavailableError("A IA recusou esta solicitação.")


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
