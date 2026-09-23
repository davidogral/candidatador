"""SQLite storage helpers."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine, func, select

from candidatador.config import Paths
from candidatador.models import Application, ApplicationStatus

_engines: dict[str, Engine] = {}
_engines_lock = threading.Lock()


def get_engine(paths: Paths) -> Engine:
    url = f"sqlite:///{paths.database}"
    with _engines_lock:  # the web UI calls this from several threads at once
        if url not in _engines:
            paths.ensure()
            engine = create_engine(url, connect_args={"timeout": 30})
            event.listen(engine, "connect", _configure_sqlite)
            SQLModel.metadata.create_all(engine)
            _engines[url] = engine
        return _engines[url]


def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    # WAL: readers never block the writer (the UI reads while a search/apply writes).
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


@contextmanager
def session(paths: Paths) -> Iterator[Session]:
    with Session(get_engine(paths), expire_on_commit=False) as s:
        yield s


def submitted_since(s: Session, hours: int = 24) -> int:
    since = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(func.count())
        .select_from(Application)
        .where(
            Application.status == ApplicationStatus.SUBMITTED,
            Application.submitted_at >= since,  # type: ignore[operator]
        )
    )
    return int(s.exec(stmt).one())
