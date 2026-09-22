"""Appliers fill and submit application forms. Built-ins + entry-point plugins."""

from __future__ import annotations

from importlib.metadata import entry_points

from candidatador.apply.answers import AnswerProvider, ResolvedAnswer
from candidatador.apply.base import Applier, ApplyContext, ApplyOutcome
from candidatador.apply.greenhouse import GreenhouseApplier
from candidatador.apply.lever import LeverApplier

BUILTIN: list[type[Applier]] = [GreenhouseApplier, LeverApplier]
ENTRY_POINT_GROUP = "candidatador.appliers"


def available_appliers() -> list[type[Applier]]:
    appliers = list(BUILTIN)
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            appliers.append(ep.load())
        except Exception:
            continue
    return appliers


def find_applier(url: str) -> type[Applier] | None:
    return next((a for a in available_appliers() if a.supports(url)), None)


__all__ = [
    "AnswerProvider",
    "Applier",
    "ApplyContext",
    "ApplyOutcome",
    "ResolvedAnswer",
    "available_appliers",
    "find_applier",
]
