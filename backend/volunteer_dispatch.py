"""
PSAN Radar — Module 2: Volunteer Skills Matcher & Pro Bono Dispatch Engine
==========================================================================

Matches a target UAT's technical intervention requirements (ANRE Grade IIA/IIB
electrical sign-off, civil/hydrotechnical wetland design, environmental
permitting, embedded telemetry, and field first aid) against registered
Engineers Without Borders Romania (Ingineri Fără Frontiere) volunteers,
ranking candidates by geodesic Haversine distance to the UAT centroid.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field


# =============================================================================
# ENUMS & SCHEMAS (Pydantic v2)
# =============================================================================

class VolunteerQualification(str, Enum):
    ANRE_2A = "ANRE_2A"
    ANRE_2B = "ANRE_2B"
    CIVIL_HYDRO_ENGINEER = "CIVIL_HYDRO_ENGINEER"
    ENVIRONMENTAL_ENGINEER = "ENVIRONMENTAL_ENGINEER"
    FIRST_AID = "FIRST_AID"
    SOFTWARE_EMBEDDED = "SOFTWARE_EMBEDDED"


class VolunteerRecord(BaseModel):
    id: str = Field(..., description="Unique volunteer identifier")
    name: str = Field(..., description="Full name and professional title")
    email: str = Field(..., description="Contact email")
    phone: str = Field(..., description="Mobile phone number")
    county: str = Field(..., description="Base county in Romania")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    qualifications: List[VolunteerQualification] = Field(..., min_length=1)
    available: bool = Field(True, description="Whether currently available for field deployment")


class MatchedVolunteer(BaseModel):
    volunteer: VolunteerRecord
    distance_km: float = Field(..., description="Geodesic Haversine distance to target UAT (km)")
    matched_roles: List[str] = Field(..., description="Technical roles fulfilled by this volunteer")
    estimated_travel_hours: float = Field(..., description="Estimated road transit time (hours)")


class DispatchTeamRequest(BaseModel):
    max_team_size: int = Field(4, ge=1, le=12, description="Maximum number of volunteers to dispatch")
    required_qualifications: Optional[List[VolunteerQualification]] = Field(
        None,
        description="Optional override of required qualifications; auto-inferred from UAT deficits if omitted",
    )


class DispatchTeamResponse(BaseModel):
    dispatch_id: str
    siruta: int
    uat_name: str
    county: str
    uat_centroid: Dict[str, float]
    required_qualifications: List[str]
    covered_qualifications: List[str]
    missing_qualifications: List[str]
    readiness_score_pct: float
    dispatched_team: List[MatchedVolunteer]
    mobilization_order_summary: str
    dispatched_at: str


# =============================================================================
# HAVERSINE GEODESIC DISTANCE
# =============================================================================

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute exact geodesic great-circle distance (km) using the Haversine formula."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return round(EARTH_RADIUS_KM * c, 2)


# =============================================================================
# SEED ROSTER — EWB ROMÂNIA PRO BONO SPECIALISTS
# =============================================================================

INITIAL_VOLUNTEERS: List[VolunteerRecord] = [
    VolunteerRecord(
        id="ewb-vol-001",
        name="Ing. Andrei Munteanu (ANRE IIB)",
        email="andrei.munteanu@ewb-romania.ro",
        phone="+40 742 110 201",
        county="Galați",
        latitude=45.4353,
        longitude=28.0080,
        qualifications=[
            VolunteerQualification.ANRE_2A,
            VolunteerQualification.ANRE_2B,
            VolunteerQualification.FIRST_AID,
        ],
        available=True,
    ),
    VolunteerRecord(
        id="ewb-vol-002",
        name="Dr. Ing. Elena Dobrescu (Hidrotehnică)",
        email="elena.dobrescu@ewb-romania.ro",
        phone="+40 723 445 890",
        county="Iași",
        latitude=47.1585,
        longitude=27.6014,
        qualifications=[
            VolunteerQualification.CIVIL_HYDRO_ENGINEER,
            VolunteerQualification.ENVIRONMENTAL_ENGINEER,
        ],
        available=True,
    ),
    VolunteerRecord(
        id="ewb-vol-003",
        name="Ing. Radu Sava (Sisteme Fotovoltaice & IoT)",
        email="radu.sava@ewb-romania.ro",
        phone="+40 751 309 112",
        county="Vrancea",
        latitude=45.6964,
        longitude=27.1833,
        qualifications=[
            VolunteerQualification.ANRE_2A,
            VolunteerQualification.SOFTWARE_EMBEDDED,
        ],
        available=True,
    ),
    VolunteerRecord(
        id="ewb-vol-004",
        name="Ing. Cristina Ionescu (Mediu & Fitodepurare)",
        email="cristina.ionescu@ewb-romania.ro",
        phone="+40 766 812 405",
        county="Tulcea",
        latitude=45.1788,
        longitude=28.8055,
        qualifications=[
            VolunteerQualification.ENVIRONMENTAL_ENGINEER,
            VolunteerQualification.CIVIL_HYDRO_ENGINEER,
            VolunteerQualification.FIRST_AID,
        ],
        available=True,
    ),
    VolunteerRecord(
        id="ewb-vol-005",
        name="Ing. Mihai Toma (SCADA / LoRaWAN / EduPod)",
        email="mihai.toma@ewb-romania.ro",
        phone="+40 730 998 114",
        county="Bacău",
        latitude=46.5670,
        longitude=26.9146,
        qualifications=[
            VolunteerQualification.SOFTWARE_EMBEDDED,
            VolunteerQualification.FIRST_AID,
        ],
        available=True,
    ),
    VolunteerRecord(
        id="ewb-vol-006",
        name="Ing. Sorin Vasile (ANRE IIA/IIB & PRAM)",
        email="sorin.vasile@ewb-romania.ro",
        phone="+40 744 512 778",
        county="Botoșani",
        latitude=47.7486,
        longitude=26.6694,
        qualifications=[
            VolunteerQualification.ANRE_2A,
            VolunteerQualification.ANRE_2B,
        ],
        available=True,
    ),
]

_volunteers_db: List[VolunteerRecord] = list(INITIAL_VOLUNTEERS)


# =============================================================================
# MATCHING ENGINE
# =============================================================================

def infer_required_qualifications(uat_props: Dict[str, Any]) -> List[VolunteerQualification]:
    """Infer mandatory engineering qualifications from UAT vulnerability indices."""
    req: List[VolunteerQualification] = []
    i_energy = float(uat_props.get("i_energy", 0.0))
    i_sanitation = float(uat_props.get("i_sanitation", 0.0))
    i_education = float(uat_props.get("i_education", 0.0))

    if i_energy >= 0.30:
        req.extend([VolunteerQualification.ANRE_2A, VolunteerQualification.ANRE_2B])
    if i_sanitation >= 0.30:
        req.extend([
            VolunteerQualification.CIVIL_HYDRO_ENGINEER,
            VolunteerQualification.ENVIRONMENTAL_ENGINEER,
        ])
    if i_education >= 0.30:
        req.append(VolunteerQualification.SOFTWARE_EMBEDDED)

    req.append(VolunteerQualification.FIRST_AID)
    # Deduplicate preserving order
    seen = set()
    ordered = []
    for q in req:
        if q not in seen:
            seen.add(q)
            ordered.append(q)
    return ordered


def dispatch_optimal_team(
    uat_props: Dict[str, Any],
    centroid_lat: float,
    centroid_lon: float,
    request: Optional[DispatchTeamRequest] = None,
) -> DispatchTeamResponse:
    """
    Greedy set-cover + Haversine distance optimizer:
    Selects available volunteers that maximize coverage of the UAT's required
    engineering qualifications while minimizing geodesic travel distance.
    """
    req = request or DispatchTeamRequest()
    required_quals = req.required_qualifications or infer_required_qualifications(uat_props)
    uncovered = set(required_quals)

    candidates = [v for v in _volunteers_db if v.available]
    scored_candidates = []
    for v in candidates:
        dist = haversine_km(centroid_lat, centroid_lon, v.latitude, v.longitude)
        scored_candidates.append((v, dist))

    selected: List[MatchedVolunteer] = []
    used_ids = set()

    # Step 1: Greedy selection covering missing qualifications by closest distance
    while uncovered and len(selected) < req.max_team_size:
        best_pair = None
        best_score = -1e9
        for v, dist in scored_candidates:
            if v.id in used_ids:
                continue
            newly_covered = [q for q in v.qualifications if q in uncovered]
            if not newly_covered:
                continue
            # Prioritize number of needed certs covered, breaking ties by closest Haversine distance
            score = (len(newly_covered) * 1000.0) - dist
            if score > best_score:
                best_score = score
                best_pair = (v, dist, newly_covered)

        if best_pair is None:
            break

        v, dist, newly_covered = best_pair
        used_ids.add(v.id)
        for q in v.qualifications:
            uncovered.discard(q)
        selected.append(
            MatchedVolunteer(
                volunteer=v,
                distance_km=dist,
                matched_roles=[q.value for q in v.qualifications if q in required_quals],
                estimated_travel_hours=round(max(0.4, dist / 62.0), 1),
            )
        )

    # Sort final roster by geodesic distance ascending
    selected.sort(key=lambda m: m.distance_km)

    covered_set = {
        q
        for m in selected
        for q in m.volunteer.qualifications
        if q in required_quals
    }
    covered_list = [q.value for q in required_quals if q in covered_set]
    missing_list = [q.value for q in required_quals if q not in covered_set]
    readiness = round((len(covered_list) / max(1, len(required_quals))) * 100.0, 1)

    siruta = int(uat_props["siruta"])
    uat_name = str(uat_props["uat_name"])
    county = str(uat_props["county"])
    dispatch_id = f"EWB-DSP-{siruta}-{int(datetime.now(timezone.utc).timestamp())}"

    team_names = ", ".join(f"{m.volunteer.name} ({m.distance_km:.1f} km)" for m in selected)
    summary = (
        f"Ordin de Mobilizare Pro Bono #{dispatch_id} pentru {uat_name} (jud. {county}, SIRUTA {siruta}): "
        f"Echipă formată din {len(selected)} specialiști ({team_names}). "
        f"Acoperire calificări reglementate: {readiness:.0f}% ({', '.join(covered_list)})."
    )

    return DispatchTeamResponse(
        dispatch_id=dispatch_id,
        siruta=siruta,
        uat_name=uat_name,
        county=county,
        uat_centroid={"latitude": round(centroid_lat, 5), "longitude": round(centroid_lon, 5)},
        required_qualifications=[q.value for q in required_quals],
        covered_qualifications=covered_list,
        missing_qualifications=missing_list,
        readiness_score_pct=readiness,
        dispatched_team=selected,
        mobilization_order_summary=summary,
        dispatched_at=datetime.now(timezone.utc).isoformat(),
    )


# =============================================================================
# ROUTER FOR STANDALONE VOLUNTEER DIRECTORY
# =============================================================================

router = APIRouter(prefix="/api/v1/volunteers", tags=["Volunteer Dispatch"])


@router.get("", response_model=List[VolunteerRecord])
async def list_volunteers(county: Optional[str] = None, qualification: Optional[VolunteerQualification] = None) -> List[VolunteerRecord]:
    """List registered EWB Romania pro bono volunteers."""
    results = list(_volunteers_db)
    if county:
        results = [v for v in results if v.county.lower() == county.lower()]
    if qualification:
        results = [v for v in results if qualification in v.qualifications]
    return results


@router.post("", response_model=VolunteerRecord, status_code=status.HTTP_201_CREATED)
async def register_volunteer(volunteer: VolunteerRecord) -> VolunteerRecord:
    """Register or update a pro bono volunteer in the EWB Romania roster."""
    global _volunteers_db
    _volunteers_db = [v for v in _volunteers_db if v.id != volunteer.id]
    _volunteers_db.append(volunteer)
    return volunteer
