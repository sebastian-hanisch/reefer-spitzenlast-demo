"""Plotly-Abbildungen. Alle Achsen sind gesperrt (fixedrange), damit Touch-Geräte beim Scrollen nicht am Diagramm hängen bleiben."""

import numpy as np
import plotly.graph_objects as go

import rsl_constants as C


def lock_axes(fig):
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig


def _base(fig, height=360):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.25), plot_bgcolor="rgba(0,0,0,0)")
    return lock_axes(fig)


def _clock_axis(fig):
    """Zeitachse über 24 Stunden ab dem Start (8 Uhr): Beschriftung als Uhrzeit, auch jenseits von 24 Uhr (28 h = 04:00)."""
    ticks = [C.START_HOUR + 4.0 * k for k in range(int(C.HORIZON_H // 4) + 1)]
    fig.update_xaxes(title_text="Uhrzeit", tickmode="array", tickvals=ticks, ticktext=[f"{int(t % 24):02d}:00" for t in ticks], range=[C.START_HOUR, C.START_HOUR + C.HORIZON_H])


def clock_hours(steps: int) -> np.ndarray:
    """Uhrzeit (Stunden seit 0 Uhr des Starttags, fortlaufend, also auch über 24 hinaus) der Schritte 0 .. steps - 1."""
    return C.START_HOUR + np.arange(steps) * C.DT_H


def build_power(a):
    """Leistung über dem Tag für die drei Regeln, dazu die eingestellte Grenze und die untere Schranke mit Bruchteilen."""
    hours = clock_hours(C.STEPS)
    fig = go.Figure()
    for rule in C.RULES:
        r = a.results[rule]
        fig.add_trace(go.Scatter(x=hours, y=r.power_kw, mode="lines", line=dict(color=C.COLOR_RULES[rule], width=2.5, shape="hv"), name=C.RULE_LABELS[rule],
                                 hovertemplate="%{x:.2f} h: %{y:.1f} kW<extra></extra>"))
    span = [hours[0], hours[-1] + C.DT_H]
    # Grenze und Schranke als Linien mit Eintrag in der Legende (Annotationen an add_hline legen Plotly beim ersten Zeichnen -Infinity in den SVG-Text)
    fig.add_trace(go.Scatter(x=span, y=[a.cap_kw] * 2, mode="lines", line=dict(color=C.COLOR_RULES["grenze"], width=1.5, dash="dash"), name="eingestellte Grenze",
                             hovertemplate="Grenze: %{y:.1f} kW<extra></extra>"))
    if a.lp.peak_kw is not None:
        fig.add_trace(go.Scatter(x=span, y=[a.lp.peak_kw] * 2, mode="lines", line=dict(color=C.COLOR_BOUND, width=1.5, dash="dot"), name="Untergrenze (Bruchteile)",
                                 hovertemplate="Untergrenze: %{y:.1f} kW<extra></extra>"))
    _clock_axis(fig)
    fig.update_yaxes(title_text="Leistung des Blocks (kW)", rangemode="tozero")
    return _base(fig, 400)


def build_temperature(a, reefer: int):
    """Innentemperatur eines Reefers unter den drei Regeln; Regelband und sicherer Bereich sind hinterlegt."""
    inst = a.inst
    hours = C.START_HOUR + np.arange(C.STEPS + 1) * C.DT_H
    lo, hi, hi_safe = float(inst.lo[reefer]), float(inst.hi[reefer]), float(inst.hi_safe[reefer])
    fig = go.Figure()
    fig.add_hrect(y0=lo, y1=hi, fillcolor=C.COLOR_BAND, line_width=0)
    if hi_safe > hi:
        fig.add_hrect(y0=hi, y1=hi_safe, fillcolor="rgba(217,138,43,0.14)", line_width=0)
    for rule in C.RULES:
        fig.add_trace(go.Scatter(x=hours, y=a.results[rule].temp[:, reefer], mode="lines", line=dict(color=C.COLOR_RULES[rule], width=2.2), name=C.RULE_LABELS[rule],
                                 hovertemplate="%{x:.2f} h: %{y:.2f} °C<extra></extra>"))
    _clock_axis(fig)
    fig.update_yaxes(title_text="Innentemperatur (°C)")
    return _base(fig, 320)


def build_margin(rows):
    """Spitze gegen Reserve: Median der kleinsten Grenze über die festen Instanzen (Minimum bis Maximum), Spitze ohne Steuerung, Untergrenze der eingestellten Instanz."""
    usable = [r for r in rows if r["cap"] is not None]
    xs = [r["margin"] for r in usable]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs + xs[::-1], y=[r["high"] for r in usable] + [r["low"] for r in usable][::-1], fill="toself", fillcolor="rgba(47,107,101,0.18)",
                             line=dict(width=0), hoverinfo="skip", name="Minimum bis Maximum der kleinsten Grenze"))
    fig.add_trace(go.Scatter(x=xs, y=[r["cap"] for r in usable], mode="lines+markers", line=dict(color=C.COLOR_RULES["grenze"], width=3), name="kleinste Grenze (Median)",
                             hovertemplate="Reserve %{x:.2f} K: %{y:.1f} kW<extra></extra>"))
    fig.add_trace(go.Scatter(x=[r["margin"] for r in rows], y=[r["uncontrolled"] for r in rows], mode="lines+markers", line=dict(color=C.COLOR_RULES["ungesteuert"], width=2, dash="dash"),
                             name="ohne Steuerung (Median)", hovertemplate="Reserve %{x:.2f} K: %{y:.1f} kW<extra></extra>"))
    lp_rows = [r for r in rows if r["lp"] is not None]
    fig.add_trace(go.Scatter(x=[r["margin"] for r in lp_rows], y=[r["lp"] for r in lp_rows], mode="lines+markers", line=dict(color=C.COLOR_BOUND, width=2, dash="dot"),
                             name="Untergrenze mit Bruchteilen (eingestellte Instanz)", hovertemplate="Reserve %{x:.2f} K: %{y:.1f} kW<extra></extra>"))
    fig.update_xaxes(title_text="Reserve über dem Regelband (K)")
    fig.update_yaxes(title_text="Spitze (kW)", rangemode="tozero")
    return _base(fig)
