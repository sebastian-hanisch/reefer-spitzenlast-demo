"""PDF-Export: Sonderzeichen (fpdf2 stürzt bei „–“ und „€“ ab), Inhalt, Randeinstellungen."""

import re

import pytest

import rsl_constants as C
import rsl_evaluation as ev
from rsl_pdf_export import generate_rsl_pdf, pdf_text

EXPECTED = {"–": "-", "—": "-", "−": "-", "€": "EUR", "δ": "Delta", "≥": ">=", "≤": "<=", "→": "->", "≈": "ca.", "„": '"', "“": '"', "’": "'", "·": "-", "±": "+-", "⚠️": "(!)", "**": ""}


@pytest.mark.parametrize("char,replacement", list(EXPECTED.items()))
def test_pdf_text_replaces_every_known_troublemaker(char, replacement):
    assert pdf_text(f"a{char}b") == f"a{replacement}b"


def test_pdf_text_keeps_german_umlauts_and_survives_unknown_characters():
    assert pdf_text("Spitze über Größe ß") == "Spitze über Größe ß"
    assert pdf_text("😀") == "?"


def _texts(data):
    raw = re.findall(rb"\((.*?)\)\s*Tj", data)
    return [t.decode("latin-1") for t in raw]


def test_pdf_contains_the_settings_the_rules_and_the_verdicts():
    a = ev.analyse(ev.Settings())
    data = generate_rsl_pdf(a, compress=False)
    assert data.startswith(b"%PDF")
    text = " ".join(_texts(data))
    for rule in C.RULES:
        assert pdf_text(C.RULE_LABELS[rule].split(" ")[0]) in text  # erstes Wort: Umlaute stehen im PDF als Escape-Folge, nicht als Zeichen
    assert "88,0" in text and "42,0 kW" in text            # Spitze ohne Steuerung und kleinste Grenze am Standard-Block
    assert "Zufalls-Seed" in text and "Modellrechnungen" in text
    assert "**" not in text


@pytest.mark.parametrize("settings", [
    ev.Settings(tmean=35, sun=10, band=0.5, margin=0.0),   # schon ohne Steuerung außerhalb: keine Grenze, keine untere Schranke
    ev.Settings(n=C.N_MIN, margin=C.MARGIN_MAX, sync=0),
    ev.Settings(cap=C.CAP_MIN),
])
def test_pdf_generation_works_at_the_edges(settings):
    assert generate_rsl_pdf(ev.analyse(settings)).startswith(b"%PDF")
