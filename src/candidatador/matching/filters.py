"""Hard filters: a job that fails any of them is discarded before scoring.

Each rejection returns a short reason; the search reports how many jobs each filter
removed, so the user can see what to loosen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from candidatador.config import Profile
from candidatador.matching.location import accepts
from candidatador.matching.seniority import job_seniority
from candidatador.sources.base import JobPosting, SearchQuery, matches_keywords, normalize

TALENT_POOL_TERMS = [
    "banco de talentos",
    "talent pool",
    "talent community",
    "banco de curriculos",
    "cadastro reserva",
    "vaga reserva",
]

#: contract types the filters understand (values of JobPosting.employment_type)
CONTRACT_LABELS = {
    "clt": "CLT",
    "pj": "PJ",
    "estagio": "Estágio",
    "aprendiz": "Aprendiz",
    "temporario": "Temporário",
    "autonomo": "Autônomo",
    "cooperado": "Cooperado",
}
_CONTRACT_ALIASES = {"internship": "estagio", "intern": "estagio", "banco_de_talentos": ""}


@dataclass
class Filters:
    """Search-time filters: the query's choices, falling back to the profile's defaults."""

    seniority: list[str]
    include_unknown_seniority: bool
    countries: list[str]
    include_unknown_country: bool
    contract_types: list[str]
    exclude_talent_pool: bool
    title_must_match: bool

    @classmethod
    def resolve(cls, query: SearchQuery, profile: Profile) -> Filters:
        t = profile.target

        def pick(value, default):
            return default if value is None else value

        return cls(
            seniority=pick(query.seniority, t.seniority_levels),
            include_unknown_seniority=pick(
                query.include_unknown_seniority, t.include_unknown_seniority
            ),
            countries=pick(query.countries, t.countries),
            include_unknown_country=pick(query.include_unknown_country, t.include_unknown_country),
            contract_types=[normalize(c) for c in pick(query.contract_types, t.contract_types)],
            exclude_talent_pool=pick(query.exclude_talent_pool, t.exclude_talent_pool),
            title_must_match=pick(query.title_must_match, t.title_must_match),
        )


def contract_of(job: JobPosting) -> str:
    """Normalized contract type, or "" when the source doesn't say."""
    value = normalize(job.employment_type).replace(" ", "_")
    value = _CONTRACT_ALIASES.get(value, value)
    return value if value in CONTRACT_LABELS else ""


def is_talent_pool(job: JobPosting) -> bool:
    return job.employment_type == "banco_de_talentos" or matches_keywords(
        job.title, TALENT_POOL_TERMS
    )


def passes_filters(
    job: JobPosting, profile: Profile, query: SearchQuery, filters: Filters | None = None
) -> tuple[bool, str]:
    """Return (ok, reason_if_rejected)."""
    target = profile.target
    f = filters or Filters.resolve(query, profile)
    text = f"{job.title}\n{job.description}"

    excluded_companies = {normalize(c) for c in target.companies_excluded}
    if normalize(job.company) in excluded_companies:
        return False, "empresa excluída"

    if f.exclude_talent_pool and is_talent_pool(job):
        return False, "banco de talentos"

    if target.keywords_excluded and matches_keywords(job.title, target.keywords_excluded):
        return False, "palavra excluída no título"

    if target.keywords_required and not matches_keywords(text, target.keywords_required):
        return False, "sem palavras obrigatórias"

    wanted_titles = query.keywords or target.roles
    if f.title_must_match and wanted_titles and not title_matches(job.title, wanted_titles):
        return False, "título fora do cargo buscado"

    remote_only = query.remote_only or target.remote == "only"
    if remote_only and job.remote is False:
        return False, "não é remota"
    if target.remote == "no" and job.remote is True:
        return False, "é remota"

    if f.countries and not accepts(job, f.countries, include_unknown=f.include_unknown_country):
        return False, "país"

    if f.seniority:
        levels = job_seniority(job.title, job.raw)
        if levels and not set(levels) & set(f.seniority):
            return False, "senioridade"
        if not levels and not f.include_unknown_seniority:
            return False, "senioridade não informada"

    contract = contract_of(job)
    if f.contract_types and contract and contract not in f.contract_types:
        return False, "tipo de contrato"

    if query.posted_within_days and job.posted_at:
        posted = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=UTC)
        if posted < datetime.now(UTC) - timedelta(days=query.posted_within_days):
            return False, "vaga antiga"

    return True, ""


_STOPWORDS = {
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "e",
    "a",
    "o",
    "as",
    "os",
    "of",
    "the",
    "and",
    "para",
    "com",
    "in",
    "for",
}
_PREFIX = 4


def _stems(text: str) -> list[str]:
    """Significant words cut to a prefix: "Engenheiro(a) de Dados" -> ["enge", "dado"]."""
    return [w[:_PREFIX] for w in normalize(text).split() if w not in _STOPWORDS and len(w) > 1]


def title_matches(title: str, wanted: list[str]) -> bool:
    """True if every significant word of some wanted role appears in the title.

    Tolerant to connectors ("Analista Dados JR"), gender marks ("Engenheiro(a)") and word
    forms ("Engenharia de Dados" ~ "Engenheiro de Dados", "Ciência" ~ "Cientista").
    """
    title_stems = set(_stems(title))
    for role in wanted:
        stems = _stems(role)
        if stems and all(s in title_stems for s in stems):
            return True
    return False
