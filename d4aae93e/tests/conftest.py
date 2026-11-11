from __future__ import annotations

import pytest

from src.engine import CampusPulseEngine


@pytest.fixture(scope="session")
def engine() -> CampusPulseEngine:
    return CampusPulseEngine.load()
