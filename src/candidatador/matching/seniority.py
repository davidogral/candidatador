"""Seniority detection from job titles (pt/en), used for scoring and for the UI filter."""

from __future__ import annotations

import re

from candidatador.sources.base import normalize

#: level -> terms that identify it in a (normalized) job title
SENIORITY_TERMS: dict[str, list[str]] = {
    "estagio": [
        "estagio",
        "estagiario",
        "estagiaria",
        "intern",
        "internship",
        "trainee",
        "aprendiz",
    ],
    "junior": ["junior", "jr", "entry level", "associate"],
    "pleno": ["pleno", "pl", "mid level", "mid"],
    "senior": ["senior", "sr"],
    "especialista": ["especialista", "staff", "principal", "specialist", "expert"],
    "lideranca": [
        "lead",
        "lider",
        "lideranca",
        "tech lead",
        "head",
        "manager",
        "gerente",
        "coordenador",
        "coordenadora",
        "supervisor",
        "supervisora",
        "diretor",
        "diretora",
    ],
}

LABELS: dict[str, str] = {
    "estagio": "Estágio/Trainee",
    "junior": "Júnior",
    "pleno": "Pleno",
    "senior": "Sênior",
    "especialista": "Especialista",
    "lideranca": "Liderança",
}

#: "Analista de Dados II", "Data Scientist III": common level suffixes
_ROMAN = {"i": "junior", "ii": "pleno", "iii": "senior", "iv": "especialista"}
_ROMAN_RE = re.compile(r"\b(i{1,3}|iv)\b")


def detect_seniority(title: str) -> list[str]:
    """Levels mentioned in the title, in canonical order ([] when not stated).

    A title can mention more than one ("Desenvolvedor Pleno/Sênior", "PL/SR").
    """
    text = f" {normalize(title)} "
    found = {
        level
        for level, terms in SENIORITY_TERMS.items()
        if any(f" {normalize(term)} " in text for term in terms)
    }
    if not found:
        # "Analista de Dados II" -> pleno; but in "Especialista I" / "Gerente I" the numeral is
        # a step inside that track, so it only counts when no other level is named
        for match in _ROMAN_RE.finditer(text):
            found.add(_ROMAN[match.group(1)])
    return [level for level in SENIORITY_TERMS if level in found]
