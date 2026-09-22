"""Command-line interface: `candidatador --help`."""

from __future__ import annotations

import json
import time
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from sqlmodel import Session, col, select

from candidatador import __version__
from candidatador.config import Paths, init_home, load_config, load_profile
from candidatador.db import session, submitted_since
from candidatador.documents import add_document, pick_resume
from candidatador.models import (
    Application,
    ApplicationStatus,
    Document,
    DocumentKind,
    Job,
    JobStatus,
    utcnow,
)
from candidatador.pipeline import job_to_posting, run_search
from candidatador.sources import SearchQuery, available_sources

app = typer.Typer(
    help="Candidatador: organize seus documentos, encontre vagas e candidate-se.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
docs_app = typer.Typer(
    help="Gerencie currículos, cartas, certificados e cursos.", no_args_is_help=True
)
profile_app = typer.Typer(help="Veja e edite seu perfil profissional.", no_args_is_help=True)
app.add_typer(docs_app, name="docs")
app.add_typer(profile_app, name="profile")

console = Console()


def _paths() -> Paths:
    return Paths()


def _require_init(paths: Paths) -> None:
    if not paths.profile.exists():
        console.print("[yellow]Nenhum perfil encontrado. Rode primeiro:[/] candidatador init")
        raise typer.Exit(1)


# --------------------------------------------------------------------------- setup


@app.command()
def version() -> None:
    """Mostra a versão instalada."""
    console.print(f"candidatador {__version__}")


@app.command()
def init(
    force: Annotated[bool, typer.Option(help="Sobrescreve arquivos existentes.")] = False,
) -> None:
    """Cria a pasta de dados local com profile.yaml e config.yaml."""
    paths = _paths()
    written = init_home(paths, overwrite=force)
    with session(paths):
        pass  # creates the database
    console.print(f"Pasta de dados: [bold]{paths.root}[/]")
    for path in written:
        console.print(f"  criado {path.name}")
    console.print(
        "\nPróximos passos:\n"
        "  1. [bold]candidatador profile edit[/]  — preencha seu perfil\n"
        "  2. [bold]candidatador docs add curriculo.pdf --kind resume --default[/]\n"
        "  3. [bold]candidatador search -k python --remote[/]"
    )


@profile_app.command("show")
def profile_show() -> None:
    """Mostra o perfil carregado."""
    paths = _paths()
    _require_init(paths)
    console.print_json(load_profile(paths).model_dump_json())


@profile_app.command("edit")
def profile_edit() -> None:
    """Abre o profile.yaml no editor padrão."""
    paths = _paths()
    _require_init(paths)
    typer.launch(str(paths.profile))
    console.print(f"Editando {paths.profile}")


# --------------------------------------------------------------------------- documents


@docs_app.command("add")
def docs_add(
    file: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="PDF, DOCX, TXT, imagem...")
    ],
    kind: Annotated[DocumentKind, typer.Option("--kind", "-k")] = DocumentKind.RESUME,
    title: Annotated[str | None, typer.Option("--title", "-t")] = None,
    language: Annotated[str, typer.Option("--lang", help="pt, en, es...")] = "pt",
    tags: Annotated[str, typer.Option(help="Separadas por vírgula, ex.: backend,python")] = "",
    default: Annotated[bool, typer.Option("--default", help="Versão padrão deste tipo.")] = False,
    issued_by: Annotated[str, typer.Option(help="Instituição (certificados/cursos).")] = "",
    issued_at: Annotated[str, typer.Option(help="Data de emissão.")] = "",
) -> None:
    """Adiciona um documento ao cofre local."""
    paths = _paths()
    with session(paths) as s:
        doc = add_document(
            s,
            paths,
            file,
            kind=kind,
            title=title,
            language=language,
            tags=[t.strip() for t in tags.split(",") if t.strip()],
            is_default=default,
            issued_by=issued_by,
            issued_at=issued_at,
        )
    extracted = (
        f"{len(doc.text)} caracteres de texto extraídos" if doc.text else "sem texto extraído"
    )
    console.print(f"[green]✓[/] #{doc.id} {doc.title} ({doc.kind.value}) — {extracted}")


@docs_app.command("list")
def docs_list(kind: Annotated[DocumentKind | None, typer.Option("--kind", "-k")] = None) -> None:
    """Lista os documentos cadastrados."""
    with session(_paths()) as s:
        stmt = select(Document).order_by(Document.kind, col(Document.created_at).desc())
        if kind:
            stmt = stmt.where(Document.kind == kind)
        docs = list(s.exec(stmt))
    table = Table("id", "tipo", "título", "idioma", "tags", "padrão", "arquivo")
    for d in docs:
        table.add_row(
            str(d.id),
            d.kind.value,
            d.title,
            d.language,
            ", ".join(d.tags),
            "★" if d.is_default else "",
            d.original_name,
        )
    console.print(table)


@docs_app.command("remove")
def docs_remove(doc_id: int) -> None:
    """Remove um documento do cofre."""
    with session(_paths()) as s:
        doc = s.get(Document, doc_id)
        if not doc:
            raise typer.BadParameter(f"documento {doc_id} não existe")
        Path(doc.path).unlink(missing_ok=True)
        s.delete(doc)
        s.commit()
    console.print(f"Removido #{doc_id}")


# --------------------------------------------------------------------------- search


@app.command()
def sources() -> None:
    """Lista as fontes de vagas disponíveis e quais estão ativas."""
    config = load_config(_paths())
    enabled = set(config.enabled_sources())
    table = Table("fonte", "nome", "regiões", "ativa", "observação")
    for name, cls in sorted(available_sources().items()):
        table.add_row(
            name,
            cls.display_name,
            ", ".join(cls.regions),
            "[green]sim[/]" if name in enabled else "não",
            cls.terms_note or "",
        )
    console.print(table)
    console.print(
        "Ative/desative fontes em config.yaml (candidatador profile edit mostra a pasta)."
    )


@app.command()
def search(
    keyword: Annotated[
        list[str] | None, typer.Option("--keyword", "-k", help="Repita para vários.")
    ] = None,
    location: Annotated[str | None, typer.Option("--location", "-l")] = None,
    remote: Annotated[bool, typer.Option("--remote", help="Somente vagas remotas.")] = False,
    days: Annotated[
        int | None, typer.Option("--days", "-d", help="Publicadas nos últimos N dias.")
    ] = None,
    source: Annotated[
        list[str] | None, typer.Option("--source", "-s", help="Limita às fontes.")
    ] = None,
    limit: Annotated[int, typer.Option(help="Máximo de vagas por fonte.")] = 50,
    ai: Annotated[
        bool | None, typer.Option("--ai/--no-ai", help="Refina a pontuação com IA.")
    ] = None,
) -> None:
    """Busca vagas em todas as fontes ativas, filtra, pontua e salva."""
    paths = _paths()
    _require_init(paths)
    config, profile = load_config(paths), load_profile(paths)
    query = SearchQuery(
        keywords=keyword or profile.target.roles,
        location=location,
        remote_only=remote,
        posted_within_days=days,
        limit=limit,
    )
    use_ai = config.matching.use_ai if ai is None else ai
    with session(paths) as s, console.status("Buscando vagas...") as status:
        report = run_search(
            s,
            config,
            profile,
            query,
            only_sources=source,
            use_ai=use_ai,
            on_progress=lambda msg: status.update(msg),
        )

    for name, err in report.errors.items():
        console.print(f"[red]✗ {name}:[/] {err}")
    console.print(
        f"{report.fetched} vagas encontradas · {report.filtered_out} filtradas · "
        f"{report.duplicates} duplicadas · {len(report.stored)} salvas"
    )
    _print_jobs([j for j in report.stored if (j.score or 0) >= config.matching.min_score][:30])


def _print_jobs(jobs: list[Job]) -> None:
    table = Table("id", "score", "vaga", "empresa", "local", "fonte", "status")
    for j in jobs:
        where = "🌎 remoto" if j.remote else j.location
        table.add_row(
            j.id, f"{j.score or 0:.0f}", j.title, j.company, where, j.source, j.status.value
        )
    console.print(table)


@app.command()
def jobs(
    status: Annotated[JobStatus | None, typer.Option("--status")] = None,
    min_score: Annotated[float | None, typer.Option("--min-score")] = None,
    limit: Annotated[int, typer.Option()] = 50,
) -> None:
    """Lista vagas salvas, ordenadas por pontuação."""
    paths = _paths()
    threshold = load_config(paths).matching.min_score if min_score is None else min_score
    with session(paths) as s:
        stmt = select(Job).where(col(Job.score) >= threshold)
        if status:
            stmt = stmt.where(Job.status == status)
        stmt = stmt.order_by(col(Job.score).desc()).limit(limit)
        _print_jobs(list(s.exec(stmt)))


@app.command()
def show(job_id: str) -> None:
    """Mostra detalhes de uma vaga."""
    with session(_paths()) as s:
        job = s.get(Job, job_id)
        if not job:
            raise typer.BadParameter(f"vaga {job_id} não encontrada")
    reasons = "\n".join(f"• {r}" for r in job.score_reasons)
    body = (
        f"[bold]{job.company}[/] · {job.location} · {'remota' if job.remote else ''}\n"
        f"Pontuação: {job.score or 0:.0f}\n{reasons}\n\n{job.url}\n\n{job.description[:3000]}"
    )
    console.print(Panel(body, title=job.title))


@app.command()
def mark(job_id: str, status: JobStatus) -> None:
    """Marca uma vaga (shortlisted, ignored...)."""
    with session(_paths()) as s:
        job = s.get(Job, job_id)
        if not job:
            raise typer.BadParameter(f"vaga {job_id} não encontrada")
        job.status = status
        s.add(job)
        s.commit()
    console.print(f"{job_id} → {status.value}")


# --------------------------------------------------------------------------- apply


@app.command()
def apply(
    job_id: str,
    doc: Annotated[int | None, typer.Option("--doc", help="id do currículo a enviar.")] = None,
    auto: Annotated[bool, typer.Option("--auto", help="Envia sem pedir confirmação.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preenche mas não envia.")] = False,
    ai: Annotated[
        bool | None, typer.Option("--ai/--no-ai", help="Usa IA para perguntas abertas.")
    ] = None,
    cover_letter: Annotated[bool, typer.Option(help="Gera carta de apresentação com IA.")] = False,
) -> None:
    """Preenche o formulário da vaga e (com sua confirmação) envia a candidatura."""
    paths = _paths()
    _require_init(paths)
    with session(paths) as s:
        job = s.get(Job, job_id)
        if not job:
            raise typer.BadParameter(f"vaga {job_id} não encontrada")
        status = _apply_one(
            s, paths, job, doc_id=doc, auto=auto, dry_run=dry_run, ai=ai, cover_letter=cover_letter
        )
    if status == ApplicationStatus.FAILED:
        raise typer.Exit(1)


@app.command("apply-batch")
def apply_batch(
    status: Annotated[JobStatus, typer.Option("--status")] = JobStatus.SHORTLISTED,
    min_score: Annotated[float | None, typer.Option("--min-score")] = None,
    max_jobs: Annotated[
        int, typer.Option("--max", help="Máximo de candidaturas nesta rodada.")
    ] = 5,
    auto: Annotated[bool, typer.Option("--auto", help="Envia sem pedir confirmação.")] = False,
    ai: Annotated[bool | None, typer.Option("--ai/--no-ai")] = None,
) -> None:
    """Candidata-se em sequência às melhores vagas (padrão: as marcadas como shortlisted)."""
    paths = _paths()
    _require_init(paths)
    config = load_config(paths)
    threshold = config.matching.min_score if min_score is None else min_score
    with session(paths) as s:
        stmt = (
            select(Job)
            .where(Job.status == status, col(Job.score) >= threshold)
            .order_by(col(Job.score).desc())
            .limit(max_jobs)
        )
        queue = list(s.exec(stmt))
        console.print(f"{len(queue)} vagas na fila.")
        for i, job in enumerate(queue):
            result = _apply_one(s, paths, job, auto=auto, ai=ai)
            if result is None:  # daily limit reached
                break
            if i < len(queue) - 1 and result == ApplicationStatus.SUBMITTED:
                time.sleep(config.apply.delay_seconds)


def _apply_one(
    s: Session,
    paths: Paths,
    job: Job,
    *,
    doc_id: int | None = None,
    auto: bool = False,
    dry_run: bool = False,
    ai: bool | None = None,
    cover_letter: bool = False,
) -> ApplicationStatus | None:
    from candidatador.apply import AnswerProvider, ApplyContext, find_applier

    config, profile = load_config(paths), load_profile(paths)
    mode = "auto" if auto else config.apply.mode

    if not dry_run and submitted_since(s) >= config.apply.max_per_day:
        console.print(
            f"[yellow]Limite diário de {config.apply.max_per_day} candidaturas atingido.[/]"
        )
        return None

    resume = (
        s.get(Document, doc_id) if doc_id else pick_resume(s, f"{job.title}\n{job.description}")
    )
    posting = job_to_posting(job)
    url = job.apply_url or job.url
    applier_cls = find_applier(url)
    console.rule(f"{job.title} @ {job.company}")

    if applier_cls is None:
        console.print(f"Ainda não há preenchimento automático para esta vaga ({job.source}).")
        console.print(f"Abrindo {url} — currículo sugerido: {resume.path if resume else 'nenhum'}")
        webbrowser.open(url)
        if Confirm.ask("Você concluiu a candidatura manualmente?"):
            _record(s, job, resume, "manual", mode, ApplicationStatus.MANUAL, {}, "")
            return ApplicationStatus.MANUAL
        return ApplicationStatus.SKIPPED

    use_ai = config.matching.use_ai if ai is None else ai
    assistant = None
    if use_ai or cover_letter:
        from candidatador.llm import ClaudeAssistant

        assistant = ClaudeAssistant(config.ai)

    def ask_user(question: str, options: list[str] | None) -> str | None:
        hint = f" ({' / '.join(options)})" if options else ""
        return Prompt.ask(f"[cyan]?[/] {question}{hint}", default="") or None

    answers = AnswerProvider(profile, posting, resume, assistant if use_ai else None, ask_user)
    letter = (
        assistant.cover_letter(profile, resume, posting) if (cover_letter and assistant) else None
    )
    ctx = ApplyContext(
        profile=profile,
        job=posting,
        resume=resume,
        answers=answers,
        confirm=lambda q: Confirm.ask(q, default=False),
        mode=mode,
        dry_run=dry_run,
        headless=config.apply.headless and mode == "auto",
        browser_state=paths.browser_state,
        cover_letter=letter,
    )
    console.print(
        f"via {applier_cls.display_name} · modo {mode}{' · dry-run' if dry_run else ''}"
        f" · currículo: {resume.title if resume else 'nenhum'}"
    )
    try:
        outcome = applier_cls().apply(ctx)
    except Exception as exc:
        _record(
            s,
            job,
            resume,
            applier_cls.name,
            mode,
            ApplicationStatus.FAILED,
            answers.log,
            f"{type(exc).__name__}: {exc}",
        )
        console.print(f"[red]Falhou:[/] {exc}")
        return ApplicationStatus.FAILED

    _record(
        s,
        job,
        resume,
        applier_cls.name,
        mode,
        outcome.status,
        answers.log,
        outcome.error,
        "\n".join(outcome.notes),
    )
    for note in outcome.notes:
        console.print(f"[yellow]•[/] {note}")
    console.print(
        f"Resultado: [bold]{outcome.status.value}[/] · {len(answers.log)} respostas registradas"
    )
    return outcome.status


def _record(
    s: Session,
    job: Job,
    resume: Document | None,
    applier: str,
    mode: str,
    status: ApplicationStatus,
    answers: dict,
    error: str,
    notes: str = "",
) -> None:
    serialized = {q: vars(a) for q, a in answers.items()}
    s.add(
        Application(
            job_id=job.id,
            document_id=resume.id if resume else None,
            applier=applier,
            mode=mode,
            status=status,
            answers_json=json.dumps(serialized, ensure_ascii=False),
            error=error,
            notes=notes,
            submitted_at=utcnow() if status == ApplicationStatus.SUBMITTED else None,
        )
    )
    if status in (ApplicationStatus.SUBMITTED, ApplicationStatus.MANUAL):
        job.status = JobStatus.APPLIED
        s.add(job)
    s.commit()


@app.command()
def applications(limit: Annotated[int, typer.Option()] = 50) -> None:
    """Histórico das suas candidaturas."""
    with session(_paths()) as s:
        rows = s.exec(
            select(Application, Job)
            .join(Job)
            .order_by(col(Application.created_at).desc())
            .limit(limit)
        ).all()
    table = Table("quando", "vaga", "empresa", "via", "status", "notas")
    for application, job in rows:
        table.add_row(
            application.created_at.strftime("%d/%m %H:%M"),
            job.title,
            job.company,
            application.applier,
            application.status.value,
            (application.error or application.notes)[:60],
        )
    console.print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
