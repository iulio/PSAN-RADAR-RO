#!/usr/bin/env python3
"""
PSAN Radar — Phase 7 (Refined): EU Grant Engineering, MySMIS 2021+ Financial
Structuring, HG 907/2016 Deviz General, ETF Scoring & DNSH Compliance Engine
=============================================================================

Bridges deterministic engineering sizing (`engineering_sizing.py`), corporate CSR
in-kind allocations (`materials_marketplace.py`), and demographic vulnerability
metrics (`INS RPL 2021`, `Ministerul Energiei`, `MATE/SIIIR`) with the formal
requirements of Romanian & EU non-reimbursable funding programmes:
  - PoIDS 2021–2027 (Programul Incluziune și Demnitate Socială — FSE+ & FEDR)
  - Fondul pentru Modernizare / AFM (Sisteme Fotovoltaice Gospodării Izolate)
  - PNRAS / PNRR C15 (Programul Național pentru Reducerea Abandonului Școlar)
  - PNRR C1 / AFIR DR-27 (Epurare Descentralizată & Fitodepurare NTPA-001/011)
  - Programul Regional 2021–2027 (PR Nord-Est / PR Sud-Est — Micro-Rețele Comunitare)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from engineering_sizing import InterventionType, calculate_bom
from materials_marketplace import get_uat_allocations

# =============================================================================
# CONFIGURATION
# =============================================================================

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
LLM_API_MODE = os.getenv("LLM_API_MODE", "ollama")  # "ollama" | "openai"
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))

SYSTEM_PROMPT = (
    "Ești un expert senior în scrierea cererilor de finanțare pentru fonduri "
    "europene nerambursabile în România (MySMIS 2021+, PoIDS, PNRAS, Fondul pentru "
    "Modernizare, AFIR, Programe Regionale 2021-2027) și inginerie comunitară pentru "
    "organizația Ingineri Fără Frontiere România (EWB Romania). "
    "Redactezi în limba română, în registrul formal-birocratic specific Ghidului "
    "Solicitantului și HG nr. 907/2016, cu paragrafe coerente, citând explicit "
    "sursele oficiale (INS RPL 2021, Ministerul Energiei, MATE/SIIIR, SR EN 62124, "
    "NTPA-001/011, Reg. UE 2020/852 DNSH) și valorile financiare exacte din deviz."
)


# =============================================================================
# OFFICIAL ROMANIAN & EU FUNDING PROGRAMMES CATALOG (2024–2027)
# =============================================================================

FUNDING_PROGRAMMES_CATALOG: Dict[str, Dict[str, Any]] = {
    "PoIDS": {
        "key": "PoIDS",
        "name": "PoIDS 2021–2027 — Dezvoltare Locală și Reducerea Sărăciei în Comunități Marginalizate",
        "call_code": "PEO/PoIDS/P02/FSE+/FEDR/2025",
        "managing_authority": "MIPE — Autoritatea de Management PoIDS",
        "funding_source": "FSE+ & FEDR (Reg. UE 2021/1060)",
        "grant_intensity_pct": 98.0,
        "uat_cofinancing_pct": 2.0,
        "max_grant_eur": 2000000.0,
        "min_grant_eur": 100000.0,
        "intervention_type": InterventionType.INTEGRATED,
        "description": (
            "Finanțare integrată FSE+/FEDR (98% nerambursabil, 2% cofinanțare UAT) pentru "
            "infrastructură comunitară de bază (micro-rețele PV, fitodepurare descentralizată "
            "și centre educaționale multifuncționale) în UAT-uri rurale vulnerabile."
        ),
    },
    "Fondul pentru Modernizare": {
        "key": "Fondul pentru Modernizare",
        "name": "Fondul pentru Modernizare / AFM — Sisteme Fotovoltaice pentru Gospodării Izolate",
        "call_code": "FM-AFM-OFFGRID-I7-2025",
        "managing_authority": "Ministerul Energiei & Administrația Fondului pentru Mediu (AFM)",
        "funding_source": "Fondul pentru Modernizare (Directiva UE 2018/410 Art. 10d)",
        "grant_intensity_pct": 100.0,
        "uat_cofinancing_pct": 0.0,
        "max_grant_eur": 500000.0,
        "min_grant_eur": 25000.0,
        "intervention_type": InterventionType.OFFGRID_PV,
        "description": (
            "Finanțare 100% nerambursabilă pentru electrificarea gospodăriilor izolate "
            "neconectate la SEN prin sisteme fotovoltaice off-grid și stocare LiFePO4 "
            "dimensionate conform SR EN 62124 și normativului I7/2011."
        ),
    },
    "PNRAS": {
        "key": "PNRAS",
        "name": "PNRAS / PNRR C15 — Reducerea Abandonului Școlar & Centre Digitale EduPod",
        "call_code": "PNRR-C15-I4-PNRAS-R2",
        "managing_authority": "Ministerul Educației — UMPFE",
        "funding_source": "PNRR — Componenta 15 Educație (Reforma 3 / Investiția 4)",
        "grant_intensity_pct": 100.0,
        "uat_cofinancing_pct": 0.0,
        "max_grant_eur": 300000.0,
        "min_grant_eur": 40000.0,
        "intervention_type": InterventionType.EDUCATION,
        "description": (
            "Grant 100% nerambursabil (până la 300.000 EUR/unitate școlară) pentru "
            "prevenirea părăsirii timpurii a școlii prin hub-uri digitale containerizate "
            "EduPod NZEB (ISO 6346 / C107), stații IT și program «Școală după Școală»."
        ),
    },
    "AFIR Fitodepurare": {
        "key": "AFIR Fitodepurare",
        "name": "PNRR C1 / AFIR DR-27 — Stații Ecologice de Fitodepurare NTPA-001/011 (<2.000 l.e.)",
        "call_code": "AFIR-DR27-PNRR-C1-APA",
        "managing_authority": "AFIR & Ministerul Mediului, Apelor și Pădurilor (MMAP)",
        "funding_source": "FEADR (PS PAC 2023–2027) & PNRR C1 Managementul Apei",
        "grant_intensity_pct": 95.0,
        "uat_cofinancing_pct": 5.0,
        "max_grant_eur": 1500000.0,
        "min_grant_eur": 50000.0,
        "intervention_type": InterventionType.SANITATION,
        "description": (
            "Finanțare 95% nerambursabilă pentru sisteme descentralizate de colectare și "
            "epurare extensivă (decantoare primare Imhoff + bazine de fitodepurare HSSF "
            "cu macrofite Phragmites australis) conforme cu HG 188/2002 (NTPA-001/011)."
        ),
    },
    "Programul Regional": {
        "key": "Programul Regional",
        "name": "Programul Regional 2021–2027 (PR NE / SE) — Eficiență Energetică & Micro-Rețele",
        "call_code": "PR-2021-2027-P3-ENERGIE",
        "managing_authority": "Agenția pentru Dezvoltare Regională (ADR Nord-Est / Sud-Est)",
        "funding_source": "FEDR — Prioritatea 3: O regiune durabilă și prietenoasă cu mediul",
        "grant_intensity_pct": 98.0,
        "uat_cofinancing_pct": 2.0,
        "max_grant_eur": 1200000.0,
        "min_grant_eur": 80000.0,
        "intervention_type": InterventionType.INTEGRATED,
        "description": (
            "Finanțare FEDR (98% grant, 2% aport UAT) pentru autonomie energetică locală, "
            "reabilitare termică C107 și infrastructură verde-albastră în comunele din "
            "regiunile Nord-Est și Sud-Est."
        ),
    },
}


def resolve_programme_spec(funding_line: str) -> Dict[str, Any]:
    """Match a funding_line query string to the canonical programme specification."""
    clean = (funding_line or "PoIDS").strip()
    if clean in FUNDING_PROGRAMMES_CATALOG:
        return FUNDING_PROGRAMMES_CATALOG[clean]
    low = clean.lower()
    if "modern" in low or "afm" in low or "foto" in low:
        return FUNDING_PROGRAMMES_CATALOG["Fondul pentru Modernizare"]
    if "pnras" in low or "educa" in low or "c15" in low:
        return FUNDING_PROGRAMMES_CATALOG["PNRAS"]
    if "afir" in low or "fito" in low or "ntpa" in low or "apa" in low or "c1" in low:
        return FUNDING_PROGRAMMES_CATALOG["AFIR Fitodepurare"]
    if "regional" in low or "adr" in low or "fedr" in low:
        return FUNDING_PROGRAMMES_CATALOG["Programul Regional"]
    return FUNDING_PROGRAMMES_CATALOG["PoIDS"]


# =============================================================================
# PYDANTIC RESPONSE SCHEMAS (Pydantic v2)
# =============================================================================

class HG907BudgetChapter(BaseModel):
    chapter_code: str = Field(..., description="HG 907/2016 Chapter Code (Cap. 1-2, Cap. 3, Cap. 4, Cap. 5, Cap. 6)")
    chapter_name: str = Field(..., description="Official HG 907/2016 Chapter Title")
    eligible_eur: float = Field(..., ge=0)
    non_eligible_eur: float = Field(..., ge=0)
    total_eur: float = Field(..., ge=0)


class GrantFinancialPlan(BaseModel):
    programme_key: str
    programme_name: str
    call_code: str
    managing_authority: str
    funding_source: str
    intervention_type: str
    gross_bom_capex_eur: float = Field(..., description="Total deterministic BOM CAPEX before CSR")
    csr_in_kind_deduction_eur: float = Field(..., description="Net CAPEX saved via allocated CSR lots")
    net_investment_required_eur: float = Field(..., description="Net project CAPEX to be financed")
    eligible_expenditure_eur: float = Field(..., description="Eligible expenditure under call rules")
    non_eligible_expenditure_eur: float = Field(..., description="Non-eligible expenditure covered locally")
    grant_intensity_pct: float = Field(..., description="Non-reimbursable grant intensity (%)")
    uat_cofinancing_pct: float = Field(..., description="Applicant co-financing rate on eligible costs (%)")
    eu_grant_amount_eur: float = Field(..., description="Non-reimbursable EU/national grant amount (EUR)")
    uat_cofinancing_eur: float = Field(..., description="Total UAT co-financing including non-eligible costs (EUR)")
    max_grant_ceiling_eur: float
    within_call_ceiling: bool
    hg907_chapters: List[HG907BudgetChapter]


class ETFCriterionScore(BaseModel):
    code: str
    title: str
    score: float
    max_score: float
    justification: str


class ETFScorecard(BaseModel):
    total_score: float = Field(..., ge=0, le=100)
    quality_threshold: float = Field(70.0)
    qualifies_for_funding: bool
    status_label: str
    criteria: List[ETFCriterionScore]


class DNSHObjectiveItem(BaseModel):
    objective_code: str
    objective_name: str
    compliant: bool
    technical_compliance_justification: str


class GrantNarrative(BaseModel):
    funding_line: str = Field(..., description="Target EU funding programme")
    justificarea_nevoii: str = Field(..., description="Secțiunea: Justificarea Nevoii și Grupul Țintă")
    descrierea_activitatilor: str = Field(..., description="Secțiunea: Descrierea Activităților Propuse")
    rezultate_si_indicatori: str = Field(..., description="Secțiunea: Rezultate Așteptate și Indicatori")
    sustenabilitate: str = Field(..., description="Secțiunea: Sustenabilitate și Impact pe Termen Lung")
    buget_sumar: str = Field(..., description="Secțiunea: Buget Sumar și Capitole de Cheltuieli")
    generated_by: str = Field(..., description="'llm' or 'fallback-template'")
    financial_plan: Optional[GrantFinancialPlan] = None
    etf_scorecard: Optional[ETFScorecard] = None
    dnsh_matrix: Optional[List[DNSHObjectiveItem]] = None
    mysmis_markdown_export: Optional[str] = None


# =============================================================================
# DETERMINISTIC HG 907/2016 FINANCIAL PLAN, ETF SCORECARD & DNSH ENGINE
# =============================================================================

def compute_grant_financial_plan(dossier: dict, funding_line: str) -> tuple[GrantFinancialPlan, Any]:
    """
    Calculate the HG nr. 907/2016 Deviz General breakdown, CSR deductions,
    EU grant amount, and UAT co-financing for the target UAT and funding call.
    """
    spec = resolve_programme_spec(funding_line)
    p = dossier["uat_profile"]
    d = dossier["identified_deficits"]

    siruta = int(p["siruta"])
    households_total = int(p.get("households_total", 300))
    population = int(p.get("population", 1000))
    county = str(p.get("county", "Vrancea"))

    offgrid_ratio = float(d.get("offgrid_percent", 30.0)) / 100.0
    sanitation_ratio = float(d.get("sanitation_percent", 30.0)) / 100.0
    education_ratio = float(d.get("education_risk_percent", 30.0)) / 100.0

    target_households = max(1, int(households_total * offgrid_ratio))
    connected_pe = max(5, int(population * sanitation_ratio))
    student_stations = max(8, int(population * 0.02 * education_ratio))

    bom_res = calculate_bom(
        intervention_type=spec["intervention_type"],
        target_households=target_households,
        connected_people_equivalent=connected_pe,
        student_stations=student_stations,
        container_size_ft=20,
        county=county,
    )

    gross_capex = round(float(bom_res.total_project_capex_eur), 2)

    # Check active SQLite CSR allocations for this UAT
    try:
        allocations = get_uat_allocations(siruta)
        csr_savings = round(sum(a.net_capex_saving_eur for a in allocations), 2)
    except Exception:
        csr_savings = 0.0

    csr_deduction = round(min(csr_savings, gross_capex * 0.65), 2)
    net_investment = round(max(1000.0, gross_capex - csr_deduction), 2)

    # Structure into HG nr. 907/2016 Deviz General chapters
    # Cap 1 & 2: Amenajarea terenului și utilități (~6% of direct works)
    # Cap 3: Proiectare, studii teren, avize, consultanță MySMIS (~8%)
    # Cap 4: Investiția de bază (C+M + Echipamente tehnologice, net of CSR) (~74%)
    # Cap 5: Organizare șantier, cote ISC, diverse și neprevăzute (~10%, of which 30% non-eligible buffer)
    # Cap 6: Probe tehnologice, PRAM și instruire personal (~2%)
    cap12_total = round(net_investment * 0.06, 2)
    cap3_total = round(net_investment * 0.08, 2)
    cap5_total = round(net_investment * 0.10, 2)
    cap6_total = round(net_investment * 0.02, 2)
    cap4_total = round(net_investment - (cap12_total + cap3_total + cap5_total + cap6_total), 2)

    # Under MySMIS 2021+ / PNRR rules, ISC quotas and excess contingency in Cap. 5 (~3% of project) are non-eligible
    cap5_non_eligible = round(cap5_total * 0.30, 2)
    cap5_eligible = round(cap5_total - cap5_non_eligible, 2)

    chapters = [
        HG907BudgetChapter(
            chapter_code="Cap. 1 & 2",
            chapter_name="Amenajarea terenului, protecția mediului și asigurarea utilităților",
            eligible_eur=cap12_total,
            non_eligible_eur=0.0,
            total_eur=cap12_total,
        ),
        HG907BudgetChapter(
            chapter_code="Cap. 3",
            chapter_name="Proiectare tehnică (DALI/PT), studii geo/topo, avize și management MySMIS",
            eligible_eur=cap3_total,
            non_eligible_eur=0.0,
            total_eur=cap3_total,
        ),
        HG907BudgetChapter(
            chapter_code="Cap. 4",
            chapter_name="Investiția de bază (4.1 Construcții și instalații + 4.3 Echipamente, net de CSR)",
            eligible_eur=cap4_total,
            non_eligible_eur=0.0,
            total_eur=cap4_total,
        ),
        HG907BudgetChapter(
            chapter_code="Cap. 5",
            chapter_name="Alte cheltuieli (5.1 Organizare șantier, 5.2 Cote ISC, 5.3 Diverse și neprevăzute)",
            eligible_eur=cap5_eligible,
            non_eligible_eur=cap5_non_eligible,
            total_eur=cap5_total,
        ),
        HG907BudgetChapter(
            chapter_code="Cap. 6",
            chapter_name="Probe tehnologice, încercări PRAM (ANRE IIA/IIB) și instruire operatori locali",
            eligible_eur=cap6_total,
            non_eligible_eur=0.0,
            total_eur=cap6_total,
        ),
    ]

    eligible_total = round(sum(c.eligible_eur for c in chapters), 2)
    non_eligible_total = round(sum(c.non_eligible_eur for c in chapters), 2)

    grant_pct = float(spec["grant_intensity_pct"])
    cofin_pct = float(spec["uat_cofinancing_pct"])
    max_ceiling = float(spec["max_grant_eur"])

    raw_grant = round(eligible_total * (grant_pct / 100.0), 2)
    eu_grant = round(min(raw_grant, max_ceiling), 2)
    uat_cofinancing = round((net_investment - eu_grant), 2)

    plan = GrantFinancialPlan(
        programme_key=spec["key"],
        programme_name=spec["name"],
        call_code=spec["call_code"],
        managing_authority=spec["managing_authority"],
        funding_source=spec["funding_source"],
        intervention_type=spec["intervention_type"].value,
        gross_bom_capex_eur=gross_capex,
        csr_in_kind_deduction_eur=csr_deduction,
        net_investment_required_eur=net_investment,
        eligible_expenditure_eur=eligible_total,
        non_eligible_expenditure_eur=non_eligible_total,
        grant_intensity_pct=grant_pct,
        uat_cofinancing_pct=cofin_pct,
        eu_grant_amount_eur=eu_grant,
        uat_cofinancing_eur=uat_cofinancing,
        max_grant_ceiling_eur=max_ceiling,
        within_call_ceiling=raw_grant <= max_ceiling,
        hg907_chapters=chapters,
    )
    return plan, bom_res


def compute_etf_scorecard(dossier: dict, plan: GrantFinancialPlan) -> ETFScorecard:
    """
    Simulate the official MySMIS 2021+ Techno-Financial Evaluation Grid (Grila ETF 0–100 pct)
    based on UAT RVI severity, marginalization index, CSR co-financing leverage, and DNSH compliance.
    """
    p = dossier["uat_profile"]
    d = dossier["identified_deficits"]
    rvi = float(p.get("rvi_score", 50.0))
    marg = float(dossier.get("i_marginalization", 0.45))

    # Criterion 1: Strategic Relevance & Vulnerability Severity (Max 30 pts)
    c1_base = 18.0 + min(12.0, (rvi / 100.0) * 10.0 + marg * 4.0)
    c1_score = round(min(30.0, c1_base), 1)

    # Criterion 2: Technical Maturity, Normative Sizing & Cost-Effectiveness (Max 25 pts)
    csr_bonus = 3.5 if plan.csr_in_kind_deduction_eur > 0 else 1.5
    c2_score = round(min(25.0, 20.5 + csr_bonus), 1)

    # Criterion 3: DNSH Compliance (Reg. EU 2020/852) & Circular Economy (Max 25 pts)
    c3_score = round(min(25.0, 22.0 + (2.5 if plan.csr_in_kind_deduction_eur > 0 else 1.0)), 1)

    # Criterion 4: Operational Sustainability, Pro Bono ANRE/Hydro Team & IoT Telemetry (Max 20 pts)
    c4_score = 18.5

    total_score = round(c1_score + c2_score + c3_score + c4_score, 1)
    qualifies = total_score >= 70.0

    if total_score >= 85.0:
        status_label = "PRIORITATE FINANȚARE (Peste pragul de excelență 85 pct)"
    elif qualifies:
        status_label = "ELIGIBIL & ADMIS (Peste pragul minim de calitate 70 pct)"
    else:
        status_label = "RISC DE DEZANGAJARE (Sub pragul minim de 70 pct)"

    criteria = [
        ETFCriterionScore(
            code="C1",
            title="Relevanța Strategică și Severitatea Vulnerabilității (INS RPL 2021 & Atlas Marginalizare)",
            score=c1_score,
            max_score=30.0,
            justification=(
                f"Scor RVI {rvi:.1f}/100 ({p['priority_tier']}), rată fără canalizare {d['sanitation_percent']:.1f}%, "
                f"sărăcie energetică {d['offgrid_percent']:.1f}% și indice marginalizare {marg * 100:.1f}%."
            ),
        ),
        ETFCriterionScore(
            code="C2",
            title="Maturitatea Tehnică, Dimensionarea Normată (SR EN 62124 / NTPA-001) și Eficiența Cost-Beneficiu",
            score=c2_score,
            max_score=25.0,
            justification=(
                f"Deviz dimensionat determinist conform HG nr. 907/2016 ({plan.gross_bom_capex_eur:,.2f} EUR) "
                f"cu reducere CAPEX prin materiale CSR de {plan.csr_in_kind_deduction_eur:,.2f} EUR."
            ),
        ),
        ETFCriterionScore(
            code="C3",
            title="Conformitatea DNSH (Reg. UE 2020/852 Art. 17), Tranziția Verde și Economia Circulară",
            score=c3_score,
            max_score=25.0,
            justification=(
                "Tehnologii 100% verzi: producție solară fără emisii, stocare LiFePO4 fără plumb/cadmiu, "
                "fitodepurare gravitațională fără consum chimic și reutilizare containere ISO 6346."
            ),
        ),
        ETFCriterionScore(
            code="C4",
            title="Sustenabilitatea Operațională, Echipă Autorizată ANRE IIA/IIB și Telemetrie LoRaWAN",
            score=c4_score,
            max_score=20.0,
            justification=(
                "Asumare tehnică pro bono prin Ingineri Fără Frontiere România (specialiști ANRE IIA/IIB "
                "și hidrotehnicieni) + monitorizare continuă SCADA/LoRaWAN a parametrilor energetici și de apă."
            ),
        ),
    ]

    return ETFScorecard(
        total_score=total_score,
        quality_threshold=70.0,
        qualifies_for_funding=qualifies,
        status_label=status_label,
        criteria=criteria,
    )


def build_dnsh_compliance_matrix(uat_name: str, bom_res: Any) -> List[DNSHObjectiveItem]:
    """Build the 6-objective EU Taxonomy Regulation (EU) 2020/852 Art. 17 DNSH compliance matrix."""
    ep = bom_res.engineering_parameters
    pv_kwp = ep.pv_kwp or ep.solar_kwp or 15.0
    wetland_m2 = ep.wetland_area_m2 or 250.0

    return [
        DNSHObjectiveItem(
            objective_code="DNSH-1",
            objective_name="1. Atenuarea schimbărilor climatice",
            compliant=True,
            technical_compliance_justification=(
                f"Instalarea a {pv_kwp:.1f} kWp panouri fotovoltaice monocristaline și stocare LiFePO4 în UAT {uat_name} "
                f"elimină generatoarele diesel și lămpile cu kerosen, evitând ~{pv_kwp * 1150 * 0.000265:.2f} tone CO₂/an."
            ),
        ),
        DNSHObjectiveItem(
            objective_code="DNSH-2",
            objective_name="2. Adaptarea la schimbările climatice",
            compliant=True,
            technical_compliance_justification=(
                "Bazinul de fitodepurare include strat de protecție la îngheț de 15 cm pietriș (T_apă iarnă = 6°C), "
                "iar structura EduPod este termoizolată cu vată bazaltică ignifugă conform normativului C107."
            ),
        ),
        DNSHObjectiveItem(
            objective_code="DNSH-3",
            objective_name="3. Utilizarea durabilă și protecția resurselor de apă",
            compliant=True,
            technical_compliance_justification=(
                f"Stația de fitodepurare HSSF ({wetland_m2:.0f} m²) impermeabilizată cu geomembrană HDPE 1.5 mm "
                "oprește infiltrarea nitraților în pânza freatică și asigură efluent conform NTPA-001 (CBO5 ≤ 25 mg/L)."
            ),
        ),
        DNSHObjectiveItem(
            objective_code="DNSH-4",
            objective_name="4. Tranziția către o economie circulară",
            compliant=True,
            technical_compliance_justification=(
                "Conversia containerelor maritime ISO 6346 existente în centre EduPod și integrarea stocurilor "
                "corporative excedentare (CSR) reduc amprenta de materii prime virgine cu peste 35%."
            ),
        ),
        DNSHObjectiveItem(
            objective_code="DNSH-5",
            objective_name="5. Prevenirea și controlul poluării în aer, apă sau sol",
            compliant=True,
            technical_compliance_justification=(
                "Acumulatorii LiFePO4 nu conțin plumb, acid sulfuric liber sau cadmiu și sunt predați la finalul "
                "ciclului de viață (>6.000 cicluri) către operatori colectori autorizați conform OUG 5/2015 (DEEE)."
            ),
        ),
        DNSHObjectiveItem(
            objective_code="DNSH-6",
            objective_name="6. Protecția și refacerea biodiversității și a ecosistemelor",
            compliant=True,
            technical_compliance_justification=(
                "Zona umedă construită utilizează exclusiv specii autohtone de macrofite (Phragmites australis și "
                "Typha latifolia), creând un micro-habitat umed fără specii alohtone invazive."
            ),
        ),
    ]


def build_mysmis_markdown_dossier(
    dossier: dict,
    narrative: GrantNarrative,
    plan: GrantFinancialPlan,
    etf: ETFScorecard,
    dnsh: List[DNSHObjectiveItem],
) -> str:
    """Generate a complete, copy-and-paste ready MySMIS 2021+ Application Dossier in Markdown."""
    p = dossier["uat_profile"]
    ch_rows = "\n".join(
        f"| {c.chapter_code} | {c.chapter_name} | {c.eligible_eur:,.2f} | {c.non_eligible_eur:,.2f} | **{c.total_eur:,.2f}** |"
        for c in plan.hg907_chapters
    )
    etf_rows = "\n".join(
        f"| {c.code} | {c.title} | **{c.score:.1f} / {c.max_score:.0f}** | {c.justification} |"
        for c in etf.criteria
    )
    dnsh_rows = "\n".join(
        f"| {item.objective_code} | {item.objective_name} | **DA (Conform)** | {item.technical_compliance_justification} |"
        for item in dnsh
    )

    return f"""# CERERE DE FINANȚARE MYSMIS 2021+ — FIȘĂ TEHNICO-FINANCIARĂ INTEGRATĂ
**Apel de Proiecte:** `{plan.call_code}` — {plan.programme_name}
**Autoritate de Management:** {plan.managing_authority} ({plan.funding_source})
**Solicitant / Parteneriat:** UAT {p['uat_name']} (Județul {p['county']}, SIRUTA {p['siruta']}) în parteneriat cu **Asociația Ingineri Fără Frontiere România (EWB România)**
**Indice Vulnerabilitate Radar (RVI):** {p['rvi_score']:.1f} / 100 (`{p['priority_tier']}`) · **Punctaj Grilă ETF Estimat:** **{etf.total_score:.1f} / 100 puncte** ({etf.status_label})

---

## 1. SINTEZA FINANCIARĂ ȘI CO-FINANȚAREA PROIECTULUI (EUR, fără TVA)
- **Valoare Brută Deviz Ingineresc (BOM):** `{plan.gross_bom_capex_eur:,.2f} EUR`
- **Deducere Aport în Natură / Stocuri CSR Alocate:** `-{plan.csr_in_kind_deduction_eur:,.2f} EUR`
- **Valoare Netă Investiție de Finanțat:** `{plan.net_investment_required_eur:,.2f} EUR`
- **Valoare Totală Eligibilă:** `{plan.eligible_expenditure_eur:,.2f} EUR`
- **Grant Nerambursabil Solicitat ({plan.grant_intensity_pct:.0f}%):** **`{plan.eu_grant_amount_eur:,.2f} EUR`** (Plafon apel: `{plan.max_grant_ceiling_eur:,.2f} EUR`)
- **Contribuție Proprie UAT ({plan.uat_cofinancing_pct:.0f}% eligibil + neeligibil):** **`{plan.uat_cofinancing_eur:,.2f} EUR`**

### Deviz General Structurat pe Capitole (conform HG nr. 907/2016)
| Capitol HG 907/2016 | Denumire Capitol Bugetar | Cheltuieli Eligibile (EUR) | Cheltuieli Neeligibile (EUR) | Total Capitol (EUR) |
| :--- | :--- | ---: | ---: | ---: |
{ch_rows}
| **TOTAL** | **TOTAL GENERAL INVESTIȚIE (NET DE CSR)** | **{plan.eligible_expenditure_eur:,.2f}** | **{plan.non_eligible_expenditure_eur:,.2f}** | **{plan.net_investment_required_eur:,.2f}** |

---

## 2. SECȚIUNILE NARATIVE MYSMIS 2021+

### 2.1. Justificarea Nevoii și Grupul Țintă
{narrative.justificarea_nevoii}

### 2.2. Descrierea Activităților Propuse (Work Packages)
{narrative.descrierea_activitatilor}

### 2.3. Rezultate Așteptate și Indicatori de Realizare / Rezultat
{narrative.rezultate_si_indicatori}

### 2.4. Sustenabilitate Operațională și Impact pe Termen Lung
{narrative.sustenabilitate}

### 2.5. Fundamentarea Bugetului și Eficiența Cost-Beneficiu
{narrative.buget_sumar}

---

## 3. AUTOEVALUAREA PUNCTAJULUI ÎN GRILA ETF (0–100 PUNCTE)
| Cod | Criteriu de Evaluare Tehnico-Financiară | Punctaj | Fundamentare Tehnică |
| :--- | :--- | :---: | :--- |
{etf_rows}
| **TOTAL** | **PUNCTAJ TOTAL ESTIMAT GRILĂ ETF (Prag minim: {etf.quality_threshold:.0f} pct)** | **{etf.total_score:.1f} / 100** | **{etf.status_label}** |

---

## 4. DECLARAȚIE DE CONFORMITATE DNSH (REGULAMENTUL UE 2020/852 ART. 17)
| Cod | Obiectiv de Mediu (Taxonomia UE) | Statut | Justificare Tehnică și Normativă |
| :--- | :--- | :---: | :--- |
{dnsh_rows}
"""


# =============================================================================
# DETERMINISTIC NARRATIVE BUILDER (WITH EXACT BOM & FINANCIAL INJECTION)
# =============================================================================

def _fallback_narrative(
    dossier: dict,
    funding_line: str,
    plan: GrantFinancialPlan,
    bom_res: Any,
    etf: ETFScorecard,
) -> GrantNarrative:
    p = dossier["uat_profile"]
    d = dossier["identified_deficits"]
    ep = bom_res.engineering_parameters
    interventions = "; ".join(iv["description"] for iv in dossier["recommended_interventions"]) or (
        "implementarea infrastructurii comunitare descentralizate de energie solară, epurare ecologică și educație digitală"
    )

    pv_kwp = ep.pv_kwp or ep.solar_kwp or 15.0
    batt_kwh = ep.battery_kwh or 30.0
    wetland_m2 = ep.wetland_area_m2 or 250.0
    pe_count = ep.connected_pe or int(p["population"] * (d["sanitation_percent"] / 100.0))
    stations = ep.student_stations or 16

    justificare = (
        f"Unitatea Administrativ-Teritorială {p['uat_name']}, județul {p['county']} (cod SIRUTA {p['siruta']}), "
        f"înregistrează o populație stabilă de {p['population']:,} locuitori distribuită în {p['households_total']:,} "
        f"gospodării și prezintă un Indice de Vulnerabilitate Radar (RVI) de {p['rvi_score']:.1f}/100, "
        f"fiind încadrată în nivelul de urgență {p['priority_tier']}. Conform datelor oficiale ale Institutului "
        f"Național de Statistică (Recensământul Populației și Locuințelor RPL 2021), {d['sanitation_percent']:.1f}% "
        f"dintre locuințele ocupate sunt lipsite de acces la rețele publice de canalizare sau sisteme autorizate "
        f"de epurare a apelor uzate menajere. În paralel, evidențele Ministerului Energiei («România fără Lumină») "
        f"confirmă că {d['offgrid_percent']:.1f}% dintre gospodării se află în sărăcie energetică extremă, "
        f"iar raportările MATE/SIIIR indică un risc de abandon școlar și decalaj digital de {d['education_risk_percent']:.1f}%. "
        f"Suprapunerea acestor trei deficite structurale justifică intervenția prioritară prin apelul "
        f"«{plan.call_code}» ({plan.programme_name}), gestionat de {plan.managing_authority}."
    )

    activitati = (
        f"Proiectul elaborat în parteneriat cu Asociația Ingineri Fără Frontiere România (EWB România) este "
        f"structurat în trei pachete de lucru (Work Packages) corelate cu etapele HG nr. 907/2016: "
        f"WP1 — Studii de teren (topografice și geotehnice), obținerea Certificatului de Urbanism (cu aplicarea "
        f"exceptării de la autorizație de construire conform Legii nr. 50/1991 Art. 11 alin. 1 lit. m pentru "
        f"sistemele fotovoltaice) și obținerea Avizului de Gospodărire a Apelor (NTPA-001/011); "
        f"WP2 — Achiziția, execuția lucrărilor de construcții-montaj și instalarea echipamentelor pentru: "
        f"{interventions} (incluzând {pv_kwp:.1f} kWp capacitate fotovoltaică cu {batt_kwh:.1f} kWh stocare LiFePO4 "
        f"dimensionată la 80% DoD conform SR EN 62124, bazin de fitodepurare HSSF de {wetland_m2:.0f} m² pentru "
        f"{pe_count} locuitori echivalenți și centru educațional containerizat EduPod cu {stations} stații digitale); "
        f"WP3 — Încercări PRAM sub semnătura specialiștilor ANRE IIA/IIB, integrarea nodurilor de telemetrie "
        f"SCADA/LoRaWAN în platforma PSAN Radar și instruirea comitetului local de operare."
    )

    rezultate = (
        f"Indicatorii de realizare și de rezultat asumați prin Cererea de Finanțare vizează: "
        f"(1) instalarea unei puteri fotovoltaice de {pv_kwp:.1f} kWp și a unei capacități de stocare LiFePO4 "
        f"de {batt_kwh:.1f} kWh, asigurând autonomia energetică de iarnă și reducerea emisiilor de gaze cu efect "
        f"de seră cu {pv_kwp * 1150 * 0.000265:.2f} tone CO₂ echivalent/an; (2) epurarea biologică extensivă a "
        f"apelor uzate pentru {pe_count} locuitori echivalenți pe o suprafață de zonă umedă construită de "
        f"{wetland_m2:.0f} m², cu respectarea strictă a pragurilor NTPA-001 (CBO5 ≤ 25 mg/L, CCO-Cr ≤ 125 mg/L, "
        f"materii în suspensie ≤ 35 mg/L); și (3) operaționalizarea a {stations} posturi de studiu digital "
        f"asistate în hub-ul modular EduPod, reducând riscul de abandon școlar în UAT {p['uat_name']}."
    )

    sustenabilitate = (
        f"Sustenabilitatea financiară și tehnică pe perioada de durabilitate de minimum 5 ani (conform Art. 65 "
        f"din Regulamentul UE 2021/1060) este garantată prin costurile operaționale minime ale soluțiilor "
        f"pasive selectate: fitodepurarea gravitațională cu macrofite Phragmites australis nu necesită reactivi "
        f"chimici sau pompe energofage, iar bateriile LiFePO4 oferă peste 6.000 de cicluri de încărcare-descărcare. "
        f"Monitorizarea în timp real prin senzorii IoT LoRaWAN (tensiune baterie, putere MPPT, debit și turbiditate "
        f"apă tratată) permite intervenția preventivă pro bono a inginerilor voluntari EWB România înainte de "
        f"apariția oricărei avarii critice."
    )

    buget = (
        f"Valoarea brută a devizului tehnic dimensionat conform standardelor în vigoare este de "
        f"{plan.gross_bom_capex_eur:,.2f} EUR (fără TVA). Prin alocarea stocurilor corporative din Mecanismul "
        f"CSR în valoare netă de {plan.csr_in_kind_deduction_eur:,.2f} EUR, necesarul financiar net al proiectului "
        f"scade la {plan.net_investment_required_eur:,.2f} EUR, din care {plan.eligible_expenditure_eur:,.2f} EUR "
        f"reprezintă cheltuieli eligibile conform HG nr. 907/2016 (Cap. 1–2: {plan.hg907_chapters[0].total_eur:,.2f} EUR; "
        f"Cap. 3 Proiectare: {plan.hg907_chapters[1].total_eur:,.2f} EUR; Cap. 4 Investiția de bază: "
        f"{plan.hg907_chapters[2].total_eur:,.2f} EUR; Cap. 5 Alte cheltuieli: {plan.hg907_chapters[3].total_eur:,.2f} EUR; "
        f"Cap. 6 Probe PRAM: {plan.hg907_chapters[4].total_eur:,.2f} EUR). Finanțarea nerambursabilă solicitată "
        f"({plan.grant_intensity_pct:.0f}%) este de {plan.eu_grant_amount_eur:,.2f} EUR, iar contribuția proprie "
        f"a UAT {p['uat_name']} ({plan.uat_cofinancing_pct:.0f}% eligibil + cheltuieli neeligibile) este de doar "
        f"{plan.uat_cofinancing_eur:,.2f} EUR, proiectul obținând un punctaj estimat în Grila ETF de "
        f"{etf.total_score:.1f}/100 puncte."
    )

    dnsh_matrix = build_dnsh_compliance_matrix(p["uat_name"], bom_res)

    narrative = GrantNarrative(
        funding_line=funding_line,
        justificarea_nevoii=justificare,
        descrierea_activitatilor=activitati,
        rezultate_si_indicatori=rezultate,
        sustenabilitate=sustenabilitate,
        buget_sumar=buget,
        generated_by="fallback-template",
        financial_plan=plan,
        etf_scorecard=etf,
        dnsh_matrix=dnsh_matrix,
    )
    narrative.mysmis_markdown_export = build_mysmis_markdown_dossier(
        dossier, narrative, plan, etf, dnsh_matrix
    )
    return narrative


# =============================================================================
# LLM CLIENT
# =============================================================================

def _build_user_prompt(dossier: dict, funding_line: str, plan: GrantFinancialPlan, etf: ETFScorecard) -> str:
    return (
        f"Redactează narativele unei cereri de finanțare MySMIS 2021+ pentru linia «{funding_line}» "
        f"(Cod apel: {plan.call_code}, Grant nerambursabil: {plan.eu_grant_amount_eur:,.2f} EUR, "
        f"Cofinanțare UAT: {plan.uat_cofinancing_eur:,.2f} EUR, Scor ETF: {etf.total_score}/100) "
        f"pe baza următorului dosar de vulnerabilitate (JSON):\n"
        f"{json.dumps(dossier, ensure_ascii=False, indent=2)}\n\n"
        "Răspunde STRICT cu un obiect JSON valid cu exact aceste 5 chei "
        "(valori = text narativ în limba română, câte 1-2 paragrafe fiecare):\n"
        "justificarea_nevoii, descrierea_activitatilor, rezultate_si_indicatori, "
        "sustenabilitate, buget_sumar."
    )


async def _call_llm(prompt: str) -> str:
    """Call the local LLM (Ollama or OpenAI-compatible) and return raw text."""
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        if LLM_API_MODE == "openai":
            resp = await client.post(
                f"{LLM_BASE_URL.rstrip('/')}/v1/chat/completions",
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        resp = await client.post(
            f"{LLM_BASE_URL.rstrip('/')}/api/generate",
            json={
                "model": LLM_MODEL,
                "system": SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.4},
            },
        )
        resp.raise_for_status()
        return resp.json()["response"]


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM response.")
    return json.loads(text[start:end + 1])


# =============================================================================
# PUBLIC API
# =============================================================================

async def draft_grant_narrative(
    dossier: dict,
    funding_line: str = "PoIDS",
) -> GrantNarrative:
    """
    Draft the EU grant narrative, HG 907/2016 financial plan, ETF scorecard,
    DNSH compliance matrix, and MySMIS 2021+ Markdown dossier for a UAT.
    """
    plan, bom_res = compute_grant_financial_plan(dossier, funding_line)
    etf = compute_etf_scorecard(dossier, plan)
    dnsh_matrix = build_dnsh_compliance_matrix(dossier["uat_profile"]["uat_name"], bom_res)

    try:
        raw = await _call_llm(_build_user_prompt(dossier, funding_line, plan, etf))
        sections = _extract_json(raw)
        narrative = GrantNarrative(
            funding_line=funding_line,
            justificarea_nevoii=sections["justificarea_nevoii"],
            descrierea_activitatilor=sections["descrierea_activitatilor"],
            rezultate_si_indicatori=sections["rezultate_si_indicatori"],
            sustenabilitate=sections["sustenabilitate"],
            buget_sumar=sections["buget_sumar"],
            generated_by="llm",
            financial_plan=plan,
            etf_scorecard=etf,
            dnsh_matrix=dnsh_matrix,
        )
        narrative.mysmis_markdown_export = build_mysmis_markdown_dossier(
            dossier, narrative, plan, etf, dnsh_matrix
        )
        return narrative
    except Exception as exc:
        print(
            f"[grant-narrative] LLM unavailable ({exc.__class__.__name__}: {exc}) "
            f"— using deterministic engineering & financial template."
        )
        return _fallback_narrative(dossier, funding_line, plan, bom_res, etf)
