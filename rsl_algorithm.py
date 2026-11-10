"""Kern: Wärmemodell, drei Regeln für den Strom und die exakte Untergrenze der Spitze (LP bzw. MILP).

Wärmemodell je Reefer i und Schritt t (15 Minuten), `u` ist 1, wenn der Reefer in dem Schritt Strom bekommt und kühlt:

    T[t+1] = a·T[t] + (1 − a)·A[t] − b·u[t],   a = exp(−Δt/τ),  b = Kühlrate·Δt.

Das ist die Form der Gleichung (1) von van Duin u. a. (TRB 2017) für die Erwärmung ohne Strom, hier um die Kühlung ergänzt. Leistung im Schritt:
Σ P_i·u_i[t] (Mittel über die 15 Minuten). Erlaubt ist das Band [Sollwert − δ, Sollwert + δ] zu jedem Zeitpunkt.

Die Regeln unterscheiden sich nur darin, wer wann Strom bekommt; das Thermostat ist überall dasselbe (siehe `_update_thermostat`).
"""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import block_diag, coo_matrix, csr_matrix, hstack, vstack

import rsl_constants as C
from rsl_scenario import Instance


@dataclass(frozen=True, eq=False)
class Result:
    """Ergebnis eines Laufs. `u`: (STEPS, n) bool, `temp`: (STEPS + 1, n), `power_kw`: (STEPS,)."""

    rule: str
    u: np.ndarray
    temp: np.ndarray
    power_kw: np.ndarray
    peak_kw: float
    energy_kwh: float
    max_excess_k: float        # größte Abweichung aus dem sicheren Bereich in K (0 = immer eingehalten)
    reefer_hours_out: float    # Summe über Reefer der Stunden außerhalb des sicheren Bereichs
    max_above_control_k: float  # höchste Temperatur über dem Regelband in K (die genutzte Reserve; 0 = nie über dem Regelband)

    @property
    def in_band(self) -> bool:
        return self.max_excess_k <= C.EPS


def evaluate(inst: Instance, rule: str, u: np.ndarray, temp: np.ndarray) -> Result:
    """Kennzahlen eines Plans: Leistung je Schritt, Spitze, Energie und Bandverletzung (an allen STEPS + 1 Zeitpunkten)."""
    power = (u * inst.power_kw[None, :]).sum(axis=1)
    excess = np.maximum(temp - inst.hi_safe[None, :], 0.0) + np.maximum(inst.lo[None, :] - temp, 0.0)
    above_control = np.maximum(temp - inst.hi[None, :], 0.0)
    return Result(
        rule=rule,
        u=u,
        temp=temp,
        power_kw=power,
        peak_kw=float(power.max()),
        energy_kwh=float(power.sum() * C.DT_H),
        max_excess_k=float(excess.max()),
        reefer_hours_out=float((excess > C.EPS).sum() * C.DT_H),
        max_above_control_k=float(above_control.max()),
    )


def replay(inst: Instance, u: np.ndarray) -> np.ndarray:
    """Temperaturverlauf (STEPS + 1, n) zu einem festen Plan `u` (STEPS, n); unabhängig von jeder Regel."""
    a, b = inst.a, inst.b
    temp = np.empty((C.STEPS + 1, inst.n))
    temp[0] = inst.t0
    for t in range(C.STEPS):
        temp[t + 1] = a * temp[t] + (1.0 - a) * inst.ambient[t] - b * u[t]
    return temp


def _update_thermostat(inst: Instance, on: np.ndarray, temp: np.ndarray, t: int):
    """Vorausschauendes Thermostat mit Hysterese. Gibt (neuer Zustand, Temperatur ohne Kühlung im nächsten Schritt) zurück.

    An, wenn die Temperatur im nächsten Schritt ohne Kühlung über dem Band läge; aus, wenn ein Schritt Kühlung unter das Band führen würde;
    sonst bleibt der Zustand. Das Band ist mindestens einen Kühlschritt breit (2·δ ≥ b), beide Bedingungen schließen sich also nicht aus.
    """
    free_next = inst.a * temp + (1.0 - inst.a) * inst.ambient[t]
    must = free_next > inst.hi + C.EPS
    stop = (free_next - inst.b) < inst.lo - C.EPS
    return np.where(must, True, np.where(stop, False, on)), free_next


def simulate(inst: Instance, rule: str, *, groups: int = C.DEFAULT_GROUPS, slot_steps: int = C.DEFAULT_SLOT, cap_kw: float | None = None) -> Result:
    """Läuft den Block über 24 Stunden mit einer der drei Regeln.

    - `ungesteuert`: jeder Reefer schaltet nach seinem Thermostat, die Leistung ergibt sich.
    - `reihum`: die Reefer sind in `groups` Gruppen (Index mod groups) geteilt; in Slots von `slot_steps` Schritten hat reihum je eine Gruppe
      Strom, die übrigen pausieren. Das Thermostat gilt nur für die Gruppe mit Strom.
    - `grenze`: die Summe der Leistungen darf `cap_kw` nicht überschreiten; wollen mehr Reefer kühlen, bekommen die mit der geringsten
      Reserve zur sicheren Obergrenze im nächsten Schritt (ohne Kühlung) zuerst Strom, solange die Grenze reicht.
    """
    if rule not in C.RULES:
        raise ValueError(f"unbekannte Regel: {rule}")
    if rule == "grenze" and cap_kw is None:
        raise ValueError("Regel 'grenze' braucht cap_kw")
    n = inst.n
    temp = np.empty((C.STEPS + 1, n))
    u = np.zeros((C.STEPS, n), dtype=bool)
    temp[0] = inst.t0
    on = np.zeros(n, dtype=bool)  # das Thermostat schaltet im ersten Schritt, wer sofort kühlen muss
    group_of = np.arange(n) % max(groups, 1)
    power = inst.power_kw
    for t in range(C.STEPS):
        on, free_next = _update_thermostat(inst, on, temp[t], t)
        if rule == "ungesteuert":
            cool = on
        elif rule == "reihum":
            powered = group_of == (t // max(slot_steps, 1)) % max(groups, 1)
            cool = on & powered
        else:
            cool = _grant_by_urgency(on, free_next - inst.hi_safe, power, float(cap_kw))
        u[t] = cool
        temp[t + 1] = inst.a * temp[t] + (1.0 - inst.a) * inst.ambient[t] - inst.b * cool
    return evaluate(inst, rule, u, temp)


def _grant_by_urgency(on: np.ndarray, urgency: np.ndarray, power: np.ndarray, cap_kw: float) -> np.ndarray:
    """Wer kühlen will (`on`), bekommt Strom in der Reihenfolge der Dringlichkeit, solange die Grenze reicht; Gleichstand: kleinerer Index."""
    granted = np.zeros(len(on), dtype=bool)
    if power[on].sum() <= cap_kw + C.EPS:
        return on.copy()
    order = sorted(np.flatnonzero(on), key=lambda i: (-urgency[i], i))
    used = 0.0
    for i in order:
        if used + power[i] <= cap_kw + C.EPS:
            granted[i] = True
            used += power[i]
    return granted


def smallest_cap(inst: Instance, *, tol_kw: float = 0.05) -> float | None:
    """Kleinste Leistungsgrenze (Bisektion), bei der die Regel `grenze` das Band einhält; None, wenn schon ohne Grenze das Band verlassen wird.

    Annahme: Hält die Regel bei einer Grenze das Band, dann auch bei jeder größeren (tests/test_claims.py zählt das über die Sweep-Instanzen).
    """
    hi_cap = inst.total_power_kw
    if not simulate(inst, "grenze", cap_kw=hi_cap).in_band:
        return None
    lo_cap = 0.0
    while hi_cap - lo_cap > tol_kw:
        mid = 0.5 * (lo_cap + hi_cap)
        if simulate(inst, "grenze", cap_kw=mid).in_band:
            hi_cap = mid
        else:
            lo_cap = mid
    return hi_cap


# --- Exakte Untergrenze: Leistung kleinstmöglich, Band immer eingehalten -------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class ExactResult:
    status: str                # "optimal", "zeitlimit" oder "unzulässig"
    peak_kw: float | None      # kleinste Spitze (bei "zeitlimit": beste gefundene, eine obere Schranke)
    lower_bound_kw: float | None
    u: np.ndarray | None       # (STEPS, n), bei LP (integer=False) Bruchteile in [0, 1]


def _free_response(inst: Instance) -> np.ndarray:
    """Temperatur (STEPS, n) für t = 1..STEPS ohne jede Kühlung."""
    a = inst.a
    t_free = np.empty((C.STEPS, inst.n))
    cur = inst.t0.copy()
    for t in range(C.STEPS):
        cur = a * cur + (1.0 - a) * inst.ambient[t]
        t_free[t] = cur
    return t_free


def exact_peak(inst: Instance, *, integer: bool, time_limit_s: float | None = None) -> ExactResult:
    """Kleinste Spitze, bei der es einen Plan gibt, der das Band zu allen Zeitpunkten einhält.

    `integer=False`: Reefer dürfen mit Bruchteilen der Leistung laufen (LP): untere Schranke für jeden Plan, der das Band einhält, auch für Ein/Aus-Pläne.
    `integer=True`: nur an/aus (MILP, HiGHS): die wirklich kleinste Spitze eines Ein/Aus-Plans.
    Variablen: u[i, s] (n·STEPS) und die Spitze P. T[i, t] ist linear in u (siehe Modul-Docstring).
    """
    n, steps = inst.n, C.STEPS
    a, b = inst.a, inst.b
    t_free = _free_response(inst)  # (STEPS, n): T[t] ohne Kühlung, t = 1..STEPS
    blocks, rhs_up, rhs_lo = [], [], []
    for i in range(n):
        # Matrix M[t-1, s] = b·a^(t-1-s) für s < t; Zeile t gehört zum Zeitpunkt t (1..STEPS)
        idx = np.arange(steps)
        expo = idx[:, None] - idx[None, :]          # t-1 - s mit Zeile r = t-1, Spalte s
        m = np.where(expo >= 0, b[i] * a[i] ** np.maximum(expo, 0), 0.0)
        blocks.append(csr_matrix(m))
        rhs_up.append(t_free[:, i] - inst.lo[i])      # T = t_free − M·u ≥ lo  ⇔  M·u ≤ t_free − lo
        rhs_lo.append(t_free[:, i] - inst.hi_safe[i])  # T ≤ hi + Reserve  ⇔  M·u ≥ t_free − hi_safe
    m_all = block_diag(blocks, format="csr")           # (n·steps, n·steps), Variablen i-major
    # Leistung je Schritt: Σ_i P_i·u[i, t] − P ≤ 0
    rows, cols, vals = [], [], []
    for i in range(n):
        for t in range(steps):
            rows.append(t)
            cols.append(i * steps + t)
            vals.append(inst.power_kw[i])
    p_sum = coo_matrix((vals, (rows, cols)), shape=(steps, n * steps)).tocsr()
    a_mat = vstack([
        hstack([m_all, csr_matrix((n * steps, 1))]),
        hstack([p_sum, csr_matrix(-np.ones((steps, 1)))]),
    ], format="csr")
    lo_vec = np.concatenate([np.concatenate(rhs_lo), np.full(steps, -np.inf)])
    hi_vec = np.concatenate([np.concatenate(rhs_up), np.zeros(steps)])
    cost = np.zeros(n * steps + 1)
    cost[-1] = 1.0
    bounds = Bounds(np.zeros(n * steps + 1), np.concatenate([np.ones(n * steps), [inst.total_power_kw]]))
    integrality = np.concatenate([np.ones(n * steps) if integer else np.zeros(n * steps), [0]])
    options = {"presolve": True}
    if time_limit_s is not None:
        options["time_limit"] = float(time_limit_s)
    res = milp(cost, constraints=LinearConstraint(a_mat, lo_vec, hi_vec), bounds=bounds, integrality=integrality, options=options)
    if res.x is None:
        status = "unzulässig" if res.status in (2, 3) or "infeasible" in str(res.message).lower() else "zeitlimit"
        return ExactResult(status, None, None, None)
    u = res.x[:-1].reshape(n, steps).T
    status = "optimal" if res.status == 0 else "zeitlimit"
    bound = getattr(res, "mip_dual_bound", None)
    return ExactResult(status, float(res.x[-1]), None if bound is None else float(bound), u)
