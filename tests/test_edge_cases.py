"""Randfälle (DEMO-PLAYBOOK §12): ein und zwei Reefer, Grenze 0, Gruppen größer als der Block, Reglerränder, Gleichstand, inklusive Grenze."""

import numpy as np
import pytest

import rsl_algorithm as A
import rsl_constants as C
import rsl_evaluation as ev
from rsl_scenario import make_instance


@pytest.mark.parametrize("n", [1, 2, 3])
def test_tiny_blocks_run_under_every_rule(n):
    inst = make_instance(n, 50, 1.0, 0.5, 80, 16, 2, 7)
    for rule in C.RULES:
        r = A.simulate(inst, rule, groups=2, slot_steps=1, cap_kw=inst.total_power_kw)
        assert r.u.shape == (C.STEPS, n) and np.isfinite(r.temp).all()
    assert A.exact_peak(inst, integer=False).peak_kw is not None


def test_a_single_reefer_with_a_cap_below_its_power_never_cools():
    inst = make_instance(1, 0, 1.0, 0.5, 100, 16, 2, 7)
    r = A.simulate(inst, "grenze", cap_kw=inst.power_kw[0] - 0.01)
    assert not r.u.any() and r.peak_kw == 0.0 and not r.in_band  # ohne Kühlung steigt die Temperatur über den sicheren Bereich


def test_cap_zero_holds_nothing_but_runs():
    inst = make_instance(6, 50, 1.0, 0.5, 80, 16, 2, 7)
    r = A.simulate(inst, "grenze", cap_kw=0.0)
    assert r.peak_kw == 0.0 and not r.in_band and r.reefer_hours_out > 0


def test_more_groups_than_reefers_leaves_some_slots_empty():
    inst = make_instance(3, 50, 1.0, 0.5, 80, 16, 2, 7)
    r = A.simulate(inst, "reihum", groups=6, slot_steps=1)
    assert np.isfinite(r.temp).all()
    assert not r.u[3:6].any()  # die Gruppen 3 bis 5 haben keinen Reefer: in diesen Schritten fließt kein Strom


def test_slot_longer_than_the_horizon_gives_the_first_group_all_the_power():
    inst = make_instance(4, 50, 1.0, 0.5, 80, 16, 2, 7)
    r = A.simulate(inst, "reihum", groups=2, slot_steps=C.STEPS * 2)
    assert not r.u[:, [1, 3]].any()  # Gruppe 1 bekommt nie Strom


def test_share_and_sync_at_the_ends_of_their_ranges():
    for share in (0, 100):
        inst = make_instance(8, share, 1.0, 0.5, 100, 16, 2, 7)
        assert bool(inst.frozen.all()) == (share == 100) and bool((~inst.frozen).all()) == (share == 0)
        assert np.allclose(inst.t0, inst.hi)  # sync 100 %: alle starten genau am oberen Rand des Regelbands
    inst = make_instance(8, 50, 1.0, 0.5, 0, 16, 2, 7)
    assert (inst.t0 <= inst.hi).all() and (inst.t0 >= inst.lo).all() and not np.allclose(inst.t0, inst.hi)


def test_every_setting_at_its_extreme_runs_without_error():
    specs = {"n": (C.N_MIN, C.N_MAX), "share": (C.SHARE_MIN, C.SHARE_MAX), "band": (C.BAND_MIN, C.BAND_MAX), "margin": (C.MARGIN_MIN, C.MARGIN_MAX),
             "sync": (C.SYNC_MIN, C.SYNC_MAX), "tmean": (C.TMEAN_MIN, C.TMEAN_MAX), "sun": (C.SUN_MIN, C.SUN_MAX), "groups": (C.GROUPS_MIN, C.GROUPS_MAX),
             "slot": (C.SLOT_MIN, C.SLOT_MAX), "cap": (C.CAP_MIN, C.CAP_MAX)}
    for key, edge_values in specs.items():
        for value in edge_values:
            a = ev.analyse(ev.Settings(**{key: value}))
            assert set(a.results) == set(C.RULES), (key, value)
            assert ev.verdict_peak(a)[1] and ev.verdict_cap_setting(a)[1]


def test_no_effect_case_has_no_division_by_zero():
    # kein Strom nötig (Umgebung gleich Sollwert-Obergrenze): Spitze 0 überall, alle Verdikte laufen durch, Reduktion 0 statt Division durch 0
    a = ev.analyse(ev.Settings(tmean=C.TMEAN_MIN, sun=0, share=0))
    r = ev.reduction_percent(0.0, 0.0)
    assert r == 0.0
    assert ev.verdict_peak(a)[0] in ("success", "info", "warning")


def test_upper_edge_is_inclusive_for_the_thermostat():
    # Ambient = oberer Rand des Regelbands, Start am oberen Rand: es wird nicht gekühlt (Gleichheit zählt nicht als Überschreitung)
    from conftest import build

    inst = build(1, steps=C.STEPS, ambient=1.0)
    r = A.simulate(inst, "ungesteuert")
    assert not r.u.any() and r.max_above_control_k == 0.0


def test_ties_in_the_cap_rule_go_to_the_smaller_index():
    from conftest import build

    inst = build(3, steps=C.STEPS, ambient=20.0)  # drei gleiche Reefer, gleiche Dringlichkeit, Grenze für einen
    r = A.simulate(inst, "grenze", cap_kw=10.0)
    assert r.u[0].tolist() == [True, False, False]


def test_the_same_settings_give_the_same_block():
    a = make_instance(12, 50, 1.0, 0.5, 80, 16, 2, 99)
    b = make_instance(12, 50, 1.0, 0.5, 80, 16, 2, 99)
    assert np.array_equal(a.t0, b.t0) and np.array_equal(a.tau_h, b.tau_h) and np.array_equal(a.frozen, b.frozen)
    c = make_instance(12, 50, 1.0, 0.5, 80, 16, 2, 100)
    assert not np.array_equal(a.tau_h, c.tau_h)
