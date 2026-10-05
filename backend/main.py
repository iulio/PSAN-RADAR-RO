# Phase 2 & Architectural Hardening: FastAPI Backend for PSAN Radar
# Includes:
# - GZipMiddleware & automatic topology-preserving simplification (>10 MB)
# - O(1) in-memory SIRUTA hash map index with live ground-truth invalidation
# - RFC 7807 Problem Details exception responses
# - Engineering Sizing & BOM Calculator (Phase 8 Hardened)
# - Field Surveys Sync Engine (Phase 9)
# - IoT Telemetry & WebSocket Alert Engine (Phase 10)
# - Romanian Regulatory & Permitting Compliance Navigator (Module 1)
# - Volunteer Skills Matcher & Pro Bono Dispatch Engine (Module 2)
# - Corporate Materials & CSR Surplus Marketplace (Module 3)

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import geopandas as gpd
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from pdf_generator import build_uat_dossier_pdf
from grant_narrative_agent import GrantNarrative, draft_grant_narrative
from engineering_sizing import (
    calculate_bom,
    InterventionType,
    CalculateBOMRequest,
    CalculateBOMResponse,
    EngineeringParametersModel,
    BOMItemModel,
)
from field_surveys import (
    router as field_surveys_router,
    register_geojson_update_callback,
)
from telemetry_engine import router as telemetry_router
from compliance_navigator import (
    PermittingRoadmapResponse,
    build_permitting_roadmap,
)
from volunteer_dispatch import (
    router as volunteers_router,
    DispatchTeamRequest,
    DispatchTeamResponse,
    dispatch_optimal_team,
)
from materials_marketplace import (
    router as marketplace_router,
    CSRAllocationCreateRequest,
    CSRAllocationRecord,
    UATCSRMarketplaceResponse,
    allocate_csr_lot_to_uat,
    optimize_csr_materials_for_uat,
    revoke_csr_allocation,
)

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
GEOJSON_PATH = BASE_DIR / "data" / "uat_vulnerability.geojson"
SIMPLIFY_THRESHOLD_BYTES = 10 * 1024 * 1024  # 10 MB

# =============================================================================
# PYDANTIC MODELS (Pydantic v2)
# =============================================================================

class UATProfile(BaseModel):
    siruta: int = Field(..., description="Unique Romanian administrative code")
    uat_name: str = Field(..., description="Name of the UAT")
    county: str = Field(..., description="County")
    population: int = Field(..., description="Total population")
    households_total: int = Field(..., description="Total registered households")
    rvi_score: float = Field(..., ge=0, le=100, description="Radar Vulnerability Index (0-100)")
    priority_tier: str = Field(..., description="Priority tier: CRITICAL, HIGH, or MODERATE")


class IdentifiedDeficits(BaseModel):
    sanitation_percent: float = Field(..., ge=0, le=100, description="Percentage of households without sanitation")
    offgrid_percent: float = Field(..., ge=0, le=100, description="Percentage of off-grid/unelectrified households")
    education_risk_percent: float = Field(..., ge=0, le=100, description="Percentage representing dropout risk")


class RecommendedIntervention(BaseModel):
    description: str = Field(..., description="Concrete technical solution")
    condition: str = Field(..., description="Condition that triggers this intervention")


class EligibleEuFundingLine(BaseModel):
    name: str = Field(..., description="Name of the EU funding line")
    description: Optional[str] = Field(None, description="Brief description of the funding line")
    programme_key: str = Field("PoIDS", description="Canonical key for grant-narrative endpoint")
    call_code: str = Field("PEO/PoIDS/P02/FSE+/FEDR/2025", description="Official MySMIS / PNRR call code")
    managing_authority: str = Field("MIPE — Autoritatea de Management PoIDS", description="Managing Authority")
    funding_source: str = Field("FSE+ & FEDR", description="EU / National funding source")
    grant_intensity_pct: float = Field(98.0, description="Non-reimbursable grant rate (%)")
    uat_cofinancing_pct: float = Field(2.0, description="Applicant UAT co-financing rate (%)")
    max_grant_eur: float = Field(2000000.0, description="Maximum grant ceiling (EUR)")
    estimated_etf_score: float = Field(85.0, description="Estimated MySMIS ETF grid score (0-100)")
    eligibility_status: str = Field("ELIGIBIL PRIORITAR", description="ELIGIBIL PRIORITAR | ELIGIBIL COMPLEMENTAR")


class EngineeringJustification(BaseModel):
    text: str = Field(..., description="Pre-written paragraph synthesizing the local deficits for grant proposals")


class EUProjectDossier(BaseModel):
    uat_profile: UATProfile
    identified_deficits: IdentifiedDeficits
    recommended_interventions: List[RecommendedIntervention]
    eligible_eu_funding_lines: List[EligibleEuFundingLine]
    engineering_justification: EngineeringJustification


class HealthResponse(BaseModel):
    status: str = Field(..., description="Status of the API")
    total_records: int = Field(..., description="Total number of UAT records")
    o1_index_size: int = Field(..., description="Number of UATs indexed in O(1) hash map")
    timestamp: str = Field(..., description="ISO timestamp of the response")


# =============================================================================
# IN-MEMORY GEOSPATIAL CACHE & O(1) SIRUTA INDEX
# =============================================================================

gdf: Optional[gpd.GeoDataFrame] = None
_cached_geojson_dict: Optional[Dict[str, Any]] = None
_siruta_index: Dict[int, Dict[str, Any]] = {}


def reload_geospatial_store() -> None:
    """
    Load the GeoJSON file, apply Douglas-Peucker simplification if file > 10 MB,
    cache the serialized FeatureCollection, and populate the O(1) SIRUTA hash map.
    """
    global gdf, _cached_geojson_dict, _siruta_index

    if not GEOJSON_PATH.exists():
        raise RuntimeError(f"GeoJSON file missing at {GEOJSON_PATH}")

    loaded = gpd.read_file(GEOJSON_PATH)
    required_props = [
        "siruta",
        "uat_name",
        "county",
        "population",
        "households_total",
        "i_sanitation",
        "i_energy",
        "i_education",
        "i_marginalization",
        "rvi_score",
        "priority_tier",
    ]
    for prop in required_props:
        if prop not in loaded.columns:
            raise ValueError(f"Missing required property in GeoJSON: {prop}")

    # Apply topology-preserving simplification if payload > 10 MB
    if GEOJSON_PATH.stat().st_size > SIMPLIFY_THRESHOLD_BYTES:
        loaded["geometry"] = loaded.geometry.simplify(0.001, preserve_topology=True)

    # Ensure any ISO timestamp columns parsed as pd.Timestamp by pyogrio are JSON-serializable strings
    for col in loaded.columns:
        if col == "geometry":
            continue
        if pd.api.types.is_datetime64_any_dtype(loaded[col]) or loaded[col].dtype == "object":
            loaded[col] = loaded[col].apply(
                lambda v: v.isoformat() if hasattr(v, "isoformat") else (None if pd.isna(v) else v)
            )

    gdf = loaded
    _cached_geojson_dict = json.loads(gdf.to_json())

    new_index: Dict[int, Dict[str, Any]] = {}
    for _, row in gdf.iterrows():
        siruta_code = int(row["siruta"])
        geom = row.geometry
        centroid = geom.centroid if geom is not None and not geom.is_empty else None
        lat = float(centroid.y) if centroid is not None else 45.8
        lon = float(centroid.x) if centroid is not None else 27.6
        props_dict = {col: row[col] for col in gdf.columns if col != "geometry"}
        new_index[siruta_code] = {
            "row": row,
            "props": props_dict,
            "centroid_lat": lat,
            "centroid_lon": lon,
        }

    _siruta_index = new_index


def get_uat_entry_or_404(siruta: int) -> Dict[str, Any]:
    """O(1) hash map lookup for a UAT by its integer SIRUTA code."""
    if gdf is None or not _siruta_index:
        raise HTTPException(status_code=500, detail="GeoJSON data not loaded. Check server logs.")
    entry = _siruta_index.get(siruta)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"UAT with SIRUTA {siruta} not found.")
    return entry


def generate_dossier_for_uat(uat_props: Dict[str, Any]) -> EUProjectDossier:
    """Generate a deterministic EU project dossier and multi-programme funding matrix for a UAT."""
    rvi = float(uat_props["rvi_score"])
    i_san = float(uat_props["i_sanitation"])
    i_eng = float(uat_props["i_energy"])
    i_edu = float(uat_props["i_education"])
    i_marg = float(uat_props.get("i_marginalization", 0.45))

    uat_profile = UATProfile(
        siruta=int(uat_props["siruta"]),
        uat_name=str(uat_props["uat_name"]),
        county=str(uat_props["county"]),
        population=int(uat_props["population"]),
        households_total=int(uat_props["households_total"]),
        rvi_score=rvi,
        priority_tier=str(uat_props["priority_tier"]),
    )

    identified_deficits = IdentifiedDeficits(
        sanitation_percent=round(i_san * 100.0, 2),
        offgrid_percent=round(i_eng * 100.0, 2),
        education_risk_percent=round(i_edu * 100.0, 2),
    )

    recommended_interventions: List[RecommendedIntervention] = []
    if i_eng >= 0.25:
        recommended_interventions.append(
            RecommendedIntervention(
                description="Kit Fotovoltaic Off-Grid (3–5 kWp) + Stocare LiFePO4 (DoD 80%, SR EN 62124 / I7/2011) pentru gospodăriile izolate",
                condition=f"i_energy = {i_eng:.2f} (≥ 0.25)",
            )
        )
    if i_san >= 0.25:
        recommended_interventions.append(
            RecommendedIntervention(
                description="Stație Descentralizată de Fitodepurare HSSF cu Macrofite + Decantor Imhoff (conform HG 188/2002 NTPA-001/011)",
                condition=f"i_sanitation = {i_san:.2f} (≥ 0.25)",
            )
        )
    if i_edu >= 0.25:
        recommended_interventions.append(
            RecommendedIntervention(
                description="Centru Comunitar Digital EduPod Containerizat NZEB (ISO 6346 / C107) autonom solar",
                condition=f"i_education = {i_edu:.2f} (≥ 0.25)",
            )
        )

    base_etf = round(min(96.0, 74.0 + (rvi / 100.0) * 16.0 + i_marg * 6.0), 1)
    eligible_eu_funding_lines: List[EligibleEuFundingLine] = []

    # 1. PoIDS 2021-2027 (Integrated Social & Community Infrastructure)
    eligible_eu_funding_lines.append(
        EligibleEuFundingLine(
            name="PoIDS 2021–2027 — Dezvoltare Locală în Comunități Rurale Marginalizate",
            description="Finanțare integrată FSE+/FEDR (98% grant, 2% UAT) pentru micro-rețele PV, fitodepurare și centre comunitare.",
            programme_key="PoIDS",
            call_code="PEO/PoIDS/P02/FSE+/FEDR/2025",
            managing_authority="MIPE — Autoritatea de Management PoIDS",
            funding_source="FSE+ & FEDR (Reg. UE 2021/1060)",
            grant_intensity_pct=98.0,
            uat_cofinancing_pct=2.0,
            max_grant_eur=2000000.0,
            estimated_etf_score=round(min(98.0, base_etf + (3.0 if rvi >= 50 else 0.0)), 1),
            eligibility_status="ELIGIBIL PRIORITAR" if rvi >= 50 or i_marg >= 0.45 else "ELIGIBIL COMPLEMENTAR",
        )
    )

    # 2. Fondul pentru Modernizare / AFM (Off-Grid Solar PV & BESS)
    if i_eng >= 0.20:
        eligible_eu_funding_lines.append(
            EligibleEuFundingLine(
                name="Fondul pentru Modernizare / AFM — Sisteme Fotovoltaice Gospodării Izolate",
                description="Grant 100% nerambursabil pentru electrificarea gospodăriilor neconectate la SEN (SR EN 62124 / Legea 50/1991 Art. 11m).",
                programme_key="Fondul pentru Modernizare",
                call_code="FM-AFM-OFFGRID-I7-2025",
                managing_authority="Ministerul Energiei & AFM",
                funding_source="Fondul pentru Modernizare (Directiva UE 2018/410)",
                grant_intensity_pct=100.0,
                uat_cofinancing_pct=0.0,
                max_grant_eur=500000.0,
                estimated_etf_score=round(min(98.0, 75.0 + i_eng * 22.0), 1),
                eligibility_status="ELIGIBIL PRIORITAR" if i_eng >= 0.45 else "ELIGIBIL COMPLEMENTAR",
            )
        )

    # 3. PNRR C1 / AFIR DR-27 (Decentralized Constructed Wetlands NTPA-001/011)
    if i_san >= 0.25:
        eligible_eu_funding_lines.append(
            EligibleEuFundingLine(
                name="PNRR C1 / AFIR DR-27 — Stații Ecologice de Fitodepurare NTPA-001/011 (<2.000 l.e.)",
                description="Finanțare 95% nerambursabilă pentru epurare extensivă HSSF și decantoare Imhoff în comune fără canalizare.",
                programme_key="AFIR Fitodepurare",
                call_code="AFIR-DR27-PNRR-C1-APA",
                managing_authority="AFIR & MMAP",
                funding_source="FEADR & PNRR C1 Managementul Apei",
                grant_intensity_pct=95.0,
                uat_cofinancing_pct=5.0,
                max_grant_eur=1500000.0,
                estimated_etf_score=round(min(97.0, 74.0 + i_san * 22.0), 1),
                eligibility_status="ELIGIBIL PRIORITAR" if i_san >= 0.50 else "ELIGIBIL COMPLEMENTAR",
            )
        )

    # 4. PNRAS / PNRR C15 (School Dropout Prevention & EduPod Digital Hub)
    if i_edu >= 0.20:
        eligible_eu_funding_lines.append(
            EligibleEuFundingLine(
                name="PNRAS / PNRR C15 — Reducerea Abandonului Școlar & Hub Digital EduPod",
                description="Grant 100% nerambursabil (până la 300.000 EUR) pentru centre digitale containerizate ISO 6346 și programe remediale.",
                programme_key="PNRAS",
                call_code="PNRR-C15-I4-PNRAS-R2",
                managing_authority="Ministerul Educației — UMPFE",
                funding_source="PNRR — Componenta 15 Educație",
                grant_intensity_pct=100.0,
                uat_cofinancing_pct=0.0,
                max_grant_eur=300000.0,
                estimated_etf_score=round(min(97.0, 75.0 + i_edu * 21.0), 1),
                eligibility_status="ELIGIBIL PRIORITAR" if i_edu >= 0.45 else "ELIGIBIL COMPLEMENTAR",
            )
        )

    # 5. Programul Regional 2021-2027 (ADR Nord-Est / Sud-Est)
    eligible_eu_funding_lines.append(
        EligibleEuFundingLine(
            name=f"Programul Regional 2021–2027 ({uat_props['county']}) — Eficiență Energetică & Micro-Rețele",
            description="Finanțare FEDR (98% grant, 2% UAT) pentru infrastructură publică verde-albastră și autonomie energetică locală.",
            programme_key="Programul Regional",
            call_code="PR-2021-2027-P3-ENERGIE",
            managing_authority="ADR Nord-Est / ADR Sud-Est",
            funding_source="FEDR — Prioritatea 3 Tranziție Verde",
            grant_intensity_pct=98.0,
            uat_cofinancing_pct=2.0,
            max_grant_eur=1200000.0,
            estimated_etf_score=round(min(95.0, base_etf - 1.5), 1),
            eligibility_status="ELIGIBIL COMPLEMENTAR",
        )
    )

    eligible_eu_funding_lines.sort(key=lambda f: f.estimated_etf_score, reverse=True)

    justification_text = (
        f"UAT {uat_props['uat_name']} (Județul {uat_props['county']}, SIRUTA {uat_props['siruta']}) "
        f"înregistrează un Indice de Vulnerabilitate Radar (RVI) de {rvi:.1f}/100 ({uat_props['priority_tier']}), "
        f"determinat de convergența a trei deficite majore certificate statistic: {i_san*100:.1f}% gospodării fără "
        f"canalizare/epurare (INS RPL 2021), {i_eng*100:.1f}% gospodării în sărăcie energetică off-grid "
        f"(Ministerul Energiei) și {i_edu*100:.1f}% risc de abandon școlar (MATE/SIIIR). "
        f"Soluția tehnică dimensionată de Ingineri Fără Frontiere România combină sisteme fotovoltaice cu stocare "
        f"LiFePO4 (SR EN 62124), stații de fitodepurare HSSF (NTPA-001/011) și hub-uri digitale EduPod (ISO 6346), "
        f"încadrându-se cu punctaj ETF prioritar ({eligible_eu_funding_lines[0].estimated_etf_score:.1f}/100 pct) "
        f"pe apelul {eligible_eu_funding_lines[0].call_code}."
    )
    engineering_justification = EngineeringJustification(text=justification_text)

    return EUProjectDossier(
        uat_profile=uat_profile,
        identified_deficits=identified_deficits,
        recommended_interventions=recommended_interventions,
        eligible_eu_funding_lines=eligible_eu_funding_lines,
        engineering_justification=engineering_justification,
    )


# =============================================================================
# FASTAPI APPLICATION & MIDDLEWARE
# =============================================================================

app = FastAPI(
    title="PSAN Radar API",
    description=(
        "Mission-critical GIS decision-support, deterministic engineering sizing, "
        "permitting compliance, volunteer dispatch, and EU grant preparation platform "
        "for Engineers Without Borders Romania (Ingineri Fără Frontiere)."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# RFC 7807 Problem Details Exception Handler (preserves 'detail' field for backwards compatibility)
@app.exception_handler(HTTPException)
async def rfc7807_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    titles = {
        400: "Bad Request",
        404: "Resource Not Found",
        422: "Unprocessable Entity",
        500: "Internal Server Error",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://psan-radar.ewb.ro/problems/http-{exc.status_code}",
            "title": titles.get(exc.status_code, "HTTP Error"),
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": str(request.url.path),
        },
    )


# Mount Modular Routers
app.include_router(field_surveys_router)
app.include_router(telemetry_router)
app.include_router(volunteers_router)
app.include_router(marketplace_router)

# Register cache invalidation hook so field survey syncs update O(1) index immediately
register_geojson_update_callback(reload_geospatial_store)

try:
    reload_geospatial_store()
except Exception as e:
    print(f"Warning: Failed to load GeoJSON at startup: {e}")


# =============================================================================
# CORE RADAR & ADVANCED MODULE ENDPOINTS
# =============================================================================

@app.get("/api/v1/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Health check endpoint with O(1) index verification."""
    if gdf is None:
        raise HTTPException(status_code=500, detail="GeoJSON data not loaded. Check server logs.")
    return HealthResponse(
        status="ok",
        total_records=len(gdf),
        o1_index_size=len(_siruta_index),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/v1/radar/geojson")
def get_geojson() -> Dict[str, Any]:
    """Return the cached GeoJSON FeatureCollection in O(1)."""
    if _cached_geojson_dict is None:
        raise HTTPException(status_code=500, detail="GeoJSON data not loaded. Check server logs.")
    return _cached_geojson_dict


@app.get("/api/v1/radar/filter")
def filter_geojson(
    min_rvi: float = Query(0.0, ge=0, le=100, description="Minimum RVI score (0-100)"),
    county: Optional[str] = Query(None, description="Filter by county"),
    priority_tier: Optional[str] = Query(None, description="Filter by priority tier (CRITICAL, HIGH, MODERATE)"),
    require_offgrid: bool = Query(False, description="Filter for off-grid households (i_energy >= 0.5)"),
    require_sanitation: bool = Query(False, description="Filter for sanitation deficit (i_sanitation >= 0.5)"),
    require_education_risk: bool = Query(False, description="Filter for education risk (i_education >= 0.5)"),
) -> Dict[str, Any]:
    """Return a filtered GeoJSON FeatureCollection based on multi-criteria query parameters."""
    if _cached_geojson_dict is None:
        raise HTTPException(status_code=500, detail="GeoJSON data not loaded. Check server logs.")

    features = _cached_geojson_dict.get("features", [])
    filtered_features = []
    for feat in features:
        p = feat.get("properties", {})
        if min_rvi > 0 and float(p.get("rvi_score", 0.0)) < min_rvi:
            continue
        if county and str(p.get("county", "")) != county:
            continue
        if priority_tier and str(p.get("priority_tier", "")) != priority_tier:
            continue
        if require_offgrid and float(p.get("i_energy", 0.0)) < 0.5:
            continue
        if require_sanitation and float(p.get("i_sanitation", 0.0)) < 0.5:
            continue
        if require_education_risk and float(p.get("i_education", 0.0)) < 0.5:
            continue
        filtered_features.append(feat)

    return {
        "type": "FeatureCollection",
        "features": filtered_features,
    }


@app.get("/api/v1/radar/uat/{siruta}/dossier", response_model=EUProjectDossier)
def get_uat_dossier(siruta: int) -> EUProjectDossier:
    """Generate an EU project dossier for a specific UAT using O(1) SIRUTA lookup."""
    entry = get_uat_entry_or_404(siruta)
    return generate_dossier_for_uat(entry["props"])


@app.get("/api/v1/radar/uat/{siruta}/export-pdf")
def export_uat_dossier_pdf(siruta: int) -> StreamingResponse:
    """Export the EU project dossier for a UAT as a downloadable PDF."""
    entry = get_uat_entry_or_404(siruta)
    uat_props = entry["props"]

    dossier = generate_dossier_for_uat(uat_props).model_dump()
    dossier["i_marginalization"] = float(uat_props["i_marginalization"])

    pdf_buffer = build_uat_dossier_pdf(dossier)
    filename = f"fisa_fundamentare_{siruta}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/v1/radar/uat/{siruta}/grant-narrative", response_model=GrantNarrative)
@app.post("/api/v1/radar/uat/{siruta}/generate-grant-narrative", response_model=GrantNarrative)
async def generate_grant_narrative(
    siruta: int,
    funding_line: str = Query("PoIDS", description="Target EU funding programme (PoIDS, Fondul pentru Modernizare, PNRAS)"),
) -> GrantNarrative:
    """Draft the EU grant narrative sections for a UAT using a local LLM with deterministic fallback."""
    entry = get_uat_entry_or_404(siruta)
    uat_props = entry["props"]

    dossier = generate_dossier_for_uat(uat_props).model_dump()
    dossier["i_marginalization"] = float(uat_props["i_marginalization"])
    return await draft_grant_narrative(dossier, funding_line=funding_line)


@app.post("/api/v1/radar/uat/{siruta}/calculate-bom", response_model=CalculateBOMResponse)
def calculate_bom_endpoint(siruta: int, request: CalculateBOMRequest) -> CalculateBOMResponse:
    """
    Calculate deterministic engineering BOM and CAPEX for a specific intervention type.
    Uses O(1) UAT lookup to auto-populate regional irradiation and demographic defaults.
    """
    entry = get_uat_entry_or_404(siruta)
    uat_props = entry["props"]

    households_total = int(uat_props["households_total"])
    offgrid_pct = float(uat_props["i_energy"])
    sanitation_pct = float(uat_props["i_sanitation"])
    education_pct = float(uat_props["i_education"])
    population = int(uat_props["population"])
    county = str(uat_props["county"])

    target_households = request.target_households or max(1, int(households_total * offgrid_pct))
    connected_pe = request.connected_people_equivalent or max(5, int(population * sanitation_pct))
    student_stations = request.student_stations or max(8, int(population * 0.02 * education_pct))
    container_size = request.container_size_ft if request.container_size_ft in (20, 40) else 20

    try:
        result = calculate_bom(
            intervention_type=request.intervention_type,
            target_households=target_households,
            connected_people_equivalent=connected_pe,
            student_stations=student_stations,
            container_size_ft=container_size,
            daily_energy_per_household_kwh=request.daily_energy_per_household_kwh,
            county=county,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"BOM calculation failed: {str(exc)}") from exc

    return CalculateBOMResponse(
        intervention_type=result.intervention_type.value,
        engineering_parameters=EngineeringParametersModel(**result.engineering_parameters.to_dict()),
        itemized_bom=[
            BOMItemModel(
                description=item.description,
                category=item.category.value,
                unit=item.unit,
                qty=item.qty,
                unit_price_eur=item.unit_price_eur,
                total_eur=item.total_eur,
            )
            for item in result.itemized_bom
        ],
        subtotal_equipment_eur=result.subtotal_equipment_eur,
        subtotal_works_labor_eur=result.subtotal_works_labor_eur,
        contingency_reserve_eur=result.contingency_reserve_eur,
        total_project_capex_eur=result.total_project_capex_eur,
    )


@app.get("/api/v1/radar/uat/{siruta}/permitting-roadmap", response_model=PermittingRoadmapResponse, tags=["Compliance & Permitting"])
def get_uat_permitting_roadmap(siruta: int) -> PermittingRoadmapResponse:
    """
    Module 1: Generate the Romanian regulatory & permitting compliance checklist
    (Legea 50/1991 Art. 11 lit. m, ANRE IIA/IIB, Apele Române NTPA-001/011, APM)
    and pre-filled administrative Markdown dossier for a UAT.
    """
    entry = get_uat_entry_or_404(siruta)
    return build_permitting_roadmap(entry["props"])


@app.post("/api/v1/radar/uat/{siruta}/dispatch-team", response_model=DispatchTeamResponse, tags=["Volunteer Dispatch"])
def dispatch_uat_volunteer_team(
    siruta: int,
    request: Optional[DispatchTeamRequest] = None,
) -> DispatchTeamResponse:
    """
    Module 2: Match the target UAT's technical requirements with the nearest
    certified EWB Romania pro bono volunteers using the geodesic Haversine formula.
    """
    entry = get_uat_entry_or_404(siruta)
    return dispatch_optimal_team(
        uat_props=entry["props"],
        centroid_lat=entry["centroid_lat"],
        centroid_lon=entry["centroid_lon"],
        request=request,
    )


@app.get("/api/v1/radar/uat/{siruta}/csr-marketplace", response_model=UATCSRMarketplaceResponse, tags=["CSR Materials Marketplace"])
def get_uat_csr_marketplace_matches(siruta: int) -> UATCSRMarketplaceResponse:
    """
    Module 3: Match corporate CSR donated equipment lots to the target UAT's
    real Engineering BOM requirements and compute road freight logistics cost and net CAPEX savings.
    """
    entry = get_uat_entry_or_404(siruta)
    return optimize_csr_materials_for_uat(
        uat_props=entry["props"],
        centroid_lat=entry["centroid_lat"],
        centroid_lon=entry["centroid_lon"],
    )


@app.post("/api/v1/radar/uat/{siruta}/csr-allocations", response_model=CSRAllocationRecord, tags=["CSR Materials Marketplace"])
def create_uat_csr_allocation(siruta: int, request: CSRAllocationCreateRequest) -> CSRAllocationRecord:
    """
    Reserve a quantity from a CSR warehouse lot for the target UAT's Bill of Materials,
    decrementing available stock in SQLite and updating net CAPEX savings.
    """
    entry = get_uat_entry_or_404(siruta)
    return allocate_csr_lot_to_uat(
        uat_props=entry["props"],
        centroid_lat=entry["centroid_lat"],
        centroid_lon=entry["centroid_lon"],
        request=request,
    )


@app.delete("/api/v1/radar/uat/{siruta}/csr-allocations/{allocation_id}", tags=["CSR Materials Marketplace"])
def delete_uat_csr_allocation(siruta: int, allocation_id: str) -> Dict[str, Any]:
    """
    Cancel a CSR material allocation for a UAT and return the reserved quantity to warehouse stock.
    """
    get_uat_entry_or_404(siruta)
    return revoke_csr_allocation(siruta=siruta, allocation_id=allocation_id)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
