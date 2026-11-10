"""Gemeinsame Fixtures: kleine Reefer-Blöcke mit wenigen Schritten, an denen jede Einheit von Hand geprüft wird (DEMO-PLAYBOOK §1b)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rsl_constants as C  # noqa: E402
from rsl_scenario import Instance  # noqa: E402


def build(n=1, *, steps=6, setpoint=0.0, band=1.0, margin=0.5, tau=24.0, cool=2.0, power=10.0, t0=None, ambient=20.0) -> Instance:
    """Reefer-Block mit gleichen Reefern: `t0` Starttemperatur (Standard: oberer Rand des Regelbands), `ambient` konstant oder Liste je Schritt."""
    amb = np.full(steps, float(ambient)) if np.isscalar(ambient) else np.asarray(ambient, dtype=float)
    start = np.asarray(setpoint, dtype=float) + band if t0 is None else t0
    full = lambda x: np.full(n, float(x)) if np.isscalar(x) else np.asarray(x, dtype=float)  # noqa: E731
    return Instance(
        frozen=np.zeros(n, dtype=bool), setpoint=full(setpoint), band=float(band), margin=float(margin), tau_h=full(tau),
        cool_k_per_h=full(cool), power_kw=full(power), t0=full(start), ambient=amb,
    )


@pytest.fixture
def short(monkeypatch):
    """Sechs Schritte statt 96: der Kern liest die Schrittzahl bei jedem Aufruf aus den Konstanten."""
    monkeypatch.setattr(C, "STEPS", 6)
    return 6
