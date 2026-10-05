"""
PSAN Radar — Module 1: Romanian Regulatory & Permitting Compliance Navigator
============================================================================

Generates deterministic legal and administrative permitting roadmaps for
humanitarian engineering interventions in Romania:
  - Off-Grid Solar PV + LiFePO4 BESS: Legea 50/1991 Art. 11 lit. m exemption,
    ANRE Grade IIA/IIB sign-off (Normativ I7/2011), PRAM report, ISU/DSVSA notice.
  - Constructed Wetlands / Decentralized Sanitation: Certificat de Urbanism,
    Aviz Gospodărirea Apelor (Apele Române, Legea 107/1996, NTPA-001/011),
    Notificare APM (Legea 292/2018), Aviz Sanitar DSP (Ordinul MS 119/2014).
  - Solar Modular EduPod Hub: Legea 50/1991 modular placement, ISU HG 571/2016,
    I7/2011 electrical verification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# PYDANTIC SCHEMAS (Pydantic v2)
# =============================================================================

class PermittingStepModel(BaseModel):
    step_number: int = Field(..., description="Sequential order in the permitting workflow")
    intervention_domain: str = Field(..., description="OFFGRID_SOLAR | CONSTRUCTED_WETLAND | EDUPOD_HUB")
    document_name: str = Field(..., description="Official Romanian title of the permit/notice")
    issuing_authority: str = Field(..., description="Competent Romanian institution")
    legal_basis: str = Field(..., description="Applicable Romanian law / normative")
    estimated_days: int = Field(..., ge=1, description="Statutory or realistic processing time in calendar days")
    mandatory_signoff: str = Field(..., description="Required specialist certification (e.g., ANRE IIA/IIB)")
    exemption_applicable: bool = Field(False, description="True if building permit exemption applies")
    checklist_items: List[str] = Field(default_factory=list, description="Required dossier attachments")


class PermittingRoadmapResponse(BaseModel):
    siruta: int
    uat_name: str
    county: str
    priority_tier: str
    rvi_score: float
    applicable_domains: List[str]
    total_estimated_critical_path_days: int
    fast_track_solar_exemption: bool
    steps: List[PermittingStepModel]
    administrative_dossier_markdown: str
    generated_at: str


# =============================================================================
# ROADMAP GENERATOR
# =============================================================================

def build_permitting_roadmap(uat_props: Dict[str, Any]) -> PermittingRoadmapResponse:
    """
    Build a tailored Romanian regulatory & permitting compliance roadmap for a UAT
    based on its deficit profile (i_energy, i_sanitation, i_education).
    """
    siruta = int(uat_props["siruta"])
    uat_name = str(uat_props["uat_name"])
    county = str(uat_props["county"])
    priority_tier = str(uat_props.get("priority_tier", "MODERATE"))
    rvi_score = float(uat_props.get("rvi_score", 0.0))

    i_energy = float(uat_props.get("i_energy", 0.0))
    i_sanitation = float(uat_props.get("i_sanitation", 0.0))
    i_education = float(uat_props.get("i_education", 0.0))

    applicable_domains: List[str] = []
    if i_energy >= 0.35 or (i_energy < 0.5 and i_sanitation < 0.5 and i_education < 0.5):
        applicable_domains.append("OFFGRID_SOLAR")
    if i_sanitation >= 0.35:
        applicable_domains.append("CONSTRUCTED_WETLAND")
    if i_education >= 0.35:
        applicable_domains.append("EDUPOD_HUB")
    if not applicable_domains:
        applicable_domains = ["OFFGRID_SOLAR", "CONSTRUCTED_WETLAND"]

    steps: List[PermittingStepModel] = []
    step_idx = 1

    # 1. Off-Grid Solar Permitting (Always included or when OFFGRID_SOLAR active)
    if "OFFGRID_SOLAR" in applicable_domains:
        steps.append(
            PermittingStepModel(
                step_number=step_idx,
                intervention_domain="OFFGRID_SOLAR",
                document_name="Notificare Primărie — Exceptare Autorizație de Construire (Sisteme Fotovoltaice)",
                issuing_authority=f"Primăria {uat_name} (Compartiment Urbanism), Județul {county}",
                legal_basis="Legea nr. 50/1991 privind autorizarea executării lucrărilor de construcții, Art. 11 alin. (1) lit. m)",
                estimated_days=5,
                mandatory_signoff="Inginer Proiectant EWB România + Acord Proprietar / HCL Domeniu Public",
                exemption_applicable=True,
                checklist_items=[
                    f"Notificare prealabilă depusă la Primăria {uat_name} (cf. Art. 11 lit. m, Legea 50/1991)",
                    "Extras de Carte Funciară pentru informare (ANCPI / OCPI) sau Adeverință Rol Agricol",
                    "Memoriu tehnic scurt privind montajul panourilor fotovoltaice fără modificarea structurii de rezistență",
                    "Plan de încadrare în zonă și schița amplasării panourilor și a stocării LiFePO4",
                ],
            )
        )
        step_idx += 1

        steps.append(
            PermittingStepModel(
                step_number=step_idx,
                intervention_domain="OFFGRID_SOLAR",
                document_name="Dosar Tehnic Instalație de Utilizare & Buletin Verificare PRAM",
                issuing_authority="Electrician Autorizat ANRE Grad IIA / IIB",
                legal_basis="Ordinul ANRE nr. 11/2013, Normativ I7/2011, SR HD 60364-7-712",
                estimated_days=3,
                mandatory_signoff="Electrician Autorizat ANRE Grad IIA/IIB (Proiectare + Execuție)",
                exemption_applicable=False,
                checklist_items=[
                    "Schemă electrică monofilară DC/AC cu protecții gPV, SPD Tip 1+2 și diferențial RCD Tip A/B",
                    "Buletin de măsurare a rezistenței prizei de pământ (Rp <= 4 Ω conform I7/2011)",
                    "Proces-verbal de punere în funcțiune și instruire SSM pentru beneficiarul casnic/comunitar",
                    "Notificare ISU / DSVSA (aplicabilă pentru dispensare medicale și cantine școlare rurale)",
                ],
            )
        )
        step_idx += 1

    # 2. Constructed Wetland / Decentralized Sanitation Permitting
    if "CONSTRUCTED_WETLAND" in applicable_domains:
        steps.append(
            PermittingStepModel(
                step_number=step_idx,
                intervention_domain="CONSTRUCTED_WETLAND",
                document_name="Certificat de Urbanism (CU) — Sistem Descentralizat Fitodepurare & Imhoff",
                issuing_authority=f"Primăria {uat_name} / Consiliul Județean {county}",
                legal_basis="Legea nr. 50/1991 și Legea nr. 350/2001 privind amenajarea teritoriului și urbanismul",
                estimated_days=15,
                mandatory_signoff="Arhitect / Urbanist + Inginer Instalații Hidrotehnice",
                exemption_applicable=False,
                checklist_items=[
                    "Cerere-tip pentru emiterea Certificatului de Urbanism",
                    "Planuri cadastrale / topografice scara 1:2000 și 1:500 vizate OCPI",
                    "Memoriu justificativ privind soluția ecologică de epurare sub-superficială (HSSF CW)",
                ],
            )
        )
        step_idx += 1

        steps.append(
            PermittingStepModel(
                step_number=step_idx,
                intervention_domain="CONSTRUCTED_WETLAND",
                document_name="Aviz de Gospodărire a Apelor (Apele Române)",
                issuing_authority=f"Administrația Națională „Apele Române” (ABA aferentă jud. {county})",
                legal_basis="Legea Apelor nr. 107/1996, HG nr. 188/2002 (NTPA-001 / NTPA-011)",
                estimated_days=30,
                mandatory_signoff="Inginer Hidrotehnist / Proiectant Atestat Gospodărirea Apelor",
                exemption_applicable=False,
                checklist_items=[
                    "Breviar de calcul hidraulic și cinetică de iarnă (T_apă = 6°C) pentru încadrarea în NTPA-001 (CBO5 <= 25 mg/L, CCO-Cr <= 125 mg/L, MTS <= 35 mg/L)",
                    "Studiu hidrogeologic preliminar și verificarea adâncimii pânzei freatice",
                    "Plan de situație cu respectarea razei de protecție sanitară (minim 15 m față de fântâni conform Ord. MS 119/2014)",
                ],
            )
        )
        step_idx += 1

        steps.append(
            PermittingStepModel(
                step_number=step_idx,
                intervention_domain="CONSTRUCTED_WETLAND",
                document_name="Notificare / Decizie Etapă de Încadrare APM & Aviz Sanitar DSP",
                issuing_authority=f"Agenția pentru Protecția Mediului (APM) {county} & DSP {county}",
                legal_basis="Legea nr. 292/2018 privind evaluarea impactului asupra mediului & Ordinul MS nr. 119/2014",
                estimated_days=20,
                mandatory_signoff="Specialist Mediu / Responsabil Tehnic EWB România",
                exemption_applicable=False,
                checklist_items=[
                    "Notificare privind intenția de realizare a proiectului (Anexa 5.A din Legea 292/2018)",
                    "Dovada impermeabilizării cu geomembrană HDPE 1.5 mm pentru protecția acviferului freatic",
                    "Aviz Sanitar DSP privind distanța de siguranță față de sursele de apă potabilă",
                ],
            )
        )
        step_idx += 1

    # 3. EduPod Modular Hub Permitting
    if "EDUPOD_HUB" in applicable_domains:
        steps.append(
            PermittingStepModel(
                step_number=step_idx,
                intervention_domain="EDUPOD_HUB",
                document_name="Acord Amplasare Modul Educațional Containerizat (EduPod) & Punct de Vedere ISU",
                issuing_authority=f"Primăria {uat_name} & ISU {county}",
                legal_basis="Legea nr. 50/1991 (amplasare module provizorii), HG nr. 571/2016 și Normativ P118",
                estimated_days=14,
                mandatory_signoff="Inginer Structurist + Verificator Securitate la Incendiu",
                exemption_applicable=True,
                checklist_items=[
                    "Hotărârea Consiliului Local (HCL) pentru punerea la dispoziție a terenului (min. 50 m²)",
                    "Certificat de conformitate ISO 6346 și izolație termică incombustibilă (vată bazaltică A1)",
                    "Punct de vedere ISU privind încadrarea sub suprafața prag din HG 571/2016 și dotarea cu stingătoare P6/G2",
                ],
            )
        )
        step_idx += 1

    # Critical path estimation (parallelizing independent domain tracks)
    solar_days = sum(s.estimated_days for s in steps if s.intervention_domain == "OFFGRID_SOLAR")
    wetland_days = sum(s.estimated_days for s in steps if s.intervention_domain == "CONSTRUCTED_WETLAND")
    edupod_days = sum(s.estimated_days for s in steps if s.intervention_domain == "EDUPOD_HUB")
    critical_path_days = max(solar_days, wetland_days, edupod_days, 5)

    date_str = datetime.now().strftime("%d.%m.%Y")
    markdown_dossier = rf"""# DOSAR ADMINISTRATIV PRE-COMPLETAT — CONFORMITATE ȘI AVIZARE
**Organizație Aplicantă:** Ingineri Fără Frontiere România (Engineers Without Borders Romania)  
**Unitatea Administrativ-Teritorială (UAT):** {uat_name}, Județul {county} (Cod SIRUTA: `{siruta}`)  
**Indice de Vulnerabilitate Radar (RVI):** `{rvi_score:.1f} / 100` — Nivel Prioritate: **{priority_tier}**  
**Data Generării:** {date_str}  

---

## 1. Către: Primăria {uat_name}, Județul {county} — Compartimentul Urbanism și Amenajarea Teritoriului
**Obiect:** *Notificare prealabilă privind executarea lucrărilor de instalare sisteme fotovoltaice off-grid conform Art. 11 alin. (1) lit. m) din Legea nr. 50/1991*

Subscrisa **Asociația Ingineri Fără Frontiere România (EWB România)**, în parteneriat cu UAT **{uat_name}** (SIRUTA `{siruta}`), notifică prin prezenta demararea lucrărilor de montaj pentru sistemele fotovoltaice autonome cu stocare LiFePO4 destinate gospodăriilor izolate și obiectivelor sociale din comună (indice deficit energetic: `{i_energy * 100:.1f}%`).

Conform prevederilor **Art. 11 alin. (1) lit. m) din Legea nr. 50/1991**, montarea sistemelor de panouri fotovoltaice nu necesită emiterea Autorizației de Construire, întrucât nu se aduc modificări structurii de rezistență a acoperișului sau regimului de înălțime. Recepția tehnică și buletinul PRAM ($R_p \le 4\,\Omega$) vor fi semnate și parafate de un **Electrician Autorizat ANRE Grad IIA/IIB** conform **Normativului I7/2011** și **SR HD 60364-7-712**.

---

## 2. Memoriu Tehnic Sintetic pentru Apele Române (ABA) & APM {county}
**Obiect:** *Notificare privind realizarea sistemului descentralizat de fitodepurare (HSSF Constructed Wetland) și decantor Imhoff — Conformitate NTPA-001 / NTPA-011*

1. **Încadrare Cadastrală și Amplasament:** UAT {uat_name}, Județul {county}, Extras CF nr. `[COMPLETAȚI NR. CF / NR. CADASTRAL]`, teren aflat în domeniul public/privat cu suprafață disponibilă minimă de 30–50 m², situat la o distanță orizontală $\ge 15\text{{ m}}$ față de orice sursă de apă potabilă (fântână/izvor), în conformitate cu **Ordinul MS nr. 119/2014**.
2. **Parametri de Dimensionare Hidraulică și Biologică:** Sistemul sub-superficial cu curgere orizontală (HSSF) este dimensionat cinetic pentru temperatura de calcul de iarnă a apei ($T_{{\text{{apă}}}} = 6^\circ\text{{C}}$, $\theta = 1.06$), prevăzut cu strat termoizolant anti-îngheț de pietriș spălat ($15\text{{ cm}}$) și impermeabilizare dublă cu geomembrană **HDPE 1,5 mm**.
3. **Valori Limită la Evacuare (NTPA-001 / HG 188/2002):**
   - $\text{{CBO}}_5 \le 25\text{{ mg O}}_2/\text{{L}}$
   - $\text{{CCO-Cr}} \le 125\text{{ mg O}}_2/\text{{L}}$
   - $\text{{Materii în suspensie (MTS)}} \le 35\text{{ mg/L}}$

---

## 3. Semnături și Asumare Tehnică
- **Responsabil Tehnic EWB România:** `Ing. _________________________`
- **Electrician Autorizat ANRE (Grad IIA/IIB):** `Ing./Teh. _________________________ (Legitimație ANRE nr. ________)`
- **Reprezentant Legal UAT {uat_name}:** `Primar _________________________`
"""

    return PermittingRoadmapResponse(
        siruta=siruta,
        uat_name=uat_name,
        county=county,
        priority_tier=priority_tier,
        rvi_score=rvi_score,
        applicable_domains=applicable_domains,
        total_estimated_critical_path_days=critical_path_days,
        fast_track_solar_exemption="OFFGRID_SOLAR" in applicable_domains,
        steps=steps,
        administrative_dossier_markdown=markdown_dossier,
        generated_at=datetime.now().isoformat(),
    )
