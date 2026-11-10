"""Kennzahlen, Verdikt-Logik und Sweeps. Verdikte sind reine Funktionen (Art, Text): die App ruft st.<Art>(Text), der Test prüft jede Zahl im Text."""

from dataclasses import dataclass
from statistics import median

import numpy as np

import rsl_algorithm as A
import rsl_constants as C
from rsl_scenario import Instance, make_instance


@dataclass(frozen=True, kw_only=True)
class Settings:
    """Einstellungen; nur mit Namen aufrufbar (ein eingefügtes Feld darf nie still Werte verschieben)."""

    n: int = C.DEFAULT_N
    share: int = C.DEFAULT_SHARE          # Prozent gefrorene Reefer
    band: float = C.DEFAULT_BAND          # Halbbreite des Regelbands in K
    margin: float = C.DEFAULT_MARGIN      # Reserve über dem Regelband in K
    sync: int = C.DEFAULT_SYNC            # Prozent der Reefer, die am oberen Bandrand starten
    tmean: float = C.DEFAULT_TMEAN        # Tagesmittel der Außentemperatur in °C
    sun: float = C.DEFAULT_SUN            # Sonnenzuschlag um 12 Uhr in K
    groups: int = C.DEFAULT_GROUPS        # Gruppen der Regel „Strom reihum“
    slot: int = C.DEFAULT_SLOT            # Slotlänge in Schritten zu 15 Minuten
    cap: int = C.DEFAULT_CAP              # Leistungsgrenze in Prozent der Summe der Betriebsleistungen
    seed: int = C.DEFAULT_SEED


def de(x: float, nd: int = 1) -> str:
    """Zahl mit Dezimalkomma für sichtbare Texte (nur die Zahl wird umformatiert, nie ein ganzer Satz)."""
    return f"{x:.{nd}f}".replace(".", ",")


def instance_of(s: Settings, *, seed: int | None = None, margin: float | None = None) -> Instance:
    return make_instance(s.n, s.share, s.band, s.margin if margin is None else margin, s.sync, s.tmean, s.sun, s.seed if seed is None else seed)


@dataclass(frozen=True, eq=False)
class Analysis:
    settings: Settings
    inst: Instance
    results: dict            # Regel -> A.Result
    cap_kw: float            # eingestellte Leistungsgrenze in kW
    smallest_cap_kw: float | None   # kleinste Grenze, bei der die Regel „grenze“ den sicheren Bereich hält; None = schon ohne Grenze nicht
    lp: A.ExactResult        # untere Schranke der Spitze mit Bruchteilen der Leistung


def reduction_percent(peak: float, reference: float) -> float:
    """Wie viel Prozent der Referenz-Spitze fehlen: 100·(Referenz − Spitze)/Referenz; ohne Referenz-Spitze gibt es nichts zu senken."""
    return 0.0 if reference <= 0 else 100.0 * (reference - peak) / reference


def analyse(s: Settings) -> Analysis:
    inst = instance_of(s)
    cap_kw = s.cap / 100.0 * inst.total_power_kw
    results = {
        "ungesteuert": A.simulate(inst, "ungesteuert"),
        "reihum": A.simulate(inst, "reihum", groups=s.groups, slot_steps=s.slot),
        "grenze": A.simulate(inst, "grenze", cap_kw=cap_kw),
    }
    return Analysis(s, inst, results, cap_kw, A.smallest_cap(inst), A.exact_peak(inst, integer=False))


def sweep_margin(s: Settings, margins=C.MARGIN_SWEEP, seeds=C.SWEEP_SEEDS) -> list[dict]:
    """Spitze gegen Reserve: je Reserve Median, Minimum und Maximum über die festen Instanzen SWEEP_SEEDS (alle anderen Einstellungen wie `s`).

    `uncontrolled`: Spitze ohne Steuerung, `cap`: kleinste Grenze, die den sicheren Bereich hält (Instanzen ohne eine solche Grenze zählen in `none`
    und gehen nicht in den Median ein). `lp`: untere Schranke mit Bruchteilen für die EINGESTELLTE Instanz (ein Seed), nicht gemittelt.
    """
    rows = []
    for margin in margins:
        peaks, caps, none = [], [], 0
        for seed in seeds:
            inst = instance_of(s, seed=seed, margin=margin)
            peaks.append(A.simulate(inst, "ungesteuert").peak_kw)
            cap = A.smallest_cap(inst)
            if cap is None:
                none += 1
            else:
                caps.append(cap)
        lp = A.exact_peak(instance_of(s, margin=margin), integer=False)
        rows.append({
            "margin": margin,
            "uncontrolled": median(peaks),
            "cap": median(caps) if caps else None,
            "low": min(caps) if caps else None,
            "high": max(caps) if caps else None,
            "none": none,
            "lp": lp.peak_kw,
        })
    return rows


def sweep_slots(s: Settings, groups=C.GROUPS_SWEEP, slots=C.SLOT_SWEEP, seeds=C.SWEEP_SEEDS) -> list[dict]:
    """Strom reihum je (Gruppen, Slotlänge): in wie vielen der festen Instanzen bleibt jeder Reefer im sicheren Bereich, mittlere Spitze."""
    insts = [instance_of(s, seed=seed) for seed in seeds]
    rows = []
    for g in groups:
        for slot in slots:
            runs = [A.simulate(inst, "reihum", groups=g, slot_steps=slot) for inst in insts]
            rows.append({
                "groups": g,
                "slot": slot,
                "in_band": sum(r.in_band for r in runs),
                "runs": len(runs),
                "peak": float(np.mean([r.peak_kw for r in runs])),
                "excess": float(np.mean([r.max_excess_k for r in runs])),
            })
    return rows


def duty_cycle(a: Analysis) -> float:
    """Tastverhältnis ohne Steuerung: Anteil der Zeit, den ein Reefer im Mittel kühlt (Energie / (24 h · Summe der Betriebsleistungen))."""
    return a.results["ungesteuert"].energy_kwh / (C.HORIZON_H * a.inst.total_power_kw)


# --- Verdikte (reine Funktionen) -----------------------------------------------------------------------------------------------------------


def verdict_peak(a: Analysis) -> tuple[str, str]:
    """Kernfrage: Wie weit lässt sich die Spitze senken, ohne dass ein Reefer den sicheren Bereich verlässt?"""
    base = a.results["ungesteuert"]
    if not base.in_band:
        if a.lp.peak_kw is None:
            return "warning", (f"Schon ohne Steuerung verlässt ein Reefer den sicheren Bereich (um bis zu {de(base.max_excess_k, 1)} K): die Kühlleistung reicht in diesem Szenario nicht, "
                               "auch mit stufenlos regelbarer Leistung hält kein Plan den Bereich.")
        return "warning", (f"Das einfache Thermostat hält den sicheren Bereich nicht (um bis zu {de(base.max_excess_k, 1)} K), und die Regeln bauen darauf auf. "
                           f"Ein vorausplanender Plan könnte ihn halten; die untere Schranke seiner Spitze ist {de(a.lp.peak_kw, 1)} kW.")
    if a.smallest_cap_kw is None:
        return "warning", "Mit der Regel „Leistungsgrenze“ gibt es keine Grenze, die den sicheren Bereich hält."
    red = reduction_percent(a.smallest_cap_kw, base.peak_kw)
    lp = a.lp.peak_kw
    lp_text = "" if lp is None else f" Selbst mit stufenlos regelbarer Leistung ginge es unter Einhaltung des sicheren Bereichs nicht unter {de(lp, 1)} kW."
    if red >= 20:
        return "success", (f"Mit einer Grenze von **{de(a.smallest_cap_kw, 1)} kW** bleibt jeder Reefer im sicheren Bereich: **{de(red, 0)} % weniger** "
                           f"als die Spitze von {de(base.peak_kw, 1)} kW ohne Steuerung.{lp_text}")
    if red > 0:
        return "info", (f"Die Spitze lässt sich nur um **{de(red, 1)} %** senken ({de(a.smallest_cap_kw, 1)} statt {de(base.peak_kw, 1)} kW): "
                        f"die Reserve oder die Verteilung der Startzeiten lässt wenig Spielraum.{lp_text}")
    return "info", (f"Hier gibt es nichts zu senken: Die kleinste Grenze ({de(a.smallest_cap_kw, 1)} kW) liegt nicht unter der Spitze ohne Steuerung "
                    f"({de(base.peak_kw, 1)} kW).{lp_text}")


def verdict_cap_setting(a: Analysis) -> tuple[str, str]:
    """Verdikt zur eingestellten Leistungsgrenze (Regler): hält sie den sicheren Bereich?"""
    r = a.results["grenze"]
    base = a.results["ungesteuert"]
    if r.in_band:
        return "success", (f"Bei {de(a.cap_kw, 1)} kW Grenze bleibt jeder Reefer im sicheren Bereich; die Spitze ist {de(r.peak_kw, 1)} kW "
                           f"({de(reduction_percent(r.peak_kw, base.peak_kw), 0)} % unter der Spitze ohne Steuerung).")
    return "warning", (f"Bei {de(a.cap_kw, 1)} kW Grenze verlässt mindestens ein Reefer den sicheren Bereich: um bis zu {de(r.max_excess_k, 1)} K, "
                       f"insgesamt {de(r.reefer_hours_out, 1)} Reefer-Stunden außerhalb.")


def verdict_margin(rows: list[dict]) -> tuple[str, str]:
    """Verdikt der Kurve Spitze gegen Reserve: nennt die Werte ohne Reserve und mit der größten Reserve der Kurve."""
    first, last = rows[0], rows[-1]
    if first["cap"] is None or last["cap"] is None:
        return "info", "Für diese Einstellungen gibt es nicht bei jeder Reserve eine Grenze, die den sicheren Bereich hält."
    return "info", (f"Ohne Reserve ({de(first['margin'], 2)} K) braucht die Leistungsgrenze im Median {de(first['cap'], 1)} kW, mit {de(last['margin'], 2)} K Reserve "
                    f"{de(last['cap'], 1)} kW; die Spitze ohne Steuerung liegt im Median bei {de(first['uncontrolled'], 1)} kW. "
                    "Gemessen an den festen Instanzen, alle anderen Regler wie eingestellt.")


def verdict_slots(rows: list[dict]) -> tuple[str, str]:
    """Verdikt der Slot-Tabelle: in wie vielen Fällen hält „Strom reihum“ den sicheren Bereich (Zählung über alle Zellen)."""
    ok = [r for r in rows if r["in_band"] == r["runs"]]
    some = [r for r in rows if r["in_band"] > 0]
    if not some:
        return "warning", f"„Strom reihum“ hält den sicheren Bereich in keiner der {len(rows)} Zellen aus Gruppenzahl und Slotlänge, in keiner Instanz."
    if not ok:
        return "info", (f"„Strom reihum“ hält den sicheren Bereich nur in {len(some)} von {len(rows)} Kombinationen aus Gruppenzahl und Slotlänge, "
                        "und dort nicht in allen Instanzen.")
    return "success", f"„Strom reihum“ hält den sicheren Bereich in {len(ok)} von {len(rows)} Zellen in allen {ok[0]['runs']} Instanzen."
