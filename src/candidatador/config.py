"""Paths, user configuration (config.yaml) and professional profile (profile.yaml)."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml
from platformdirs import user_data_dir
from pydantic import BaseModel, Field

HOME_ENV = "CANDIDATADOR_HOME"


class Paths:
    """Everything the tool stores lives under a single local directory."""

    def __init__(self, root: Path | None = None) -> None:
        env = os.environ.get(HOME_ENV)
        self.root = Path(root or env or user_data_dir("candidatador", appauthor=False))

    @property
    def config(self) -> Path:
        return self.root / "config.yaml"

    @property
    def profile(self) -> Path:
        return self.root / "profile.yaml"

    @property
    def database(self) -> Path:
        return self.root / "candidatador.db"

    @property
    def vault(self) -> Path:
        """Where uploaded documents (resumes, certificates...) are copied to."""
        return self.root / "vault"

    @property
    def browser_state(self) -> Path:
        """Persistent browser profile, so logins survive between runs."""
        return self.root / "browser"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault.mkdir(exist_ok=True)


# --------------------------------------------------------------------------- config.yaml


class MatchingConfig(BaseModel):
    min_score: float = 40
    use_ai: bool = False


class AIConfig(BaseModel):
    model: str = "claude-opus-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"


class ApplyConfig(BaseModel):
    mode: Literal["review", "auto"] = "review"
    headless: bool = False
    max_per_day: int = 20
    delay_seconds: int = 30


class Config(BaseModel):
    sources: dict[str, dict[str, Any]] = Field(default_factory=dict)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    apply: ApplyConfig = Field(default_factory=ApplyConfig)

    def source_settings(self, name: str) -> dict[str, Any]:
        return dict(self.sources.get(name) or {})

    def enabled_sources(self) -> list[str]:
        return [name for name, cfg in self.sources.items() if (cfg or {}).get("enabled")]


# --------------------------------------------------------------------------- profile.yaml


class PersonalInfo(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""

    @property
    def first_name(self) -> str:
        return self.full_name.split(" ", 1)[0] if self.full_name else ""

    @property
    def last_name(self) -> str:
        parts = self.full_name.split(" ", 1)
        return parts[1] if len(parts) > 1 else ""


class Language(BaseModel):
    name: str
    level: str = ""


class Target(BaseModel):
    roles: list[str] = Field(default_factory=list)
    keywords_required: list[str] = Field(default_factory=list)
    keywords_excluded: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote: Literal["only", "preferred", "any", "no"] = "any"
    contract_types: list[str] = Field(default_factory=list)
    min_salary_brl: float | None = None
    companies_excluded: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    personal: PersonalInfo = Field(default_factory=PersonalInfo)
    headline: str = ""
    summary: str = ""
    seniority: str = ""
    years_of_experience: float | None = None
    skills: list[str] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    target: Target = Field(default_factory=Target)
    answers: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- loading


def _template(name: str) -> str:
    return resources.files("candidatador.templates").joinpath(name).read_text(encoding="utf-8")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def init_home(paths: Paths, *, overwrite: bool = False) -> list[Path]:
    """Create the data directory and the starter YAML files. Returns files written."""
    paths.ensure()
    written = []
    for target, template in ((paths.config, "config.yaml"), (paths.profile, "profile.yaml")):
        if overwrite or not target.exists():
            target.write_text(_template(template), encoding="utf-8")
            written.append(target)
    return written


def load_config(paths: Paths) -> Config:
    data = _load_yaml(paths.config) or yaml.safe_load(_template("config.yaml"))
    return Config.model_validate(data)


def load_profile(paths: Paths) -> Profile:
    return Profile.model_validate(_load_yaml(paths.profile))
