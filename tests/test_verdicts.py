"""Verdikte als reine Funktionen (DEMO-PLAYBOOK §12): Schwellen und jede Zahl im Text an handgesetzten Werten."""

from types import SimpleNamespace as NS

import pytest

import rsl_evaluation as ev


def result(peak=100.0, in_band=True, excess=0.0, hours=0.0):
    return NS(peak_kw=peak, in_band=in_band, max_excess_k=excess, reefer_hours_out=hours)


def analysis(*, base=None, grenze=None, smallest=60.0, lp=55.0, cap_kw=54.0):
    return NS(results={"ungesteuert": base or result(), "grenze": grenze or result(54.0)}, smallest_cap_kw=smallest, lp=NS(peak_kw=lp), cap_kw=cap_kw)


def test_de_formats_with_a_decimal_comma():
    assert ev.de(42.04, 1) == "42,0" and ev.de(0.5, 2) == "0,50" and ev.de(-3.0, 0) == "-3"


def test_reduction_percent_and_the_zero_reference():
    assert ev.reduction_percent(60.0, 100.0) == pytest.approx(40.0)
    assert ev.reduction_percent(120.0, 100.0) == pytest.approx(-20.0)
    assert ev.reduction_percent(5.0, 0.0) == 0.0


def test_peak_verdict_success_names_every_number():
    kind, text = ev.verdict_peak(analysis())
    assert kind == "success"
    assert "**60,0 kW**" in text and "**40 % weniger**" in text and "100,0 kW" in text and "55,0 kW" in text


def test_peak_verdict_threshold_at_twenty_percent():
    assert ev.verdict_peak(analysis(smallest=80.0))[0] == "success"   # genau 20 %
    kind, text = ev.verdict_peak(analysis(smallest=80.5))             # 19,5 %
    assert kind == "info" and "**19,5 %**" in text and "80,5 statt 100,0 kW" in text


def test_peak_verdict_without_any_reduction():
    kind, text = ev.verdict_peak(analysis(smallest=100.0))
    assert kind == "info" and "nichts zu senken" in text and "100,0 kW" in text
    kind, text = ev.verdict_peak(analysis(smallest=110.0))
    assert kind == "info" and "nichts zu senken" in text


def test_peak_verdict_when_the_lower_bound_is_missing():
    kind, text = ev.verdict_peak(analysis(lp=None))
    assert kind == "success" and "stufenlos" not in text


def test_peak_verdict_when_the_cooling_power_is_not_enough_even_for_a_fractional_plan():
    kind, text = ev.verdict_peak(analysis(base=result(in_band=False, excess=2.46), lp=None))
    assert kind == "warning" and "um bis zu 2,5 K" in text and "hält kein Plan den Bereich" in text


def test_peak_verdict_when_only_the_simple_thermostat_fails_but_a_plan_could_hold_the_band():
    # Fehler aus der unabhängigen Aussagenprüfung: „keine Regel kann das beheben“ stand auch dort, wo die LP zulässig ist
    kind, text = ev.verdict_peak(analysis(base=result(in_band=False, excess=0.007), lp=22.0))
    assert kind == "warning"
    assert "Das einfache Thermostat hält den sicheren Bereich nicht (um bis zu 0,0 K)" in text and "22,0 kW" in text
    assert "kein Plan" not in text and "keine Regel" not in text


def test_peak_verdict_without_a_cap_that_holds_the_band():
    kind, text = ev.verdict_peak(analysis(smallest=None))
    assert kind == "warning" and "keine Grenze" in text


def test_cap_setting_verdict_held_and_violated():
    kind, text = ev.verdict_cap_setting(analysis(grenze=result(54.0), cap_kw=54.0))
    assert kind == "success" and "54,0 kW Grenze" in text and "46 % unter" in text
    kind, text = ev.verdict_cap_setting(analysis(grenze=result(54.0, in_band=False, excess=2.95, hours=31.25), cap_kw=54.0))
    assert kind == "warning" and "bis zu 3,0 K" in text and "31,2 Reefer-Stunden" in text


def rows(first_cap=90.0, last_cap=34.0):
    return [{"margin": 0.0, "cap": first_cap, "uncontrolled": 98.0}, {"margin": 2.0, "cap": last_cap, "uncontrolled": 98.0}]


def test_margin_verdict_names_first_and_last_value():
    kind, text = ev.verdict_margin(rows())
    assert kind == "info" and "(0,00 K)" in text and "90,0 kW" in text and "2,00 K Reserve 34,0 kW" in text and "98,0 kW" in text


def test_margin_verdict_when_a_cap_is_missing():
    assert "nicht bei jeder Reserve" in ev.verdict_margin(rows(first_cap=None))[1]
    assert "nicht bei jeder Reserve" in ev.verdict_margin(rows(last_cap=None))[1]


def slot_rows(counts):
    return [{"groups": 2, "slot": i + 1, "in_band": c, "runs": 20, "peak": 50.0, "excess": 0.0} for i, c in enumerate(counts)]


def test_slots_verdict_three_cases_with_counts():
    kind, text = ev.verdict_slots(slot_rows([0, 0, 0]))
    assert kind == "warning" and "keiner der 3 Zellen" in text
    kind, text = ev.verdict_slots(slot_rows([0, 5, 20]))
    assert kind == "success" and "1 von 3 Zellen" in text and "allen 20 Instanzen" in text
    kind, text = ev.verdict_slots(slot_rows([0, 5, 12]))
    assert kind == "info" and "2 von 3 Kombinationen" in text and "nicht in allen" in text
