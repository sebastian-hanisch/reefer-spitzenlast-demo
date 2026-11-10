"""Jede Zahl der README-Tabelle „Befunde“ wird hier über dieselben Auswertungsfunktionen wie in der App nachgerechnet (DEMO-PLAYBOOK §4, §11a).

Alle Mittel und Mediane laufen über die 20 festen Blöcke `SWEEP_SEEDS` (nie ein einzelner Zufalls-Seed). Standard: 12 Reefer, 50 % gefroren, Regelband ±1 K,
80 % starten am oberen Rand, 16 °C Tagesmittel, 2 K Sonne, 0,5 K Reserve, 2 Gruppen, Slots zu 15 Minuten.
"""

from statistics import median

import numpy as np
import pytest

import rsl_algorithm as A
import rsl_constants as C
import rsl_evaluation as ev

SEEDS = C.SWEEP_SEEDS


def block_rows(**kw):
    """Je fester Block: Spitze ohne Steuerung, kleinste Grenze der Regel, untere Schranke, ob ohne Steuerung das Band hält, Tastverhältnis, mittlere Leistung."""
    s = ev.Settings(**kw)
    rows = []
    for seed in SEEDS:
        inst = ev.instance_of(s, seed=seed)
        base = A.simulate(inst, "ungesteuert")
        rows.append({
            "base": base.peak_kw,
            "base_in_band": base.in_band,
            "cap": A.smallest_cap(inst),
            "lp": A.exact_peak(inst, integer=False).peak_kw,
            "duty": base.energy_kwh / (C.HORIZON_H * inst.total_power_kw),
            "mean_kw": base.energy_kwh / C.HORIZON_H / inst.n,
            "total": inst.total_power_kw,
        })
    return rows


def reductions(rows):
    return [100.0 * (1.0 - r["cap"] / r["base"]) for r in rows]


@pytest.fixture(scope="module")
def by_margin():
    return {m: block_rows(margin=m) for m in (0.0, 0.25, 0.5, 1.0, 2.0)}


def test_without_reserve_the_cap_rule_barely_helps(by_margin):
    red = reductions(by_margin[0.0])
    assert median(red) == pytest.approx(8.0, abs=0.5) and max(red) == pytest.approx(16.7, abs=0.5)
    assert min(red) > -0.5  # in keinem Block ist die kleinste Grenze nennenswert größer als die Spitze ohne Steuerung


def test_a_quarter_kelvin_of_reserve_removes_about_half_of_the_peak(by_margin):
    for margin, med in ((0.25, 56.0), (0.5, 56.6)):
        red = reductions(by_margin[margin])
        assert median(red) == pytest.approx(med, abs=0.5), margin
        assert min(red) >= 49.5 and max(red) <= 62.5, margin


def test_more_reserve_helps_only_slowly(by_margin):
    meds = {m: median(reductions(by_margin[m])) for m in (0.25, 0.5, 1.0, 2.0)}
    assert meds[1.0] == pytest.approx(61.0, abs=0.5) and meds[2.0] == pytest.approx(64.0, abs=0.5)
    assert meds[0.25] <= meds[0.5] <= meds[1.0] <= meds[2.0]
    assert median(r["base"] for r in by_margin[0.5]) == 98.0 and by_margin[0.5][0]["total"] == 108.0


def test_the_peak_without_control_is_most_of_the_connected_power(by_margin):
    assert median(r["base"] for r in by_margin[0.5]) / by_margin[0.5][0]["total"] == pytest.approx(98.0 / 108.0)
    assert {r["total"] for r in by_margin[0.5]} == {108.0}


def test_the_thermostat_alone_keeps_every_reefer_inside_the_safe_range(by_margin):
    for margin, rows in by_margin.items():
        assert sum(r["base_in_band"] for r in rows) == 20, margin


def test_the_cap_rule_never_beats_the_lower_bound_and_the_gap_is_measured(by_margin):
    for margin, rows in by_margin.items():
        assert all(r["cap"] >= r["lp"] - 1e-6 for r in rows), margin
    gap = lambda m: [100.0 * (r["cap"] / r["lp"] - 1.0) for r in by_margin[m]]  # noqa: E731
    assert median(gap(0.5)) == pytest.approx(16.1, abs=0.5) and min(gap(0.5)) >= 10.0 and max(gap(0.5)) <= 23.0
    assert median(gap(0.0)) == pytest.approx(138.2, abs=1.0) and min(gap(0.0)) >= 100.0


def test_mean_power_per_reefer_without_control(by_margin):
    mean_kw = [r["mean_kw"] for r in by_margin[0.5]]
    assert median(mean_kw) == pytest.approx(3.05, abs=0.05) and min(mean_kw) >= 2.7 and max(mean_kw) <= 3.5
    assert median(r["duty"] for r in by_margin[0.5]) == pytest.approx(0.34, abs=0.01)


def test_slot_table_counts():
    rows = {(r["groups"], r["slot"]): r for r in ev.sweep_slots(ev.Settings())}
    assert (rows[(2, 1)]["in_band"], rows[(2, 2)]["in_band"]) == (13, 10)
    assert all(rows[(2, slot)]["in_band"] == 0 for slot in (4, 8))
    assert all(rows[(g, slot)]["in_band"] == 0 for g in (3, 4) for slot in C.SLOT_SWEEP)
    assert sum(r["in_band"] > 0 for r in rows.values()) == 2 and len(rows) == 12
    assert all(rows[(2, slot)]["peak"] == pytest.approx(55.3, abs=0.2) for slot in C.SLOT_SWEEP)
    assert rows[(3, 1)]["peak"] == pytest.approx(37.7, abs=0.2) and rows[(4, 1)]["peak"] == pytest.approx(28.3, abs=0.2)


WEATHER = ((8, 0), (12, 0), (16, 2), (20, 3), (24, 4), (32, 8))


@pytest.fixture(scope="module")
def weather():
    out = {}
    for tmean, sun in WEATHER:
        s = ev.Settings(tmean=tmean, sun=sun)
        rows = block_rows(tmean=tmean, sun=sun)
        in_band = [A.simulate(ev.instance_of(s, seed=seed), "reihum", groups=2, slot_steps=1).in_band for seed in SEEDS]
        out[(tmean, sun)] = {"rows": rows, "reihum_in_band": sum(in_band)}
    return out


def test_strom_reihum_works_only_on_cool_days(weather):
    assert [weather[w]["reihum_in_band"] for w in WEATHER] == [20, 20, 13, 3, 0, 0]


def scaled_classes(cool=1.0, tau=1.0):
    return {
        name: {**c, "cool_k_per_h": tuple(x * cool for x in c["cool_k_per_h"]), "tau_h": tuple(x * tau for x in c["tau_h"])}
        for name, c in C.CLASSES.items()
    }


@pytest.mark.parametrize("cool,tau,expected", [(1.0, 1.0, 13), (0.5, 1.0, 0), (2.0, 1.0, 20), (1.0, 0.5, 0), (1.0, 2.0, 20)])
def test_strom_reihum_depends_strongly_on_the_assumed_rates(monkeypatch, cool, tau, expected):
    """Aus der Aussagenprüfung: „13 von 20“ ist ein Modellwert. Kühlrate und Zeitkonstante je Klasse mit dem Faktor skaliert, sonst Voreinstellung
    (2 Gruppen, 15-Minuten-Slots, 16 °C Tagesmittel). Bei doppelter Kühlrate ist das Band schmaler als ein Kühlschritt (2δ < b): das Thermostat ist
    dann nur noch eine Näherung, der Fall zeigt die Richtung der Abhängigkeit, kein Szenario der Demo."""
    monkeypatch.setattr(C, "CLASSES", scaled_classes(cool, tau))
    s = ev.Settings()
    ok = sum(A.simulate(ev.instance_of(s, seed=seed), "reihum", groups=2, slot_steps=1).in_band for seed in SEEDS)
    assert ok == expected


def test_duty_cycle_and_cap_reduction_by_weather(weather):
    duty = [median(r["duty"] for r in weather[w]["rows"]) for w in WEATHER]
    red = [median(reductions(weather[w]["rows"])) for w in WEATHER]
    assert duty == pytest.approx([0.22, 0.27, 0.34, 0.40, 0.45, 0.58], abs=0.01)
    assert red == pytest.approx([69.6, 63.0, 56.6, 50.0, 44.7, 33.3], abs=0.5)
    assert all(r["cap"] is not None for w in WEATHER for r in weather[w]["rows"])  # in allen 120 Blöcken gibt es eine Grenze, die das Band hält
    assert red == sorted(red, reverse=True)


def test_cap_feasibility_is_monotone_on_a_two_kilowatt_grid():
    s = ev.Settings()
    for seed in SEEDS:
        inst = ev.instance_of(s, seed=seed)
        seen_violation = False
        for cap in np.arange(inst.total_power_kw, 10.0, -2.0):
            ok = A.simulate(inst, "grenze", cap_kw=float(cap)).in_band
            assert not (seen_violation and ok), (seed, cap)
            seen_violation = seen_violation or not ok


def test_continuous_cooling_covers_the_warming_except_in_the_hottest_weather():
    """b_i >= (1 - a_i)(A_max - hi_safe_i) für alle Reefer der 20 Blöcke: in den fünf kühleren Wetterlagen ja, in der heißesten für den ungünstigsten Reefer knapp nicht."""
    worst = []
    for tmean, sun in WEATHER:
        slack = min(
            float((inst.b - (1 - inst.a) * (inst.ambient.max() - inst.hi_safe)).min())
            for inst in (ev.instance_of(ev.Settings(tmean=tmean, sun=sun), seed=seed) for seed in SEEDS)
        )
        worst.append(slack)
    assert all(x > 0 for x in worst[:5])
    assert worst[5] == pytest.approx(-0.04, abs=0.02)


def test_exact_on_off_peak_equals_the_rule_for_four_reefers():
    s = ev.Settings(n=4)
    for seed in SEEDS[:5]:
        inst = ev.instance_of(s, seed=seed)
        exact = A.exact_peak(inst, integer=True, time_limit_s=60.0)
        assert exact.status == "optimal"
        assert A.smallest_cap(inst) == pytest.approx(exact.peak_kw, abs=0.05)
        assert exact.peak_kw in (16.0, 18.0)
