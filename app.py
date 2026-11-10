"""Reefer-Spitzenlast: Wie lange darf der Strom pausieren? - interaktive Fall-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Ein Block Kühlcontainer über 24 Stunden: drei Regeln für den Strom (ungesteuert, Strom reihum, Leistungsgrenze) gegen die Spitze der Leistung,
dazu die untere Schranke (LP) und der exakte Ein/Aus-Plan (MILP) für kleine Blöcke. Aufbau und Regeln stehen im DEMO-PLAYBOOK.md (§2).

Lauffähig mit: streamlit run app.py
"""

import pandas as pd
import streamlit as st

import rsl_algorithm as A
import rsl_constants as C
from rsl_evaluation import (
    Settings,
    analyse,
    de,
    duty_cycle,
    instance_of,
    reduction_percent,
    sweep_margin,
    sweep_slots,
    verdict_cap_setting,
    verdict_margin,
    verdict_peak,
    verdict_slots,
)
from rsl_layout import dunkles_design, kopf_css
from rsl_pdf_export import generate_rsl_pdf
from rsl_presets import (
    bounds,
    init_session_state_defaults,
    load_permalink_settings,
    randomize_seed,
    sidebar_presets,
    sync_query_params,
)
from rsl_visualization import build_margin, build_power, build_temperature

st.set_page_config(page_title="Reefer-Spitzenlast – Sebastian Hanisch", layout="wide")


@st.cache_data(show_spinner=False)
def _analysis(settings):
    return analyse(settings)


@st.cache_data(show_spinner=False)
def _margin_sweep(settings):
    return sweep_margin(settings)


@st.cache_data(show_spinner=False)
def _slot_sweep(settings):
    return sweep_slots(settings)


@st.cache_data(show_spinner=False)
def _exact(settings):
    return A.exact_peak(instance_of(settings), integer=True, time_limit_s=C.EXACT_TIME_LIMIT_S)


def _sweep_key(settings, *, with_seed):
    """Nur die Einstellungen, von denen ein Sweep abhängt (sonst rechnet jeder Regler an Grenze, Gruppen oder Slot ihn neu)."""
    return Settings(n=settings.n, share=settings.share, band=settings.band, margin=settings.margin, sync=settings.sync, tmean=settings.tmean,
                    sun=settings.sun, seed=settings.seed if with_seed else C.DEFAULT_SEED)


# Fester Kopf: nur der Titel bleibt beim Scrollen oben (Stylesheet in rsl_layout.py).
st.html(kopf_css(dunkles_design()))
with st.container(key="kopf"):
    st.title("❄️ Reefer-Spitzenlast: Wie lange darf der Strom pausieren?")
st.markdown(
    """
Kühlcontainer (**Reefer**) im Block brauchen Strom, und viele Stromversorger rechnen nach der **höchsten Spitze** ab. Kühlen viele Reefer zugleich, etwa nach dem Anlanden, entsteht eine hohe Spitze.
Die Demo fragt: **Wie weit lässt sich die Spitze senken, ohne dass die Ware wärmer wird, als es sicher ist, und welche Regel für den Strom holt wie viel davon heraus?**
Verglichen werden drei Regeln (**ungesteuert**, **Strom reihum**, **Leistungsgrenze**) mit der **unteren Schranke** und, für kleine Blöcke, dem **exakten Plan**.

Weiter unten: die **Kernfrage**, zwei **Experimente** (Reserve; Gruppen und Slotlänge) und die Expander **🔧 Wie wir das erreichen – vollständiger Methodenvergleich** und **📐 Mathematische Formulierung**.
Welche Reefer wohin kommen, zeigt die [Reefer-Demo zum Steckdosen-Puffer](https://sebastianhanisch-reefer-demo.streamlit.app/); hier stehen die Reefer schon am Strom.
"""
)

# erklaerseite:einfach:start (erzeugt von tools/set_demo_explainer.py (Website-Repo) aus tools/content/explainers/reefer-spitzenlast-erklaert.json, nicht von Hand ändern)
with st.expander("💬 In einfachen Worten"):
    st.markdown(
        """
Kühlcontainer stehen am Strom und kühlen in Zyklen: Die Anlage schaltet an, wenn die Ware zu warm zu werden droht, und aus, wenn sie kalt genug ist. Kühlen viele zugleich, entsteht eine hohe Stromspitze, nach der manche Stromversorger abrechnen. Die Demo spielt einen Block über einen Tag durch und vergleicht drei Regeln für den Strom: jeder Container für sich, Gruppen, die sich abwechseln, und eine feste Obergrenze für die Gesamtleistung. Dazu kommt eine Zahl, die zeigt, wie klein die Spitze im besten Fall würde. Wichtig ist die Reserve: der Temperaturspielraum, den die Ware über das Regelband hinaus verträgt. Alle Größen sind erfunden und nicht an einem echten Terminal gemessen.

[Ausführlich und verständlich erklärt, mit Fachteil](https://sebastianhanisch.net/reefer-spitzenlast-erklaert.html)
        """
    )
# erklaerseite:einfach:end

st.caption("🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, um ein Szenario zu teilen.")

load_permalink_settings()
init_session_state_defaults()

with st.sidebar:
    sidebar_presets()  # Schnellstart oben, das aktive Preset ist hervorgehoben
    st.header("⚙️ Block und Wetter")
    st.markdown("**Reefer-Block**")
    n = st.slider("Reefer im Block", *bounds("n_slider"), key="n_slider", help="Wie viele Reefer am Strom stehen.")
    share = st.slider("Anteil gefrorener Reefer (%)", *bounds("share_slider"), key="share_slider", step=10,
                      help="Gefrorene Reefer (Sollwert −20 °C) brauchen mehr Leistung als gekühlte (Sollwert +2 °C); Annahmen siehe Abschnitt „Wo die Annahmen enden“.")
    band = st.slider("Regelband ± (K)", *bounds("band_slider"), key="band_slider", step=0.25,
                     help="Halbbreite des Bands um den Sollwert, in dem das Thermostat die Temperatur hält.")
    margin = st.slider("Reserve über dem Regelband (K)", *bounds("margin_slider"), key="margin_slider", step=0.25,
                       help="Bis zu dieser Höhe über dem Regelband gilt die Ware noch als sicher. Nach unten gibt es keine Reserve. Ohne Reserve muss jeder Reefer sofort kühlen, wenn er den Rand erreicht.")
    sync = st.slider("Reefer, die am oberen Rand starten (%)", *bounds("sync_slider"), key="sync_slider", step=10,
                     help="Wer am oberen Rand des Regelbands startet, muss sofort kühlen (etwa nach dem Anlanden). Alle anderen starten gleichverteilt im Band.")
    st.markdown("**Wetter**")
    tmean = st.slider("Außentemperatur, Tagesmittel (°C)", *bounds("tmean_slider"), key="tmean_slider",
                      help="Ohne Sonnenzuschlag; dazu kommen ±5 K Tagesgang mit Spitze um 15 Uhr.")
    sun = st.slider("Sonnenzuschlag um 12 Uhr (K)", *bounds("sun_slider"), key="sun_slider",
                    help="Zuschlag zur Umgebungstemperatur durch die Sonne zwischen 6 und 18 Uhr (Halbsinus).")
    st.header("🔌 Regeln für den Strom")
    st.markdown("**Strom reihum**")
    groups = st.slider("Gruppen", *bounds("groups_slider"), key="groups_slider", help="In wie viele Gruppen (Racks) die Reefer geteilt werden; je Slot hat eine Gruppe Strom.")
    slot = st.slider("Slotlänge (Schritte zu 15 Minuten)", *bounds("slot_slider"), key="slot_slider", help="Wie lange eine Gruppe Strom hat, bevor die nächste dran ist.")
    st.markdown("**Leistungsgrenze**")
    cap = st.slider("Grenze (% der Summe der Betriebsleistungen)", *bounds("cap_slider"), key="cap_slider", step=5,
                    help="Die Leistung des Blocks darf diese Grenze nicht überschreiten; wollen mehr Reefer kühlen, bekommen die mit der geringsten Reserve zur Obergrenze zuerst Strom.")
    st.markdown("**Zufall**")
    seed = st.number_input("Zufalls-Seed des Blocks", *bounds("seed_input"), key="seed_input", step=1,
                           help="Legt fest, welche Reefer gefroren sind, ihre Zeitkonstanten, Kühlraten und Startwerte.")
    st.button("🎲 Neuen Block würfeln", width="stretch", on_click=randomize_seed)

sync_query_params({
    "n_slider": int(n), "share_slider": int(share), "band_slider": float(band), "margin_slider": float(margin), "sync_slider": int(sync),
    "tmean_slider": int(tmean), "sun_slider": int(sun), "groups_slider": int(groups), "slot_slider": int(slot), "cap_slider": int(cap),
    "seed_input": int(seed),
})

settings = Settings(n=int(n), share=int(share), band=float(band), margin=float(margin), sync=int(sync), tmean=float(tmean), sun=float(sun),
                    groups=int(groups), slot=int(slot), cap=int(cap), seed=int(seed))
a = _analysis(settings)
base = a.results["ungesteuert"]
rev = a.results["reihum"]
grz = a.results["grenze"]

# --- Ergebnis ------------------------------------------------------------------------------------------------------------------------------

st.markdown("## 🎯 Ergebnis")
m1, m2, m3, m4 = st.columns(4)
# Delta immer als „mein Wert minus Referenz“; die Farbe regelt delta_color="inverse" (Vorzeichen-Falle, DEMO-PLAYBOOK §2).
m1.metric("Spitze ungesteuert", f"{de(base.peak_kw)} kW", delta="Referenz", delta_color="off")
m2.metric("Spitze Strom reihum", f"{de(rev.peak_kw)} kW", delta=f"{de(rev.peak_kw - base.peak_kw)} kW gegen ungesteuert", delta_color="inverse")
m3.metric("Spitze Leistungsgrenze (eingestellt)", f"{de(grz.peak_kw)} kW", delta=f"{de(grz.peak_kw - base.peak_kw)} kW gegen ungesteuert", delta_color="inverse")
if a.smallest_cap_kw is None:
    m4.metric("Kleinste Grenze, die das Band hält", "keine", delta="schon ohne Grenze nicht", delta_color="off")
else:
    m4.metric("Kleinste Grenze, die das Band hält", f"{de(a.smallest_cap_kw)} kW", delta=f"{de(a.smallest_cap_kw - base.peak_kw)} kW gegen ungesteuert", delta_color="inverse")
st.plotly_chart(build_power(a), width="stretch", key="power_chart")
st.caption(
    "Leistung des Blocks je 15-Minuten-Schritt über 24 Stunden. Gestrichelt: die eingestellte Grenze. Gepunktet: die untere Schranke: unter ihr liegt kein Plan, der den sicheren Bereich einhält, auch kein Plan mit "
    "stufenlos regelbarer Leistung (gilt in diesem Modell, bei diesen Einstellungen). Regeln, die den Bereich verletzen, können darunter liegen."
)
st.download_button(
    "📄 Ergebnis als PDF", data=generate_rsl_pdf(a), file_name="reefer_spitzenlast_ergebnis.pdf", mime="application/pdf", key="primary_pdf_download",
)

rows = []
for rule in C.RULES:
    r = a.results[rule]
    rows.append({
        "Regel": C.RULE_LABELS[rule],
        "Spitze (kW)": r.peak_kw,
        "Spitze gegen ungesteuert (%)": -reduction_percent(r.peak_kw, base.peak_kw),
        "Energie (kWh)": r.energy_kwh,
        "Höchste Temperatur über dem Regelband (K)": r.max_above_control_k,
        "Abweichung aus dem sicheren Bereich (K)": r.max_excess_k,
        "Reefer-Stunden außerhalb": r.reefer_hours_out,
    })
st.dataframe(
    pd.DataFrame(rows),
    hide_index=True,
    width="stretch",
    column_config={
        "Spitze (kW)": st.column_config.NumberColumn(format="%.1f"),
        "Spitze gegen ungesteuert (%)": st.column_config.NumberColumn(format="%.0f %%"),
        "Energie (kWh)": st.column_config.NumberColumn(format="%.0f"),
        "Höchste Temperatur über dem Regelband (K)": st.column_config.NumberColumn(format="%.2f"),
        "Abweichung aus dem sicheren Bereich (K)": st.column_config.NumberColumn(format="%.2f"),
        "Reefer-Stunden außerhalb": st.column_config.NumberColumn(format="%.1f"),
    },
)
st.caption(
    f"Ohne Steuerung kühlen die Reefer im Mittel {de(100 * duty_cycle(a), 0)} % der Zeit (leistungsgewichtet über den Block); die Summe der Betriebsleistungen ist {de(a.inst.total_power_kw)} kW. "
    "„Sicherer Bereich“: nach unten das Regelband, nach oben Regelband plus Reserve. Alle Zahlen sind Modellrechnungen, keine Messung an einem Terminal."
)

# --- Kernfrage -----------------------------------------------------------------------------------------------------------------------------

st.markdown("## ❓ Kernfrage: Wie weit lässt sich die Spitze senken, ohne die Ware zu gefährden?")
kind, text = verdict_peak(a)
getattr(st, kind)(text)
kind, text = verdict_cap_setting(a)
getattr(st, kind)(text)

st.markdown("---")

# --- Experiment 1: Reserve ----------------------------------------------------------------------------------------------------------------------

st.markdown("## 🔬 Experiment 1: Wie viel Reserve braucht es?")
st.markdown(
    "Die Reserve ist der Spielraum über dem Regelband, den die Ware verträgt. Je größer sie ist, desto länger darf ein Reefer auf Strom warten. "
    "Die Kurve zeigt die kleinste Grenze, die den sicheren Bereich hält, über 20 feste Blöcke (alle anderen Regler wie eingestellt) und die Spitze ohne Steuerung."
)
with st.spinner("Rechne die Kurve über 20 Blöcke und sechs Reserven ..."):
    margin_rows = _margin_sweep(_sweep_key(settings, with_seed=True))
st.plotly_chart(build_margin(margin_rows), width="stretch", key="margin_chart")
kind, text = verdict_margin(margin_rows)
getattr(st, kind)(text)

# --- Experiment 2: Strom reihum ------------------------------------------------------------------------------------------------------------------

st.markdown("## 🔬 Experiment 2: Strom reihum – wie viele Gruppen, wie lange Slots?")
st.markdown(
    "„Strom reihum“ teilt die Reefer in Gruppen; je Slot hat eine Gruppe Strom. Die Spitze sinkt auf etwa ein Gruppenanteil der Summe, aber jeder Reefer kühlt nur noch "
    "in seinem Slot. Die Tabelle zählt über 20 feste Blöcke, in wie vielen jeder Reefer im sicheren Bereich bleibt."
)
with st.spinner("Rechne 12 Kombinationen über 20 Blöcke ..."):
    slot_rows = _slot_sweep(_sweep_key(settings, with_seed=False))
slot_table = pd.DataFrame([
    {"Gruppen": r["groups"], "Slotlänge (Minuten)": r["slot"] * 15, "Blöcke im sicheren Bereich": f"{r['in_band']} von {r['runs']}",
     "Spitze, Mittel (kW)": r["peak"], "Größte Abweichung, Mittel (K)": r["excess"]}
    for r in slot_rows
])
st.dataframe(
    slot_table,
    hide_index=True,
    width="stretch",
    column_config={
        "Spitze, Mittel (kW)": st.column_config.NumberColumn(format="%.1f"),
        "Größte Abweichung, Mittel (K)": st.column_config.NumberColumn(format="%.2f"),
    },
)
kind, text = verdict_slots(slot_rows)
getattr(st, kind)(text)

# --- Ein Reefer im Verlauf ----------------------------------------------------------------------------------------------------------------------

st.markdown("## 🔬 Ein Reefer im Verlauf")
labels = [
    f"Reefer {i + 1} ({'gefroren' if a.inst.frozen[i] else 'gekühlt'}, Sollwert {de(a.inst.setpoint[i], 0)} °C)" for i in range(a.inst.n)
]
choice = st.selectbox("Welchen Reefer anschauen?", range(a.inst.n), format_func=lambda i: labels[i], key="reefer_choice")
st.plotly_chart(build_temperature(a, int(choice)), width="stretch", key="temperature_chart")
st.caption("Blau hinterlegt: das Regelband, orange: die Reserve darüber. Verlässt eine Linie das Blau-Orange, ist die Ware außerhalb des sicheren Bereichs.")

st.markdown("---")

# --- Wo die Annahmen enden ----------------------------------------------------------------------------------------------------------------------

st.markdown("## 🚧 Wo die Annahmen enden")
st.markdown(
    """
- **Eigene Größenordnungen, keine Messdaten.** Zeitkonstanten (20 bis 60 Stunden), Kühlrate (1,8 bis 2,4 K je Stunde) und Betriebsleistung (10 kW gefroren, 8 kW gekühlt) sind Annahmen, nicht an einem Terminal kalibriert. Wie groß der Sprung durch die Reserve ist und ob Strom reihum reicht, hängt stark daran: Bei halber Kühlrate oder halber Zeitkonstante hielt Strom reihum (2 Gruppen, 15 Minuten) in 0 von 20 Blöcken den sicheren Bereich, bei doppelter in 20 von 20.
- **Ein Tag, ein Block, feste Reefer.** Keine Ankünfte und Abgänge im Lauf des Tages, keine Wartezeit ohne Strom beim Umstecken; der Start am oberen Rand steht für „gerade angelandet“.
- **Spitze eines Tages, nicht eines Monats.** Abgerechnet wird meist die höchste Spitze eines Zeitraums; die Demo zeigt die Spitze eines Tages und nennt keine Kosten.
- **Temperatur ist die einzige Qualitätsgröße.** Keine Feuchte, keine Ware mit eigener Wärmekapazität über einen Zeitkonstanten-Wert hinaus, kein Unterschied zwischen Chargen. Nach unten wird nur gegen den unteren Rand des Regelbands geprüft, nicht gegen eine eigene Schadensgrenze.
- **Die Leistungsgrenze ist eine Regel, kein Optimum.** Sie wird an der unteren Schranke und, bei kleinen Blöcken, am exakten Ein/Aus-Plan gemessen; bei größeren Blöcken bleibt eine Lücke offen.
"""
)

# --- Methodenvergleich ---------------------------------------------------------------------------------------------------------------------------

with st.expander("🔧 Wie wir das erreichen – vollständiger Methodenvergleich"):
    tab_rules, tab_lp, tab_exact = st.tabs(["Die drei Regeln", "Untere Schranke (LP)", "🧮 Exakt (Ein/Aus)"])
    with tab_rules:
        st.markdown(
            """
Alle Regeln haben dasselbe **Thermostat**: Ein Reefer schaltet an, wenn seine Temperatur im nächsten Schritt ohne Kühlung über dem Regelband läge, und aus, wenn ein Schritt Kühlung unter das Band führen würde.
Die Regeln unterscheiden sich nur darin, **wer Strom bekommt**:

- **Ungesteuert:** Jeder Reefer kühlt, wenn sein Thermostat es verlangt. Die Spitze ergibt sich aus der Gleichzeitigkeit.
- **Strom reihum:** Die Reefer sind in Gruppen geteilt (Nummer mod Gruppenzahl); je Slot hat eine Gruppe Strom, die übrigen pausieren, auch wenn ihr Thermostat kühlen will.
- **Leistungsgrenze:** Die Summe der Leistungen darf die Grenze nicht überschreiten. Wollen mehr Reefer kühlen, bekommen die mit der geringsten Reserve zur sicheren Obergrenze im nächsten Schritt (ohne Kühlung) zuerst Strom.
"""
        )
    with tab_lp:
        lp = a.lp
        if lp.peak_kw is None:
            st.info("Für diese Einstellungen gibt es auch mit stufenlos regelbarer Leistung keinen Plan, der den sicheren Bereich hält: die Kühlleistung reicht nicht.")
        else:
            st.markdown(
                f"Wenn jeder Reefer mit einem **Bruchteil** seiner Leistung laufen dürfte (stufenlose Regelung), ist die kleinste mögliche Spitze **{de(lp.peak_kw)} kW**. "
                "Das ist eine untere Schranke für jeden Plan dieses Modells, der den sicheren Bereich einhält, auch für Ein/Aus-Pläne; Regeln, die den Bereich verletzen, können darunter liegen. Sie ist ein lineares Programm."
            )
            st.metric("Untere Schranke", f"{de(lp.peak_kw)} kW", delta=f"{de(lp.peak_kw - base.peak_kw)} kW gegen ungesteuert", delta_color="inverse")
    with tab_exact:
        # Der Tab ist selbstständig: eigener Button, Spinner und Ergebnis, gegen das aktuelle Szenario geprüft (DEMO-PLAYBOOK §2).
        if settings.n > C.EXACT_N_LIMIT:
            st.info(f"Der exakte Ein/Aus-Plan rechnet nur bis {C.EXACT_N_LIMIT} Reefer im Browser; hier sind es {settings.n}. Die untere Schranke und die Regeln gelten weiter.")
        else:
            st.markdown(
                "Das **gemischt-ganzzahlige Programm** wählt für jeden Reefer und Schritt Ein oder Aus so, dass die Spitze kleinstmöglich ist und der sichere Bereich immer gilt."
            )
            if st.button(f"Exakt lösen (Ein/Aus, bis zu {int(C.EXACT_TIME_LIMIT_S)} Sekunden)", key="exact_start"):
                st.session_state["exact_done"] = settings
            if st.session_state.get("exact_done") == settings:
                with st.spinner("Löse das ganzzahlige Programm ..."):
                    best = _exact(settings)
                if best.peak_kw is None:
                    st.warning("Es gibt keinen Ein/Aus-Plan, der den sicheren Bereich hält." if best.status == "unzulässig" else "Im Zeitlimit wurde kein Plan gefunden.")
                else:
                    label = "Exakte kleinste Spitze" if best.status == "optimal" else "Beste gefundene Spitze (Zeitlimit)"
                    st.metric(label, f"{de(best.peak_kw)} kW",
                              delta=(f"{de(a.smallest_cap_kw - best.peak_kw)} kW unter der kleinsten Grenze der Regel" if a.smallest_cap_kw is not None else None),
                              delta_color="off")
                    if best.status != "optimal" and best.lower_bound_kw is not None:
                        st.caption(f"Zeitlimit erreicht: bewiesen ist nur, dass keine Spitze unter {de(best.lower_bound_kw)} kW möglich ist.")

with st.expander("📐 Mathematische Formulierung"):
    # erklaerseite:lesehilfe:start (erzeugt von tools/set_demo_explainer.py (Website-Repo) aus tools/content/explainers/reefer-spitzenlast-erklaert.json, nicht von Hand ändern)
    st.markdown(
        r"""
**Lesehilfe.** Gegeben sind ein Block aus Reefern mit Sollwert, Regelband und Reserve, die Umgebungstemperatur im Tagesverlauf und die Betriebsleistung je Reefer. Gesucht ist ein Plan, welcher Reefer in welchem 15-Minuten-Schritt Strom bekommt, sodass die höchste Leistung des Blocks möglichst klein ist und jede Temperatur im sicheren Bereich bleibt.

| Symbol | Bedeutung |
|---|---|
| $T_{i,t}$ | Innentemperatur des Reefers $i$ zu Beginn des Schritts $t$ |
| $u_{i,t}$ | 1, wenn Reefer $i$ im Schritt $t$ Strom bekommt und kühlt, sonst 0 |
| $a_i$ | Anteil, den die Temperatur pro Schritt ohne Kühlung an der Abweichung zur Umgebung behält ($a_i = e^{-\Delta t/\tau_i}$) |
| $b_i$ | Abkühlung in K je Schritt bei Betrieb ($b_i = c_i\,\Delta t$) |
| $A_t$ | wirksame Umgebungstemperatur im Schritt $t$ |
| $s_i, \delta, m$ | Sollwert, Halbbreite des Regelbands und Reserve nach oben |
| $P_i, \Pi$ | Betriebsleistung des Reefers $i$ und die Spitze des Blocks |
| $G$ | feste Leistungsgrenze der gleichnamigen Regel (nicht die Spitze $\Pi$ des Plans) |

[Schritt für Schritt erklärt, mit Herleitung und Literatur](https://sebastianhanisch.net/reefer-spitzenlast-erklaert.html#fachleute)
        """
    )
    # erklaerseite:lesehilfe:end
    st.markdown(
        """
Die Zeit läuft in 15-Minuten-Schritten, $t = 0, \\dots, 95$; $u_{i,t} \\in \\{0, 1\\}$ ist der gesuchte Ein/Aus-Plan.

$$T_{i,t+1} = a_i\\,T_{i,t} + (1 - a_i)\\,A_t - b_i\\,u_{i,t}$$

$$s_i - \\delta \\le T_{i,t} \\le s_i + \\delta + m \\quad \\text{für alle } i, t$$

$$\\min\\; \\Pi \\quad \\text{mit} \\quad \\sum_i P_i\\,u_{i,t} \\le \\Pi \\quad \\text{für alle } t$$

Mit u_{i,t} ∈ [0, 1] statt {0, 1} ist es ein lineares Programm und liefert die untere Schranke; mit u_{i,t} ∈ {0, 1} ist es das gemischt-ganzzahlige Programm des Tabs „Exakt“.
Die Form der Temperaturgleichung folgt Gleichung (1) von van Duin u. a. (Keep it cool, TRB 2017) für die Erwärmung ohne Strom; die Zahlenwerte stammen nicht aus dieser Arbeit.
"""
    )

st.markdown("---")
st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). "
    "Mehr zum Thema: [Hafenlogistik optimieren](https://sebastianhanisch.net/hafenlogistik-optimierung.html)."
)
