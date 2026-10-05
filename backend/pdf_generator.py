#!/usr/bin/env python3
"""
PSAN Radar — Phase 5: EU Project Proposal & Needs Assessment PDF Generator
==========================================================================

Generates a formal 2-page executive engineering dossier
("Fișă de Fundamentare Tehnică și Nevoi Comunitare") for any selected UAT,
serving as the socio-economic and technical justification attached to grant
applications (PoIDS, Fondul pentru Modernizare, PNRAS).

Pure ReportLab (platypus) — no external C/Cairo system dependencies.

Requirements:
    pip install reportlab

Usage (standalone):
    python pdf_generator.py path/to/dossier.json output.pdf
"""

from __future__ import annotations

import io
import json
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

# =============================================================================
# BRAND & STYLE CONSTANTS
# =============================================================================

EWB_DARK = colors.HexColor("#1e3a5f")     # EWB deep blue
EWB_ACCENT = colors.HexColor("#e67e22")   # engineering orange
TIER_COLORS = {
    "CRITICAL": colors.HexColor("#b91c1c"),
    "HIGH": colors.HexColor("#b45309"),
    "MODERATE": colors.HexColor("#166534"),
}
TIER_BG = {
    "CRITICAL": colors.HexColor("#fee2e2"),
    "HIGH": colors.HexColor("#fef3c7"),
    "MODERATE": colors.HexColor("#dcfce7"),
}

S_TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=14,
                         leading=18, textColor=EWB_DARK, alignment=TA_CENTER,
                         spaceAfter=4)
S_BANNER = ParagraphStyle("banner", fontName="Helvetica-Bold", fontSize=9,
                          leading=12, textColor=colors.white, alignment=TA_CENTER)
S_H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14,
                      textColor=EWB_DARK, spaceBefore=10, spaceAfter=4)
S_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12.5,
                        alignment=TA_JUSTIFY)
S_CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11)
S_CELL_B = ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.5,
                          leading=11, textColor=colors.white)
S_META = ParagraphStyle("meta", fontName="Helvetica", fontSize=8.5, leading=12)
S_FOOT = ParagraphStyle("foot", fontName="Helvetica-Oblique", fontSize=7.5,
                        leading=10, textColor=colors.HexColor("#555555"))

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

# =============================================================================
# SECTION BUILDERS
# =============================================================================

def _banner() -> Table:
    t = Table([[Paragraph("ENGINEERS WITHOUT BORDERS ROMÂNIA | INGINERI FĂRĂ FRONTIERE",
                          S_BANNER)]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), EWB_DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _metadata_bar(d: dict) -> Table:
    tier = d["uat_profile"]["priority_tier"]
    badge = ParagraphStyle("badge", parent=S_META, textColor=colors.white,
                           fontName="Helvetica-Bold", alignment=TA_CENTER)
    rows = [
        [Paragraph(f"<b>Data generării:</b> {datetime.now():%d.%m.%Y}", S_META),
         Paragraph(f"<b>UAT:</b> {d['uat_profile']['uat_name']}", S_META),
         Paragraph(f"<b>Județ:</b> {d['uat_profile']['county']}", S_META)],
        [Paragraph(f"<b>Cod SIRUTA:</b> {d['uat_profile']['siruta']}", S_META),
         Paragraph(f"<b>Populație:</b> {d['uat_profile']['population']:,}".replace(",", "."), S_META),
         Table([[Paragraph(f"STATUT: {tier}", badge)]],
               colWidths=[CONTENT_W / 3 - 4 * mm],
               style=TableStyle([
                   ("BACKGROUND", (0, 0), (-1, -1), TIER_COLORS.get(tier, EWB_DARK)),
                   ("TOPPADDING", (0, 0), (-1, -1), 2),
                   ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
               ]))],
    ]
    t = Table(rows, colWidths=[CONTENT_W / 3] * 3)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, EWB_DARK),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def _executive_summary(d: dict) -> KeepTogether:
    tier = d["uat_profile"]["priority_tier"]
    rvi = d["uat_profile"]["rvi_score"]
    deficits = d["identified_deficits"]
    text = (
        f"<b>Radar Vulnerability Index (RVI): {rvi:.1f} / 100 — {tier}.</b> "
        f"{d['engineering_justification']['text']} "
        f"Deficite principale: {deficits['sanitation_percent']:.1f}% gospodării fără "
        f"canalizare, {deficits['offgrid_percent']:.1f}% neelectrificate, "
        f"{deficits['education_risk_percent']:.1f}% risc de abandon școlar. "
        f"Intervenția urgentă este justificată de convergența acestor deficite "
        f"infrastructurale și sociale."
    )
    inner = Table([[Paragraph(text, S_BODY)]], colWidths=[CONTENT_W - 8 * mm])
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TIER_BG.get(tier, colors.whitesmoke)),
        ("BOX", (0, 0), (-1, -1), 1, TIER_COLORS.get(tier, EWB_DARK)),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return KeepTogether([Paragraph("1. REZUMAT EXECUTIV — JUSTIFICAREA URGENȚEI", S_H2), inner])


def _pct(x: float) -> str:
    return f"{x:.1f}%"


def _indicators_table(d: dict) -> KeepTogether:
    deficits = d["identified_deficits"]
    marg = d.get("i_marginalization")
    marg_pct = _pct(marg * 100) if marg is not None else "n/d"
    header = [Paragraph("Indicator", S_CELL_B), Paragraph("Valoare", S_CELL_B),
              Paragraph("Sursă oficială", S_CELL_B), Paragraph("Prag critic", S_CELL_B)]
    rows = [
        ["Canalizare & Salubritate (gospodării fără racord)",
         _pct(deficits["sanitation_percent"]), "INS — RPL 2021", "≥ 50%"],
        ["Sărăcie Energetică (gospodării neconectate la rețea)",
         _pct(deficits["offgrid_percent"]), "Ministerul Energiei / România fără Lumină", "≥ 50%"],
        ["Risc de Abandon Școlar",
         _pct(deficits["education_risk_percent"]), "MATE / SIIIR", "≥ 50%"],
        ["Indice Marginalizare Comunitară (LHDI)",
         marg_pct, "PNUD / INS", "≥ 50%"],
    ]
    data = [header] + [[Paragraph(str(c), S_CELL) for c in r] for r in rows]
    t = Table(data, colWidths=[CONTENT_W * 0.40, CONTENT_W * 0.13,
                               CONTENT_W * 0.32, CONTENT_W * 0.15], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), EWB_DARK),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in range(1, len(data)):
        if i % 2 == 1:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.whitesmoke))
        else:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.white))
    t.setStyle(TableStyle(style))
    return KeepTogether([Paragraph("2. INDICATORI DETALIAȚI DE VULNERABILITATE", S_H2), t])


def _interventions_matrix(d: dict) -> KeepTogether:
    header = [Paragraph("Intervenție Tehnică Propusă", S_CELL_B),
              Paragraph("Condiție de Declanșare", S_CELL_B),
              Paragraph("Buget Estimativ (EUR)", S_CELL_B),
              Paragraph("Durată (luni)", S_CELL_B)]
    budget_map = {
        "fotovoltaic": ("25.000 – 60.000", "4 – 8"),
        "fito": ("80.000 – 180.000", "8 – 14"),
        "educa": ("40.000 – 90.000", "6 – 10"),
    }

    def budget_for(desc: str) -> tuple[str, str]:
        dl = desc.lower()
        for key, val in budget_map.items():
            if key in dl:
                return val
        return ("30.000 – 100.000", "6 – 12")

    rows = []
    for iv in d["recommended_interventions"]:
        b, dur = budget_for(iv["description"])
        rows.append([iv["description"], iv["condition"], b, dur])
    if not rows:
        rows.append(["Program de monitorizare și mentenanță preventivă a infrastructurii existente",
                     "toți indicatorii sub prag critic", "10.000 – 25.000", "3 – 6"])
    data = [header] + [[Paragraph(str(c), S_CELL) for c in r] for r in rows]
    t = Table(data, colWidths=[CONTENT_W * 0.46, CONTENT_W * 0.20,
                               CONTENT_W * 0.19, CONTENT_W * 0.15], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), EWB_ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in range(1, len(data)):
        style.append(("BACKGROUND", (0, i), (-1, i),
                      colors.whitesmoke if i % 2 == 1 else colors.white))
    t.setStyle(TableStyle(style))
    return KeepTogether([Paragraph("3. SPECIFICAȚII TEHNICE DE INGINERIE — MATRICEA INTERVENȚIILOR", S_H2), t])


def _funding_table(d: dict) -> KeepTogether:
    header = [
        Paragraph("Linie de Finanțare & Cod Apel", S_CELL_B),
        Paragraph("Autoritate & Sursă", S_CELL_B),
        Paragraph("Grant / Cofin.", S_CELL_B),
        Paragraph("Plafon Max.", S_CELL_B),
        Paragraph("Scor ETF", S_CELL_B),
    ]
    rows = []
    for f in d["eligible_eu_funding_lines"]:
        call_code = f.get("call_code", "MYSMIS-2025")
        auth = f.get("managing_authority", "MIPE")
        src = f.get("funding_source", "FSE+/FEDR")
        g_pct = f.get("grant_intensity_pct", 98.0)
        c_pct = f.get("uat_cofinancing_pct", 2.0)
        max_eur = f.get("max_grant_eur", 1000000.0)
        etf = f.get("estimated_etf_score", 85.0)
        status = f.get("eligibility_status", "ELIGIBIL")
        rows.append([
            f"<b>{f['name']}</b><br/>Cod: {call_code}<br/>{f.get('description') or ''}",
            f"{auth}<br/>({src})",
            f"{g_pct:.0f}% grant<br/>{c_pct:.0f}% UAT",
            f"{max_eur:,.0f} EUR".replace(",", "."),
            f"<b>{etf:.1f}/100</b><br/>{status}",
        ])
    if not rows:
        rows = [[
            "PoIDS / Fondul pentru Modernizare / PNRAS",
            "MIPE / AFM / ME",
            "98–100%",
            "2.000.000 EUR",
            "85.0/100",
        ]]
    data = [header] + [[Paragraph(str(c), S_CELL) for c in r] for r in rows]
    t = Table(
        data,
        colWidths=[
            CONTENT_W * 0.38,
            CONTENT_W * 0.22,
            CONTENT_W * 0.12,
            CONTENT_W * 0.14,
            CONTENT_W * 0.14,
        ],
        repeatRows=1,
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), EWB_DARK),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in range(1, len(data)):
        style.append(("BACKGROUND", (0, i), (-1, i),
                      colors.whitesmoke if i % 2 == 1 else colors.white))
    t.setStyle(TableStyle(style))
    return KeepTogether([Paragraph("4. MATRICEA DE ELIGIBILITATE ȘI SCOR ETF PE APELURI UE / NAȚIONALE", S_H2), t])


def _signoff() -> KeepTogether:
    sig = Table([
        [Paragraph("_____________________________", S_META),
         Paragraph("_____________________________", S_META)],
        [Paragraph("Technical Lead<br/>Ingineri fără Frontiere România", S_META),
         Paragraph("Project Coordinator<br/>EWB România", S_META)],
    ], colWidths=[CONTENT_W / 2] * 2)
    sig.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    footer = Paragraph(
        "Document generat pe baza datelor oficiale INS, RPL 2021 și Ministerul "
        "Energiei prin platforma PSAN Radar. Valorile indicatoare au caracter "
        "orientativ și trebuie validate prin audit tehnic de teren înainte de "
        "depunerea cererii de finanțare.", S_FOOT)
    return KeepTogether([Spacer(1, 8 * mm), sig, Spacer(1, 4 * mm), footer])

# =============================================================================
# PUBLIC API
# =============================================================================

def build_uat_dossier_pdf(dossier_data: dict) -> io.BytesIO:
    """Build the 2-page UAT engineering dossier PDF and return it as an
    in-memory buffer.

    dossier_data: dict matching the EUProjectDossier schema from main.py
    (optionally with a top-level "i_marginalization" float).
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Fișă de Fundamentare — {dossier_data['uat_profile']['uat_name']}",
        author="Engineers Without Borders România — PSAN Radar",
    )
    story = [
        _banner(),
        Spacer(1, 5 * mm),
        Paragraph("RAPORT DE EVALUARE A VULNERABILITĂȚII ȘI FIȘĂ DE INTERVENȚIE TEHNICĂ",
                  S_TITLE),
        _metadata_bar(dossier_data),
        _executive_summary(dossier_data),
        _indicators_table(dossier_data),
        _interventions_matrix(dossier_data),
        _funding_table(dossier_data),
        _signoff(),
    ]
    doc.build(story)
    buf.seek(0)
    return buf


if __name__ == "__main__":
    import sys
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f:
        payload = json.load(f)
    with open(dst, "wb") as f:
        f.write(build_uat_dossier_pdf(payload).read())
    print(f"PDF written to {dst}")
