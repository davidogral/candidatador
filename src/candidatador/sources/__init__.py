"""Job sources. Built-ins are registered here; third parties use entry points."""

from __future__ import annotations

from importlib.metadata import entry_points

from candidatador.sources.ats import AshbySource, GreenhouseSource, LeverSource
from candidatador.sources.base import JobPosting, JobSource, SearchQuery, SourceError
from candidatador.sources.gupy import GupySource
from candidatador.sources.jobspy import JobSpySource
from candidatador.sources.remotive import RemotiveSource

BUILTIN: dict[str, type[JobSource]] = {
    cls.name: cls
    for cls in (
        GupySource,
        RemotiveSource,
        GreenhouseSource,
        LeverSource,
        AshbySource,
        JobSpySource,
    )
}

ENTRY_POINT_GROUP = "candidatador.sources"


def available_sources() -> dict[str, type[JobSource]]:
    sources = dict(BUILTIN)
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            cls = ep.load()
        except Exception:  # a broken plugin must not break the CLI
            continue
        sources[getattr(cls, "name", ep.name)] = cls
    return sources


__all__ = ["JobPosting", "JobSource", "SearchQuery", "SourceError", "available_sources"]
