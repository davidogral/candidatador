"""Command-line interface: `candidatador --help`."""

from __future__ import annotations

import os
import sys
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
from candidatador.db import session
from candidatador.documents import add_document
from candidatador.models import (
    Application,
    ApplicationStatus,
    Document,
    DocumentKind,
    Job,
    JobStatus,
)
from candidatador.pipeline import run_search
from candidatador.service import ApplyHooks, ApplyOptions, apply_to_job, record_application
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
    def ask_user(question: str, options: list[str] | None) -> str | None:
        hint = f" ({' / '.join(options)})" if options else ""
        return Prompt.ask(f"[cyan]?[/] {question}{hint}", default="") or None

    console.rule(f"{job.title} @ {job.company}")
    options = ApplyOptions(
        doc_id=doc_id,
        mode="auto" if auto else None,
        dry_run=dry_run,
        ai=ai,
        cover_letter=cover_letter,
    )
    hooks = ApplyHooks(
        confirm=lambda q: Confirm.ask(q, default=False), ask_user=ask_user, log=console.print
    )
    result = apply_to_job(s, paths, job, options, hooks)

    if result.manual_required:
        resume_path = result.resume.path if result.resume else "nenhum"
        console.print(f"Ainda não há preenchimento automático para esta vaga ({job.source}).")
        console.print(f"Abrindo {result.url} — currículo sugerido: {resume_path}")
        webbrowser.open(result.url)
        if Confirm.ask("Você concluiu a candidatura manualmente?"):
            record_application(
                s, job, result.resume, "manual", "manual", ApplicationStatus.MANUAL, {}
            )
            return ApplicationStatus.MANUAL
        return ApplicationStatus.SKIPPED

    if result.status is None:
        console.print(f"[yellow]{result.error}[/]")
        return None
    for note in result.notes:
        console.print(f"[yellow]•[/] {note}")
    if result.error:
        console.print(f"[red]Falhou:[/] {result.error}")
    console.print(
        f"Resultado: [bold]{result.status.value}[/] · {len(result.answers)} respostas registradas"
    )
    return result.status


@app.command()
def ui(
    port: Annotated[int, typer.Option(help="Porta local.")] = 8765,
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = True,
) -> None:
    """Abre a interface web local (http://127.0.0.1:8765)."""
    import threading

    import uvicorn

    from candidatador.web import create_app

    paths = _paths()
    init_home(paths)
    url = f"http://127.0.0.1:{port}"
    console.print(f"Interface disponível em [bold]{url}[/] (Ctrl+C para sair)")
    if open_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(
        create_app(paths, port=port),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        timeout_graceful_shutdown=2,
    )
    # A search may still be running in worker threads (JobSpy and the AI use thread pools,
    # which Python joins on exit, so Ctrl+C would hang for minutes). Nothing is lost by
    # stopping now: a search only writes at the very end, in one atomic transaction.
    console.print("Interface encerrada.")
    sys.stdout.flush()
    os._exit(0)


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
