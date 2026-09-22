"""Fast, offline, explainable scoring (0-100). The AI matcher can refine it."""

from __future__ import annotations

from pydantic import BaseModel, Field

from candidatador.config import Profile
from candidatador.sources.base import JobPosting, matches_keywords, normalize

SENIORITY_TERMS = {
    "estagio": ["estagio", "estagiario", "intern", "internship"],
    "junior": ["junior", "jr"],
    "pleno": ["pleno", "mid level", "mid-level", "pl"],
    "senior": ["senior", "sr"],
    "especialista": ["especialista", "staff", "principal", "specialist"],
    "lideranca": ["lead", "lider", "tech lead", "head", "manager", "gerente", "coordenador"],
}


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

    # 2) Skills overlap: up to 40 points
    skills = [s for s in profile.skills if s.strip()]
    missing: list[str] = []
    if skills:
        hits = [s for s in skills if matches_keywords(text, [s])]
        missing = [s for s in skills if s not in hits]
        ratio = len(hits) / len(skills)
        score += 40 * min(1.0, ratio * 1.5)  # matching ~2/3 of your skills is already great
        if hits:
            reasons.append(f"habilidades: {', '.join(hits[:8])}")

    # 3) Seniority: up to 10 points (or -15 on a clear mismatch)
    wanted = normalize(profile.seniority)
    if wanted in SENIORITY_TERMS:
        title_levels = [
            lvl for lvl, terms in SENIORITY_TERMS.items() if matches_keywords(job.title, terms)
        ]
        if wanted in title_levels:
            score += 10
            reasons.append(f"senioridade {profile.seniority}")
        elif title_levels:
            score -= 15
            reasons.append(f"senioridade diferente ({', '.join(title_levels)})")
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
