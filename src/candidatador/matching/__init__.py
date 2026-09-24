from candidatador.matching.filters import CONTRACT_LABELS, Filters, passes_filters
from candidatador.matching.location import COUNTRIES
from candidatador.matching.scorer import MatchResult, score_job
from candidatador.matching.seniority import LABELS as SENIORITY_LABELS
from candidatador.matching.seniority import detect_seniority, job_seniority

__all__ = [
    "CONTRACT_LABELS",
    "COUNTRIES",
    "SENIORITY_LABELS",
    "Filters",
    "MatchResult",
    "detect_seniority",
    "job_seniority",
    "passes_filters",
    "score_job",
]
