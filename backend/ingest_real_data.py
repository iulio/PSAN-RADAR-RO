#!/usr/bin/env python3
"""
PSAN Radar — Phase 4: Real Data Ingestion Pipeline
===================================================

Transitions the PSAN Radar from synthetic mock polygons to real Romanian
official administrative boundaries (UAT level) and real public indicator
datasets.

Data sources:
  * UAT vector boundaries: geo-spatial.org / Romanian administrative
    boundaries public GeoJSON mirrors on GitHub.
  * Sanitation: INS RPL 2021 (Recensământul Populației și Locuințelor) /
    TEMPO export — households without sewage/septic connection.
  * Energy poverty: Ministerul Energiei / "România fără Lumină" off-grid
    localities registry.
  * Education: MATE / SIIIR school dropout risk indices at UAT level.

Output: data/uat_vulnerability.geojson  (EPSG:4326, simplified, <15 MB)

Requirements:
    pip install geopandas pandas requests openpyxl

Usage:
    python ingest_real_data.py
    python ingest_real_data.py --boundaries data/romania_uat_raw.geojson \
        --ins data/ins_rpl2021_sanitation.csv \
        --energy data/offgrid_registry.csv \
        --education data/mate_dropout.csv
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

# =============================================================================
# CONFIGURATION
# =============================================================================

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_PATH = DATA_DIR / "uat_vulnerability.geojson"
LOCAL_BOUNDARIES_FALLBACK = DATA_DIR / "romania_uat_raw.geojson"

# Public mirrors of official simplified Romanian UAT boundaries (EPSG:4326).
# Tried in order; first successful download wins.
BOUNDARY_URLS = [
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/ROU/ADM2/geoBoundaries-ROU-ADM2_simplified.geojson",
]

DOWNLOAD_TIMEOUT = 60  # seconds
MAX_OUTPUT_BYTES = 15 * 1024 * 1024  # 15 MB web-rendering budget
SIMPLIFY_TOLERANCE = 0.001  # degrees (~100 m) — keeps GeoJSON lightweight

# RVI weights (Unified Data Dictionary formula)
W_SANITATION = 0.30
W_ENERGY = 0.30
W_EDUCATION = 0.25
W_MARGINALIZATION = 0.15

TIER_CRITICAL = 75.0
TIER_HIGH = 50.0

# =============================================================================
# SIRUTA / TEXT NORMALIZATION
# =============================================================================

def normalize_siruta(value) -> int | None:
    """Parse SIRUTA as a zero-free integer.

    Accepts ints, floats, and strings with whitespace or leading zeros.
    Returns None for unparseable values.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        digits = "".join(ch for ch in str(value).strip() if ch.isdigit())
        if not digits:
            return None
        return int(digits.lstrip("0") or "0")
    except (ValueError, TypeError):
        return None


def siruta_str(value) -> str | None:
    """Standardized 6-digit zero-padded SIRUTA string for join keys."""
    n = normalize_siruta(value)
    return f"{n:06d}" if n is not None else None


def strip_diacritics(text: str) -> str:
    """Remove Romanian diacritics (ș ț ă î â) for fuzzy name matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", str(text))
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


def find_column(df: pd.DataFrame, *candidates: str) -> str | None:
    """Find a dataframe column by diacritic-insensitive fuzzy matching."""
    normalized = {strip_diacritics(c).replace(" ", "_"): c for c in df.columns}
    for cand in candidates:
        key = strip_diacritics(cand).replace(" ", "_")
        if key in normalized:
            return normalized[key]
    # substring fallback
    for cand in candidates:
        key = strip_diacritics(cand).replace(" ", "_")
        for nk, orig in normalized.items():
            if key in nk or nk in key:
                return orig
    return None

# =============================================================================
# 1. BOUNDARY FETCHER
# =============================================================================

def fetch_uat_boundaries(local_path: Path | None = None) -> gpd.GeoDataFrame:
    """Load or download official simplified Romanian UAT boundaries.

    Uses the real geoBoundaries ADM2 + ADM1 pipeline (scripts/download_real_boundaries.py)
    or existing real UAT GeoJSON on disk.
    """
    if OUTPUT_PATH.exists():
        gdf_existing = gpd.read_file(OUTPUT_PATH)
        if len(gdf_existing) > 50 and "siruta" in gdf_existing.columns:
            print(f"[boundaries] Loaded {len(gdf_existing)} real UAT polygons from {OUTPUT_PATH}")
            return gdf_existing

    fallback = local_path or LOCAL_BOUNDARIES_FALLBACK
    if fallback.exists():
        gdf_local = gpd.read_file(fallback)
        if len(gdf_local) > 50 and "siruta" in gdf_local.columns:
            print(f"[boundaries] Using local real boundaries: {fallback} ({len(gdf_local)} UATs)")
            return gdf_local

    print("[boundaries] Running scripts/download_real_boundaries.py to ingest real Romanian UAT polygons...")
    from scripts.download_real_boundaries import download_and_build_eastern_romania_uats
    return download_and_build_eastern_romania_uats()


def standardize_boundaries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Normalize boundary schema to: siruta, uat_name, county, geometry."""
    siruta_col = find_column(gdf, "siruta", "siruta_code", "cod_siruta", "SIRUTA")
    name_col = find_column(gdf, "uat_name", "name", "nume", "uat", "NAME")
    county_col = find_column(gdf, "county", "judet", "county_name", "JUDET")

    if siruta_col is None:
        raise ValueError("Boundary dataset has no SIRUTA column.")

    data = {
        "siruta": gdf[siruta_col].map(normalize_siruta),
        "uat_name": gdf[name_col].astype(str) if name_col else "UAT " + gdf[siruta_col].astype(str),
        "county": gdf[county_col].astype(str) if county_col else "Necunoscut",
        "geometry": gdf.geometry,
    }
    # Preserve pre-computed indicator columns (e.g. from the synthetic fallback)
    for col in ["population", "households_total", "i_sanitation", "i_energy",
                "i_education", "i_marginalization"]:
        if col in gdf.columns:
            data[col] = pd.to_numeric(gdf[col], errors="coerce")

    out = gpd.GeoDataFrame(data, crs=gdf.crs or "EPSG:4326")

    out = out.dropna(subset=["siruta"])
    out["siruta"] = out["siruta"].astype(int)
    out = out.to_crs("EPSG:4326")
    out["geometry"] = out.geometry.simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
    out = out[out.geometry.notna() & ~out.geometry.is_empty]
    print(f"[boundaries] Standardized {len(out)} UATs.")
    return out

# =============================================================================
# 2. INS RPL 2021 SANITATION PARSER
# =============================================================================
#
# Expected INS RPL 2021 / TEMPO export format (UTF-8 CSV). Sample rows:
#
#   siruta,uat_name,county,gospodarii_totale,fara_canalizare
#   179135,"Comuna Chiojdeni",Vrancea,812,401
#   162450,"Comuna Pungești",Vaslui,1240,893
#
# Real TEMPO exports may use Romanian headers such as
# "Gospodarii - Total" / "Fara canalizare sau grup de epurare" — the parser
# matches headers fuzzily (diacritic-insensitive).

def parse_ins_sanitation(csv_path: str | Path) -> pd.DataFrame:
    """Parse INS RPL 2021 sanitation export.

    Extracts total occupied dwellings (gospodarii_totale) and dwellings
    lacking connection to sewage systems or septic tanks (fara_canalizare),
    then computes i_sanitation = fara_canalizare / gospodarii_totale.
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"[ins] File not found: {path} — skipping sanitation indicator.")
        return pd.DataFrame(columns=["siruta", "households_total", "i_sanitation", "fara_canalizare"])

    df = pd.read_csv(path, encoding="utf-8-sig")
    siruta_col = find_column(df, "siruta", "cod_siruta")
    total_col = find_column(df, "gospodarii_totale", "gospodarii_total",
                            "gospodarii - total", "locuinte_ocupate")
    no_sew_col = find_column(df, "fara_canalizare",
                             "fara canalizare sau grup de epurare",
                             "fara_canalizare_sau_grup_de_epurare")
    if not all([siruta_col, total_col, no_sew_col]):
        raise ValueError(f"[ins] Could not identify required columns in {path}. "
                         f"Found: {list(df.columns)}")

    out = pd.DataFrame({
        "siruta": df[siruta_col].map(normalize_siruta),
        "households_total": pd.to_numeric(df[total_col], errors="coerce"),
        "fara_canalizare": pd.to_numeric(df[no_sew_col], errors="coerce"),
    }).dropna(subset=["siruta"])
    out["siruta"] = out["siruta"].astype(int)
    out["i_sanitation"] = (out["fara_canalizare"] / out["households_total"]).clip(0, 1)
    print(f"[ins] Parsed sanitation for {len(out)} UATs.")
    return out[["siruta", "households_total", "i_sanitation"]]

# =============================================================================
# 3. MINISTRY OF ENERGY — UNELECTRIFIED LOCALITIES MAPPER
# =============================================================================
#
# Expected off-grid registry format (Ministerul Energiei / România fără Lumină):
#
#   siruta,uat_name,gospodarii_neelectrificare
#   179135,"Comuna Chiojdeni",37
#   162450,"Comuna Pungești",112

def merge_energy_poverty(gdf: gpd.GeoDataFrame,
                         offgrid_registry_path: str | Path) -> gpd.GeoDataFrame:
    """Map isolated off-grid households to their UAT SIRUTA code and compute
    i_energy as a normalized vulnerability factor."""
    path = Path(offgrid_registry_path)
    if not path.exists():
        print(f"[energy] File not found: {path} — skipping energy indicator.")
        if "i_energy" not in gdf.columns:
            gdf["i_energy"] = pd.NA
        return gdf

    df = pd.read_csv(path, encoding="utf-8-sig")
    siruta_col = find_column(df, "siruta", "cod_siruta")
    offgrid_col = find_column(df, "gospodarii_neelectrificare", "neelectrificare",
                              "offgrid", "gospodarii_izolate", "fara_curent")
    if not all([siruta_col, offgrid_col]):
        raise ValueError(f"[energy] Could not identify required columns in {path}.")

    reg = pd.DataFrame({
        "siruta": df[siruta_col].map(normalize_siruta),
        "offgrid_households": pd.to_numeric(df[offgrid_col], errors="coerce"),
    }).dropna(subset=["siruta"])
    reg["siruta"] = reg["siruta"].astype(int)

    gdf = gdf.merge(reg, on="siruta", how="left")
    denom = gdf["households_total"].replace(0, pd.NA) if "households_total" in gdf else pd.NA
    gdf["i_energy"] = (gdf["offgrid_households"] / denom).clip(0, 1)
    print(f"[energy] Merged off-grid registry for {reg['siruta'].nunique()} UATs.")
    return gdf

# =============================================================================
# 4. MATE / EDUCATION VULNERABILITY INTEGRATION
# =============================================================================
#
# Expected MATE / SIIIR export format:
#
#   siruta,uat_name,risc_abandon_scolar
#   179135,"Comuna Chiojdeni",0.31
#   162450,"Comuna Pungești",0.42

def merge_education_risk(gdf: gpd.GeoDataFrame,
                         mate_path: str | Path) -> gpd.GeoDataFrame:
    """Ingest school dropout risk indices (MATE / SIIIR) at UAT level → i_education."""
    path = Path(mate_path)
    if not path.exists():
        print(f"[education] File not found: {path} — skipping education indicator.")
        if "i_education" not in gdf.columns:
            gdf["i_education"] = pd.NA
        return gdf

    df = pd.read_csv(path, encoding="utf-8-sig")
    siruta_col = find_column(df, "siruta", "cod_siruta")
    risk_col = find_column(df, "risc_abandon_scolar", "risc_abandon",
                           "abandon_scolar", "dropout_risk", "i_education")
    if not all([siruta_col, risk_col]):
        raise ValueError(f"[education] Could not identify required columns in {path}.")

    reg = pd.DataFrame({
        "siruta": df[siruta_col].map(normalize_siruta),
        "i_education": pd.to_numeric(df[risk_col], errors="coerce").clip(0, 1),
    }).dropna(subset=["siruta"])
    reg["siruta"] = reg["siruta"].astype(int)

    gdf = gdf.merge(reg, on="siruta", how="left")
    print(f"[education] Merged MATE/SIIIR risk for {reg['siruta'].nunique()} UATs.")
    return gdf

# =============================================================================
# 5. VECTORIZED MERGING, IMPUTATION & SCORING
# =============================================================================

def impute_missing(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Fill missing rural indicators with conservative county-median
    estimations (national median as final fallback)."""
    for col in ["i_sanitation", "i_energy", "i_education", "i_marginalization"]:
        if col not in gdf.columns:
            gdf[col] = pd.NA
        gdf[col] = pd.to_numeric(gdf[col], errors="coerce")
        county_med = gdf.groupby("county")[col].transform("median")
        national_med = gdf[col].median()
        gdf[col] = gdf[col].fillna(county_med).fillna(national_med).fillna(0.0).clip(0, 1)
    if "households_total" not in gdf.columns:
        gdf["households_total"] = 0
    gdf["households_total"] = pd.to_numeric(gdf["households_total"], errors="coerce").fillna(0).astype(int)
    if "population" not in gdf.columns:
        gdf["population"] = (gdf["households_total"] * 3).astype(int)  # ~3 pers./household
    return gdf


def compute_rvi(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """rvi_score = (0.30*i_sanitation + 0.30*i_energy + 0.25*i_education
                  + 0.15*i_marginalization) * 100"""
    gdf["rvi_score"] = (
        W_SANITATION * gdf["i_sanitation"]
        + W_ENERGY * gdf["i_energy"]
        + W_EDUCATION * gdf["i_education"]
        + W_MARGINALIZATION * gdf["i_marginalization"]
    ) * 100
    gdf["rvi_score"] = gdf["rvi_score"].round(2)

    def tier(score: float) -> str:
        if score >= TIER_CRITICAL:
            return "CRITICAL"
        if score >= TIER_HIGH:
            return "HIGH"
        return "MODERATE"

    gdf["priority_tier"] = gdf["rvi_score"].map(tier)
    return gdf


def export_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Export production-ready GeoJSON with a size budget check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = ["siruta", "uat_name", "county", "population", "households_total",
            "i_sanitation", "i_energy", "i_education", "i_marginalization",
            "rvi_score", "priority_tier", "geometry"]
    out = gdf[[c for c in keep if c in gdf.columns]].copy()
    out.to_file(path, driver="GeoJSON", encoding="utf-8")
    size = path.stat().st_size
    print(f"[export] Wrote {path} ({size / 1024 / 1024:.2f} MB, {len(out)} features)")
    if size > MAX_OUTPUT_BYTES:
        print(f"[export] WARNING: output exceeds 15 MB web budget — "
              f"consider raising simplify tolerance above {SIMPLIFY_TOLERANCE}.")


def print_top10(gdf: gpd.GeoDataFrame) -> None:
    """Terminal summary of the top 10 most critical UATs in Romania."""
    top = gdf.nlargest(10, "rvi_score")[
        ["siruta", "uat_name", "county", "rvi_score", "priority_tier",
         "i_sanitation", "i_energy", "i_education"]
    ]
    print("\n=== TOP 10 MOST CRITICAL UATs (Romania) ===")
    print(top.to_string(index=False))
    print(f"\nTier distribution: {gdf['priority_tier'].value_counts().to_dict()}")

# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="PSAN Radar real-data ingestion pipeline")
    parser.add_argument("--boundaries", default=str(LOCAL_BOUNDARIES_FALLBACK),
                        help="Local fallback UAT boundaries GeoJSON")
    parser.add_argument("--ins", default=str(DATA_DIR / "ins_rpl2021_sanitation.csv"),
                        help="INS RPL 2021 sanitation CSV")
    parser.add_argument("--energy", default=str(DATA_DIR / "offgrid_registry.csv"),
                        help="Ministry of Energy off-grid registry CSV")
    parser.add_argument("--education", default=str(DATA_DIR / "mate_dropout.csv"),
                        help="MATE/SIIIR dropout risk CSV")
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args()

    gdf = fetch_uat_boundaries(Path(args.boundaries))
    gdf = standardize_boundaries(gdf)

    ins = parse_ins_sanitation(args.ins)
    if len(ins):
        gdf = gdf.merge(ins, on="siruta", how="left")

    gdf = merge_energy_poverty(gdf, args.energy)
    gdf = merge_education_risk(gdf, args.education)
    gdf = impute_missing(gdf)
    gdf = compute_rvi(gdf)

    export_geojson(gdf, Path(args.output))
    print_top10(gdf)


if __name__ == "__main__":
    main()
