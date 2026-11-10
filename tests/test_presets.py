"""Presets: Vollständigkeit, gültige Werte, Standard-Preset = Standardeinstellungen; die Zahlen der Hilfetexte am Standard-Seed gemessen."""

import pytest

import rsl_constants as C
import rsl_evaluation as ev
import rsl_presets as P


def settings_of(name):
    return ev.Settings(**C.PRESETS[name])


def test_every_preset_has_help():
    assert set(C.PRESETS) == set(C.PRESET_HELP)
    assert all(C.PRESET_HELP[name] for name in C.PRESETS)


def test_preset_keys_are_known_and_values_inside_the_slider_bounds():
    inverse = {key: state_key for key, state_key in P.PRESET_KEYS.items()}
    for name, preset in C.PRESETS.items():
        for key, value in preset.items():
            lo, hi = P.bounds(inverse[key])
            assert lo <= value <= hi, (name, key)


def test_default_preset_equals_the_default_settings():
    assert settings_of("Standardfall (Voreinstellung)") == ev.Settings()


def test_setting_specs_cover_every_preset_key():
    assert set(P.PRESET_KEYS.values()) == set(P.SETTING_SPECS)


def test_presets_differ_from_each_other():
    assert len({tuple(sorted(p.items())) for p in C.PRESETS.values()}) == len(C.PRESETS)


def test_the_minimum_band_is_at_least_one_cooling_step_wide():
    # das Thermostat setzt voraus, dass 2·δ ≥ b (sonst schließen sich „muss kühlen“ und „würde unterkühlen“ nicht aus)
    longest_step = max(c["cool_k_per_h"][1] for c in C.CLASSES.values()) * C.DT_H
    assert 2 * C.BAND_MIN >= longest_step


@pytest.fixture(scope="module")
def analyses():
    return {name: ev.analyse(settings_of(name)) for name in C.PRESETS}


# Die Zahlen der Hilfetexte (PRESET_HELP), gemessen am Standard-Seed 17.


def test_help_standard_numbers(analyses):
    a = analyses["Standardfall (Voreinstellung)"]
    assert a.results["ungesteuert"].peak_kw == 88.0 and a.smallest_cap_kw == pytest.approx(42.0, abs=0.05)
    assert "88 kW" in C.PRESET_HELP["Standardfall (Voreinstellung)"] and "42 kW" in C.PRESET_HELP["Standardfall (Voreinstellung)"]


def test_help_all_at_once_numbers(analyses):
    a = analyses["Alle gleichzeitig angelandet"]
    assert a.results["ungesteuert"].peak_kw == 108.0 == a.inst.total_power_kw and a.smallest_cap_kw == pytest.approx(44.0, abs=0.05)
    assert "108 kW" in C.PRESET_HELP["Alle gleichzeitig angelandet"] and "44 kW" in C.PRESET_HELP["Alle gleichzeitig angelandet"]


def test_help_without_margin_numbers(analyses):
    a = analyses["Ohne Reserve"]
    assert a.results["ungesteuert"].peak_kw == 88.0 and a.smallest_cap_kw == pytest.approx(88.0, abs=0.05)
    assert C.PRESET_HELP["Ohne Reserve"].count("88 kW") == 2


def test_help_hot_day_numbers(analyses):
    a = analyses["Heißer Tag"]
    assert round(100 * ev.duty_cycle(a)) == 61
    assert a.results["ungesteuert"].peak_kw == 100.0 and a.smallest_cap_kw == pytest.approx(72.0, abs=0.05)
    assert a.cap_kw == 54.0 and not a.results["grenze"].in_band
    help_text = C.PRESET_HELP["Heißer Tag"]
    assert all(s in help_text for s in ("61 %", "72 kW", "100 kW", "54 kW"))


def test_help_cool_day_numbers(analyses):
    a = analyses["Kühler Tag"]
    assert round(100 * ev.duty_cycle(a)) == 22
    assert a.results["reihum"].in_band and a.results["reihum"].peak_kw == 56.0
    assert a.smallest_cap_kw == pytest.approx(28.0, abs=0.05)
    help_text = C.PRESET_HELP["Kühler Tag"]
    assert all(s in help_text for s in ("22 %", "56 kW", "28 kW"))


def test_help_long_slots_numbers(analyses):
    a = analyses["Slots zu lang"]
    assert (a.settings.groups, a.settings.slot * 15) == (2, 120)
    assert not a.results["reihum"].in_band and round(a.results["reihum"].max_excess_k, 2) == 1.25
    r = a.results["reihum"]
    assert round(float((r.temp - a.inst.hi_safe[None, :]).max()), 2) == 1.25  # die Abweichung liegt oberhalb des sicheren Bereichs, nicht darunter
    assert "1,25 K" in C.PRESET_HELP["Slots zu lang"] and "zwei Stunden" in C.PRESET_HELP["Slots zu lang"]


def test_help_not_enough_cooling_numbers(analyses):
    a = analyses["Kühlleistung reicht nicht"]
    assert not a.results["ungesteuert"].in_band and a.smallest_cap_kw is None and a.lp.peak_kw is None
    assert verdict_kind(a) == "warning"


def verdict_kind(a):
    return ev.verdict_peak(a)[0]


def test_every_preset_gives_the_expected_verdict_kind(analyses):
    # Standardfall, gleichzeitig, kühler Tag, heißer Tag: Spitze deutlich gesenkt; ohne Reserve: nichts zu senken; zu heiß: Warnung
    expected = {
        "Standardfall (Voreinstellung)": "success", "Alle gleichzeitig angelandet": "success", "Ohne Reserve": "info",
        "Heißer Tag": "success", "Kühler Tag": "success", "Slots zu lang": "success", "Kühlleistung reicht nicht": "warning",
    }
    assert {name: verdict_kind(a) for name, a in analyses.items()} == expected
