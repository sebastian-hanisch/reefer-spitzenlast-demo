# Reefer-Spitzenlast: Wie lange darf der Strom pausieren? – Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-reefer-spitzenlast-demo.streamlit.app/)**

Interaktive Fall-Demo zu **Kühlcontainern (Reefern) im Block** über 24 Stunden: Viele Reefer kühlen gleichzeitig, der Block zieht eine hohe **Spitze**, und viele Stromversorger rechnen nach der höchsten Spitze
ab. Die Demo beantwortet: **Wie weit lässt sich die Spitze senken, ohne dass die Ware wärmer wird, als es sicher ist, und welche Regel für den Strom holt wie viel davon heraus?**

Teil des Portfolios für die Website „Sebastian Hanisch – Operations Research und Machine Learning“, Zusatz zur Hafen-Linie. Das Gegenstück zur [Reefer-Demo](https://sebastianhanisch-reefer-demo.streamlit.app/): dort die Frage, *welcher Stellplatz* für
welchen Container (Steckdosen-Puffer im Block), hier die Frage, *wie lange der Strom pausieren darf*, wenn die Reefer schon am Strom stehen. Die beiden Demos teilen nur den Anlass, kein Modell.

## Warum dieses Problem

Laut van Duin u. a. (Keep it cool, TRB 2017) erheben Stromversorger Zusatzkosten auf die höchste gemessene Spitze; die Arbeit testet dafür zwei Regeln in einer Simulation: Strom reihum auf Racks und eine Leistungsgrenze.
Naheliegend ist, die Spitze einfach zu deckeln. Gemessen ist das **ohne Reserve kaum wirksam** (Median 8 %): Wer am oberen Rand seines Temperaturbands startet, muss sofort kühlen. Schon **0,25 K Reserve** über dem Regelband
verändern das Bild (Tabelle unten). Dazwischen liegt die eigentliche Frage: Wie viel Reserve, welche Regel, und wo ist die Grenze dessen, was überhaupt möglich ist?

## Modell

Je Reefer eine Innentemperatur *T*, ein Sollwert mit **Regelband** ±δ und eine **Reserve** *m* nach oben (bis dahin gilt die Ware als sicher; nach unten gibt es keine Reserve). Schritte zu 15 Minuten, 24 Stunden, der Start um 8 Uhr.
Ohne Kühlung relaxiert die Temperatur zur Umgebung, mit Kühlung sinkt sie um eine feste Rate:

*T*(t+1) = *a*·*T*(t) + (1 − *a*)·*A*(t) − *b*·*u*(t),  *a* = exp(−Δt/τ),  *b* = Kühlrate·Δt,

*u* ∈ {0, 1} ist „bekommt Strom und kühlt“, *A* die Umgebung (Tagesmittel ohne Sonnenzuschlag, ±5 K Tagesgang mit Spitze um 15 Uhr, Sonnenzuschlag als Halbsinus zwischen 6 und 18 Uhr). Die Form folgt Gleichung (1) von van Duin u. a. für die
Erwärmung ohne Strom; **die Zahlenwerte sind eigene Annahmen** (siehe „Ehrliche Grenzen“). Zwei Klassen: gefroren (Sollwert −20 °C, 10 kW bei Betrieb) und gekühlt (+2 °C, 8 kW). Zeitkonstanten, Kühlraten und Starttemperaturen
sind je Reefer aus dem Zufalls-Seed gezogen; ein einstellbarer Anteil startet genau am oberen Rand des Regelbands (etwa nach dem Anlanden). Formal im Expander „📐 Mathematische Formulierung“.

## Methodik – drei Regeln, eine Schranke, ein exakter Plan

Alle Regeln haben dasselbe vorausschauende **Thermostat** (an, wenn die Temperatur im nächsten Schritt ohne Kühlung über dem Regelband läge; aus, wenn ein Schritt Kühlung unter das Band führen würde). Sie unterscheiden sich darin, **wer Strom bekommt**:

- **Ungesteuert:** jeder Reefer nach seinem Thermostat; die Spitze ergibt sich aus der Gleichzeitigkeit.
- **Strom reihum:** die Reefer in Gruppen (Nummer mod Gruppenzahl), je Slot hat eine Gruppe Strom (die erste Regel aus Keep it cool, dort mit Slots von 5 und 15 Minuten).
- **Leistungsgrenze:** die Summe der Leistungen darf eine Grenze nicht überschreiten; wollen mehr Reefer kühlen, bekommen die mit der geringsten Reserve zur sicheren Obergrenze zuerst Strom (angelehnt an die zweite Regel aus Keep it cool; die Reihenfolge nach Reserve ist hier eine eigene Annahme).
- **Untere Schranke (LP):** Dürfte jeder Reefer mit einem Bruchteil seiner Leistung laufen, ist die kleinste Spitze ein lineares Programm (`scipy.optimize.milp`, HiGHS). Sie ist eine untere Schranke für jeden Plan dieses Modells, der den sicheren Bereich einhält, auch für Ein/Aus-Pläne; Regeln, die den Bereich verletzen, können darunter liegen (etwa „Strom reihum“ mit 3 bis 6 Gruppen bei Zufalls-Seed 17).
- **Exakter Ein/Aus-Plan (MILP):** dasselbe Programm mit ganzzahligem *u*; im Browser bis fünf Reefer (30 Sekunden Zeitlimit, das Ergebnis nennt den Status; bei Zeitlimit nur die beste gefundene Spitze und die bewiesene Untergrenze).
- **Kleinste Grenze:** die kleinste Grenze, bei der die Regel „Leistungsgrenze“ den sicheren Bereich hält, per Bisektion auf 0,05 kW genau (Annahme: hält sie bei einer Grenze, dann auch bei jeder größeren; 0 Verstöße auf einem 2-kW-Gitter in 20 Blöcken, siehe Tabelle).

## Befunde (gemessen, keine Behauptungen)

Alle Zahlen: Median über die 20 festen Blöcke `SWEEP_SEEDS`, Standard (12 Reefer, 50 % gefroren, Band ±1 K, 80 % starten am Rand, 16 °C Tagesmittel, 2 K Sonne, 0,5 K Reserve, 2 Gruppen, 15-Minuten-Slots), soweit nichts anderes steht.
Die Spalte „Test“ nennt die Funktion in `tests/test_claims.py` (Band oder exakt, wie angegeben).

| Frage | Befund | Test |
|---|---|---|
| **Wie hoch ist die Spitze ohne Steuerung?** | **98 kW** von 108 kW Summe der Betriebsleistungen (91 %); die Reefer kühlen im Median 34 % der Zeit (das **Tastverhältnis**: Energie durch 24 Stunden mal Summe der Betriebsleistungen, also leistungsgewichtet über den Block, ein Wert je Block), im Mittel je Reefer 3,05 kW (2,76 bis 3,42 kW). | `test_the_peak_without_control_is_most_of_the_connected_power`, `test_mean_power_per_reefer_without_control` (Bänder) |
| **Hält das Thermostat allein den sicheren Bereich?** | Ja, in allen 20 Blöcken bei jeder der fünf Reserven (0 bis 2 K). | `test_the_thermostat_alone_keeps_every_reefer_inside_the_safe_range` |
| **Hilft die Leistungsgrenze ohne Reserve?** | Kaum: die kleinste Grenze liegt im Median **8 %** unter der Spitze ohne Steuerung (Bereich 0 bis 17 %). | `test_without_reserve_the_cap_rule_barely_helps` (Band ±0,5) |
| **Was bringt schon wenig Reserve?** | 0,25 K: **56 %** weniger (Bereich 50 bis 62 %), 0,5 K: **57 %**; 1 K: 61 %, 2 K: 64 %. Der Sprung liegt zwischen 0 und 0,25 K, danach wächst es langsam. | `test_a_quarter_kelvin_of_reserve_removes_about_half_of_the_peak`, `test_more_reserve_helps_only_slowly` (Bänder) |
| **Wie weit ist die Regel von der unteren Schranke?** | Mit 0,5 K Reserve liegt die kleinste Grenze im Median **16 %** über der Schranke (Bereich 10 bis 23 %); ohne Reserve **138 %** (mindestens 106 %). In allen 100 Fällen (5 Reserven × 20 Blöcke) liegt sie nicht darunter. | `test_the_cap_rule_never_beats_the_lower_bound_and_the_gap_is_measured` (Bänder) |
| **Ist die Regel bei kleinen Blöcken optimal?** | Bei **vier** Reefern gleich der exakten Ein/Aus-Spitze in 5 von 5 Blöcken (16 oder 18 kW, Abweichung höchstens 0,05 kW). | `test_exact_on_off_peak_equals_the_rule_for_four_reefers` |
| **Reicht „Strom reihum“?** | Mit 2 Gruppen und 15-Minuten-Slots hält jeder Reefer den sicheren Bereich in **13 von 20** Blöcken, mit 30 Minuten in 10 von 20, mit einer Stunde oder länger in 0 von 20; mit 3 oder 4 Gruppen in 0 von 20 bei jeder Slotlänge. **Der Wert hängt stark an den angenommenen Kühlraten und Zeitkonstanten:** mit halber Kühlrate 0 von 20, mit doppelter 20 von 20; mit halber Zeitkonstante 0 von 20, mit doppelter 20 von 20 (bei doppelter Kühlrate ist das Band schmaler als ein Kühlschritt, der Fall zeigt nur die Richtung). Nur 2 von 12 Kombinationen hatten mindestens einen Treffer. Die Spitze ist bei 2 Gruppen im Mittel 55 kW. | `test_slot_table_counts` (Zählung exakt, Spitzen Band ±0,2), `test_strom_reihum_depends_strongly_on_the_assumed_rates` (Zählung exakt) |
| **Wann reicht „Strom reihum“?** | Bei 2 Gruppen und 15-Minuten-Slots nur an kühlen Tagen: in 20 von 20 Blöcken bei 8 und 12 °C Tagesmittel (ohne Sonne), in 13 bei 16 °C (2 K Sonne), in 3 bei 20 °C (3 K), in 0 bei 24 °C (4 K) und 32 °C (8 K); Tastverhältnis 0,22 / 0,27 / 0,34 / 0,40 / 0,45 / 0,58. | `test_strom_reihum_works_only_on_cool_days`, `test_duty_cycle_and_cap_reduction_by_weather` |
| **Und die Leistungsgrenze bei dem Wetter?** | Senkt die Spitze im Median um 70 / 63 / 57 / 50 / 45 / 33 % (gleiche sechs Wetterlagen); in allen 120 Blöcken gibt es eine Grenze, die das Band hält. | `test_duty_cycle_and_cap_reduction_by_weather` (Band ±0,5) |
| **Gleicht die Kühlung die Erwärmung aus?** | Bedingung b_i ≥ (1 − a_i)(A_max − s_i − δ − m) (Kühlung je Schritt mindestens so groß wie die Erwärmung bei der höchsten Umgebungstemperatur an der sicheren Obergrenze): in den fünf kühleren Wetterlagen für alle Reefer aller 20 Blöcke erfüllt, in der heißesten (32 °C, 8 K Sonne) verfehlt sie der ungünstigste Reefer um etwa 0,04 K je Schritt; die Leistungsgrenze hielt das Band trotzdem in allen 20 Blöcken (Deutung: die höchste Umgebungstemperatur liegt nur kurz an). | `test_continuous_cooling_covers_the_warming_except_in_the_hottest_weather` (Band ±0,02) |
| **Ist „hält bei Grenze G“ monoton in G?** | Ja auf einem 2-kW-Gitter von der Summe bis 10 kW: 0 Verstöße in 20 Blöcken. | `test_cap_feasibility_is_monotone_on_a_two_kilowatt_grid` |

**Messungen dieser README, nicht im Test** (zu langsam für die Suite): Bei **sechs** Reefern (Standardeinstellungen, die drei ersten festen Blöcke) braucht der exakte Ein/Aus-Plan auf dem Entwicklungsrechner 5 bis 60 Sekunden (einmal das Zeitlimit; maschinenabhängig, ein Nachlauf des Aussagenprüfers: 7 bis 60 Sekunden); die Spitze ist 24,0 kW
(zweimal bewiesen optimal, einmal nur beste gefundene Lösung mit bewiesener Untergrenze 19,0 kW nach 60 Sekunden, der Wert hängt von der Rechenzeit ab). Die kleinste Grenze der Regel ist dort 24,02 / 24,02 / 26,02 kW; in einem von drei Blöcken liegt die Regel also
**8 % über** dem Optimum. Bei fünf Reefern (sieben Blöcke) war sie wieder gleich (18 kW); die Rechenzeit lag zwischen 0,3 und 16 Sekunden (maschinenabhängig, im Nachlauf 0,4 bis 19,7), deshalb endet der Tab bei fünf.

## Ehrliche Grenzen

- **Eigene Größenordnungen, keine Messdaten.** Zeitkonstanten 20 bis 60 Stunden, Kühlrate 1,8 bis 2,4 K je Stunde, Betriebsleistung 10 kW (gefroren) und 8 kW (gekühlt) sind nicht an einem Terminal kalibriert. Die mittlere Leistung je Reefer
  (3,05 kW im Standard) liegt unter den 7,4 bis 7,7 kW, die Budiyanto und Shinoda (IJTech 2017) an einem Stapel aus drei Reefern in Fukuoka gemessen haben (ausgewertet ein Tag, der 22.10.2015; der Abstract nennt Sommer 2015; die Mittelungsbasis steht im Text nicht, der Vergleich mit dem 24-Stunden-Mittel der Demo ist also nur grob); bei heißem Wetter steigt das Tastverhältnis auf 0,58. Die absoluten Kilowatt sind
  Modellwerte. **Wie groß der Sprung durch die Reserve ist und ob Strom reihum reicht, hängt an den angenommenen Kühlraten und Zeitkonstanten** (Tabelle „Befunde“, Zeile zu „Strom reihum“); die Aussage der Demo ist
  das Vorgehen und die Richtung, keine einzelne Zahl.
- **Ein Tag, ein Block, feste Reefer.** Keine Ankünfte und Abgänge im Lauf des Tages, keine Zeit ohne Strom beim Umstecken; der Start am oberen Rand steht für „gerade angelandet“. Die Spitze eines Tages ist nicht die Monatsspitze, auf der
  die Abrechnung meist beruht: die Demo nennt **keine Kosten**.
- **Temperatur ist die einzige Qualitätsgröße.** Keine Feuchte, keine Unterschiede zwischen Chargen und Waren, nach unten wird nur gegen den unteren Rand des Regelbands geprüft, nicht gegen eine eigene Schadensgrenze.
- **Reserve ist eine Annahme, keine Messung.** Wie viel Erwärmung eine Ware verträgt, hängt von der Ware ab; die Demo zeigt nur, was jede Reserve an Spitze kostet oder bringt. Keep it cool nennt für Strom reihum einen Temperaturanstieg im Reefer, der mit kürzeren Slots kleiner wird, und ein Produktrisiko; hier hält diese Regel bei 16 °C Tagesmittel mit 0,5 K Reserve in 13 von 20 Blöcken, die Modelle sind nicht vergleichbar (anderes Thermostat, andere Daten).
- **Die Leistungsgrenze ist eine Regel, kein Optimum.** Sie wird an der unteren Schranke und, bei bis zu fünf Reefern, am exakten Ein/Aus-Plan gemessen; bei größeren Blöcken bleibt die Lücke offen (Median 16 % zur Schranke mit 0,5 K Reserve, die Schranke ist
  nicht erreichbar, weil Ein/Aus ganzzahlig ist: eine **Deutung**, nicht gemessen).
- **Nicht im Modell:** Stellplatzabhängigkeit des Verbrauchs (Sonne je Position, Stapelebene), Reefer-Racks als eigenes Lagerkonzept, Strompreisverlauf und Lastverschiebung über den Tag, Netzanschlussgrenzen mehrerer Blöcke.

## Befunde und Korrekturen gegenüber dem Plan

- **Der unabhängige Aussagenprüfer (2026-11-10) fand:** ein falsches Verdikt („keine Regel kann das beheben“ stand auch dort, wo ein vorausplanender Plan den Bereich hält; behoben, der Satz unterscheidet jetzt nach der unteren Schranke), zwei übertriebene Sätze („unter die kein Plan kommt“ gilt nur für Pläne im sicheren Bereich; „die Reihenfolge der Regeln ist die Aussage“ ist an die Annahmen gebunden, siehe Tabelle) und mehrere zu ungenaue Angaben (Tastverhältnis leistungsgewichtet, Rechenzeiten maschinenabhängig, Messbasis der IJTech-Arbeit). Alle Rechenzahlen der README stimmten.
- **Der Plan sah eine harte Obergrenze vor** („Band immer eingehalten“). Das erste Modell zeigte: Wer am oberen Rand startet, muss im ersten Schritt kühlen; die Leistungsgrenze senkte die Spitze im Median nur um 8 %, im ersten Messlauf (22 °C Tagesmittel, 12 Reefer, Zufalls-Seed 17) lag der exakte Ein/Aus-Plan bei 88 kW
  gleichauf mit der Regel. Erst die **Reserve über dem Regelband** machte die Frage interessant (Sprung auf 56 % mit 0,25 K); sie wurde als Regler und als Experiment aufgenommen.
- **Die untere Schranke mit Bruchteilen sah zuerst eng aus** (im ersten Messlauf mit 22 °C Tagesmittel und Zufalls-Seed 17: 51 kW bei 88 kW der Regel ohne Reserve). Sie ist es nicht: Ein/Aus verlangt, dass jeder Reefer am Rand im ersten Schritt voll kühlt; der Unterschied steht als Kennzahl in der Tabelle.
- **„Strom reihum“ (2 Gruppen, 15-Minuten-Slots, 0,5 K Reserve) verletzte im ersten Standardwetter (22 °C Tagesmittel, 4 K Sonne) in 20 von 20 Blöcken das Band.** Das Standardwetter wurde auf 16 °C mit 2 K Sonne gesenkt, damit die Regel nicht von vornherein scheitert; die Wetter-Zeile der Tabelle zeigt beide Seiten.
- **Stellplatzkosten nach Sonne und Stapelebene wurden nicht aufgenommen:** Budiyanto und Shinoda (2017) messen an einem Stapel aus drei Reefern, ausgewertet an einem Tag, höchstens 0,3 kW Unterschied zwischen den Ebenen (Mittelwerte); das reicht nicht für ein Kostenmodell einer Zuordnung.

## Tests

- **Kern:** Wärmeschritt, Thermostat, Slots und Leistungsgrenze gegen Handrechnung auf Mini-Blöcken (`tests/test_algorithm.py`); Randfälle (ein und zwei Reefer, Grenze 0, mehr Gruppen als Reefer, Slot länger als der Tag, Gleichstand, inklusive Obergrenze, jeder Regler am Rand) in `tests/test_edge_cases.py`.
- **Orakel:** `tests/test_oracle_reefer_spitzenlast.py` zählt bei zwei Reefern und sechs Schritten alle 4.096 Ein/Aus-Pläne auf (Rekursion ohne Matrix) und vergleicht mit dem MILP; die untere Schranke darf nie darüber liegen; die Temperatur ohne Kühlung gegen die geschlossene Formel; ein Test prüft, dass die Mini-Instanzen nicht leer laufen.
- **Aussagen:** jede Zahl der Tabelle oben in `tests/test_claims.py` (Mediane über die 20 festen Blöcke); Verdikte als reine Funktionen in `tests/test_verdicts.py`; die Zahlen der Preset-Hilfetexte in `tests/test_presets.py`.
- **Oberfläche:** AppTest-Rauchtest, Layout (Schnellstart oben, aktives Preset hervorgehoben, jeder Regler hebt die Markierung auf), Footer, Laufzeit-Importe.

## Dateistruktur

| Datei | Zweck |
|---|---|
| `.github/workflows/tests.yml` | CI: Push, Pull Request, wöchentlicher Canary |
| `.gitignore` | venv, Caches, Streamlit-Secrets |
| `.streamlit/config.toml` | Streamlit-Einstellungen (keine Nutzungsstatistik) |
| `app.py` | Streamlit-App |
| `requirements-dev.txt` | Laufzeit plus pytest |
| `requirements.txt` | Laufzeit-Bibliotheken (ungepinnt) |
| `rsl_algorithm.py` | Kern: Wärmemodell, drei Regeln, kleinste Grenze, LP und MILP |
| `rsl_constants.py` | Regler-Grenzen, Modellannahmen, Farben, Presets |
| `rsl_evaluation.py` | Einstellungen, Kennzahlen, Sweeps über feste Blöcke, Verdikte |
| `rsl_layout.py` | Fester Kopf (Stylesheet) |
| `rsl_pdf_export.py` | PDF-Export des Ergebnisses (fpdf2, nur Kernschrift) |
| `rsl_presets.py` | Permalink (Begrenzen), Presets (Schnellstart in der Seitenleiste), Zufalls-Seed-Button |
| `rsl_scenario.py` | Reefer-Block (Instanz aus Einstellungen und Zufalls-Seed) |
| `rsl_visualization.py` | Plotly-Abbildungen (Achsen gesperrt) |
| `tests/` | Kern, Randfälle, Orakel, Aussagen, Verdikte, Presets, Layout, AppTest, Footer, Laufzeit-Importe |

## Bewusst nicht umgesetzt

- **Stellplatzkosten nach Sonne und Stapelebene** (siehe oben): die Datenlage reicht dafür nicht.
- **Ankünfte und Abgänge im Tagesverlauf, Strompreisverlauf (Lastverschiebung), mehrere Blöcke an einem Netzanschluss:** eigene Fragen; Tang u. a. (International Journal of Production Research 2025) behandeln Ladeplanung mit Preisen und Spitzenkappung, hier nur dem Abstract nach bekannt und nicht nachgebaut.
- **Kostenrechnung:** ein Tag ersetzt kein Monatsmaximum; ohne Tarif gäbe es nur eine erfundene Zahl.

## Lokal ausführen

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

## Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Gebaut mit Streamlit, Plotly, NumPy, pandas, SciPy (HiGHS) und fpdf2.

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). Mehr zum Thema: [Hafenlogistik optimieren](https://sebastianhanisch.net/hafenlogistik-optimierung.html).
