"""Where a job accepts candidates from — works for remote jobs too.

Sources describe location very differently: "Remote, United States" (Greenhouse),
"Worldwide" / "LATAM, Europe" (Remotive), "Toledo, Paraná, Brasil" (Gupy), a separate
ISO code (Lever "US"). This module turns any of them into country codes and regions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from candidatador.sources.base import JobPosting, normalize


@dataclass(frozen=True)
class Country:
    code: str
    label: str
    terms: tuple[str, ...]  # normalized names, cities and aliases
    regions: tuple[str, ...]  # regions that include this country


COUNTRIES: dict[str, Country] = {
    c.code: c
    for c in (
        Country(
            "BR",
            "Brasil",
            (
                "brasil",
                "brazil",
                "brazilian",
                "sao paulo",
                "rio de janeiro",
                "belo horizonte",
                "curitiba",
                "porto alegre",
                "florianopolis",
                "recife",
                "fortaleza",
                "brasilia",
                "campinas",
                "goiania",
                "manaus",
                "belem",
                "londrina",
                "maringa",
                "joinville",
                "blumenau",
                "vitoria",
                "natal",
                "joao pessoa",
                "cascavel",
                "acre",
                "alagoas",
                "amapa",
                "amazonas",
                "bahia",
                "ceara",
                "distrito federal",
                "espirito santo",
                "goias",
                "maranhao",
                "mato grosso",
                "mato grosso do sul",
                "minas gerais",
                "para",
                "paraiba",
                "parana",
                "pernambuco",
                "piaui",
                "rio grande do norte",
                "rio grande do sul",
                "rondonia",
                "roraima",
                "santa catarina",
                "sergipe",
                "tocantins",
            ),
            ("latam", "americas", "south_america"),
        ),
        Country(
            "AR",
            "Argentina",
            ("argentina", "buenos aires", "cordoba"),
            ("latam", "americas", "south_america"),
        ),
        Country("CL", "Chile", ("chile", "santiago"), ("latam", "americas", "south_america")),
        Country(
            "CO",
            "Colômbia",
            ("colombia", "bogota", "medellin"),
            ("latam", "americas", "south_america"),
        ),
        Country("PE", "Peru", ("peru", "lima"), ("latam", "americas", "south_america")),
        Country(
            "UY",
            "Uruguai",
            ("uruguay", "uruguai", "montevideo", "montevideu"),
            ("latam", "americas", "south_america"),
        ),
        Country(
            "MX",
            "México",
            ("mexico", "cdmx", "guadalajara", "monterrey"),
            ("latam", "americas", "north_america"),
        ),
        Country(
            "US",
            "Estados Unidos",
            (
                "united states",
                "usa",
                "us",
                "u s a",
                "u s",
                "eua",
                "estados unidos",
                "new york",
                "san francisco",
                "seattle",
                "washington",
                "palo alto",
                "austin",
                "boston",
                "chicago",
                "los angeles",
                "denver",
                "miami",
                "atlanta",
                "honolulu",
            ),
            ("americas", "north_america"),
        ),
        Country(
            "CA",
            "Canadá",
            ("canada", "toronto", "vancouver", "montreal", "ottawa"),
            ("americas", "north_america"),
        ),
        Country(
            "GB",
            "Reino Unido",
            (
                "united kingdom",
                "uk",
                "england",
                "london",
                "scotland",
                "manchester",
                "edinburgh",
                "reino unido",
                "great britain",
            ),
            ("europe", "emea"),
        ),
        Country("IE", "Irlanda", ("ireland", "irlanda", "dublin"), ("europe", "emea")),
        Country("PT", "Portugal", ("portugal", "lisbon", "lisboa"), ("europe", "emea")),
        Country(
            "ES",
            "Espanha",
            ("spain", "espanha", "espana", "madrid", "barcelona"),
            ("europe", "emea"),
        ),
        Country(
            "DE",
            "Alemanha",
            ("germany", "alemanha", "deutschland", "berlin", "munich"),
            ("europe", "emea"),
        ),
        Country("FR", "França", ("france", "franca", "paris"), ("europe", "emea")),
        Country("NL", "Holanda", ("netherlands", "holanda", "amsterdam"), ("europe", "emea")),
        Country("PL", "Polônia", ("poland", "polonia", "warsaw", "krakow"), ("europe", "emea")),
        Country("IN", "Índia", ("india", "bangalore", "bengaluru", "hyderabad", "pune"), ("apac",)),
        Country("IL", "Israel", ("israel", "tel aviv"), ("emea",)),
    )
}

#: region -> phrases in location text (normalized)
REGION_TERMS: dict[str, tuple[str, ...]] = {
    "worldwide": (
        "worldwide",
        "anywhere",
        "global",
        "remote global",
        "work from anywhere",
        "qualquer lugar",
        "mundo todo",
    ),
    "latam": ("latam", "latin america", "america latina", "latinoamerica"),
    "south_america": ("south america", "america do sul"),
    "americas": ("americas", "amer", "the americas"),
    "north_america": ("north america", "northern america", "america do norte"),
    "europe": ("europe", "european union", "eu", "europa"),
    "emea": ("emea",),
    "apac": ("apac", "asia pacific"),
}

#: State codes are only trusted right after a comma ("Toledo, PR", "Denver, CO"). Codes
#: used by both countries (PA, SC, MA, AL, MS, MT) say nothing on their own.
_BR_STATES = set(
    [
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    ]
)
_US_STATES = set(
    [
        "AK",
        "AL",
        "AR",
        "AZ",
        "CA",
        "CO",
        "CT",
        "DC",
        "DE",
        "FL",
        "GA",
        "HI",
        "IA",
        "ID",
        "IL",
        "IN",
        "KS",
        "KY",
        "LA",
        "MA",
        "MD",
        "ME",
        "MI",
        "MN",
        "MO",
        "MS",
        "MT",
        "NC",
        "ND",
        "NE",
        "NH",
        "NJ",
        "NM",
        "NV",
        "NY",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VA",
        "VT",
        "WA",
        "WI",
        "WV",
        "WY",
    ]
)
_STATE_RE = re.compile(r",\s*([A-Z]{2})\b")


@dataclass
class Where:
    countries: set[str]
    regions: set[str]

    @property
    def known(self) -> bool:
        return bool(self.countries or self.regions)


def _location_text(job: JobPosting) -> str:
    raw = job.raw or {}
    parts = [job.location, str(raw.get("candidate_required_location") or "")]
    return " ; ".join(p for p in parts if p)


def where(job: JobPosting) -> Where:
    """Countries and regions a job is open to, from all location hints of every source."""
    original = _location_text(job)
    text = f" {normalize(original)} "
    countries = {
        code
        for code, country in COUNTRIES.items()
        if any(f" {term} " in text for term in country.terms)
    }
    for code in _STATE_RE.findall(original):
        in_br, in_us = code in _BR_STATES, code in _US_STATES
        if in_br and not in_us:
            countries.add("BR")
        elif in_us and not in_br:
            countries.add("US")
    iso = str((job.raw or {}).get("country_code") or "").upper()
    if iso in COUNTRIES:
        countries.add(iso)
    regions = {
        region for region, terms in REGION_TERMS.items() if any(f" {t} " in text for t in terms)
    }
    return Where(countries, regions)


def accepts(job: JobPosting, wanted: list[str], *, include_unknown: bool = True) -> bool:
    """True if the job is open to candidates in any of the `wanted` country codes.

    A remote job counts when it names the country, a region that contains it (LATAM,
    Americas…) or "worldwide". Jobs that don't say where are kept only if include_unknown.
    """
    if not wanted:
        return True
    w = where(job)
    if not w.known:
        return include_unknown
    for code in wanted:
        country = COUNTRIES.get(code)
        if code in w.countries or "worldwide" in w.regions:
            return True
        if country and w.regions.intersection(country.regions):
            return True
    return False
