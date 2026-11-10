"""Kern gegen Handrechnung (DEMO-PLAYBOOK §1b): Wärmeschritt, Thermostat, Slots, Leistungsgrenze, Kennzahlen."""

import math

import numpy as np
import pytest

import rsl_algorithm as A
import rsl_constants as C
from conftest import build


def test_one_cooling_step_by_hand(short):
    # a = exp(-0,25 / 24); T1 = a·T0 + (1 − a)·A − b·u mit T0 = 1 (oberer Rand), A = 20, b = 2,0 K/h · 0,25 h = 0,5
    a = math.exp(-0.25 / 24.0)
    inst = build(1)
    r = A.simulate(inst, "ungesteuert")
    assert r.u[0, 0]  # im nächsten Schritt ohne Kühlung wäre T = a + (1 − a)·20 ≈ 1,197 > 1: das Thermostat schaltet an
    assert r.temp[1, 0] == pytest.approx(a * 1.0 + (1 - a) * 20.0 - 0.5, abs=1e-12)
    assert r.temp[1, 0] == pytest.approx(0.6969, abs=5e-5)


def test_replay_reproduces_the_simulated_temperatures(short):
    inst = build(3, t0=[0.2, -0.5, 1.0], tau=[20.0, 30.0, 25.0])
    r = A.simulate(inst, "ungesteuert")
    assert np.allclose(A.replay(inst, r.u), r.temp, atol=1e-12)


def test_no_cooling_when_the_ambient_equals_the_setpoint_edge(short):
    # Umgebung = oberer Rand: ohne Kühlung bleibt T = 1 (Grenze inklusive, nicht darüber): nie Strom, Band bleibt gehalten
    inst = build(1, ambient=1.0)
    r = A.simulate(inst, "ungesteuert")
    assert not r.u.any() and r.peak_kw == 0.0 and r.energy_kwh == 0.0
    assert r.in_band and r.max_above_control_k == 0.0


def test_thermostat_stays_on_until_one_more_step_would_leave_the_band(short):
    # T0 = 1, A = 20: es kühlt Schritt für Schritt (0,6969; 0,3975 ...), bis ein weiterer Schritt unter −1 führen würde, dann aus
    inst = build(1, steps=6)
    r = A.simulate(inst, "ungesteuert")
    assert r.u[:, 0].tolist() == [True] * 6  # in sechs Schritten (1,5 h) erreicht keine Kühlung die Untergrenze −1
    assert r.in_band


def test_cooling_stops_at_the_lower_edge(monkeypatch):
    monkeypatch.setattr(C, "STEPS", 12)
    inst = build(1, steps=12, cool=8.0)  # b = 2,0 K je Schritt: Band ist 2·δ = 2,0 K breit (Grenzfall 2δ = b)
    r = A.simulate(inst, "ungesteuert")
    assert r.in_band
    assert not r.u.all()  # nach einem Schritt Kühlung würde der nächste unter −1 führen: das Thermostat schaltet ab


def test_slots_give_power_to_one_group_at_a_time(short):
    inst = build(4, ambient=40.0, margin=3.0)
    r = A.simulate(inst, "reihum", groups=2, slot_steps=1)
    assert not (r.u[0, [1, 3]]).any() and not (r.u[1, [0, 2]]).any()  # Schritt 0: nur Gruppe 0 (Reefer 0, 2), Schritt 1: nur Gruppe 1
    assert r.u[0, [0, 2]].all()


def test_slot_length_two_holds_the_group_for_two_steps(short):
    inst = build(2, ambient=40.0, margin=3.0)
    r = A.simulate(inst, "reihum", groups=2, slot_steps=2)
    assert r.u[:2, 0].all() and not r.u[:2, 1].any()
    assert r.u[2:4, 1].all() and not r.u[2:4, 0].any()


def test_cap_grants_the_most_urgent_reefer_first(short):
    # zwei Reefer wollen kühlen, die Grenze reicht für einen; der mit der kleineren Reserve zur sicheren Obergrenze (heißere Umgebung/Start) bekommt Strom
    inst = build(2, t0=[0.2, 1.0], ambient=20.0)
    r = A.simulate(inst, "grenze", cap_kw=10.0)
    assert r.u[0].tolist() == [False, True]
    assert r.peak_kw <= 10.0


def test_cap_rule_never_exceeds_the_cap(short):
    inst = build(5, t0=[1.0, 0.9, 1.0, 0.5, 1.0], ambient=25.0)
    for cap in (10.0, 20.0, 35.0):
        assert A.simulate(inst, "grenze", cap_kw=cap).peak_kw <= cap + 1e-9


def test_cap_at_the_total_power_equals_uncontrolled(short):
    inst = build(4, t0=[1.0, 0.8, 0.4, 1.0], ambient=25.0)
    free = A.simulate(inst, "ungesteuert")
    capped = A.simulate(inst, "grenze", cap_kw=inst.total_power_kw)
    assert np.array_equal(free.u, capped.u)


def test_unknown_rule_and_missing_cap_raise(short):
    inst = build(1)
    with pytest.raises(ValueError):
        A.simulate(inst, "gibt-es-nicht")
    with pytest.raises(ValueError):
        A.simulate(inst, "grenze")


def test_metrics_peak_energy_and_excess_by_hand(short):
    inst = build(2, power=[10.0, 6.0])
    u = np.array([[1, 0], [1, 1], [0, 1], [0, 0], [0, 0], [0, 0]], dtype=bool)
    r = A.evaluate(inst, "ungesteuert", u, A.replay(inst, u))
    assert r.power_kw.tolist() == [10.0, 16.0, 6.0, 0.0, 0.0, 0.0]
    assert r.peak_kw == 16.0
    assert r.energy_kwh == pytest.approx(32.0 * 0.25)  # (10 + 16 + 6) kW · 0,25 h


def test_excess_counts_only_beyond_the_safe_upper_limit(short):
    # T0 = 1 (oberer Rand), A = 41, kein Strom: ohne Kühlung steigt T; Reserve 0,5 → sicher bis 1,5
    inst = build(1, ambient=41.0)
    u = np.zeros((6, 1), dtype=bool)
    r = A.evaluate(inst, "ungesteuert", u, A.replay(inst, u))
    assert r.max_above_control_k == pytest.approx(r.temp.max() - 1.0)
    assert r.max_excess_k == pytest.approx(r.temp.max() - 1.5)
    assert not r.in_band and r.reefer_hours_out > 0


def test_instance_geometry_properties():
    inst = build(2, setpoint=[-20.0, 2.0], band=1.0, margin=0.5)
    assert inst.lo.tolist() == [-21.0, 1.0]
    assert inst.hi.tolist() == [-19.0, 3.0]
    assert inst.hi_safe.tolist() == [-18.5, 3.5]
    assert inst.b.tolist() == [0.5, 0.5]
