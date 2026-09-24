"""Fast, offline, explainable scoring (0-100). The AI matcher can refine it."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from candidatador.config import Profile
from candidatador.matching.seniority import LABELS, SENIORITY_TERMS, detect_seniority
from candidatador.sources.base import JobPosting, matches_keywords, normalize

#: skills matched for the full 40 points (profiles list many skills; a job cites a few)
SKILLS_FOR_FULL_SCORE = 6


class MatchResult(BaseModel):
    score: float
    reasons: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


def score_job(job: JobPosting, profile: Profile) -> MatchResult:
    text = f"{job.title}\n{job.description}"
    reasons: list[str] = []
    score = 0.0

    # 1) Role/title match: up to 35 points
    roles = profile.target.roles
    if roles and matches_keywords(job.title, roles):
        score += 35
        reasons.append("título compatível com o cargo desejado")
    elif roles and matches_keywords(text, roles):
        score += 15
        reasons.append("cargo desejado citado na descrição")

    # 2) Skills overlap: up to 40 points. Variants such as "PowerBI"/"Power BI" count once,
    #    and a long skills list is not penalized: ~6 matches already give full points.
    skills = _unique_skills(profile.skills)
    missing: list[str] = []
    if skills:
        hits = [s for s in skills if matches_keywords(text, [s])]
        missing = [s for s in skills if s not in hits]
        needed = min(SKILLS_FOR_FULL_SCORE, math.ceil(len(skills) * 2 / 3))
        score += 40 * min(1.0, len(hits) / needed)
        if hits:
            reasons.append(f"habilidades: {', '.join(hits[:8])}")

    # 3) Seniority (from the title): up to 10 points, or -15 on a clear mismatch
    wanted = normalize(profile.seniority)
    if wanted in SENIORITY_TERMS:
        title_levels = detect_seniority(job.title)
        if wanted in title_levels:
            score += 10
            reasons.append(f"senioridade {LABELS[wanted].lower()}")
        elif title_levels:
            score -= 15
            found = ", ".join(LABELS[level].lower() for level in title_levels)
            reasons.append(f"senioridade diferente ({found})")
        else:
            score += 5

    # 4) Location / remote preference: up to 15 points
    pref = profile.target.remote
    if job.remote and pref in ("only", "preferred"):
        score += 15
        reasons.append("remota")
    elif profile.target.locations and matches_keywords(job.location, profile.target.locations):
        score += 15
        reasons.append(f"local: {job.location}")
    elif pref == "any":
        score += 5

    return MatchResult(
        score=round(max(0.0, min(100.0, score)), 1), reasons=reasons, missing_skills=missing
    )


def _unique_skills(skills: list[str]) -> list[str]:
    """Drop blanks and spelling variants that differ only by spaces/case/accents."""
    seen: set[str] = set()
    unique = []
    for skill in skills:
        key = normalize(skill).replace(" ", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(skill)
    return unique
