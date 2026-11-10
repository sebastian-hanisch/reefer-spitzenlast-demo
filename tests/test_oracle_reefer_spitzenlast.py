"""Orakel-Test reefer-spitzenlast-demo: die kleinste Spitze (LP bzw. MILP) und die Regeln gegen einen anderen Rechenweg.

Orakel 1 (Aufzählung): bei zwei Reefern und sechs Schritten gibt es 2^12 = 4096 Ein/Aus-Pläne. Jeder wird mit `replay` (die Rekursion
T' = a·T + (1 − a)·A − b·u, ohne Matrix) auf das Band geprüft; die kleinste Spitze der zulässigen Pläne ist das Orakel für `exact_peak`
(Matrix-Formulierung, HiGHS). Orakel 2 (geschlossene Formel): die Temperatur ohne Kühlung folgt T_t = A + (T_0 − A)·a^t bei konstanter Umgebung.
Orakel 3 (Invarianten): untere Schranke ≤ Spitze jedes zulässigen Plans; die Regeln liefern zulässige Pläne, die Leistungsgrenze hält ihre Grenze.
Das Orakel selbst ist an einem Handbeispiel geprüft (test_brute_force_oracle_on_a_hand_example).
"""

import itertools

import numpy as np
import pytest

import rsl_algorithm as A
import rsl_constants as C
from conftest import build


def brute_force_min_peak(inst, steps):
    """Kleinste Spitze über alle Ein/Aus-Pläne, die das Band an allen Zeitpunkten halten; None, wenn es keinen gibt."""
    n = inst.n
    best = None
    for bits in itertools.product((0, 1), repeat=n * steps):
        u = np.array(bits, dtype=bool).reshape(steps, n)
        temp = A.replay(inst, u)
        excess = np.maximum(temp - inst.hi_safe[None, :], 0.0) + np.maximum(inst.lo[None, :] - temp, 0.0)
        if excess.max() > C.EPS:
            continue
        peak = float((u * inst.power_kw[None, :]).sum(axis=1).max())
        best = peak if best is None else min(best, peak)
    return best


def random_mini(seed, steps=6):
    """Zwei Reefer; gerade Seeds starten am oberen Rand (gleichzeitiger Start), ungerade verteilt im Band."""
    rng = np.random.default_rng(seed)
    n = 2
    return build(
        n, steps=steps, band=float(rng.choice([0.5, 1.0])), margin=float(rng.choice([0.0, 0.25, 0.5])),
        tau=rng.uniform(3.0, 10.0, n), cool=rng.uniform(1.5, 3.0, n), power=rng.choice([6.0, 8.0, 10.0], n),
        t0=None if seed % 2 == 0 else rng.uniform(-0.5, 0.5, n), ambient=rng.uniform(3.0, 15.0, steps),
    )


def test_the_mini_instances_are_not_vacuous(short):
    """Das Orakel prüft nur etwas, wenn die meisten Instanzen zulässig sind und die kleinste Spitze nicht schon die volle Leistung ist (oder 0)."""
    peaks = [(brute_force_min_peak(random_mini(s), 6), random_mini(s).total_power_kw) for s in range(12)]
    assert sum(p is not None for p, _ in peaks) >= 10
    assert sum(p is not None and 0 < p < total for p, total in peaks) >= 3


def test_brute_force_oracle_on_a_hand_example(short):
    # Ein Reefer, Umgebung = oberer Rand: ohne Kühlung bleibt T = 1 → der beste Plan ist „nie kühlen“ mit Spitze 0
    inst = build(1, ambient=1.0)
    assert brute_force_min_peak(inst, 6) == 0.0
    # Ein Reefer bei A = 20: T1 ohne Kühlung ≈ 1,197 > 1,5 − 0,5?  Reserve 0,5 → sicher bis 1,5: schon der erste Schritt ohne Kühlung ist zulässig,
    # aber über sechs Schritte (T wächst um etwa 0,2 je Schritt) muss mindestens einmal gekühlt werden: Spitze = 10
    assert brute_force_min_peak(build(1, ambient=20.0), 6) == 10.0


@pytest.mark.parametrize("seed", range(12))
def test_exact_peak_equals_enumeration_and_the_lp_is_a_lower_bound(short, seed):
    inst = random_mini(seed)
    oracle = brute_force_min_peak(inst, 6)
    milp_result = A.exact_peak(inst, integer=True)
    lp_result = A.exact_peak(inst, integer=False)
    if oracle is None:
        assert milp_result.status == "unzulässig" and milp_result.peak_kw is None
        return
    assert milp_result.status == "optimal"
    assert milp_result.peak_kw == pytest.approx(oracle, abs=1e-6)
    assert lp_result.peak_kw is not None and lp_result.peak_kw <= oracle + 1e-6


@pytest.mark.parametrize("seed", range(6))
def test_the_exact_plan_replays_inside_the_band_with_the_reported_peak(short, seed):
    inst = random_mini(seed)
    res = A.exact_peak(inst, integer=True)
    if res.peak_kw is None:
        pytest.skip("kein zulässiger Plan")
    u = res.u > 0.5
    r = A.evaluate(inst, "ungesteuert", u, A.replay(inst, u))
    assert r.in_band
    assert r.peak_kw <= res.peak_kw + 1e-6


@pytest.mark.parametrize("seed", range(12))
def test_rule_plans_are_feasible_and_never_beat_the_exact_peak(short, seed):
    inst = random_mini(seed)
    oracle = brute_force_min_peak(inst, 6)
    if oracle is None:
        return
    cap = A.smallest_cap(inst)
    if cap is not None:  # die Regel hält das Band bei dieser Grenze: ihr Plan ist zulässig, die Grenze also nicht unter dem Optimum
        assert cap >= oracle - 0.05 - 1e-9
        assert A.simulate(inst, "grenze", cap_kw=cap).in_band
    free = A.simulate(inst, "ungesteuert")
    if free.in_band:
        assert free.peak_kw >= oracle - 1e-9


def test_free_response_matches_the_closed_form(short):
    inst = build(2, tau=[10.0, 30.0], ambient=15.0, t0=[0.0, -3.0])
    t_free = A._free_response(inst)  # T_t für t = 1..STEPS ohne jede Kühlung
    for i in range(2):
        a = np.exp(-C.DT_H / inst.tau_h[i])
        expected = 15.0 + (inst.t0[i] - 15.0) * a ** np.arange(1, 7)
        assert np.allclose(t_free[:, i], expected, atol=1e-12)


def test_full_horizon_lp_bound_never_exceeds_a_feasible_plan_and_the_mean_power():
    # 24-Stunden-Block (96 Schritte): untere Schranke ≤ Spitze der Regel, und jede Spitze ≥ mittlere Leistung (Energieerhaltung)
    from rsl_scenario import make_instance

    for seed in range(5):
        inst = make_instance(8, 50, 1.0, 0.5, 80, 16, 2, seed)
        lp = A.exact_peak(inst, integer=False)
        cap = A.smallest_cap(inst)
        assert lp.peak_kw is not None and cap is not None
        assert lp.peak_kw <= cap + 1e-6
        res = A.simulate(inst, "grenze", cap_kw=cap)
        assert res.peak_kw >= res.energy_kwh / C.HORIZON_H - 1e-9


def test_milp_gap_on_the_default_block_matches_the_rule():
    # gemessen an einem Block mit vier Reefern: die kleinste Grenze der Regel ist so groß wie die exakte Ein/Aus-Spitze
    from rsl_scenario import make_instance

    inst = make_instance(4, 50, 1.0, 0.5, 80, 16, 2, 17)
    exact = A.exact_peak(inst, integer=True, time_limit_s=60.0)
    cap = A.smallest_cap(inst)
    assert exact.status == "optimal"
    assert cap is not None and cap >= exact.peak_kw - 1e-6
    assert cap - exact.peak_kw <= 0.05 + 1e-6
