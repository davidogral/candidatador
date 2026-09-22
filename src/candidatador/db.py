"""SQLite storage helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, func, select

from candidatador.config import Paths
from candidatador.models import Application, ApplicationStatus

_engines: dict[str, Engine] = {}


def get_engine(paths: Paths) -> Engine:
    url = f"sqlite:///{paths.database}"
    if url not in _engines:
        paths.ensure()
        engine = create_engine(url)
        SQLModel.metadata.create_all(engine)
        _engines[url] = engine
    return _engines[url]


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
