from __future__ import annotations

import pytest

from candidatador.config import Paths, Profile, init_home, load_profile


@pytest.fixture
def paths(tmp_path, monkeypatch) -> Paths:
    monkeypatch.setenv("CANDIDATADOR_HOME", str(tmp_path / "home"))
    p = Paths()
    init_home(p)
    return p


@pytest.fixture
def profile(paths) -> Profile:
    return load_profile(paths)
