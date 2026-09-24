"""Local web UI: `candidatador ui`.

A small FastAPI app bound to 127.0.0.1 that exposes every CLI feature to a single-page
front-end (static/index.html, no build step). Applications run in a worker thread; when
the applier needs the user (a question or the final "submit?" confirmation) the session
pauses and the page shows the prompt.
"""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlmodel import col, select

from candidatador import __version__
from candidatador.apply import find_applier
from candidatador.config import Config, Paths, Profile, init_home, load_config, load_profile
from candidatador.db import session, submitted_since
from candidatador.documents import add_document
from candidatador.llm.backends import available_providers, resolve_provider
from candidatador.matching import detect_seniority
from candidatador.models import (
    Application,
    ApplicationStatus,
    Document,
    DocumentKind,
    Job,
    JobStatus,
)
from candidatador.pipeline import run_search
from candidatador.service import ApplyHooks, ApplyOptions, ApplyResult, apply_to_job
from candidatador.service import record_application as _record
from candidatador.sources import SearchQuery, available_sources

STATIC = Path(__file__).parent / "static"
PROMPT_TIMEOUT_SECONDS = 15 * 60
CSRF_HEADER = "x-candidatador"


# --------------------------------------------------------------------------- apply sessions


class ApplySession:
    """One application running in a background thread, possibly waiting for the user."""

    def __init__(self, job_id: str) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.job_id = job_id
        self.state: Literal["running", "waiting", "done"] = "running"
        self.log: list[str] = []
        self.prompt: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self._answer: Any = None
        self._event = threading.Event()
        self._lock = threading.Lock()

    def add_log(self, message: str) -> None:
        with self._lock:
            self.log.append(str(message))

    def ask(self, kind: str, text: str, options: list[str] | None = None) -> Any:
        with self._lock:
            self._event.clear()
            self._answer = None
            self.prompt = {
                "id": uuid.uuid4().hex[:8],
                "kind": kind,
                "text": text,
                "options": options,
            }
            self.state = "waiting"
        answered = self._event.wait(PROMPT_TIMEOUT_SECONDS)
        with self._lock:
            value = self._answer if answered else None
            self.prompt = None
            self.state = "running"
        return value

    def respond(self, prompt_id: str, value: Any) -> bool:
        with self._lock:
            if not self.prompt or self.prompt["id"] != prompt_id:
                return False
            self._answer = value
        self._event.set()
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "job_id": self.job_id,
                "state": self.state,
                "log": list(self.log),
                "prompt": self.prompt,
                "result": self.result,
            }


class SearchTask:
    """A search running in a background thread, with progress messages for the page."""

    def __init__(self) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.state: Literal["running", "done"] = "running"
        self.log: list[str] = []
        self.result: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def add_log(self, message: str) -> None:
        with self._lock:
            self.log.append(str(message))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id,
                "state": self.state,
                "log": list(self.log),
                "result": self.result,
            }


# --------------------------------------------------------------------------- request bodies


class SearchBody(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    location: str | None = None
    remote: bool = False
    days: int | None = None
    sources: list[str] | None = None
    limit: int = 50
    ai: bool | None = None


class ApplyBody(BaseModel):
    doc_id: int | None = None
    mode: Literal["review", "auto"] | None = None
    dry_run: bool = False
    ai: bool | None = None
    cover_letter: bool = False


class StatusBody(BaseModel):
    status: JobStatus


class RespondBody(BaseModel):
    prompt_id: str
    value: Any = None


class ManualBody(BaseModel):
    doc_id: int | None = None
    notes: str = ""


class DocumentPatch(BaseModel):
    title: str | None = None
    language: str | None = None
    tags: list[str] | None = None
    is_default: bool | None = None


# --------------------------------------------------------------------------- serializers


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


def job_dict(job: Job, *, full: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": job.id,
        "source": job.source,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "url": job.url,
        "apply_url": job.apply_url,
        "employment_type": job.employment_type,
        "salary": job.salary,
        "posted_at": _iso(job.posted_at),
        "fetched_at": _iso(job.fetched_at),
        "score": job.score,
        "score_reasons": job.score_reasons,
        "status": job.status.value,
        "auto_apply": find_applier(job.apply_url or job.url) is not None,
        "seniority": detect_seniority(job.title),
    }
    if full:
        data["description"] = job.description
    return data


def document_dict(doc: Document) -> dict[str, Any]:
    return {
        "id": doc.id,
        "kind": doc.kind.value,
        "title": doc.title,
        "language": doc.language,
        "tags": doc.tags,
        "original_name": doc.original_name,
        "is_default": doc.is_default,
        "issued_by": doc.issued_by,
        "issued_at": doc.issued_at,
        "text_chars": len(doc.text),
        "created_at": _iso(doc.created_at),
    }


def result_dict(result: ApplyResult) -> dict[str, Any]:
    return {
        "status": result.status.value if result.status else None,
        "applier": result.applier,
        "url": result.url,
        "resume": document_dict(result.resume) if result.resume else None,
        "notes": result.notes,
        "error": result.error,
        "manual_required": result.manual_required,
        "answers": {q: vars(a) for q, a in result.answers.items()},
    }


# --------------------------------------------------------------------------- app


def create_app(paths: Paths | None = None, *, port: int = 8765) -> FastAPI:
    paths = paths or Paths()
    init_home(paths)
    app = FastAPI(title="Candidatador", version=__version__, docs_url="/api/docs")
    sessions: dict[str, ApplySession] = {}
    searches: dict[str, SearchTask] = {}
    searches_lock = threading.Lock()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", "testserver"}

    @app.middleware("http")
    async def local_only(request: Request, call_next: Any) -> Response:
        # Blocks DNS-rebinding (Host) and cross-site requests from other pages (custom header
        # forces a CORS preflight, which this server never approves).
        if request.headers.get("host") not in allowed_hosts:
            return JSONResponse({"detail": "host não permitido"}, status_code=403)
        if request.method not in ("GET", "HEAD") and request.headers.get(CSRF_HEADER) != "1":
            return JSONResponse({"detail": "cabeçalho ausente"}, status_code=403)
        response: Response = await call_next(request)
        return response

    # ------------------------------------------------------------------ page

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------------ status

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        config = load_config(paths)
        with session(paths) as s:
            counts = dict(s.exec(select(Job.status, func.count()).group_by(Job.status)).all())
            applied_today = submitted_since(s)
        return {
            "version": __version__,
            "data_dir": str(paths.root),
            "ai_providers": available_providers(),
            "ai_provider": resolve_provider(config.ai),
            "playwright_installed": importlib.util.find_spec("playwright") is not None,
            "jobspy_installed": importlib.util.find_spec("jobspy") is not None,
            "applied_today": applied_today,
            "max_per_day": config.apply.max_per_day,
            "jobs": {s.value: counts.get(s, 0) for s in JobStatus},
            "busy": any(sess.state != "done" for sess in sessions.values()),
            "search_running": next((t.id for t in searches.values() if t.state != "done"), None),
        }

    # ------------------------------------------------------------------ profile & config

    @app.get("/api/profile")
    def get_profile() -> dict[str, Any]:
        return load_profile(paths).model_dump()

    @app.put("/api/profile")
    def put_profile(profile: Profile) -> dict[str, Any]:
        _write_yaml(paths.profile, profile.model_dump())
        return profile.model_dump()

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return load_config(paths).model_dump()

    @app.put("/api/config")
    def put_config(config: Config) -> dict[str, Any]:
        _write_yaml(paths.config, config.model_dump())
        return config.model_dump()

    @app.get("/api/sources")
    def get_sources() -> list[dict[str, Any]]:
        config = load_config(paths)
        return [
            {
                "name": name,
                "display_name": cls.display_name,
                "regions": list(cls.regions),
                "terms_note": cls.terms_note,
                "list_setting": getattr(cls, "settings_key", None),
                "settings": config.source_settings(name),
                "enabled": bool(config.source_settings(name).get("enabled")),
            }
            for name, cls in sorted(available_sources().items())
        ]

    # ------------------------------------------------------------------ documents

    @app.get("/api/documents")
    def list_documents() -> list[dict[str, Any]]:
        with session(paths) as s:
            stmt = select(Document).order_by(Document.kind, col(Document.created_at).desc())
            return [document_dict(d) for d in s.exec(stmt)]

    @app.post("/api/documents")
    async def upload_document(
        file: UploadFile = File(...),
        kind: DocumentKind = Form(DocumentKind.RESUME),
        title: str = Form(""),
        language: str = Form("pt"),
        tags: str = Form(""),
        is_default: bool = Form(False),
        issued_by: str = Form(""),
        issued_at: str = Form(""),
    ) -> dict[str, Any]:
        name = Path(file.filename or "documento").name
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / name
            with target.open("wb") as out:
                shutil.copyfileobj(file.file, out)
            with session(paths) as s:
                doc = add_document(
                    s,
                    paths,
                    target,
                    kind=kind,
                    title=title or None,
                    language=language,
                    tags=[t.strip() for t in tags.split(",") if t.strip()],
                    is_default=is_default,
                    issued_by=issued_by,
                    issued_at=issued_at,
                )
                return document_dict(doc)

    @app.patch("/api/documents/{doc_id}")
    def patch_document(doc_id: int, body: DocumentPatch) -> dict[str, Any]:
        import json

        with session(paths) as s:
            doc = _get_or_404(s, Document, doc_id)
            if body.title is not None:
                doc.title = body.title
            if body.language is not None:
                doc.language = body.language
            if body.tags is not None:
                doc.tags_json = json.dumps(body.tags, ensure_ascii=False)
            if body.is_default:
                for other in s.exec(select(Document).where(Document.kind == doc.kind)):
                    other.is_default = False
                    s.add(other)
                doc.is_default = True
            elif body.is_default is False:
                doc.is_default = False
            s.add(doc)
            s.commit()
            s.refresh(doc)
            return document_dict(doc)

    @app.delete("/api/documents/{doc_id}")
    def delete_document(doc_id: int) -> dict[str, bool]:
        with session(paths) as s:
            doc = _get_or_404(s, Document, doc_id)
            Path(doc.path).unlink(missing_ok=True)
            s.delete(doc)
            s.commit()
        return {"ok": True}

    @app.get("/api/documents/{doc_id}/file")
    def document_file(doc_id: int) -> FileResponse:
        with session(paths) as s:
            doc = _get_or_404(s, Document, doc_id)
        return FileResponse(doc.path, filename=doc.original_name)

    # ------------------------------------------------------------------ search & jobs

    @app.post("/api/search")
    def start_search(body: SearchBody) -> dict[str, Any]:
        """Starts a search in the background; poll GET /api/search/{id} for progress."""
        with searches_lock:
            if any(t.state != "done" for t in searches.values()):
                raise HTTPException(409, "Já existe uma busca em andamento.")
            task = SearchTask()
            searches[task.id] = task

        config, profile = load_config(paths), load_profile(paths)
        query = SearchQuery(
            keywords=[k for k in body.keywords if k.strip()] or profile.target.roles,
            location=body.location or None,
            remote_only=body.remote,
            posted_within_days=body.days,
            limit=body.limit,
        )
        use_ai = config.matching.use_ai if body.ai is None else body.ai

        def worker() -> None:
            try:
                with session(paths) as s:
                    report = run_search(
                        s,
                        config,
                        profile,
                        query,
                        only_sources=body.sources or None,
                        use_ai=use_ai,
                        on_progress=task.add_log,
                    )
                task.result = {
                    "fetched": report.fetched,
                    "filtered_out": report.filtered_out,
                    "duplicates": report.duplicates,
                    "ai_evaluated": report.ai_evaluated,
                    "stored": len(report.stored),
                    "errors": report.errors,
                }
            except Exception as exc:
                task.result = {"error": f"{type(exc).__name__}: {exc}"}
            finally:
                task.state = "done"

        threading.Thread(target=worker, name=f"search-{task.id}", daemon=True).start()
        return task.snapshot()

    @app.get("/api/search/{task_id}")
    def search_status(task_id: str) -> dict[str, Any]:
        task = searches.get(task_id)
        if not task:
            raise HTTPException(404, "busca não encontrada")
        return task.snapshot()

    @app.get("/api/jobs")
    def list_jobs(
        q: str = "",
        status: str = "",
        source: str = "",
        remote: bool | None = None,
        auto_apply: bool | None = None,
        seniority: str = "",
        min_score: float | None = None,
        sort: Literal["score", "posted", "fetched"] = "score",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        config = load_config(paths)
        threshold = config.matching.min_score if min_score is None else min_score
        stmt = select(Job).where(col(Job.score) >= threshold)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(col(Job.title).ilike(like), col(Job.company).ilike(like)))
        if status:
            stmt = stmt.where(col(Job.status).in_(status.split(",")))
        if source:
            stmt = stmt.where(col(Job.source).startswith(source))
        if remote is not None:
            stmt = stmt.where(Job.remote == remote)
        order_column = {"score": Job.score, "posted": Job.posted_at, "fetched": Job.fetched_at}
        order = col(order_column[sort]).desc()
        with session(paths) as s:
            jobs = [job_dict(j) for j in s.exec(stmt.order_by(order))]
            sources = sorted(set(s.exec(select(Job.source).distinct()).all()))
        if auto_apply is not None:
            jobs = [j for j in jobs if j["auto_apply"] == auto_apply]
        if seniority:
            # "nao_informada" keeps jobs whose title doesn't state a level
            wanted = set(seniority.split(","))
            jobs = [j for j in jobs if wanted.intersection(j["seniority"] or ["nao_informada"])]
        return {"total": len(jobs), "items": jobs[offset : offset + limit], "sources": sources}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        with session(paths) as s:
            job = _get_or_404(s, Job, job_id)
            data = job_dict(job, full=True)
            apps = s.exec(
                select(Application)
                .where(Application.job_id == job_id)
                .order_by(col(Application.created_at).desc())
            ).all()
            data["applications"] = [_application_dict(a) for a in apps]
            return data

    @app.patch("/api/jobs/{job_id}")
    def set_job_status(job_id: str, body: StatusBody) -> dict[str, Any]:
        with session(paths) as s:
            job = _get_or_404(s, Job, job_id)
            job.status = body.status
            s.add(job)
            s.commit()
            return job_dict(job)

    @app.post("/api/jobs/{job_id}/manual")
    def mark_manual(job_id: str, body: ManualBody) -> dict[str, Any]:
        with session(paths) as s:
            job = _get_or_404(s, Job, job_id)
            resume = s.get(Document, body.doc_id) if body.doc_id else None
            application = _record(
                s, job, resume, "manual", "manual", ApplicationStatus.MANUAL, {}, notes=body.notes
            )
            return _application_dict(application)

    # ------------------------------------------------------------------ apply

    @app.post("/api/jobs/{job_id}/apply")
    def start_apply(job_id: str, body: ApplyBody) -> dict[str, Any]:
        if any(sess.state != "done" for sess in sessions.values()):
            raise HTTPException(409, "Já existe uma candidatura em andamento.")
        with session(paths) as s:
            _get_or_404(s, Job, job_id)

        sess = ApplySession(job_id)
        sessions[sess.id] = sess
        options = ApplyOptions(
            doc_id=body.doc_id,
            mode=body.mode,
            dry_run=body.dry_run,
            ai=body.ai,
            cover_letter=body.cover_letter,
        )
        hooks = ApplyHooks(
            confirm=lambda text: sess.ask("confirm", text) is True,
            ask_user=lambda text, options: sess.ask("question", text, options) or None,
            log=sess.add_log,
        )

        def worker() -> None:
            try:
                with session(paths) as s:
                    job = s.get(Job, job_id)
                    assert job is not None
                    sess.add_log(f"Iniciando: {job.title} @ {job.company}")
                    sess.result = result_dict(apply_to_job(s, paths, job, options, hooks))
            except Exception as exc:
                sess.result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            finally:
                sess.state = "done"

        threading.Thread(target=worker, name=f"apply-{sess.id}", daemon=True).start()
        return sess.snapshot()

    @app.get("/api/apply/{session_id}")
    def apply_status(session_id: str) -> dict[str, Any]:
        sess = sessions.get(session_id)
        if not sess:
            raise HTTPException(404, "sessão não encontrada")
        return sess.snapshot()

    @app.post("/api/apply/{session_id}/respond")
    def apply_respond(session_id: str, body: RespondBody) -> dict[str, Any]:
        sess = sessions.get(session_id)
        if not sess or not sess.respond(body.prompt_id, body.value):
            raise HTTPException(409, "nenhuma pergunta pendente")
        return {"ok": True}

    # ------------------------------------------------------------------ history

    @app.get("/api/applications")
    def list_applications(limit: int = 200) -> list[dict[str, Any]]:
        with session(paths) as s:
            rows = s.exec(
                select(Application, Job)
                .join(Job)
                .order_by(col(Application.created_at).desc())
                .limit(limit)
            ).all()
            return [{**_application_dict(a), "job": job_dict(j)} for a, j in rows]

    return app


def _application_dict(a: Application) -> dict[str, Any]:
    import json

    return {
        "id": a.id,
        "job_id": a.job_id,
        "document_id": a.document_id,
        "applier": a.applier,
        "mode": a.mode,
        "status": a.status.value,
        "answers": json.loads(a.answers_json or "{}"),
        "error": a.error,
        "notes": a.notes,
        "created_at": _iso(a.created_at),
        "submitted_at": _iso(a.submitted_at),
    }


def _get_or_404(s: Any, model: Any, key: Any) -> Any:
    obj = s.get(model, key)
    if obj is None:
        raise HTTPException(404, "não encontrado")
    return obj


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8"
    )
