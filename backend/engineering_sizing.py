"""
Phase 8 (Hardened): Engineering Sizing Engine & Automated BOM/CAPEX Calculator
==============================================================================
Deterministic engineering dimensioning for Romanian rural humanitarian
interventions with 2024–2026 Romanian market rates (EUR, VAT excluded).

Standards & Normatives Referenced:
- Solar PV / BESS: SR EN 62124, SR EN IEC 61724, I7/2011, regional Romanian
  December winter Peak Sun Hours (1.6 – 2.1 PSH), LiFePO4 80% DoD safety limit,
  temperature derating (-0.4%/°C above 25°C STC), and 2.5x inverter surge rating.
- Phytoremediation / Constructed Wetlands: NTPA-001 & NTPA-011 (HG 188/2002 /
  HG 352/2005) BOD5/COD/TSS effluent limits, winter kinetics (T_water = 6°C),
  and 15 cm frost-protection gravel surcharge.
- EduPod Modular Hub: ISO 6346, NP 074, C107 thermal insulation normative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import math

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class InterventionType(str, Enum):
    ENERGY_OFFGRID = "ENERGY_OFFGRID"
    OFFGRID_PV = "OFFGRID_PV"
    PHYTOSANITATION = "PHYTOSANITATION"
    SANITATION = "SANITATION"
    EDUCATION_HUB = "EDUCATION_HUB"
    EDUCATION = "EDUCATION"
    INTEGRATED = "INTEGRATED"


class BOMCategory(str, Enum):
    EQUIPMENT = "EQUIPMENT"
    MATERIALS = "MATERIALS"
    LABOR = "LABOR"
    ENGINEERING = "ENGINEERING"
    CONTINGENCY = "CONTINGENCY"


@dataclass
class BOMItem:
    description: str
    category: BOMCategory
    unit: str
    qty: float
    unit_price_eur: float
    total_eur: float = field(init=False)

    def __post_init__(self) -> None:
        self.qty = round(float(self.qty), 2)
        self.unit_price_eur = round(float(self.unit_price_eur), 2)
        self.total_eur = round(self.qty * self.unit_price_eur, 2)


@dataclass
class EngineeringParameters:
    """Computed engineering parameters across all intervention types."""
    # Off-grid solar & BESS
    pv_array_kwp: Optional[float] = None
    pv_kwp: Optional[float] = None
    battery_kwh: Optional[float] = None
    inverter_kva: Optional[float] = None
    inverter_kw: Optional[float] = None
    inverter_surge_kva: Optional[float] = None
    winter_psh: Optional[float] = None
    temp_derating_coeff_pct_per_c: Optional[float] = None
    lifepo4_dod: Optional[float] = None
    target_households: Optional[int] = None

    # Constructed wetland (NTPA-001 / NTPA-011)
    connected_pe: Optional[int] = None
    wetland_area_m2: Optional[float] = None
    imhoff_tank_m3: Optional[float] = None
    gravel_volume_m3: Optional[float] = None
    macrophytes_count: Optional[int] = None
    piping_m: Optional[float] = None
    hydraulic_loading_rate_m_day: Optional[float] = None
    frost_surcharge_m: Optional[float] = None
    ntpa001_bod5_target_mg_l: Optional[float] = None
    ntpa001_cod_target_mg_l: Optional[float] = None
    ntpa001_tss_target_mg_l: Optional[float] = None

    # EduPod container conversion
    container_size_ft: Optional[int] = None
    insulation_m2: Optional[float] = None
    hvac_kw: Optional[float] = None
    solar_kwp: Optional[float] = None
    computer_stations: Optional[int] = None
    student_stations: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class EngineeringBOMResponse:
    intervention_type: InterventionType
    engineering_parameters: EngineeringParameters
    itemized_bom: List[BOMItem]
    subtotal_equipment_eur: float
    subtotal_works_labor_eur: float
    contingency_reserve_eur: float
    total_project_capex_eur: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intervention_type": self.intervention_type.value,
            "engineering_parameters": self.engineering_parameters.to_dict(),
            "itemized_bom": [
                {
                    "description": item.description,
                    "category": item.category.value,
                    "unit": item.unit,
                    "qty": item.qty,
                    "unit_price_eur": item.unit_price_eur,
                    "total_eur": item.total_eur,
                }
                for item in self.itemized_bom
            ],
            "subtotal_equipment_eur": self.subtotal_equipment_eur,
            "subtotal_works_labor_eur": self.subtotal_works_labor_eur,
            "contingency_reserve_eur": self.contingency_reserve_eur,
            "total_project_capex_eur": self.total_project_capex_eur,
        }


# =============================================================================
# REGIONAL SOLAR IRRADIATION (DECEMBER WINTER PSH BY COUNTY)
# =============================================================================

COUNTY_WINTER_PSH: Dict[str, float] = {
    "Tulcea": 2.10,
    "Constanța": 2.10,
    "Galați": 1.95,
    "Brăila": 1.95,
    "Călărași": 1.95,
    "Ialomița": 1.95,
    "Vrancea": 1.80,
    "Buzău": 1.85,
    "Vaslui": 1.70,
    "Iași": 1.70,
    "Botoșani": 1.60,
    "Suceava": 1.60,
    "Neamț": 1.65,
    "Bacău": 1.75,
}
DEFAULT_WINTER_PSH = 1.85


def get_county_winter_psh(county: Optional[str]) -> float:
    if not county:
        return DEFAULT_WINTER_PSH
    return COUNTY_WINTER_PSH.get(county.strip(), DEFAULT_WINTER_PSH)


# =============================================================================
# UNIT COST DATABASE - Romanian Market Rates (EUR, VAT Excluded)
# =============================================================================

UNIT_COSTS: Dict[str, float] = {
    # Off-Grid Solar
    "pv_module_450wp": 185.0,
    "lifepo4_battery_kwh": 420.0,
    "inverter_5kva": 1250.0,
    "inverter_10kva": 2100.0,
    "mppt_controller": 380.0,
    "mounting_structure_kwp": 95.0,
    "dc_cabling_kwp": 45.0,
    "ac_cabling_kva": 35.0,
    "earthing_protection": 280.0,
    "monitoring_system": 450.0,
    "solar_installation_kwp": 180.0,

    # Constructed Wetland
    "excavation_m3": 18.0,
    "hdpe_liner_m2": 12.5,
    "gravel_10_20mm_m3": 38.0,
    "gravel_40_80mm_m3": 35.0,
    "sand_m3": 28.0,
    "imhoff_tank_m3": 420.0,
    "macrophyte_plant": 3.5,
    "piping_dn110_m": 18.0,
    "piping_dn160_m": 28.0,
    "manhole_dn600": 450.0,
    "vent_pipe": 85.0,
    "flow_control_chamber": 650.0,
    "wetland_earthworks_m2": 25.0,
    "wetland_planting_m2": 15.0,
    "wetland_piping_install_m": 12.0,

    # EduPod Container Conversion
    "container_20ft": 4200.0,
    "container_40ft": 6800.0,
    "insulation_wall_m2": 45.0,
    "insulation_roof_m2": 55.0,
    "insulation_floor_m2": 40.0,
    "interior_finish_m2": 65.0,
    "electrical_roughin_m2": 35.0,
    "electrical_fixtures": 850.0,
    "hvac_split_3_5kw": 1150.0,
    "hvac_split_5kw": 1450.0,
    "hrv_unit": 980.0,
    "pv_kit_3kwp": 2800.0,
    "pv_kit_5kwp": 4200.0,
    "battery_10kwh": 4200.0,
    "computer_station": 650.0,
    "network_rack": 450.0,
    "internet_satellite": 1200.0,
    "container_transport_20ft": 850.0,
    "container_transport_40ft": 1200.0,
    "crane_rental_day": 650.0,
    "foundation_blocks": 180.0,
    "container_modification_labor": 2800.0,
    "interior_fitout_labor": 1800.0,
    "commissioning_testing": 650.0,

    # Engineering & Soft Costs
    "design_engineering_pct": 0.08,
    "project_management_pct": 0.05,
    "permits_approvals": 1200.0,
    "contingency_pct": 0.10,
}


def _finalize_capex_breakdown(
    bom_items: List[BOMItem],
    permits_label: str = "Permits & Approvals",
) -> tuple[float, float, float, float]:
    """
    Compute subtotals and append Engineering, Permits, PM, and Contingency items.
    Guarantees the exact identity:
        total_project_capex_eur == subtotal_equipment_eur + subtotal_works_labor_eur + contingency_reserve_eur
    where subtotal_works_labor_eur aggregates direct installation labor and engineering/permitting works.
    """
    equipment_total = sum(i.total_eur for i in bom_items if i.category == BOMCategory.EQUIPMENT)
    materials_total = sum(i.total_eur for i in bom_items if i.category == BOMCategory.MATERIALS)
    labor_total = sum(i.total_eur for i in bom_items if i.category == BOMCategory.LABOR)

    subtotal_equipment = round(equipment_total + materials_total, 2)
    direct_base = round(subtotal_equipment + labor_total, 2)

    eng_item = BOMItem("Design Engineering (8%)", BOMCategory.ENGINEERING, "lump", 1, round(direct_base * UNIT_COSTS["design_engineering_pct"], 2))
    permits_item = BOMItem(permits_label, BOMCategory.ENGINEERING, "lump", 1, UNIT_COSTS["permits_approvals"])

    direct_plus_eng = round(direct_base + eng_item.total_eur + permits_item.total_eur, 2)
    pm_item = BOMItem("Project Management & Dirigenție de Șantier (5%)", BOMCategory.ENGINEERING, "lump", 1, round(direct_plus_eng * UNIT_COSTS["project_management_pct"], 2))

    subtotal_works_labor = round(labor_total + eng_item.total_eur + permits_item.total_eur + pm_item.total_eur, 2)
    subtotal_before_contingency = round(subtotal_equipment + subtotal_works_labor, 2)

    contingency_item = BOMItem(
        "Contingency Reserve / Cheltuieli Diverse și Neprevăzute (10%)",
        BOMCategory.CONTINGENCY,
        "lump",
        1,
        round(subtotal_before_contingency * UNIT_COSTS["contingency_pct"], 2),
    )

    bom_items.extend([eng_item, permits_item, pm_item, contingency_item])
    total_capex = round(subtotal_equipment + subtotal_works_labor + contingency_item.total_eur, 2)
    return subtotal_equipment, subtotal_works_labor, contingency_item.total_eur, total_capex


# =============================================================================
# OFF-GRID SOLAR SIZER
# =============================================================================

class OffGridSolarSizer:
    """
    Sizes off-grid PV + LiFePO4 BESS + hybrid inverter systems for Romanian rural households.
    Adheres to SR EN 62124, SR EN IEC 61724, I7/2011:
    - Regional December winter Peak Sun Hours (1.6 - 2.1 PSH by county)
    - Temperature derating: -0.4%/°C above 25°C STC (summer peak cell T = 55°C -> 12% derating)
    - LiFePO4 safety DoD constraint: max 80% depth of discharge
    - Inverter surge margin: 2.5x continuous rating for inductive motor startup (hydrophore/pumps)
    """

    TEMP_COEFF_PCT_PER_C = -0.40     # %/°C above 25°C STC
    DESIGN_CELL_TEMP_C = 55.0        # Peak cell temperature (°C)
    SOILING_WIRING_EFF = 0.88        # Cabling, snow/dust soiling, MPPT efficiency
    BATTERY_DOD = 0.80               # Maximum safe LiFePO4 depth of discharge
    BATTERY_EFFICIENCY = 0.95        # LiFePO4 round-trip efficiency
    AUTONOMY_DAYS = 2.5              # Winter autonomy reserve (days)
    SURGE_MULTIPLIER = 2.5           # 2.5x surge margin for inductive motor startup

    HOUSEHOLD_LOAD_PROFILES = {
        "basic": 3.5,
        "standard": 6.0,
        "enhanced": 10.0,
    }

    def __init__(
        self,
        target_households: int,
        load_profile: str = "standard",
        daily_energy_per_household_kwh: Optional[float] = None,
        county: Optional[str] = None,
        response_type: InterventionType = InterventionType.ENERGY_OFFGRID,
    ) -> None:
        self.target_households = max(1, target_households)
        self.load_profile = load_profile
        per_hh_kwh = (
            float(daily_energy_per_household_kwh)
            if daily_energy_per_household_kwh is not None and daily_energy_per_household_kwh > 0
            else self.HOUSEHOLD_LOAD_PROFILES.get(load_profile, 3.5)
        )
        self.daily_load_kwh = per_hh_kwh * self.target_households
        self.winter_psh = get_county_winter_psh(county)
        self.temp_derating_factor = 1.0 + (self.TEMP_COEFF_PCT_PER_C / 100.0) * (self.DESIGN_CELL_TEMP_C - 25.0)
        self.system_derating = round(self.temp_derating_factor * self.SOILING_WIRING_EFF, 4)
        self.response_type = response_type

    def calculate_pv_array_kwp(self) -> float:
        """Calculate required PV array capacity (kWp) using regional winter PSH and temperature derating."""
        effective_psh = max(self.winter_psh, 1.6) * 1.65  # Weighted seasonal design PSH
        pv_kwp = self.daily_load_kwh / (effective_psh * self.system_derating)
        return math.ceil(pv_kwp * 2) / 2.0

    def calculate_battery_kwh(self) -> float:
        """Calculate LiFePO4 battery bank capacity (kWh) enforcing 80% DoD safety limit."""
        usable_kwh = self.daily_load_kwh * self.AUTONOMY_DAYS
        gross_kwh = usable_kwh / (self.BATTERY_DOD * self.BATTERY_EFFICIENCY)
        return float(math.ceil(gross_kwh / 5.0) * 5)

    def calculate_inverter_kva(self) -> float:
        """Calculate continuous inverter rating (kVA), accounting for 2.5x inductive surge capability."""
        continuous_kw = (self.daily_load_kwh / 4.0) * 1.25
        continuous_kva = continuous_kw / 0.85
        standard_sizes = [3, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50]
        for size in standard_sizes:
            if size >= continuous_kva:
                return float(size)
        return float(standard_sizes[-1])

    def generate_bom(self) -> EngineeringBOMResponse:
        pv_kwp = self.calculate_pv_array_kwp()
        battery_kwh = self.calculate_battery_kwh()
        inverter_kva = self.calculate_inverter_kva()
        inverter_surge_kva = round(inverter_kva * self.SURGE_MULTIPLIER, 1)

        n_modules = math.ceil(pv_kwp * 1000 / 450)
        if inverter_kva <= 5:
            inverter_cost = UNIT_COSTS["inverter_5kva"]
        elif inverter_kva <= 10:
            inverter_cost = UNIT_COSTS["inverter_10kva"]
        else:
            n_inv = math.ceil(inverter_kva / 10)
            inverter_cost = UNIT_COSTS["inverter_10kva"] * n_inv

        n_mppt = max(1, math.ceil(pv_kwp / 3))

        params = EngineeringParameters(
            pv_array_kwp=pv_kwp,
            pv_kwp=pv_kwp,
            battery_kwh=battery_kwh,
            inverter_kva=inverter_kva,
            inverter_kw=inverter_kva,
            inverter_surge_kva=inverter_surge_kva,
            winter_psh=self.winter_psh,
            temp_derating_coeff_pct_per_c=self.TEMP_COEFF_PCT_PER_C,
            lifepo4_dod=self.BATTERY_DOD,
            target_households=self.target_households,
        )

        bom_items = [
            BOMItem(f"PV Module 450Wp Mono PERC ({n_modules} pcs)", BOMCategory.EQUIPMENT, "pcs", n_modules, UNIT_COSTS["pv_module_450wp"]),
            BOMItem(f"LiFePO4 Battery Bank {battery_kwh:.0f} kWh (80% DoD Safe Reserve)", BOMCategory.EQUIPMENT, "kWh", battery_kwh, UNIT_COSTS["lifepo4_battery_kwh"]),
            BOMItem(f"Hybrid Inverter {inverter_kva:.0f} kVA (Surge {inverter_surge_kva:.1f} kVA)", BOMCategory.EQUIPMENT, "pcs", 1, inverter_cost),
            BOMItem(f"MPPT Charge Controller 150V/60A ({n_mppt} pcs)", BOMCategory.EQUIPMENT, "pcs", n_mppt, UNIT_COSTS["mppt_controller"]),
            BOMItem(f"Hot-Dip Galvanized Mount Structure {pv_kwp:.1f} kWp", BOMCategory.MATERIALS, "kWp", pv_kwp, UNIT_COSTS["mounting_structure_kwp"]),
            BOMItem(f"Solar DC Cabling 4mm² & MC4 + gPV Fuses {pv_kwp:.1f} kWp", BOMCategory.MATERIALS, "kWp", pv_kwp, UNIT_COSTS["dc_cabling_kwp"]),
            BOMItem(f"AC Distribution & RCBO Type A/B Protection {inverter_kva:.0f} kVA", BOMCategory.MATERIALS, "kVA", inverter_kva, UNIT_COSTS["ac_cabling_kva"]),
            BOMItem("Earthing (<4 Ω) & Type 1+2 Surge Protection (SPD)", BOMCategory.MATERIALS, "system", 1, UNIT_COSTS["earthing_protection"]),
            BOMItem("IoT Remote Telemetry & BMS Gateway", BOMCategory.EQUIPMENT, "system", 1, UNIT_COSTS["monitoring_system"]),
            BOMItem(f"ANRE-Certified Installation & Commissioning {pv_kwp:.1f} kWp", BOMCategory.LABOR, "kWp", pv_kwp, UNIT_COSTS["solar_installation_kwp"]),
        ]

        subtotal_eq, subtotal_labor, contingency, total_capex = _finalize_capex_breakdown(
            bom_items, permits_label="Legea 50/1991 Art. 11(m) Notification & ANRE Dossier"
        )

        return EngineeringBOMResponse(
            intervention_type=self.response_type,
            engineering_parameters=params,
            itemized_bom=bom_items,
            subtotal_equipment_eur=subtotal_eq,
            subtotal_works_labor_eur=subtotal_labor,
            contingency_reserve_eur=contingency,
            total_project_capex_eur=total_capex,
        )


# =============================================================================
# CONSTRUCTED WETLAND SIZER (NTPA-001 / NTPA-011)
# =============================================================================

class ConstructedWetlandSizer:
    """
    Sizes Horizontal Sub-Surface Flow Constructed Wetland (HSSF CW) with Imhoff tank
    pretreatment according to Romanian NTPA-001 / NTPA-011 discharge standards
    (BOD5 <= 25 mg/L, COD <= 125 mg/L, TSS <= 35 mg/L) and Romanian winter design
    water temperature (T_water = 6°C, Arrhenius theta = 1.06) with 15 cm frost-protection
    gravel surcharge.
    """

    BOD_LOAD_PER_PE = 60.0            # g BOD5/PE/day (NTPA-011 / SR EN 12566)
    INFLUENT_BOD5_MG_L = 300.0        # After Imhoff primary settling (~30% reduction)
    EFFLUENT_BOD5_TARGET_MG_L = 25.0  # NTPA-001 maximum permissible BOD5
    EFFLUENT_COD_TARGET_MG_L = 125.0  # NTPA-001 maximum permissible COD (CCO-Cr)
    EFFLUENT_TSS_TARGET_MG_L = 35.0   # NTPA-001 maximum permissible TSS (materii în suspensie)
    K20_AREA_RATE = 0.12              # m/day first-order areal rate constant at 20°C
    THETA_ARRHENIUS = 1.06            # Temperature coefficient for winter biofilm kinetics
    WINTER_WATER_TEMP_C = 6.0         # Romanian winter subsurface water design temperature (°C)
    MAX_WINTER_HLR_M_DAY = 0.08       # Maximum winter hydraulic loading rate (m/day)
    WETLAND_DEPTH = 0.60              # m active saturated gravel bed
    FROST_SURCHARGE_DEPTH = 0.15      # m dry washed gravel surcharge for winter frost insulation
    IMHOFF_HRT = 2.5                  # hours hydraulic retention time
    IMHOFF_SLUDGE_STORAGE = 0.05      # m3 per PE (6 months)

    def __init__(
        self,
        connected_people_equivalent: int,
        response_type: InterventionType = InterventionType.PHYTOSANITATION,
    ) -> None:
        self.pe = max(5, connected_people_equivalent)
        self.daily_flow_m3 = self.pe * 0.15  # 150 L/PE/day
        self.daily_bod_load_g = self.pe * self.BOD_LOAD_PER_PE
        self.response_type = response_type

    def calculate_wetland_area_m2(self) -> float:
        """
        Calculate HSSF bed area (m²) using Kadlec & Knight first-order plug-flow kinetics
        at Romanian winter water temperature (6°C) to satisfy NTPA-001 (BOD5 <= 25 mg/L),
        checked against maximum winter hydraulic loading rate.
        """
        k_winter = self.K20_AREA_RATE * (self.THETA_ARRHENIUS ** (self.WINTER_WATER_TEMP_C - 20.0))
        area_kinetics = (self.daily_flow_m3 * math.log(self.INFLUENT_BOD5_MG_L / self.EFFLUENT_BOD5_TARGET_MG_L)) / k_winter
        area_hlr = self.daily_flow_m3 / self.MAX_WINTER_HLR_M_DAY
        return max(area_kinetics, area_hlr, 20.0)

    def calculate_imhoff_tank_m3(self) -> float:
        liquid_vol = (self.daily_flow_m3 / 24.0) * self.IMHOFF_HRT
        sludge_vol = self.pe * self.IMHOFF_SLUDGE_STORAGE
        total = (liquid_vol + sludge_vol) * 1.2
        standard_sizes = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50]
        for size in standard_sizes:
            if size >= total:
                return float(size)
        return float(standard_sizes[-1])

    def calculate_gravel_volume_m3(self, area_m2: float) -> float:
        """Calculate total gravel volume including 0.15m winter frost-protection surcharge."""
        main_media = area_m2 * 0.50
        drainage = area_m2 * 0.10
        frost_surcharge = area_m2 * self.FROST_SURCHARGE_DEPTH
        return (main_media + drainage + frost_surcharge) * 1.10

    def calculate_macrophytes(self, area_m2: float) -> int:
        return math.ceil(area_m2 * 4)

    def calculate_piping_m(self, area_m2: float) -> float:
        width = math.sqrt(area_m2 / 3.0)
        length = area_m2 / width
        n_laterals = math.ceil(length / 2.0)
        distribution = width + (n_laterals * width)
        collection = width + (n_laterals * width)
        mains = 2 * (width + 5.0)
        return distribution + collection + mains

    def generate_bom(self) -> EngineeringBOMResponse:
        area_m2 = self.calculate_wetland_area_m2()
        imhoff_m3 = self.calculate_imhoff_tank_m3()
        gravel_m3 = self.calculate_gravel_volume_m3(area_m2)
        macrophytes = self.calculate_macrophytes(area_m2)
        piping_m = self.calculate_piping_m(area_m2)
        actual_hlr = round(self.daily_flow_m3 / area_m2, 4)

        main_gravel = gravel_m3 * (5.0 / 6.0)
        drainage_gravel = gravel_m3 * (1.0 / 6.0)
        sand_m3 = area_m2 * 0.05 * 1.1
        liner_m2 = area_m2 * 1.2
        excavation_m3 = (area_m2 * (self.WETLAND_DEPTH + self.FROST_SURCHARGE_DEPTH + 0.30)) + (imhoff_m3 * 1.5)
        n_manholes = 4

        params = EngineeringParameters(
            connected_pe=self.pe,
            wetland_area_m2=round(area_m2, 1),
            imhoff_tank_m3=imhoff_m3,
            gravel_volume_m3=round(gravel_m3, 1),
            macrophytes_count=macrophytes,
            piping_m=round(piping_m, 1),
            hydraulic_loading_rate_m_day=actual_hlr,
            frost_surcharge_m=self.FROST_SURCHARGE_DEPTH,
            ntpa001_bod5_target_mg_l=self.EFFLUENT_BOD5_TARGET_MG_L,
            ntpa001_cod_target_mg_l=self.EFFLUENT_COD_TARGET_MG_L,
            ntpa001_tss_target_mg_l=self.EFFLUENT_TSS_TARGET_MG_L,
        )

        bom_items = [
            BOMItem(f"Excavation & Frost-Depth Earthworks {excavation_m3:.0f} m³", BOMCategory.LABOR, "m3", excavation_m3, UNIT_COSTS["excavation_m3"]),
            BOMItem(f"Wetland Berms & Subgrade Compaction {area_m2:.0f} m²", BOMCategory.LABOR, "m2", area_m2, UNIT_COSTS["wetland_earthworks_m2"]),
            BOMItem(f"HDPE Geomembrane 1.5mm + Geotextile {liner_m2:.0f} m²", BOMCategory.MATERIALS, "m2", liner_m2, UNIT_COSTS["hdpe_liner_m2"]),
            BOMItem(f"Washed Filter Gravel 10-20mm (incl. 15cm Frost Surcharge) {main_gravel:.1f} m³", BOMCategory.MATERIALS, "m3", main_gravel, UNIT_COSTS["gravel_10_20mm_m3"]),
            BOMItem(f"Drainage Gravel 40-80mm {drainage_gravel:.1f} m³", BOMCategory.MATERIALS, "m3", drainage_gravel, UNIT_COSTS["gravel_40_80mm_m3"]),
            BOMItem(f"Sand Filter Layer {sand_m3:.1f} m³", BOMCategory.MATERIALS, "m3", sand_m3, UNIT_COSTS["sand_m3"]),
            BOMItem(f"Precast Concrete Imhoff Tank {imhoff_m3:.0f} m³ (NTPA-011 Primary)", BOMCategory.EQUIPMENT, "m3", imhoff_m3, UNIT_COSTS["imhoff_tank_m3"]),
            BOMItem(f"PVC DN110 SN4 Distribution Piping {piping_m * 0.6:.0f} m", BOMCategory.MATERIALS, "m", piping_m * 0.6, UNIT_COSTS["piping_dn110_m"]),
            BOMItem(f"PVC DN160 SN4 Collection Piping {piping_m * 0.4:.0f} m", BOMCategory.MATERIALS, "m", piping_m * 0.4, UNIT_COSTS["piping_dn160_m"]),
            BOMItem(f"Concrete Inspection Manhole DN600 ({n_manholes} pcs)", BOMCategory.EQUIPMENT, "pcs", n_manholes, UNIT_COSTS["manhole_dn600"]),
            BOMItem("Stainless Steel Biogas Vent Pipe", BOMCategory.EQUIPMENT, "pcs", 2, UNIT_COSTS["vent_pipe"]),
            BOMItem("Hydraulic Flow Distribution & Sampling Chamber (NTPA-001)", BOMCategory.EQUIPMENT, "pcs", 1, UNIT_COSTS["flow_control_chamber"]),
            BOMItem(f"Phragmites australis / Typha latifolia ({macrophytes} rhizomes)", BOMCategory.MATERIALS, "pcs", macrophytes, UNIT_COSTS["macrophyte_plant"]),
            BOMItem(f"Macrophyte Planting & Establishment {area_m2:.0f} m²", BOMCategory.LABOR, "m2", area_m2, UNIT_COSTS["wetland_planting_m2"]),
            BOMItem(f"Hydraulic Piping Installation {piping_m:.0f} m", BOMCategory.LABOR, "m", piping_m, UNIT_COSTS["wetland_piping_install_m"]),
        ]

        subtotal_eq, subtotal_labor, contingency, total_capex = _finalize_capex_breakdown(
            bom_items, permits_label="Certificat Urbanism, Aviz Apele Române & APM"
        )

        return EngineeringBOMResponse(
            intervention_type=self.response_type,
            engineering_parameters=params,
            itemized_bom=bom_items,
            subtotal_equipment_eur=subtotal_eq,
            subtotal_works_labor_eur=subtotal_labor,
            contingency_reserve_eur=contingency,
            total_project_capex_eur=total_capex,
        )


# =============================================================================
# EDUPOD SIZER
# =============================================================================

class EduPodSizer:
    """
    Sizes shipping container conversion to a solar-powered digital education hub.
    Based on ISO 6346, Romanian building codes (NP 074, C107), and EU NZEB standards.
    """

    CONTAINER_DIMS = {
        20: {"length": 5898, "width": 2350, "height": 2393},
        40: {"length": 12032, "width": 2350, "height": 2393},
    }

    LIGHTING_W_PER_M2 = 12
    EQUIPMENT_W_PER_STATION = 45
    DAILY_OPERATION_HOURS = 8
    AUTONOMY_DAYS = 1.5

    def __init__(
        self,
        student_stations: int,
        container_size_ft: int = 20,
        response_type: InterventionType = InterventionType.EDUCATION_HUB,
    ) -> None:
        self.student_stations = max(8, student_stations)
        self.container_size_ft = container_size_ft if container_size_ft in (20, 40) else 20
        self.dims = self.CONTAINER_DIMS[self.container_size_ft]
        self.floor_area_m2 = (self.dims["length"] / 1000.0) * (self.dims["width"] / 1000.0)
        perimeter = 2.0 * (self.dims["length"] + self.dims["width"]) / 1000.0
        wall_height = self.dims["height"] / 1000.0
        self.wall_area_m2 = perimeter * wall_height * 0.75
        self.roof_area_m2 = self.floor_area_m2
        self.response_type = response_type

    def calculate_hvac_kw(self) -> float:
        wall_load = self.wall_area_m2 * 0.35 * 25
        roof_load = self.roof_area_m2 * 0.25 * 30
        floor_load = self.floor_area_m2 * 0.30 * 15
        internal_load = (
            self.student_stations * self.EQUIPMENT_W_PER_STATION
            + self.floor_area_m2 * self.LIGHTING_W_PER_M2
        ) / 1000.0
        total_kw = (wall_load + roof_load + floor_load) / 1000.0 + internal_load
        standard_sizes = [3.5, 5.0, 7.0, 10.0, 12.0, 14.0]
        for size in standard_sizes:
            if size >= total_kw * 1.15:
                return size
        return standard_sizes[-1]

    def calculate_solar_kwp(self) -> float:
        hvac_kw = self.calculate_hvac_kw()
        hvac_daily = hvac_kw * 0.6 * self.DAILY_OPERATION_HOURS
        lighting_daily = (self.floor_area_m2 * self.LIGHTING_W_PER_M2 / 1000.0) * self.DAILY_OPERATION_HOURS
        equipment_daily = (self.student_stations * self.EQUIPMENT_W_PER_STATION / 1000.0) * self.DAILY_OPERATION_HOURS
        hrvent_daily = 0.15 * self.DAILY_OPERATION_HOURS
        total_daily_kwh = hvac_daily + lighting_daily + equipment_daily + hrvent_daily

        winter_yield = 1.8
        pv_kwp = (total_daily_kwh * self.AUTONOMY_DAYS) / winter_yield * 1.2
        standard_sizes = [3, 4, 5, 6, 8, 10, 12, 15]
        for size in standard_sizes:
            if size >= pv_kwp:
                return float(size)
        return float(standard_sizes[-1])

    def calculate_insulation_m2(self) -> float:
        return self.wall_area_m2 + self.roof_area_m2 + self.floor_area_m2

    def generate_bom(self) -> EngineeringBOMResponse:
        hvac_kw = self.calculate_hvac_kw()
        solar_kwp = self.calculate_solar_kwp()
        insulation_m2 = self.calculate_insulation_m2()

        if self.container_size_ft == 20:
            container_cost = UNIT_COSTS["container_20ft"]
            transport_cost = UNIT_COSTS["container_transport_20ft"]
        else:
            container_cost = UNIT_COSTS["container_40ft"]
            transport_cost = UNIT_COSTS["container_transport_40ft"]

        hvac_cost = UNIT_COSTS["hvac_split_3_5kw"] if hvac_kw <= 3.5 else UNIT_COSTS["hvac_split_5kw"]

        if solar_kwp <= 3:
            pv_cost = UNIT_COSTS["pv_kit_3kwp"]
        elif solar_kwp <= 5:
            pv_cost = UNIT_COSTS["pv_kit_5kwp"]
        else:
            n_kits = math.ceil(solar_kwp / 5)
            pv_cost = UNIT_COSTS["pv_kit_5kwp"] * n_kits

        n_batteries = max(1, math.ceil(solar_kwp / 5))

        params = EngineeringParameters(
            container_size_ft=self.container_size_ft,
            insulation_m2=round(insulation_m2, 1),
            hvac_kw=hvac_kw,
            solar_kwp=solar_kwp,
            computer_stations=self.student_stations,
            student_stations=self.student_stations,
        )

        bom_items = [
            BOMItem(f"ISO {self.container_size_ft}ft High-Cube Container", BOMCategory.EQUIPMENT, "pcs", 1, container_cost),
            BOMItem("Container Transport & Delivery", BOMCategory.LABOR, "pcs", 1, transport_cost),
            BOMItem("Precast Foundation Blocks & Leveling", BOMCategory.MATERIALS, "lump", 1, UNIT_COSTS["foundation_blocks"]),
            BOMItem("Mobile Crane Rental (25t, 1 day)", BOMCategory.LABOR, "day", 1, UNIT_COSTS["crane_rental_day"]),
            BOMItem("Structural Modification (fenestration, welding, framing)", BOMCategory.LABOR, "pod", 1, UNIT_COSTS["container_modification_labor"]),
            BOMItem(f"Wall Insulation 100mm Basalt Wool {self.wall_area_m2:.0f} m²", BOMCategory.MATERIALS, "m2", self.wall_area_m2, UNIT_COSTS["insulation_wall_m2"]),
            BOMItem(f"Roof Insulation 150mm Basalt Wool {self.roof_area_m2:.0f} m²", BOMCategory.MATERIALS, "m2", self.roof_area_m2, UNIT_COSTS["insulation_roof_m2"]),
            BOMItem(f"Floor Insulation 80mm XPS {self.floor_area_m2:.0f} m²", BOMCategory.MATERIALS, "m2", self.floor_area_m2, UNIT_COSTS["insulation_floor_m2"]),
            BOMItem(f"Fire-Rated Interior Finish {self.floor_area_m2 * 2.5:.0f} m²", BOMCategory.MATERIALS, "m2", self.floor_area_m2 * 2.5, UNIT_COSTS["interior_finish_m2"]),
            BOMItem(f"Electrical Rough-in (I7/2011) {self.floor_area_m2:.0f} m²", BOMCategory.MATERIALS, "m2", self.floor_area_m2, UNIT_COSTS["electrical_roughin_m2"]),
            BOMItem("LED Fixtures, Sockets & Protection Panel", BOMCategory.EQUIPMENT, "pod", 1, UNIT_COSTS["electrical_fixtures"]),
            BOMItem(f"Inverter Heat-Pump Split HVAC {hvac_kw:.1f} kW", BOMCategory.EQUIPMENT, "pcs", 1, hvac_cost),
            BOMItem("Heat Recovery Ventilator (HRV) 150 m³/h", BOMCategory.EQUIPMENT, "pcs", 1, UNIT_COSTS["hrv_unit"]),
            BOMItem(f"Rooftop Solar PV Kit {solar_kwp:.0f} kWp", BOMCategory.EQUIPMENT, "kit", 1, pv_cost),
            BOMItem(f"LiFePO4 Battery Storage 10 kWh ({n_batteries} pcs)", BOMCategory.EQUIPMENT, "pcs", n_batteries, UNIT_COSTS["battery_10kwh"]),
            BOMItem(f"Digital Study Workstation x{self.student_stations}", BOMCategory.EQUIPMENT, "pcs", self.student_stations, UNIT_COSTS["computer_station"]),
            BOMItem("12U Network Rack, Managed Switch & Wi-Fi 6 AP", BOMCategory.EQUIPMENT, "pcs", 1, UNIT_COSTS["network_rack"]),
            BOMItem("Satellite Broadband Terminal (Starlink Pro)", BOMCategory.EQUIPMENT, "kit", 1, UNIT_COSTS["internet_satellite"]),
            BOMItem("Interior Fit-out & Electrical Assembly Labor", BOMCategory.LABOR, "pod", 1, UNIT_COSTS["interior_fitout_labor"]),
            BOMItem("PRAM Testing, ISU & Electrical Commissioning", BOMCategory.LABOR, "pod", 1, UNIT_COSTS["commissioning_testing"]),
        ]

        subtotal_eq, subtotal_labor, contingency, total_capex = _finalize_capex_breakdown(
            bom_items, permits_label="Building Notification & ISU Safety Clearance"
        )

        return EngineeringBOMResponse(
            intervention_type=self.response_type,
            engineering_parameters=params,
            itemized_bom=bom_items,
            subtotal_equipment_eur=subtotal_eq,
            subtotal_works_labor_eur=subtotal_labor,
            contingency_reserve_eur=contingency,
            total_project_capex_eur=total_capex,
        )


# =============================================================================
# INTEGRATED SIZER
# =============================================================================

class IntegratedSizer:
    """Combines all three intervention types for comprehensive UAT-level projects."""

    def __init__(
        self,
        target_households: int,
        connected_people_equivalent: int,
        student_stations: int,
        container_size_ft: int = 20,
        daily_energy_per_household_kwh: Optional[float] = None,
        county: Optional[str] = None,
    ) -> None:
        self.solar_sizer = OffGridSolarSizer(
            target_households,
            "standard",
            daily_energy_per_household_kwh=daily_energy_per_household_kwh,
            county=county,
        )
        self.wetland_sizer = ConstructedWetlandSizer(connected_people_equivalent)
        self.edupod_sizer = EduPodSizer(student_stations, container_size_ft)

    def generate_bom(self) -> EngineeringBOMResponse:
        solar_bom = self.solar_sizer.generate_bom()
        wetland_bom = self.wetland_sizer.generate_bom()
        edupod_bom = self.edupod_sizer.generate_bom()

        all_items = solar_bom.itemized_bom + wetland_bom.itemized_bom + edupod_bom.itemized_bom

        sp = solar_bom.engineering_parameters
        wp = wetland_bom.engineering_parameters
        ep = edupod_bom.engineering_parameters

        params = EngineeringParameters(
            pv_array_kwp=sp.pv_array_kwp,
            pv_kwp=sp.pv_kwp,
            battery_kwh=sp.battery_kwh,
            inverter_kva=sp.inverter_kva,
            inverter_kw=sp.inverter_kw,
            inverter_surge_kva=sp.inverter_surge_kva,
            winter_psh=sp.winter_psh,
            temp_derating_coeff_pct_per_c=sp.temp_derating_coeff_pct_per_c,
            lifepo4_dod=sp.lifepo4_dod,
            target_households=sp.target_households,
            connected_pe=wp.connected_pe,
            wetland_area_m2=wp.wetland_area_m2,
            imhoff_tank_m3=wp.imhoff_tank_m3,
            gravel_volume_m3=wp.gravel_volume_m3,
            macrophytes_count=wp.macrophytes_count,
            piping_m=wp.piping_m,
            hydraulic_loading_rate_m_day=wp.hydraulic_loading_rate_m_day,
            frost_surcharge_m=wp.frost_surcharge_m,
            ntpa001_bod5_target_mg_l=wp.ntpa001_bod5_target_mg_l,
            ntpa001_cod_target_mg_l=wp.ntpa001_cod_target_mg_l,
            ntpa001_tss_target_mg_l=wp.ntpa001_tss_target_mg_l,
            container_size_ft=ep.container_size_ft,
            insulation_m2=ep.insulation_m2,
            hvac_kw=ep.hvac_kw,
            solar_kwp=ep.solar_kwp,
            computer_stations=ep.computer_stations,
            student_stations=ep.student_stations,
        )

        subtotal_eq = round(
            solar_bom.subtotal_equipment_eur
            + wetland_bom.subtotal_equipment_eur
            + edupod_bom.subtotal_equipment_eur,
            2,
        )
        subtotal_labor = round(
            solar_bom.subtotal_works_labor_eur
            + wetland_bom.subtotal_works_labor_eur
            + edupod_bom.subtotal_works_labor_eur,
            2,
        )
        contingency = round(
            solar_bom.contingency_reserve_eur
            + wetland_bom.contingency_reserve_eur
            + edupod_bom.contingency_reserve_eur,
            2,
        )
        total_capex = round(subtotal_eq + subtotal_labor + contingency, 2)

        return EngineeringBOMResponse(
            intervention_type=InterventionType.INTEGRATED,
            engineering_parameters=params,
            itemized_bom=all_items,
            subtotal_equipment_eur=subtotal_eq,
            subtotal_works_labor_eur=subtotal_labor,
            contingency_reserve_eur=contingency,
            total_project_capex_eur=total_capex,
        )


# =============================================================================
# MAIN CALCULATION FUNCTION
# =============================================================================

def calculate_bom(
    intervention_type: InterventionType,
    target_households: int = 20,
    connected_people_equivalent: int = 100,
    student_stations: int = 16,
    container_size_ft: int = 20,
    daily_energy_per_household_kwh: Optional[float] = None,
    county: Optional[str] = None,
) -> EngineeringBOMResponse:
    """Main entry point for deterministic BOM & CAPEX calculation."""
    if intervention_type in (InterventionType.ENERGY_OFFGRID, InterventionType.OFFGRID_PV):
        sizer = OffGridSolarSizer(
            target_households,
            daily_energy_per_household_kwh=daily_energy_per_household_kwh,
            county=county,
            response_type=intervention_type,
        )
        return sizer.generate_bom()
    elif intervention_type in (InterventionType.PHYTOSANITATION, InterventionType.SANITATION):
        sizer = ConstructedWetlandSizer(
            connected_people_equivalent,
            response_type=intervention_type,
        )
        return sizer.generate_bom()
    elif intervention_type in (InterventionType.EDUCATION_HUB, InterventionType.EDUCATION):
        sizer = EduPodSizer(
            student_stations,
            container_size_ft,
            response_type=intervention_type,
        )
        return sizer.generate_bom()
    elif intervention_type == InterventionType.INTEGRATED:
        sizer = IntegratedSizer(
            target_households,
            connected_people_equivalent,
            student_stations,
            container_size_ft,
            daily_energy_per_household_kwh=daily_energy_per_household_kwh,
            county=county,
        )
        return sizer.generate_bom()
    else:
        raise ValueError(f"Unknown intervention type: {intervention_type}")


# =============================================================================
# PYDANTIC MODELS FOR API (Pydantic v2)
# =============================================================================

class BOMItemModel(BaseModel):
    description: str
    category: str
    unit: str
    qty: float
    unit_price_eur: float
    total_eur: float


class EngineeringParametersModel(BaseModel):
    pv_array_kwp: Optional[float] = None
    pv_kwp: Optional[float] = None
    battery_kwh: Optional[float] = None
    inverter_kva: Optional[float] = None
    inverter_kw: Optional[float] = None
    inverter_surge_kva: Optional[float] = None
    winter_psh: Optional[float] = None
    temp_derating_coeff_pct_per_c: Optional[float] = None
    lifepo4_dod: Optional[float] = None
    target_households: Optional[int] = None

    connected_pe: Optional[int] = None
    wetland_area_m2: Optional[float] = None
    imhoff_tank_m3: Optional[float] = None
    gravel_volume_m3: Optional[float] = None
    macrophytes_count: Optional[int] = None
    piping_m: Optional[float] = None
    hydraulic_loading_rate_m_day: Optional[float] = None
    frost_surcharge_m: Optional[float] = None
    ntpa001_bod5_target_mg_l: Optional[float] = None
    ntpa001_cod_target_mg_l: Optional[float] = None
    ntpa001_tss_target_mg_l: Optional[float] = None

    container_size_ft: Optional[int] = None
    insulation_m2: Optional[float] = None
    hvac_kw: Optional[float] = None
    solar_kwp: Optional[float] = None
    computer_stations: Optional[int] = None
    student_stations: Optional[int] = None


class CalculateBOMRequest(BaseModel):
    intervention_type: InterventionType
    target_households: Optional[int] = Field(None, ge=1, le=5000, description="Number of households for off-grid solar")
    daily_energy_per_household_kwh: Optional[float] = Field(None, ge=0.5, le=100.0, description="Daily kWh consumption per household")
    connected_people_equivalent: Optional[int] = Field(None, ge=5, le=50000, description="Population equivalent (PE) for wetland")
    student_stations: Optional[int] = Field(None, ge=4, le=120, description="Number of computer stations for EduPod")
    container_size_ft: int = Field(20, description="Container size in feet (20 or 40)")


class CalculateBOMResponse(BaseModel):
    intervention_type: str
    engineering_parameters: EngineeringParametersModel
    itemized_bom: List[BOMItemModel]
    subtotal_equipment_eur: float
    subtotal_works_labor_eur: float
    contingency_reserve_eur: float
    total_project_capex_eur: float