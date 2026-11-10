"""Szenario: ein Reefer-Block über 24 Stunden in 15-Minuten-Schritten.

Jeder Reefer hat eine Innentemperatur T, einen Sollwert mit Band ±δ, eine Zeitkonstante τ des Auskühlens an die Umgebung und eine Kühlrate bei
Betrieb. Die Umgebungstemperatur folgt einem Tagesgang mit Sonnenzuschlag. Alles deterministisch aus (Einstellungen, Zufalls-Seed).
"""

from dataclasses import dataclass

import numpy as np

import rsl_constants as C


@dataclass(frozen=True, eq=False)
class Instance:
    """Reefer-Block. Alle Felder sind Arrays über die Reefer (Länge n) bzw. über die Schritte (ambient, Länge STEPS)."""

    frozen: np.ndarray        # bool: gefroren (sonst gekühlt)
    setpoint: np.ndarray      # Sollwert in °C
    band: float               # Halbbreite des Regelbands in K (für alle gleich): dort hält das Thermostat die Temperatur
    margin: float             # Reserve in K oberhalb des Regelbands: bis dahin gilt die Ware noch als sicher
    tau_h: np.ndarray         # Zeitkonstante in Stunden
    cool_k_per_h: np.ndarray  # Kühlrate bei Betrieb in K je Stunde
    power_kw: np.ndarray      # elektrische Leistung bei Betrieb in kW
    t0: np.ndarray            # Starttemperatur in °C
    ambient: np.ndarray       # wirksame Umgebungstemperatur je Schritt in °C (Länge STEPS)

    @property
    def n(self) -> int:
        return len(self.setpoint)

    @property
    def lo(self) -> np.ndarray:
        return self.setpoint - self.band

    @property
    def hi(self) -> np.ndarray:
        return self.setpoint + self.band

    @property
    def hi_safe(self) -> np.ndarray:
        """Obere Grenze, bis zu der die Ware sicher ist: Regelband plus Reserve. Nach unten gibt es keine Reserve (kein Unterkühlen)."""
        return self.setpoint + self.band + self.margin

    @property
    def a(self) -> np.ndarray:
        """Faktor je Schritt, mit dem die Temperatur ohne Kühlung zur Umgebung hin relaxiert: T' = a·T + (1 − a)·A."""
        return np.exp(-C.DT_H / self.tau_h)

    @property
    def b(self) -> np.ndarray:
        """Abkühlung in K je Schritt bei Betrieb."""
        return self.cool_k_per_h * C.DT_H

    @property
    def total_power_kw(self) -> float:
        return float(self.power_kw.sum())


def ambient_profile(t_mean: float, sun: float) -> np.ndarray:
    """Wirksame Umgebungstemperatur je Schritt: Mittel + Tagesgang (Spitze 15 Uhr) + Sonnenzuschlag als Halbsinus zwischen 6 und 18 Uhr."""
    hours = (C.START_HOUR + np.arange(C.STEPS) * C.DT_H) % 24.0
    daily = C.AMBIENT_AMPLITUDE_K * np.sin(2 * np.pi * (hours - 9.0) / 24.0)
    in_sun = (hours >= C.SUN_START_H) & (hours <= C.SUN_END_H)
    sunny = np.where(in_sun, np.sin(np.pi * (hours - C.SUN_START_H) / (C.SUN_END_H - C.SUN_START_H)), 0.0)
    return t_mean + daily + sun * sunny


def make_instance(n: int, share_frozen: int, band: float, margin: float, sync: int, t_mean: float, sun: float, seed: int) -> Instance:
    """Deterministisch aus den Einstellungen: gleiche Eingabe, gleiche Instanz.

    `share_frozen` und `sync` in Prozent. Die Zahl gefrorener Reefer ist round(n · share), die Zahl der am oberen Bandrand startenden
    Reefer round(n · sync); welche es sind, entscheidet der Zufalls-Seed.
    """
    rng = np.random.default_rng(seed)
    n_frozen = int(round(n * share_frozen / 100.0))
    frozen = np.zeros(n, dtype=bool)
    frozen[rng.permutation(n)[:n_frozen]] = True
    cls = [C.CLASSES["gefroren" if f else "gekühlt"] for f in frozen]
    setpoint = np.array([c["setpoint"] for c in cls])
    power = np.array([c["power_kw"] for c in cls])
    tau = np.array([rng.uniform(*c["tau_h"]) for c in cls])
    cool = np.array([rng.uniform(*c["cool_k_per_h"]) for c in cls])
    n_sync = int(round(n * sync / 100.0))
    at_top = np.zeros(n, dtype=bool)
    at_top[rng.permutation(n)[:n_sync]] = True
    inside = np.array([rng.uniform(-band, band) for _ in range(n)])
    t0 = np.where(at_top, setpoint + band, setpoint + inside)
    return Instance(frozen, setpoint, float(band), float(margin), tau, cool, power, t0, ambient_profile(float(t_mean), float(sun)))
