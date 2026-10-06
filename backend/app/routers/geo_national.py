"""
PSAN Radar — National Geo Router
================================

FastAPI endpoints for national UAT coverage (all 3,181 units):
- GET /api/v1/geo/romania-uat-national — Cached national GeoJSON with 24h Cache-Control
- GET /api/v1/geo/counties — Sorted list of unique county names
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/geo", tags=["National Geo"])

# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
NATIONAL_GEOJSON_PATH = BASE_DIR / "app" / "data" / "romania_uat_national_rvi.geojson"

# Required properties in the national GeoJSON
REQUIRED_PROPERTIES = {
    "siruta", "uat_name", "county", "population", "households_total",
    "i_sewage", "i_water", "i_energy", "i_education", "i_isolation",
    "rvi_score", "priority_tier",
}

# In-memory cache
_cached_national_geojson: Optional[Dict[str, Any]] = None
_cached_counties: Optional[List[str]] = None
_cached_etag: Optional[str] = None


def _compute_etag(data: Dict[str, Any]) -> str:
    """Compute stable ETag using SHA-256."""
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:32]


def _validate_geojson(geojson: Dict[str, Any]) -> None:
    """Validate that GeoJSON has required structure and properties."""
    if geojson.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON root must be a FeatureCollection")
    features = geojson.get("features", [])
    if not features:
        raise ValueError("GeoJSON contains no features")
    # Check first feature for required properties
    first_props = features[0].get("properties", {})
    missing = REQUIRED_PROPERTIES - set(first_props.keys())
    if missing:
        raise ValueError(f"Missing required properties in GeoJSON: {missing}")


def load_national_geojson() -> Dict[str, Any]:
    """Load and cache the national GeoJSON FeatureCollection."""
    global _cached_national_geojson, _cached_counties, _cached_etag

    if _cached_national_geojson is not None:
        return _cached_national_geojson

    if not NATIONAL_GEOJSON_PATH.exists():
        raise RuntimeError(
            f"National GeoJSON not found at {NATIONAL_GEOJSON_PATH}. "
            "Run scripts/build_national_uat_dataset.py first."
        )

    with open(NATIONAL_GEOJSON_PATH, "r", encoding="utf-8") as f:
        _cached_national_geojson = json.load(f)

    _validate_geojson(_cached_national_geojson)
    _cached_etag = _compute_etag(_cached_national_geojson)

    # Extract and cache sorted unique county names
    counties = set()
    for feature in _cached_national_geojson.get("features", []):
        county = feature.get("properties", {}).get("county")
        if county:
            counties.add(county)
    _cached_counties = sorted(counties)

    return _cached_national_geojson


@router.get("/romania-uat-national")
def get_national_uat_geojson(response: Response) -> Dict[str, Any]:
    """
    Return the cached national UAT GeoJSON FeatureCollection (all ~3,181 units).

    Response includes 24-hour HTTP Cache-Control header for CDN/browser caching.
    """
    geojson = load_national_geojson()

    # Set 24-hour cache headers
    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=3600"
    response.headers["ETag"] = f'"{_cached_etag}"'

    return geojson


@router.get("/counties", response_model=List[str])
def get_counties() -> List[str]:
    """
    Return a sorted list of all unique county names present in the national dataset.
    """
    load_national_geojson()  # Ensures cache is populated
    if _cached_counties is None:
        raise HTTPException(status_code=500, detail="County list not available.")
    return _cached_counties


@router.get("/romania-uat-national/county/{county_name}")
def get_county_geojson(county_name: str, response: Response) -> Dict[str, Any]:
    """
    Return a filtered GeoJSON FeatureCollection for a specific county.
    """
    geojson = load_national_geojson()

    filtered_features = [
        feat for feat in geojson.get("features", [])
        if feat.get("properties", {}).get("county") == county_name
    ]

    if not filtered_features:
        raise HTTPException(status_code=404, detail=f"County '{county_name}' not found or has no UATs.")

    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=3600"
    response.headers["ETag"] = f'"{_cached_etag}-{county_name}"'

    return {
        "type": "FeatureCollection",
        "features": filtered_features,
    }


@router.get("/romania-uat-national/uat/{siruta}")
def get_uat_by_siruta(siruta: int) -> Dict[str, Any]:
    """
    Return a single UAT feature by its SIRUTA code (O(n) lookup on cached data).
    """
    geojson = load_national_geojson()

    for feature in geojson.get("features", []):
        if feature.get("properties", {}).get("siruta") == siruta:
            return feature

    raise HTTPException(status_code=404, detail=f"UAT with SIRUTA {siruta} not found.")