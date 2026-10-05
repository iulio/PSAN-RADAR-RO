"""
PSAN Radar — Module 3: Corporate Materials & CSR Surplus Marketplace
====================================================================

Persistent SQLite-backed circular supply-chain & Bill-of-Materials (BOM)
allocation engine for Engineers Without Borders Romania:
- Zero hardcoded dummy lots: all CSR lots and UAT allocations are persisted in
  `backend/data/csr_marketplace.db` (SQLite3 with WAL mode & foreign keys).
- Integrates directly with `engineering_sizing.calculate_bom()` so every UAT's
  exact engineering material requirements (450Wp PV modules, LiFePO4 kWh,
  HDPE geomembrane m², PVC SN4 piping m, washed filter gravel m³, Imhoff tanks,
  ISO 6346 containers, and EduPod workstations) are computed deterministically.
- Matches available CSR warehouse lots against the UAT's remaining unallocated
  BOM deficit (`usable_quantity = min(lot.quantity_available, uat_remaining_need)`),
  computes weight-aware multi-truck road freight costs from donor depots to the
  UAT centroid, and supports real-time reservation/allocation & revocation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from engineering_sizing import InterventionType, UNIT_COSTS, calculate_bom
from volunteer_dispatch import haversine_km


# =============================================================================
# DATABASE CONFIGURATION & ROMANIAN DEPOT GEOCODER
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSR_DB_PATH = DATA_DIR / "csr_marketplace.db"

ROAD_TORTUOSITY_FACTOR = 1.28  # Empirical road-to-geodesic ratio for Romania
TRUCK_MAX_PAYLOAD_TONNES = 22.0  # Standard 40t GVW semi-trailer net payload
BASE_LOADING_HANDLING_FEE_EUR = 120.0

# Accurate WGS84 coordinates for Romanian county seats & industrial hubs
ROMANIAN_DEPOT_COORDS: Dict[str, Dict[str, Any]] = {
    "București": {"county": "București", "lat": 44.4268, "lon": 26.1025},
    "Iași": {"county": "Iași", "lat": 47.1585, "lon": 27.6014},
    "Bacău": {"county": "Bacău", "lat": 46.5670, "lon": 26.9146},
    "Galați": {"county": "Galați", "lat": 45.4353, "lon": 28.0080},
    "Brăila": {"county": "Brăila", "lat": 45.2692, "lon": 27.9575},
    "Constanța": {"county": "Constanța", "lat": 44.1598, "lon": 28.6348},
    "Focșani": {"county": "Vrancea", "lat": 45.6964, "lon": 27.1833},
    "Vaslui": {"county": "Vaslui", "lat": 46.6407, "lon": 27.7276},
    "Bârlad": {"county": "Vaslui", "lat": 46.2316, "lon": 27.6694},
    "Botoșani": {"county": "Botoșani", "lat": 47.7486, "lon": 26.6694},
    "Suceava": {"county": "Suceava", "lat": 47.6514, "lon": 26.2556},
    "Piatra Neamț": {"county": "Neamț", "lat": 46.9275, "lon": 26.3708},
    "Roman": {"county": "Neamț", "lat": 46.9212, "lon": 26.9265},
    "Tulcea": {"county": "Tulcea", "lat": 45.1788, "lon": 28.8055},
    "Buzău": {"county": "Buzău", "lat": 45.1500, "lon": 26.8167},
    "Ploiești": {"county": "Prahova", "lat": 44.9462, "lon": 26.0254},
    "Brașov": {"county": "Brașov", "lat": 45.6580, "lon": 25.6012},
    "Cluj-Napoca": {"county": "Cluj", "lat": 46.7712, "lon": 23.6236},
    "Timișoara": {"county": "Timiș", "lat": 45.7489, "lon": 21.2087},
    "Craiova": {"county": "Dolj", "lat": 44.3302, "lon": 23.7949},
    "Sibiu": {"county": "Sibiu", "lat": 45.7983, "lon": 24.1256},
    "Târgu Mureș": {"county": "Mureș", "lat": 46.5386, "lon": 24.5575},
    "Oradea": {"county": "Bihor", "lat": 47.0465, "lon": 21.9189},
    "Arad": {"county": "Arad", "lat": 46.1866, "lon": 21.3123},
    "Pitești": {"county": "Argeș", "lat": 44.8565, "lon": 24.8692},
    "Slobozia": {"county": "Ialomița", "lat": 44.5639, "lon": 27.3661},
    "Călărași": {"county": "Călărași", "lat": 44.2051, "lon": 27.3136},
}

MATERIAL_CATEGORY_SPECS: Dict[str, Dict[str, Any]] = {
    "SOLAR_PV": {
        "label": "Panouri Fotovoltaice 450Wp Tier-1",
        "default_unit": "pcs",
        "default_unit_price_eur": UNIT_COSTS["pv_module_450wp"],
        "default_unit_weight_kg": 23.5,
    },
    "BATTERY_STORAGE": {
        "label": "Stocare Baterii LiFePO4 (kWh)",
        "default_unit": "kWh",
        "default_unit_price_eur": UNIT_COSTS["lifepo4_battery_kwh"],
        "default_unit_weight_kg": 11.5,
    },
    "HDPE_GEOMEMBRANE": {
        "label": "Geomembrană HDPE 1.5mm + Geotextil",
        "default_unit": "m2",
        "default_unit_price_eur": UNIT_COSTS["hdpe_liner_m2"],
        "default_unit_weight_kg": 1.85,
    },
    "PVC_PIPING": {
        "label": "Tubulatură PVC-KG SN4 DN110/DN160",
        "default_unit": "m",
        "default_unit_price_eur": 22.0,
        "default_unit_weight_kg": 2.4,
    },
    "GRAVEL_AGGREGATE": {
        "label": "Pietriș Spălat 10-20mm & 40-80mm Fitodepurare",
        "default_unit": "m3",
        "default_unit_price_eur": 37.5,
        "default_unit_weight_kg": 1650.0,
    },
    "IMHOFF_TANK": {
        "label": "Decantor Primar Imhoff Prefabricat (NTPA-011)",
        "default_unit": "m3",
        "default_unit_price_eur": UNIT_COSTS["imhoff_tank_m3"],
        "default_unit_weight_kg": 450.0,
    },
    "ISO_CONTAINER": {
        "label": "Container Maritim 20ft High-Cube ISO 6346",
        "default_unit": "pcs",
        "default_unit_price_eur": UNIT_COSTS["container_20ft"],
        "default_unit_weight_kg": 2300.0,
    },
    "IT_EDUPOD": {
        "label": "Stație Studiu Digitală EduPod Completă",
        "default_unit": "pcs",
        "default_unit_price_eur": UNIT_COSTS["computer_station"],
        "default_unit_weight_kg": 14.0,
    },
}


# =============================================================================
# PYDANTIC SCHEMAS (Pydantic v2)
# =============================================================================

class CSRMaterialLotCreate(BaseModel):
    donor_company: str = Field(..., min_length=2, description="Corporate CSR partner donating the surplus")
    donor_cui: Optional[str] = Field(None, description="Romanian fiscal code (CUI / CIF) for sponsorship contract")
    contact_person: Optional[str] = Field(None, description="Logistics contact person or email/phone")
    material_category: str = Field(
        ...,
        description="SOLAR_PV | BATTERY_STORAGE | HDPE_GEOMEMBRANE | PVC_PIPING | GRAVEL_AGGREGATE | IMHOFF_TANK | ISO_CONTAINER | IT_EDUPOD",
    )
    item_name: str = Field(..., min_length=2, description="Technical specification of donated material")
    quantity_available: float = Field(..., gt=0, description="Available quantity to donate")
    unit: Optional[str] = Field(None, description="pcs | kWh | m2 | m | m3")
    market_unit_value_eur: Optional[float] = Field(None, gt=0, description="Commercial unit value (EUR)")
    unit_weight_kg: Optional[float] = Field(None, gt=0, description="Weight per unit in kg for truckload calculation")
    depot_city: str = Field(..., min_length=2, description="City where the material is stored")
    depot_county: Optional[str] = Field(None, description="County of the depot")
    depot_lat: Optional[float] = Field(None, ge=-90.0, le=90.0)
    depot_lon: Optional[float] = Field(None, ge=-180.0, le=180.0)
    freight_rate_eur_per_km: float = Field(1.65, ge=0.1, le=25.0, description="Truck freight cost per road km (EUR/km)")


class CSRMaterialLot(BaseModel):
    lot_id: str = Field(..., description="Unique CSR lot identifier")
    donor_company: str = Field(..., description="Corporate CSR partner donating the surplus")
    donor_cui: Optional[str] = None
    contact_person: Optional[str] = None
    material_category: str
    item_name: str
    quantity_total: float = Field(..., ge=0)
    quantity_available: float = Field(..., ge=0)
    unit: str
    market_unit_value_eur: float = Field(..., ge=0)
    unit_weight_kg: float = Field(25.0, ge=0)
    depot_city: str
    depot_county: str
    depot_lat: float
    depot_lon: float
    freight_rate_eur_per_km: float = Field(1.65, ge=0.1)
    created_at: str


class UATBOMCategoryRequirement(BaseModel):
    material_category: str
    label: str
    unit: str
    required_quantity: float
    allocated_quantity: float
    remaining_quantity: float
    bom_unit_price_eur: float
    bom_line_total_eur: float


class CSRAllocationCreateRequest(BaseModel):
    lot_id: str = Field(..., description="CSR lot ID to allocate from")
    quantity: Optional[float] = Field(
        None,
        gt=0,
        description="Quantity to allocate; defaults to min(lot.quantity_available, uat_remaining_quantity)",
    )


class CSRAllocationRecord(BaseModel):
    allocation_id: str
    lot_id: str
    donor_company: str
    material_category: str
    item_name: str
    unit: str
    siruta: int
    uat_name: str
    county: str
    quantity_allocated: float
    gross_value_eur: float
    logistics_cost_eur: float
    net_capex_saving_eur: float
    road_distance_km: float
    num_trucks: int
    allocated_at: str


class MatchedCSRLotQuote(BaseModel):
    lot: CSRMaterialLot
    uat_required_quantity: float = Field(..., description="Total BOM quantity required by this UAT")
    uat_remaining_quantity: float = Field(..., description="Remaining unallocated BOM quantity needed by this UAT")
    usable_quantity: float = Field(..., description="Quantity from this lot usable for this UAT's BOM")
    total_weight_tonnes: float = Field(..., description="Total weight of usable quantity (tonnes)")
    num_trucks: int = Field(..., description="Number of 22t trucks required for delivery")
    geodesic_distance_km: float
    estimated_road_km: float = Field(..., description="Geodesic distance * 1.28 Romanian road tortuosity factor")
    gross_donation_value_eur: float
    logistics_transit_cost_eur: float
    net_capex_savings_eur: float
    recommended_allocation: bool


class UATCSRMarketplaceResponse(BaseModel):
    siruta: int
    uat_name: str
    county: str
    original_bom_capex_eur: float
    uat_bom_requirements: List[UATBOMCategoryRequirement]
    allocations: List[CSRAllocationRecord]
    matched_lots: List[MatchedCSRLotQuote]
    allocated_gross_donation_eur: float
    allocated_logistics_cost_eur: float
    allocated_net_capex_savings_eur: float
    potential_additional_savings_eur: float
    total_gross_donation_eur: float
    total_logistics_cost_eur: float
    total_net_capex_savings_eur: float
    adjusted_net_capex_eur: float
    generated_at: str


# =============================================================================
# SQLITE PERSISTENCE LAYER (NO HARDCODED DUMMY DATA)
# =============================================================================

def _get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CSR_DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_csr_db() -> None:
    """Initialize SQLite schema for CSR lots and UAT BOM allocations."""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS csr_lots (
                lot_id TEXT PRIMARY KEY,
                donor_company TEXT NOT NULL,
                donor_cui TEXT,
                contact_person TEXT,
                material_category TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity_total REAL NOT NULL,
                quantity_available REAL NOT NULL,
                unit TEXT NOT NULL,
                market_unit_value_eur REAL NOT NULL,
                unit_weight_kg REAL NOT NULL DEFAULT 25.0,
                depot_city TEXT NOT NULL,
                depot_county TEXT NOT NULL,
                depot_lat REAL NOT NULL,
                depot_lon REAL NOT NULL,
                freight_rate_eur_per_km REAL NOT NULL DEFAULT 1.65,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS csr_allocations (
                allocation_id TEXT PRIMARY KEY,
                lot_id TEXT NOT NULL,
                siruta INTEGER NOT NULL,
                uat_name TEXT NOT NULL,
                county TEXT NOT NULL,
                quantity_allocated REAL NOT NULL,
                gross_value_eur REAL NOT NULL,
                logistics_cost_eur REAL NOT NULL,
                net_capex_saving_eur REAL NOT NULL,
                road_distance_km REAL NOT NULL,
                num_trucks INTEGER NOT NULL DEFAULT 1,
                allocated_at TEXT NOT NULL,
                FOREIGN KEY (lot_id) REFERENCES csr_lots(lot_id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()


init_csr_db()


def _row_to_lot(row: sqlite3.Row) -> CSRMaterialLot:
    return CSRMaterialLot(
        lot_id=row["lot_id"],
        donor_company=row["donor_company"],
        donor_cui=row["donor_cui"],
        contact_person=row["contact_person"],
        material_category=row["material_category"],
        item_name=row["item_name"],
        quantity_total=float(row["quantity_total"]),
        quantity_available=float(row["quantity_available"]),
        unit=row["unit"],
        market_unit_value_eur=float(row["market_unit_value_eur"]),
        unit_weight_kg=float(row["unit_weight_kg"]),
        depot_city=row["depot_city"],
        depot_county=row["depot_county"],
        depot_lat=float(row["depot_lat"]),
        depot_lon=float(row["depot_lon"]),
        freight_rate_eur_per_km=float(row["freight_rate_eur_per_km"]),
        created_at=row["created_at"],
    )


def resolve_depot_coordinates(
    city: str,
    county: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
) -> tuple[str, float, float]:
    """Resolve WGS84 coordinates for a Romanian city/depot if lat/lon not explicitly supplied."""
    city_clean = city.strip()
    if lat is not None and lon is not None:
        resolved_county = (county or "").strip() or ROMANIAN_DEPOT_COORDS.get(city_clean, {}).get("county", city_clean)
        return resolved_county, float(lat), float(lon)

    for known_city, info in ROMANIAN_DEPOT_COORDS.items():
        if known_city.lower() == city_clean.lower():
            return info["county"], float(info["lat"]), float(info["lon"])

    if county:
        for known_city, info in ROMANIAN_DEPOT_COORDS.items():
            if info["county"].lower() == county.strip().lower():
                return info["county"], float(info["lat"]), float(info["lon"])

    # Default to central Moldavia/Muntenia logistics hub (Focșani) if custom locality without coordinates
    return (county or "Vrancea").strip(), 45.6964, 27.1833


# =============================================================================
# DETERMINISTIC ENGINEERING BOM EXTRACTION & LOGISTICS CALCULATOR
# =============================================================================

def compute_uat_bom_requirements(
    uat_props: Dict[str, Any],
    existing_allocations: List[CSRAllocationRecord],
) -> tuple[float, List[UATBOMCategoryRequirement]]:
    """
    Run the deterministic Engineering Sizing Engine (`calculate_bom`) for the target UAT
    and extract exact physical quantities required per material category.
    """
    households_total = int(uat_props.get("households_total", 200))
    offgrid_pct = float(uat_props.get("i_energy", 0.3))
    sanitation_pct = float(uat_props.get("i_sanitation", 0.3))
    education_pct = float(uat_props.get("i_education", 0.3))
    population = int(uat_props.get("population", 1000))
    county = str(uat_props.get("county", "Vrancea"))

    target_households = max(1, int(households_total * offgrid_pct))
    connected_pe = max(5, int(population * sanitation_pct))
    student_stations = max(8, int(population * 0.02 * education_pct))

    bom_res = calculate_bom(
        intervention_type=InterventionType.INTEGRATED,
        target_households=target_households,
        connected_people_equivalent=connected_pe,
        student_stations=student_stations,
        container_size_ft=20,
        county=county,
    )
    ep = bom_res.engineering_parameters

    pv_panels_qty = float(math.ceil(((ep.pv_kwp or 5.0) * 1000.0) / 450.0))
    battery_kwh_qty = round(float(ep.battery_kwh or 10.0), 1)
    hdpe_m2_qty = round(float(ep.wetland_area_m2 or 100.0) * 1.2, 1)
    piping_m_qty = round(float(ep.piping_m or 60.0), 1)
    gravel_m3_qty = round(float(ep.gravel_volume_m3 or 50.0), 1)
    imhoff_m3_qty = round(float(ep.imhoff_tank_m3 or 10.0), 1)
    container_qty = 1.0
    edupod_it_qty = float(ep.student_stations or student_stations)

    raw_needs = {
        "SOLAR_PV": pv_panels_qty,
        "BATTERY_STORAGE": battery_kwh_qty,
        "HDPE_GEOMEMBRANE": hdpe_m2_qty,
        "PVC_PIPING": piping_m_qty,
        "GRAVEL_AGGREGATE": gravel_m3_qty,
        "IMHOFF_TANK": imhoff_m3_qty,
        "ISO_CONTAINER": container_qty,
        "IT_EDUPOD": edupod_it_qty,
    }

    allocated_by_cat: Dict[str, float] = {}
    for alloc in existing_allocations:
        allocated_by_cat[alloc.material_category] = (
            allocated_by_cat.get(alloc.material_category, 0.0) + alloc.quantity_allocated
        )

    requirements: List[UATBOMCategoryRequirement] = []
    for cat_key, spec in MATERIAL_CATEGORY_SPECS.items():
        req_qty = round(raw_needs.get(cat_key, 0.0), 2)
        alloc_qty = round(allocated_by_cat.get(cat_key, 0.0), 2)
        rem_qty = round(max(0.0, req_qty - alloc_qty), 2)
        unit_price = float(spec["default_unit_price_eur"])
        requirements.append(
            UATBOMCategoryRequirement(
                material_category=cat_key,
                label=spec["label"],
                unit=spec["default_unit"],
                required_quantity=req_qty,
                allocated_quantity=alloc_qty,
                remaining_quantity=rem_qty,
                bom_unit_price_eur=unit_price,
                bom_line_total_eur=round(req_qty * unit_price, 2),
            )
        )

    return bom_res.total_project_capex_eur, requirements


def _calculate_lot_logistics(
    lot: CSRMaterialLot,
    usable_qty: float,
    centroid_lat: float,
    centroid_lon: float,
) -> tuple[float, float, float, int, float, float, float]:
    """
    Calculate geodesic km, road km, total weight (tonnes), truck count,
    gross value, freight cost, and net CAPEX savings for a specific usable quantity.
    """
    geodesic_km = haversine_km(centroid_lat, centroid_lon, lot.depot_lat, lot.depot_lon)
    road_km = round(max(5.0, geodesic_km * ROAD_TORTUOSITY_FACTOR), 1)
    total_weight_tonnes = round((usable_qty * lot.unit_weight_kg) / 1000.0, 3)
    num_trucks = max(1, int(math.ceil(total_weight_tonnes / TRUCK_MAX_PAYLOAD_TONNES)))
    gross_val = round(usable_qty * lot.market_unit_value_eur, 2)
    transit_cost = round(
        num_trucks * (BASE_LOADING_HANDLING_FEE_EUR + (road_km * lot.freight_rate_eur_per_km)),
        2,
    )
    net_savings = round(max(0.0, gross_val - transit_cost), 2)
    return geodesic_km, road_km, total_weight_tonnes, num_trucks, gross_val, transit_cost, net_savings


def get_uat_allocations(siruta: int) -> List[CSRAllocationRecord]:
    """Return all active CSR material allocations for a given UAT SIRUTA."""
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.*, l.donor_company, l.material_category, l.item_name, l.unit
            FROM csr_allocations a
            JOIN csr_lots l ON a.lot_id = l.lot_id
            WHERE a.siruta = ?
            ORDER BY a.allocated_at DESC
            """,
            (int(siruta),),
        ).fetchall()

    return [
        CSRAllocationRecord(
            allocation_id=r["allocation_id"],
            lot_id=r["lot_id"],
            donor_company=r["donor_company"],
            material_category=r["material_category"],
            item_name=r["item_name"],
            unit=r["unit"],
            siruta=int(r["siruta"]),
            uat_name=r["uat_name"],
            county=r["county"],
            quantity_allocated=float(r["quantity_allocated"]),
            gross_value_eur=float(r["gross_value_eur"]),
            logistics_cost_eur=float(r["logistics_cost_eur"]),
            net_capex_saving_eur=float(r["net_capex_saving_eur"]),
            road_distance_km=float(r["road_distance_km"]),
            num_trucks=int(r["num_trucks"]),
            allocated_at=r["allocated_at"],
        )
        for r in rows
    ]


def optimize_csr_materials_for_uat(
    uat_props: Dict[str, Any],
    centroid_lat: float,
    centroid_lon: float,
) -> UATCSRMarketplaceResponse:
    """
    Compute the UAT's exact engineering BOM material requirements, retrieve active
    SQLite CSR allocations and available CSR lots, and calculate net CAPEX reduction.
    """
    siruta = int(uat_props["siruta"])
    uat_name = str(uat_props["uat_name"])
    county = str(uat_props["county"])

    allocations = get_uat_allocations(siruta)
    original_bom_capex, bom_requirements = compute_uat_bom_requirements(uat_props, allocations)
    req_by_category = {r.material_category: r for r in bom_requirements}

    with _get_connection() as conn:
        lot_rows = conn.execute(
            "SELECT * FROM csr_lots WHERE quantity_available > 0 ORDER BY created_at DESC"
        ).fetchall()
    available_lots = [_row_to_lot(r) for r in lot_rows]

    quotes: List[MatchedCSRLotQuote] = []
    for lot in available_lots:
        req = req_by_category.get(lot.material_category)
        if not req or req.remaining_quantity <= 0:
            continue

        usable_qty = round(min(lot.quantity_available, req.remaining_quantity), 2)
        if usable_qty <= 0:
            continue

        (
            geodesic_km,
            road_km,
            weight_t,
            num_trucks,
            gross_val,
            transit_cost,
            net_savings,
        ) = _calculate_lot_logistics(lot, usable_qty, centroid_lat, centroid_lon)

        quotes.append(
            MatchedCSRLotQuote(
                lot=lot,
                uat_required_quantity=req.required_quantity,
                uat_remaining_quantity=req.remaining_quantity,
                usable_quantity=usable_qty,
                total_weight_tonnes=weight_t,
                num_trucks=num_trucks,
                geodesic_distance_km=geodesic_km,
                estimated_road_km=road_km,
                gross_donation_value_eur=gross_val,
                logistics_transit_cost_eur=transit_cost,
                net_capex_savings_eur=net_savings,
                recommended_allocation=net_savings > 0.0,
            )
        )

    quotes.sort(key=lambda q: q.net_capex_savings_eur, reverse=True)

    alloc_gross = round(sum(a.gross_value_eur for a in allocations), 2)
    alloc_logistics = round(sum(a.logistics_cost_eur for a in allocations), 2)
    alloc_net = round(sum(a.net_capex_saving_eur for a in allocations), 2)

    rec_quotes = [q for q in quotes if q.recommended_allocation]
    potential_gross = round(sum(q.gross_donation_value_eur for q in rec_quotes), 2)
    potential_logistics = round(sum(q.logistics_transit_cost_eur for q in rec_quotes), 2)
    potential_net = round(sum(q.net_capex_savings_eur for q in rec_quotes), 2)

    total_gross = round(alloc_gross + potential_gross, 2)
    total_logistics = round(alloc_logistics + potential_logistics, 2)
    total_net = round(alloc_net + potential_net, 2)
    adjusted_capex = round(max(0.0, original_bom_capex - alloc_net), 2)

    return UATCSRMarketplaceResponse(
        siruta=siruta,
        uat_name=uat_name,
        county=county,
        original_bom_capex_eur=original_bom_capex,
        uat_bom_requirements=bom_requirements,
        allocations=allocations,
        matched_lots=quotes,
        allocated_gross_donation_eur=alloc_gross,
        allocated_logistics_cost_eur=alloc_logistics,
        allocated_net_capex_savings_eur=alloc_net,
        potential_additional_savings_eur=potential_net,
        total_gross_donation_eur=total_gross,
        total_logistics_cost_eur=total_logistics,
        total_net_capex_savings_eur=total_net,
        adjusted_net_capex_eur=adjusted_capex,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def allocate_csr_lot_to_uat(
    uat_props: Dict[str, Any],
    centroid_lat: float,
    centroid_lon: float,
    request: CSRAllocationCreateRequest,
) -> CSRAllocationRecord:
    """
    Atomically reserve a quantity from a CSR lot in SQLite for the target UAT,
    decrementing `quantity_available` and recording the CAPEX reduction.
    """
    siruta = int(uat_props["siruta"])
    uat_name = str(uat_props["uat_name"])
    county = str(uat_props["county"])

    existing_allocs = get_uat_allocations(siruta)
    _, bom_reqs = compute_uat_bom_requirements(uat_props, existing_allocs)
    req_by_cat = {r.material_category: r for r in bom_reqs}

    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM csr_lots WHERE lot_id = ?",
            (request.lot_id,),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"CSR lot '{request.lot_id}' not found in database.",
            )
        lot = _row_to_lot(row)
        if lot.quantity_available <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSR lot '{lot.lot_id}' has 0 available stock.",
            )

        cat_req = req_by_cat.get(lot.material_category)
        max_needed = cat_req.remaining_quantity if cat_req else lot.quantity_available
        if max_needed <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Necesitățile BOM ale UAT {uat_name} pentru categoria {lot.material_category} sunt deja acoperite 100%.",
            )

        desired_qty = request.quantity if request.quantity is not None else min(lot.quantity_available, max_needed)
        alloc_qty = round(min(float(desired_qty), lot.quantity_available, max_needed), 2)
        if alloc_qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cantitatea alocată trebuie să fie pozitivă.",
            )

        (
            _,
            road_km,
            _,
            num_trucks,
            gross_val,
            transit_cost,
            net_savings,
        ) = _calculate_lot_logistics(lot, alloc_qty, centroid_lat, centroid_lon)

        allocation_id = f"ALLOC-{uuid.uuid4().hex[:8].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()
        new_available = round(max(0.0, lot.quantity_available - alloc_qty), 2)

        conn.execute(
            "UPDATE csr_lots SET quantity_available = ? WHERE lot_id = ?",
            (new_available, lot.lot_id),
        )
        conn.execute(
            """
            INSERT INTO csr_allocations (
                allocation_id, lot_id, siruta, uat_name, county,
                quantity_allocated, gross_value_eur, logistics_cost_eur,
                net_capex_saving_eur, road_distance_km, num_trucks, allocated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                allocation_id,
                lot.lot_id,
                siruta,
                uat_name,
                county,
                alloc_qty,
                gross_val,
                transit_cost,
                net_savings,
                road_km,
                num_trucks,
                now_iso,
            ),
        )
        conn.commit()

    return CSRAllocationRecord(
        allocation_id=allocation_id,
        lot_id=lot.lot_id,
        donor_company=lot.donor_company,
        material_category=lot.material_category,
        item_name=lot.item_name,
        unit=lot.unit,
        siruta=siruta,
        uat_name=uat_name,
        county=county,
        quantity_allocated=alloc_qty,
        gross_value_eur=gross_val,
        logistics_cost_eur=transit_cost,
        net_capex_saving_eur=net_savings,
        road_distance_km=road_km,
        num_trucks=num_trucks,
        allocated_at=now_iso,
    )


def revoke_csr_allocation(siruta: int, allocation_id: str) -> Dict[str, Any]:
    """Cancel an allocation and restore its reserved quantity back to the CSR warehouse lot."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM csr_allocations WHERE allocation_id = ? AND siruta = ?",
            (allocation_id, int(siruta)),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Allocation '{allocation_id}' not found for SIRUTA {siruta}.",
            )
        lot_id = row["lot_id"]
        qty = float(row["quantity_allocated"])

        conn.execute(
            "UPDATE csr_lots SET quantity_available = ROUND(quantity_available + ?, 2) WHERE lot_id = ?",
            (qty, lot_id),
        )
        conn.execute(
            "DELETE FROM csr_allocations WHERE allocation_id = ?",
            (allocation_id,),
        )
        conn.commit()

    return {"status": "revoked", "allocation_id": allocation_id, "restored_quantity": qty, "lot_id": lot_id}


# =============================================================================
# FASTAPI ROUTER (/api/v1/marketplace)
# =============================================================================

router = APIRouter(prefix="/api/v1/marketplace", tags=["CSR Materials Marketplace"])


@router.get("/categories")
async def list_material_categories() -> Dict[str, Any]:
    """Return supported engineering material categories and Romanian depot coordinates."""
    return {
        "categories": MATERIAL_CATEGORY_SPECS,
        "depots": ROMANIAN_DEPOT_COORDS,
    }


@router.get("/lots", response_model=List[CSRMaterialLot])
async def list_csr_lots(category: Optional[str] = None) -> List[CSRMaterialLot]:
    """List CSR surplus material lots stored in SQLite."""
    with _get_connection() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM csr_lots WHERE UPPER(material_category) = UPPER(?) ORDER BY created_at DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM csr_lots ORDER BY created_at DESC"
            ).fetchall()
    return [_row_to_lot(r) for r in rows]


@router.post("/lots", response_model=CSRMaterialLot, status_code=status.HTTP_201_CREATED)
async def create_csr_lot(payload: CSRMaterialLotCreate) -> CSRMaterialLot:
    """Register a new corporate CSR material lot in SQLite."""
    cat_key = payload.material_category.strip().upper()
    if cat_key not in MATERIAL_CATEGORY_SPECS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported material_category '{cat_key}'. Allowed: {list(MATERIAL_CATEGORY_SPECS.keys())}",
        )

    spec = MATERIAL_CATEGORY_SPECS[cat_key]
    unit = (payload.unit or spec["default_unit"]).strip()
    unit_price = float(payload.market_unit_value_eur or spec["default_unit_price_eur"])
    unit_weight = float(payload.unit_weight_kg or spec["default_unit_weight_kg"])

    resolved_county, lat, lon = resolve_depot_coordinates(
        payload.depot_city,
        payload.depot_county,
        payload.depot_lat,
        payload.depot_lon,
    )

    lot_id = f"CSR-{cat_key[:4]}-{uuid.uuid4().hex[:6].upper()}"
    now_iso = datetime.now(timezone.utc).isoformat()
    qty = round(float(payload.quantity_available), 2)

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO csr_lots (
                lot_id, donor_company, donor_cui, contact_person,
                material_category, item_name, quantity_total, quantity_available,
                unit, market_unit_value_eur, unit_weight_kg,
                depot_city, depot_county, depot_lat, depot_lon,
                freight_rate_eur_per_km, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lot_id,
                payload.donor_company.strip(),
                (payload.donor_cui or "").strip() or None,
                (payload.contact_person or "").strip() or None,
                cat_key,
                payload.item_name.strip(),
                qty,
                qty,
                unit,
                unit_price,
                unit_weight,
                payload.depot_city.strip(),
                resolved_county,
                lat,
                lon,
                round(float(payload.freight_rate_eur_per_km), 2),
                now_iso,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM csr_lots WHERE lot_id = ?", (lot_id,)).fetchone()

    return _row_to_lot(row)


@router.delete("/lots/{lot_id}")
async def delete_csr_lot(lot_id: str) -> Dict[str, str]:
    """Delete a CSR material lot and any associated allocations from SQLite."""
    with _get_connection() as conn:
        row = conn.execute("SELECT lot_id FROM csr_lots WHERE lot_id = ?", (lot_id,)).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"CSR lot '{lot_id}' not found.",
            )
        conn.execute("DELETE FROM csr_lots WHERE lot_id = ?", (lot_id,))
        conn.commit()
    return {"status": "deleted", "lot_id": lot_id}
