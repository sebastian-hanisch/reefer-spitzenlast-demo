"""PDF-Export des Ergebnisses (fpdf2, Helvetica-Kernschrift, nur Text und Tabellen).

Die Kernschriften kennen nur Latin-1: Umlaute sind erlaubt, aber Gedankenstrich, Minuszeichen, "€", "≥", "δ", Emoji usw. lassen fpdf2 abstürzen. Deshalb läuft jeder Text durch pdf_text()."""

import rsl_constants as C
from rsl_evaluation import de, reduction_percent, verdict_cap_setting, verdict_peak

_REPLACEMENTS = {
    "**": "", "–": "-", "—": "-", "‑": "-", "−": "-", "δ": "Delta", "τ": "Tau", "≥": ">=", "≤": "<=", "→": "->", "≈": "ca.", "€": "EUR", "·": "-",
    "“": '"', "”": '"', "„": '"', "’": "'", "‘": "'", "±": "+-", "⚠️": "(!)", "⚠": "(!)", "✅": "", "ℹ️": "",
}


def pdf_text(text) -> str:
    """Text für die Helvetica-Kernschrift: bekannte Sonderzeichen ersetzen, den Rest Latin-1-sicher machen."""
    text = str(text)
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    return text.encode("latin-1", "replace").decode("latin-1")


def generate_rsl_pdf(a, compress=True) -> bytes:
    """Ergebnis der aktuellen Einstellung als PDF: Einstellungen, Kennzahlen je Regel, Urteile, Hinweis zu den Annahmen. `a`: rsl_evaluation.Analysis."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    s = a.settings
    base = a.results["ungesteuert"]
    pdf = FPDF()
    pdf.set_compression(compress)
    pdf.add_page()

    def line(text, height=6):
        pdf.multi_cell(0, height, pdf_text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def heading(text):
        pdf.set_font("Helvetica", "B", 12)
        pdf.ln(2)
        line(text, 8)
        pdf.set_font("Helvetica", "", 10)

    pdf.set_font("Helvetica", "B", 16)
    line("Reefer-Spitzenlast: Wie lange darf der Strom pausieren?", 10)
    pdf.set_font("Helvetica", "", 10)
    line("Sebastian Hanisch - Operations Research und Machine Learning")

    heading("Einstellungen")
    for label, value in (
        ("Reefer im Block", s.n), ("Anteil gefrorener Reefer", f"{s.share} %"), ("Regelband +-", f"{de(s.band, 2)} K"), ("Reserve über dem Regelband", f"{de(s.margin, 2)} K"),
        ("Reefer, die am oberen Rand starten", f"{s.sync} %"), ("Außentemperatur, Tagesmittel", f"{de(s.tmean, 0)} C"), ("Sonnenzuschlag um 12 Uhr", f"{de(s.sun, 0)} K"),
        ("Strom reihum: Gruppen", s.groups), ("Strom reihum: Slotlänge", f"{s.slot * 15} Minuten"), ("Leistungsgrenze", f"{s.cap} % = {de(a.cap_kw)} kW"), ("Zufalls-Seed", s.seed),
    ):
        pdf.cell(80, 6, pdf_text(label))
        pdf.cell(0, 6, pdf_text(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    heading("Ergebnis je Regel")
    pdf.set_font("Helvetica", "B", 9)
    widths = (62, 22, 26, 24, 28, 28)
    for text, w in zip(("Regel", "Spitze kW", "gegen ungest.", "Energie kWh", "Abw. sicher K", "Reefer-Std."), widths):
        pdf.cell(w, 6, pdf_text(text), border=1)
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 9)
    for rule in C.RULES:
        r = a.results[rule]
        cells = (C.RULE_LABELS[rule], de(r.peak_kw), f"{de(-reduction_percent(r.peak_kw, base.peak_kw), 0)} %", de(r.energy_kwh, 0), de(r.max_excess_k, 2), de(r.reefer_hours_out))
        for text, w in zip(cells, widths):
            pdf.cell(w, 6, pdf_text(text), border=1)
        pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    if a.lp.peak_kw is not None:
        line(f"Untere Schranke der Spitze (stufenlose Leistung): {de(a.lp.peak_kw)} kW. Kleinste Grenze, die den sicheren Bereich hält: "
             f"{'keine' if a.smallest_cap_kw is None else de(a.smallest_cap_kw) + ' kW'}.")

    heading("Urteile")
    line(verdict_peak(a)[1])
    line(verdict_cap_setting(a)[1])

    heading("Hinweis")
    line("Alle Zahlen sind Modellrechnungen mit eigenen Annahmen (Zeitkonstanten, Kühlrate, Leistung), keine Messung an einem Terminal und nicht kalibriert. "
         "Die Reihenfolge der Regeln ist die Aussage, nicht die absoluten Kilowatt.")
    return bytes(pdf.output())
