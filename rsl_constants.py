"""Konstanten: Regler-Grenzen, feste Modellannahmen, Farben und Presets.

Alle Modellgrößen (Zeitkonstanten, Kühlrate, Leistung, Temperaturen) sind **eigene Annahmen in plausibler Größenordnung**, keine Messwerte und
nicht an einem Terminal kalibriert. Das Wärmemodell folgt in der Form der Gleichung (1) von van Duin u. a. (TRB 2017, Keep It Cool), die Zahlen
stammen nicht aus dieser Arbeit.
"""

# --- Zeitraster ---------------------------------------------------------------------------------------------------------------------------
DT_H = 0.25            # Schrittweite in Stunden (15 Minuten, das Spitzenraster in Keep It Cool)
HORIZON_H = 24.0       # betrachteter Zeitraum in Stunden
STEPS = int(round(HORIZON_H / DT_H))
START_HOUR = 8.0       # Uhrzeit des ersten Schritts (Anlanden am Vormittag, Hitze am Nachmittag)

# --- Reefer-Klassen (Annahmen) --------------------------------------------------------------------------------------------------------------
# Sollwert in Grad Celsius, Zeitkonstante τ des Auskühlens an die Umgebung in Stunden (Bereich), Kühlrate bei Betrieb in K je Stunde (Bereich),
# elektrische Leistung bei Betrieb in kW.
CLASSES = {
    "gefroren": {"setpoint": -20.0, "tau_h": (36.0, 60.0), "cool_k_per_h": (1.8, 2.4), "power_kw": 10.0},
    "gekühlt": {"setpoint": 2.0, "tau_h": (20.0, 36.0), "cool_k_per_h": (1.8, 2.4), "power_kw": 8.0},
}
AMBIENT_AMPLITUDE_K = 5.0   # Tagesschwankung der Außentemperatur (Spitze um 15 Uhr)
SUN_START_H, SUN_END_H = 6.0, 18.0   # Sonnenzuschlag als Halbsinus zwischen diesen Uhrzeiten

# --- Regler ----------------------------------------------------------------------------------------------------------------------------------
N_MIN, N_MAX, DEFAULT_N = 4, 24, 12
SHARE_MIN, SHARE_MAX, DEFAULT_SHARE = 0, 100, 50           # Anteil gefrorener Reefer in Prozent
BAND_MIN, BAND_MAX, DEFAULT_BAND = 0.5, 3.0, 1.0           # Halbbreite des Regelbands in K
MARGIN_MIN, MARGIN_MAX, DEFAULT_MARGIN = 0.0, 2.0, 0.5     # Reserve über dem Regelband in K (bis dahin ist die Ware noch sicher)
SYNC_MIN, SYNC_MAX, DEFAULT_SYNC = 0, 100, 80              # Anteil der Reefer, die am oberen Bandrand starten, in Prozent
TMEAN_MIN, TMEAN_MAX, DEFAULT_TMEAN = 8, 35, 16            # Tagesmittel der Außentemperatur in Grad Celsius
SUN_MIN, SUN_MAX, DEFAULT_SUN = 0, 10, 2                   # Sonnenzuschlag zur Umgebungstemperatur um 12 Uhr in K
GROUPS_MIN, GROUPS_MAX, DEFAULT_GROUPS = 2, 6, 2           # Gruppen (Racks) der Regel „Strom reihum“
SLOT_MIN, SLOT_MAX, DEFAULT_SLOT = 1, 8, 1                 # Slotlänge in Schritten zu 15 Minuten
CAP_MIN, CAP_MAX, DEFAULT_CAP = 20, 100, 50                # Leistungsgrenze in Prozent der Summe der Betriebsleistungen
SEED_MAX, DEFAULT_SEED = 999999, 17
SWEEP_SEEDS = tuple(range(100000, 100020))                 # feste Instanzen für alle Sweeps: nie ein einzelner Seed als Befund
MARGIN_SWEEP = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0)            # Reserven der Kurve „Spitze gegen Reserve“
SLOT_SWEEP = (1, 2, 4, 8)                                  # Slotlängen der Slot-Tabelle (Schritte zu 15 Minuten)
GROUPS_SWEEP = (2, 3, 4)

EXACT_N_LIMIT = 5      # bis zu dieser Reefer-Zahl rechnet der Tab „Exakt“ (Ein/Aus, Branch-and-Cut) im Browser
EXACT_TIME_LIMIT_S = 30.0
EPS = 1e-9

RULES = ("ungesteuert", "reihum", "grenze")
RULE_LABELS = {
    "ungesteuert": "Ungesteuert (jeder Reefer für sich)",
    "reihum": "Strom reihum (Slots)",
    "grenze": "Leistungsgrenze (dringendster zuerst)",
}
COLOR_RULES = {"ungesteuert": "#8c8c8c", "reihum": "#d98a2b", "grenze": "#2F6B65"}
COLOR_BOUND = "#4c78a8"
COLOR_BAND = "rgba(76,120,168,0.14)"

# Presets setzen nur, was vom Standard abweicht (apply_preset setzt alle übrigen Regler auf den Standard). Die Zahlen in den Hilfetexten sind am
# Zufalls-Seed 17 gemessen und stehen in tests/test_presets.py; die Hilfetexte nennen Seed 17 nicht, weil jedes Preset den Standard-Seed lässt.
PRESETS = {
    "Standardfall (Voreinstellung)": {},
    "Alle gleichzeitig angelandet": {"sync": 100},
    "Ohne Reserve": {"margin": 0.0},
    "Heißer Tag": {"tmean": 32, "sun": 8},
    "Kühler Tag": {"tmean": 8, "sun": 0},
    "Slots zu lang": {"slot": 8},
    "Kühlleistung reicht nicht": {"tmean": 35, "sun": 10, "band": 0.5, "margin": 0.0},
}
PRESET_HELP = {
    "Standardfall (Voreinstellung)": "12 Reefer, 80 % starten am oberen Rand des Regelbands, 16 °C Tagesmittel, 0,5 K Reserve. Ohne Steuerung steigt die Spitze auf 88 kW, die kleinste Leistungsgrenze, die den sicheren Bereich hält, ist 42 kW.",
    "Alle gleichzeitig angelandet": "Alle Reefer starten am oberen Rand des Regelbands, etwa nach dem Anlanden. Ohne Steuerung laufen sie alle zugleich (108 kW), die kleinste Grenze ist 44 kW.",
    "Ohne Reserve": "Ohne Reserve über dem Regelband muss jeder Reefer sofort kühlen, wenn er den Rand erreicht. Die kleinste Grenze (88 kW) liegt dann nicht unter der Spitze ohne Steuerung (88 kW).",
    "Heißer Tag": "32 °C Tagesmittel und 8 K Sonne: die Reefer kühlen im Mittel 61 % der Zeit. Die kleinste Grenze ist 72 kW statt 100 kW Spitze ohne Steuerung; die eingestellte Grenze von 54 kW reicht nicht.",
    "Kühler Tag": "8 °C Tagesmittel ohne Sonne: jeder Reefer kühlt im Mittel nur 22 % der Zeit. Strom reihum in 15-Minuten-Slots hält hier den sicheren Bereich (56 kW), die Leistungsgrenze kommt mit 28 kW aber weiter herunter.",
    "Slots zu lang": "Zwei Gruppen mit Slots von zwei Stunden: die pausierenden Reefer erwärmen sich um bis zu 1,25 K über den sicheren Bereich hinaus.",
    "Kühlleistung reicht nicht": "35 °C Tagesmittel, 10 K Sonne und ein Band von ±0,5 K ohne Reserve: schon ohne Steuerung verlässt ein Reefer den sicheren Bereich, keine Regel für den Strom kann das beheben.",
}

