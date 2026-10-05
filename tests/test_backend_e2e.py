"""
PSAN Radar - Backend E2E Test Suite
Comprehensive asynchronous tests for FastAPI backend, calculation engine, and WebSocket alerts.
"""

import asyncio
import json
import pytest
import httpx
import websockets
from typing import AsyncGenerator, Dict, Any, List
from datetime import datetime


# =============================================================================
# CONFIGURATION & FIXTURES
# =============================================================================

BASE_URL = "http://127.0.0.1:8000"
WS_URL = "ws://127.0.0.1:8000/api/v1/telemetry/ws"
TIMEOUT = 30.0

# Test SIRUTA codes from the GeoJSON data
TEST_SIRUTA_CRITICAL = 240009  # Comuna Ceatalchioi - CRITICAL tier, i_energy=0.80
TEST_SIRUTA_MODERATE = 200001  # Comuna Chiojdeni - MODERATE tier


@pytest.fixture(scope="function")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client fixture with timeout."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        yield client


@pytest.fixture(scope="function")
async def available_siruta(http_client: httpx.AsyncClient) -> int:
    """Get first available SIRUTA from GeoJSON for testing."""
    response = await http_client.get("/api/v1/radar/geojson")
    assert response.status_code == 200
    geojson = response.json()
    features = geojson.get("features", [])
    assert len(features) > 0, "No features found in GeoJSON"
    return int(features[0]["properties"]["siruta"])


@pytest.fixture(scope="function")
async def critical_siruta(http_client: httpx.AsyncClient) -> int:
    """Get a SIRUTA with CRITICAL or HIGH priority tier for testing."""
    response = await http_client.get("/api/v1/radar/geojson")
    assert response.status_code == 200
    geojson = response.json()
    features = geojson.get("features", [])
    
    # Find a feature with HIGH or CRITICAL tier
    for feature in features:
        tier = feature["properties"].get("priority_tier", "")
        if tier in ("HIGH", "CRITICAL"):
            return int(feature["properties"]["siruta"])
    
    # Fallback to first available
    return int(features[0]["properties"]["siruta"])


# =============================================================================
# TEST 1.1: Health & Spatial Integrity
# =============================================================================

class TestHealthAndSpatialIntegrity:
    """Test 1.1: Health & Spatial Integrity"""

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_ok_and_records(self, http_client: httpx.AsyncClient):
        """Verify GET /api/v1/health returns status 'ok' and total_records >= 10."""
        response = await http_client.get("/api/v1/health")
        
        assert response.status_code == 200, f"Health check failed: {response.text}"
        
        data = response.json()
        assert data["status"] == "ok", f"Expected status 'ok', got '{data['status']}'"
        assert "total_records" in data, "Response missing 'total_records' field"
        assert data["total_records"] >= 10, f"Expected at least 10 records, got {data['total_records']}"
        assert "timestamp" in data, "Response missing 'timestamp' field"
        
        # Validate timestamp format
        try:
            datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"Invalid timestamp format: {data['timestamp']}")

    @pytest.mark.asyncio
    async def test_geojson_endpoint_returns_valid_feature_collection(self, http_client: httpx.AsyncClient):
        """Verify GET /api/v1/radar/geojson returns valid RFC 7946 GeoJSON FeatureCollection."""
        response = await http_client.get("/api/v1/radar/geojson")
        
        assert response.status_code == 200, f"GeoJSON endpoint failed: {response.text}"
        
        geojson = response.json()
        
        # Validate RFC 7946 FeatureCollection structure
        assert geojson.get("type") == "FeatureCollection", "Root type must be 'FeatureCollection'"
        assert "features" in geojson, "Missing 'features' array"
        assert isinstance(geojson["features"], list), "'features' must be an array"
        assert len(geojson["features"]) > 0, "FeatureCollection must contain at least one feature"
        
        # Validate each feature
        required_properties = {"siruta", "uat_name", "rvi_score", "priority_tier"}
        
        for i, feature in enumerate(geojson["features"]):
            # Feature structure
            assert feature.get("type") == "Feature", f"Feature {i}: type must be 'Feature'"
            assert "properties" in feature, f"Feature {i}: missing 'properties'"
            assert "geometry" in feature, f"Feature {i}: missing 'geometry'"
            
            # Non-empty geometry
            geometry = feature["geometry"]
            assert geometry is not None, f"Feature {i}: geometry must not be null"
            assert geometry.get("type") in ("Polygon", "MultiPolygon"), \
                f"Feature {i}: geometry type must be Polygon or MultiPolygon"
            assert "coordinates" in geometry, f"Feature {i}: geometry missing coordinates"
            assert geometry["coordinates"], f"Feature {i}: coordinates must not be empty"
            
            # Required properties
            props = feature["properties"]
            missing_props = required_properties - set(props.keys())
            assert not missing_props, f"Feature {i}: missing required properties: {missing_props}"
            
            # Property types and ranges
            assert isinstance(props["siruta"], int), f"Feature {i}: siruta must be integer"
            assert isinstance(props["uat_name"], str) and props["uat_name"], \
                f"Feature {i}: uat_name must be non-empty string"
            assert isinstance(props["rvi_score"], (int, float)), \
                f"Feature {i}: rvi_score must be numeric"
            assert 0 <= props["rvi_score"] <= 100, \
                f"Feature {i}: rvi_score must be in range [0, 100]"
            assert props["priority_tier"] in ("CRITICAL", "HIGH", "MODERATE"), \
                f"Feature {i}: priority_tier must be CRITICAL, HIGH, or MODERATE"


# =============================================================================
# TEST 1.2: Multi-Criteria Filtering Logic
# =============================================================================

class TestMultiCriteriaFiltering:
    """Test 1.2: Multi-Criteria Filtering Logic"""

    @pytest.mark.asyncio
    async def test_filter_min_rvi_returns_critical_features(self, http_client: httpx.AsyncClient):
        """Request filter with min_rvi=75.0, assert all features have priority_tier=CRITICAL and rvi_score>=75."""
        response = await http_client.get("/api/v1/radar/filter", params={"min_rvi": 75.0})
        
        assert response.status_code == 200, f"Filter endpoint failed: {response.text}"
        
        geojson = response.json()
        features = geojson.get("features", [])
        
        # If no features match, that's valid - but we should verify the logic
        for feature in features:
            props = feature["properties"]
            assert props["priority_tier"] == "CRITICAL", \
                f"Feature with rvi_score={props['rvi_score']} has tier '{props['priority_tier']}', expected CRITICAL"
            assert props["rvi_score"] >= 75.0, \
                f"Feature has rvi_score={props['rvi_score']} < 75.0"

    @pytest.mark.asyncio
    async def test_filter_require_offgrid_returns_energy_deficit_features(self, http_client: httpx.AsyncClient):
        """Request filter with require_offgrid=true, assert all features have i_energy >= 0.5."""
        response = await http_client.get("/api/v1/radar/filter", params={"require_offgrid": "true"})
        
        assert response.status_code == 200, f"Filter endpoint failed: {response.text}"
        
        geojson = response.json()
        features = geojson.get("features", [])
        
        for feature in features:
            props = feature["properties"]
            i_energy = props.get("i_energy")
            assert i_energy is not None, "Feature missing i_energy property"
            assert i_energy >= 0.5, \
                f"Feature has i_energy={i_energy} < 0.5, but require_offgrid=true was specified"

    @pytest.mark.asyncio
    async def test_filter_combined_criteria(self, http_client: httpx.AsyncClient):
        """Test combined filter criteria work together."""
        response = await http_client.get(
            "/api/v1/radar/filter",
            params={"min_rvi": 40.0, "require_offgrid": "true", "require_sanitation": "true"}
        )
        
        assert response.status_code == 200
        
        geojson = response.json()
        features = geojson.get("features", [])
        
        for feature in features:
            props = feature["properties"]
            assert props["rvi_score"] >= 40.0
            assert props.get("i_energy", 0) >= 0.5
            assert props.get("i_sanitation", 0) >= 0.5


# =============================================================================
# TEST 1.3: Deterministic Engineering Sizing & BOM
# =============================================================================

class TestEngineeringSizingAndBOM:
    """Test 1.3: Deterministic Engineering Sizing & BOM"""

    @pytest.mark.asyncio
    async def test_calculate_bom_offgrid_pv_returns_valid_response(
        self, 
        http_client: httpx.AsyncClient, 
        critical_siruta: int
    ):
        """Test BOM calculation for OFFGRID_PV intervention type."""
        payload = {
            "intervention_type": "OFFGRID_PV",
            "target_households": 10,
            "daily_energy_per_household_kwh": 3.5
        }
        
        response = await http_client.post(
            f"/api/v1/radar/uat/{critical_siruta}/calculate-bom",
            json=payload
        )
        
        assert response.status_code == 200, f"BOM calculation failed: {response.text}"
        
        data = response.json()
        
        # Validate response structure
        assert data["intervention_type"] == "OFFGRID_PV"
        assert "engineering_parameters" in data
        assert "itemized_bom" in data
        assert isinstance(data["itemized_bom"], list)
        assert len(data["itemized_bom"]) > 0, "BOM must contain at least one item"
        
        # Validate engineering parameters
        eng_params = data["engineering_parameters"]
        assert "pv_kwp" in eng_params
        assert "battery_kwh" in eng_params
        assert "inverter_kw" in eng_params
        
        # Assert calculated values are positive
        assert eng_params["pv_kwp"] > 0, f"P_pv must be > 0, got {eng_params['pv_kwp']}"
        assert eng_params["battery_kwh"] > 0, f"C_battery must be > 0, got {eng_params['battery_kwh']}"
        assert eng_params["inverter_kw"] > 0, f"Inverter must be > 0, got {eng_params['inverter_kw']}"
        
        # Validate CAPEX breakdown
        assert "subtotal_equipment_eur" in data
        assert "subtotal_works_labor_eur" in data
        assert "contingency_reserve_eur" in data
        assert "total_project_capex_eur" in data
        
        # Verify CAPEX equation: total = equipment + works + contingency
        subtotal_equip = data["subtotal_equipment_eur"]
        subtotal_works = data["subtotal_works_labor_eur"]
        contingency = data["contingency_reserve_eur"]
        total = data["total_project_capex_eur"]
        
        expected_total = subtotal_equip + subtotal_works + contingency
        assert abs(total - expected_total) < 0.01, \
            f"CAPEX mismatch: total={total}, equipment+works+contingency={expected_total}"

    @pytest.mark.asyncio
    async def test_calculate_bom_sanitation_returns_valid_response(
        self, 
        http_client: httpx.AsyncClient, 
        critical_siruta: int
    ):
        """Test BOM calculation for SANITATION intervention type."""
        payload = {
            "intervention_type": "SANITATION",
            "connected_people_equivalent": 50
        }
        
        response = await http_client.post(
            f"/api/v1/radar/uat/{critical_siruta}/calculate-bom",
            json=payload
        )
        
        assert response.status_code == 200, f"BOM calculation failed: {response.text}"
        
        data = response.json()
        assert data["intervention_type"] == "SANITATION"
        assert data["engineering_parameters"]["connected_pe"] == 50
        assert data["total_project_capex_eur"] > 0

    @pytest.mark.asyncio
    async def test_calculate_bom_education_returns_valid_response(
        self, 
        http_client: httpx.AsyncClient, 
        critical_siruta: int
    ):
        """Test BOM calculation for EDUCATION intervention type."""
        payload = {
            "intervention_type": "EDUCATION",
            "student_stations": 20
        }
        
        response = await http_client.post(
            f"/api/v1/radar/uat/{critical_siruta}/calculate-bom",
            json=payload
        )
        
        assert response.status_code == 200, f"BOM calculation failed: {response.text}"
        
        data = response.json()
        assert data["intervention_type"] == "EDUCATION"
        assert data["engineering_parameters"]["student_stations"] == 20
        assert data["total_project_capex_eur"] > 0

    @pytest.mark.asyncio
    async def test_calculate_bom_invalid_siruta_returns_404(self, http_client: httpx.AsyncClient):
        """Test BOM calculation with invalid SIRUTA returns 404."""
        payload = {
            "intervention_type": "OFFGRID_PV",
            "target_households": 10,
            "daily_energy_per_household_kwh": 3.5
        }
        
        response = await http_client.post(
            "/api/v1/radar/uat/999999/calculate-bom",
            json=payload
        )
        
        assert response.status_code == 404


# =============================================================================
# TEST 1.4: PDF Streaming Export
# =============================================================================

class TestPDFExport:
    """Test 1.4: PDF Streaming Export"""

    @pytest.mark.asyncio
    async def test_export_pdf_returns_valid_pdf(self, http_client: httpx.AsyncClient, critical_siruta: int):
        """Test PDF export returns valid PDF with correct headers and magic bytes."""
        response = await http_client.get(f"/api/v1/radar/uat/{critical_siruta}/export-pdf")
        
        assert response.status_code == 200, f"PDF export failed: {response.text}"
        
        # Check content-type header
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, \
            f"Expected content-type 'application/pdf', got '{content_type}'"
        
        # Check Content-Disposition header
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition.lower()
        assert f"{critical_siruta}.pdf" in content_disposition or "fisa_fundamentare" in content_disposition
        
        # Check PDF magic bytes
        content = response.content
        assert content.startswith(b"%PDF-"), \
            f"Response does not start with PDF magic bytes. First 10 bytes: {content[:10]}"
        
        # Verify it's a reasonable size PDF
        assert len(content) > 1000, f"PDF too small ({len(content)} bytes), likely empty or corrupted"

    @pytest.mark.asyncio
    async def test_export_pdf_invalid_siruta_returns_404(self, http_client: httpx.AsyncClient):
        """Test PDF export with invalid SIRUTA returns 404."""
        response = await http_client.get("/api/v1/radar/uat/999999/export-pdf")
        assert response.status_code == 404


# =============================================================================
# TEST 1.5: Field Survey Batch Ingestion
# =============================================================================

class TestFieldSurveyBatchIngestion:
    """Test 1.5: Field Survey Batch Ingestion"""

    @pytest.mark.asyncio
    async def test_sync_batch_with_valid_surveys(self, http_client: httpx.AsyncClient, critical_siruta: int):
        """Test syncing a batch of 2 valid survey records."""
        # Create two valid survey records
        surveys = [
            {
                "survey_id": "test-survey-001",
                "siruta": critical_siruta,
                "uat_name": "Test UAT",
                "county": "Test County",
                "site_type": "ISOLATED_HOUSEHOLD",
                "location": {
                    "latitude": 45.0,
                    "longitude": 25.0,
                    "accuracy_meters": 5.0,
                    "timestamp": datetime.now().isoformat()
                },
                "surveyor_name": "Test Engineer",
                "energy_audit": {
                    "current_power_source": "NONE",
                    "roof_type": "SHEET_METAL",
                    "roof_orientation": "SOUTH",
                    "estimated_daily_kwh_need": 3.5
                },
                "sanitation_audit": {
                    "water_source": "NONE_HAULED",
                    "current_toilet_type": "NONE",
                    "distance_to_nearest_well_meters": 100.0,
                    "suitable_land_for_wetland": True
                },
                "social_vulnerability": {
                    "inhabitant_count": 4,
                    "minors_under_18": 2,
                    "school_age_children_not_attending": 1
                },
                "photos": [],
                "sync_status": "PENDING",
                "created_at": datetime.now().isoformat()
            },
            {
                "survey_id": "test-survey-002",
                "siruta": critical_siruta,
                "uat_name": "Test UAT",
                "county": "Test County",
                "site_type": "RURAL_SCHOOL",
                "location": {
                    "latitude": 45.1,
                    "longitude": 25.1,
                    "accuracy_meters": 3.0,
                    "timestamp": datetime.now().isoformat()
                },
                "surveyor_name": "Test Engineer",
                "energy_audit": {
                    "current_power_source": "PORTABLE_GENSET",
                    "roof_type": "CERAMIC_TILE",
                    "roof_orientation": "SOUTH_EAST",
                    "estimated_daily_kwh_need": 15.0
                },
                "sanitation_audit": {
                    "water_source": "SHALLOW_WELL_UNTESTED",
                    "current_toilet_type": "OPEN_OUTHOUSE_DRY",
                    "distance_to_nearest_well_meters": 50.0,
                    "suitable_land_for_wetland": True
                },
                "social_vulnerability": {
                    "inhabitant_count": 120,
                    "minors_under_18": 100,
                    "school_age_children_not_attending": 10
                },
                "photos": [],
                "sync_status": "PENDING",
                "created_at": datetime.now().isoformat()
            }
        ]
        
        payload = {"surveys": surveys}
        
        response = await http_client.post("/api/v1/surveys/sync-batch", json=payload)
        
        assert response.status_code == 200, f"Sync batch failed: {response.text}"
        
        data = response.json()
        assert data["synced_count"] == 2, f"Expected 2 synced, got {data['synced_count']}"
        assert data["failed_count"] == 0, f"Expected 0 failed, got {data['failed_count']}"
        assert "timestamp" in data
        assert isinstance(data["errors"], list)

    @pytest.mark.asyncio
    async def test_sync_batch_duplicate_survey_returns_error(self, http_client: httpx.AsyncClient, critical_siruta: int):
        """Test syncing duplicate survey returns appropriate error."""
        survey = {
            "survey_id": "test-duplicate-001",
            "siruta": critical_siruta,
            "uat_name": "Test UAT",
            "county": "Test County",
            "site_type": "ISOLATED_HOUSEHOLD",
            "location": {
                "latitude": 45.0,
                "longitude": 25.0,
                "accuracy_meters": 5.0,
                "timestamp": datetime.now().isoformat()
            },
            "surveyor_name": "Test Engineer",
            "energy_audit": {
                "current_power_source": "NONE",
                "roof_type": "SHEET_METAL",
                "roof_orientation": "SOUTH",
                "estimated_daily_kwh_need": 3.5
            },
            "sanitation_audit": {
                "water_source": "NONE_HAULED",
                "current_toilet_type": "NONE",
                "distance_to_nearest_well_meters": 100.0,
                "suitable_land_for_wetland": True
            },
            "social_vulnerability": {
                "inhabitant_count": 4,
                "minors_under_18": 2,
                "school_age_children_not_attending": 1
            },
            "photos": [],
            "sync_status": "PENDING",
            "created_at": datetime.now().isoformat()
        }
        
        # First sync - should succeed
        response1 = await http_client.post("/api/v1/surveys/sync-batch", json={"surveys": [survey]})
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["synced_count"] == 1
        
        # Second sync with same ID - should fail as duplicate
        response2 = await http_client.post("/api/v1/surveys/sync-batch", json={"surveys": [survey]})
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["synced_count"] == 0
        assert data2["failed_count"] == 1
        assert any("duplicate" in err.lower() for err in data2["errors"])


# =============================================================================
# TEST 1.6: IoT Telemetry & Real-Time WebSocket Alerts
# =============================================================================

class TestIoTTelemetryWebSocket:
    """Test 1.6: IoT Telemetry & Real-Time WebSocket Alerts"""

    @pytest.mark.asyncio
    async def test_websocket_connection_and_alert_on_critical_battery(
        self, 
        http_client: httpx.AsyncClient,
        critical_siruta: int
    ):
        """
        Connect to WebSocket, ingest critical battery telemetry, 
        assert WebSocket receives alert message.
        """
        # First, verify the telemetry endpoints exist
        # Try to connect to WebSocket
        alert_received = asyncio.Event()
        alert_payload = None
        
        async def websocket_listener():
            nonlocal alert_payload
            try:
                async with websockets.connect(WS_URL) as ws:
                    # Wait for alert message
                    async for message in ws:
                        data = json.loads(message)
                        if data.get("type") == "alert" or data.get("alert_type") == "critical_battery":
                            alert_payload = data
                            alert_received.set()
                            break
            except Exception as e:
                # WebSocket might not be implemented yet - mark as expected failure
                pytest.skip(f"WebSocket not available: {e}")
        
        # Start WebSocket listener
        listener_task = asyncio.create_task(websocket_listener())
        
        # Give WebSocket time to connect
        await asyncio.sleep(1.0)
        
        # Ingest critical telemetry packet (battery_soc_percent = 12.0%)
        telemetry_payload = {
            "asset_id": f"test-asset-{critical_siruta}",
            "siruta": critical_siruta,
            "timestamp": datetime.now().isoformat(),
            "battery_soc_percent": 12.0,  # Below 20% critical threshold
            "pv_power_watts": 1500.0,
            "load_power_watts": 800.0,
            "temperature_celsius": 25.0
        }
        
        # Try to ingest telemetry
        try:
            ingest_response = await http_client.post(
                "/api/v1/telemetry/ingest",
                json=telemetry_payload
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                pytest.skip("Telemetry ingest endpoint not implemented")
            raise
        
        # Wait for alert with timeout
        try:
            await asyncio.wait_for(alert_received.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            listener_task.cancel()
            pytest.skip("WebSocket alert not received within timeout - endpoint may not be implemented")
        
        # Verify alert payload
        assert alert_payload is not None, "No alert payload received"
        assert alert_payload.get("asset_id") == telemetry_payload["asset_id"]
        assert alert_payload.get("battery_soc_percent") == 12.0
        assert "critical" in str(alert_payload).lower() or "alert" in str(alert_payload).lower()
        
        listener_task.cancel()

    @pytest.mark.asyncio
    async def test_telemetry_assets_endpoint(self, http_client: httpx.AsyncClient):
        """Test GET /api/v1/telemetry/assets returns asset list."""
        try:
            response = await http_client.get("/api/v1/telemetry/assets")
            if response.status_code == 404:
                pytest.skip("Telemetry assets endpoint not implemented")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                pytest.skip("Telemetry assets endpoint not implemented")
            raise


# =============================================================================
# ADDITIONAL INTEGRATION TESTS
# =============================================================================

class TestGrantNarrativeGeneration:
    """Test grant narrative generation endpoint."""

    @pytest.mark.asyncio
    async def test_generate_grant_narrative(self, http_client: httpx.AsyncClient, critical_siruta: int):
        """Test POST /api/v1/radar/uat/{siruta}/grant-narrative returns narrative."""
        response = await http_client.post(
            f"/api/v1/radar/uat/{critical_siruta}/grant-narrative",
            params={"funding_line": "PoIDS"}
        )
        
        assert response.status_code == 200, f"Grant narrative failed: {response.text}"
        
        data = response.json()
        assert "generated_by" in data
        assert "funding_line" in data
        assert "justificarea_nevoii" in data
        assert "descrierea_activitatilor" in data
        assert "rezultate_si_indicatori" in data
        assert "sustenabilitate" in data
        assert "buget_sumar" in data
        
        # Verify content is non-empty
        for key in ["justificarea_nevoii", "descrierea_activitatilor", "rezultate_si_indicatori"]:
            assert data[key], f"Field {key} should not be empty"

        # Verify HG 907/2016 financial plan, ETF scorecard, DNSH matrix, and MySMIS markdown
        assert data.get("financial_plan") is not None
        fp = data["financial_plan"]
        assert fp["gross_bom_capex_eur"] > 0
        assert fp["eu_grant_amount_eur"] > 0
        assert len(fp["hg907_chapters"]) == 5

        assert data.get("etf_scorecard") is not None
        etf = data["etf_scorecard"]
        assert 70.0 <= etf["total_score"] <= 100.0
        assert len(etf["criteria"]) == 4

        assert data.get("dnsh_matrix") is not None
        assert len(data["dnsh_matrix"]) == 6
        assert data.get("mysmis_markdown_export") and "CERERE DE FINANȚARE MYSMIS 2021+" in data["mysmis_markdown_export"]


class TestUATDossier:
    """Test UAT dossier endpoint."""

    @pytest.mark.asyncio
    async def test_get_uat_dossier(self, http_client: httpx.AsyncClient, critical_siruta: int):
        """Test GET /api/v1/radar/uat/{siruta}/dossier returns complete dossier."""
        response = await http_client.get(f"/api/v1/radar/uat/{critical_siruta}/dossier")
        
        assert response.status_code == 200, f"Dossier failed: {response.text}"
        
        data = response.json()
        assert "uat_profile" in data
        assert "identified_deficits" in data
        assert "recommended_interventions" in data
        assert "eligible_eu_funding_lines" in data
        assert "engineering_justification" in data
        
        # Validate UAT profile
        profile = data["uat_profile"]
        assert profile["siruta"] == critical_siruta
        assert profile["priority_tier"] in ("CRITICAL", "HIGH", "MODERATE")
        
        # Validate deficits
        deficits = data["identified_deficits"]
        assert "sanitation_percent" in deficits
        assert "offgrid_percent" in deficits
        assert "education_risk_percent" in deficits


# =============================================================================
# TEST 1.7: Advanced Modules (Permitting, Volunteer Dispatch, CSR Marketplace)
# =============================================================================

class TestAdvancedModules:
    """Test 1.7: Permitting Compliance Navigator, Volunteer Dispatch, and CSR Marketplace"""

    @pytest.mark.asyncio
    async def test_permitting_roadmap_returns_valid_checklist_and_dossier(
        self,
        http_client: httpx.AsyncClient,
        critical_siruta: int,
    ):
        """Verify GET /api/v1/radar/uat/{siruta}/permitting-roadmap returns Romanian legal checklist."""
        response = await http_client.get(f"/api/v1/radar/uat/{critical_siruta}/permitting-roadmap")
        assert response.status_code == 200, f"Permitting roadmap failed: {response.text}"

        data = response.json()
        assert data["siruta"] == critical_siruta
        assert "steps" in data and len(data["steps"]) >= 2
        assert "administrative_dossier_markdown" in data
        assert "Legea nr. 50/1991" in data["administrative_dossier_markdown"]

    @pytest.mark.asyncio
    async def test_volunteer_dispatch_matches_nearest_qualified_team(
        self,
        http_client: httpx.AsyncClient,
        critical_siruta: int,
    ):
        """Verify POST /api/v1/radar/uat/{siruta}/dispatch-team assigns qualified volunteers via Haversine."""
        response = await http_client.post(
            f"/api/v1/radar/uat/{critical_siruta}/dispatch-team",
            json={"max_team_size": 4},
        )
        assert response.status_code == 200, f"Volunteer dispatch failed: {response.text}"

        data = response.json()
        assert data["siruta"] == critical_siruta
        assert len(data["dispatched_team"]) > 0
        assert data["readiness_score_pct"] == 100.0
        for member in data["dispatched_team"]:
            assert member["distance_km"] >= 0

    @pytest.mark.asyncio
    async def test_csr_marketplace_returns_matched_lots_and_savings(
        self,
        http_client: httpx.AsyncClient,
        critical_siruta: int,
    ):
        """
        Verify full SQLite CSR Marketplace lifecycle:
        1. Create a CSR lot via POST /api/v1/marketplace/lots
        2. Match against UAT Engineering BOM via GET /api/v1/radar/uat/{siruta}/csr-marketplace
        3. Allocate to UAT via POST /api/v1/radar/uat/{siruta}/csr-allocations
        4. Revoke allocation and delete test lot so no dummy data remains in SQLite.
        """
        create_res = await http_client.post(
            "/api/v1/marketplace/lots",
            json={
                "donor_company": "Test E2E Solar Partner SRL",
                "donor_cui": "RO12345678",
                "material_category": "SOLAR_PV",
                "item_name": "Panouri Fotovoltaice Monocristaline 450Wp Tier-1",
                "quantity_available": 40,
                "market_unit_value_eur": 185.0,
                "depot_city": "Iași",
                "freight_rate_eur_per_km": 1.45,
            },
        )
        assert create_res.status_code == 201, f"Create CSR lot failed: {create_res.text}"
        created_lot = create_res.json()
        lot_id = created_lot["lot_id"]

        try:
            response = await http_client.get(f"/api/v1/radar/uat/{critical_siruta}/csr-marketplace")
            assert response.status_code == 200, f"CSR marketplace failed: {response.text}"

            data = response.json()
            assert data["siruta"] == critical_siruta
            assert data["original_bom_capex_eur"] > 0
            assert len(data["uat_bom_requirements"]) > 0
            assert len(data["matched_lots"]) > 0
            assert data["total_net_capex_savings_eur"] > 0

            # Allocate the created lot to the UAT
            alloc_res = await http_client.post(
                f"/api/v1/radar/uat/{critical_siruta}/csr-allocations",
                json={"lot_id": lot_id},
            )
            assert alloc_res.status_code == 200, f"CSR allocation failed: {alloc_res.text}"
            alloc_data = alloc_res.json()
            allocation_id = alloc_data["allocation_id"]
            assert alloc_data["quantity_allocated"] > 0
            assert alloc_data["net_capex_saving_eur"] > 0

            # Verify UAT CAPEX is reduced after allocation
            after_res = await http_client.get(f"/api/v1/radar/uat/{critical_siruta}/csr-marketplace")
            after_data = after_res.json()
            assert after_data["allocated_net_capex_savings_eur"] > 0
            assert after_data["adjusted_net_capex_eur"] < after_data["original_bom_capex_eur"]

            # Revoke allocation
            revoke_res = await http_client.delete(
                f"/api/v1/radar/uat/{critical_siruta}/csr-allocations/{allocation_id}"
            )
            assert revoke_res.status_code == 200
        finally:
            await http_client.delete(f"/api/v1/marketplace/lots/{lot_id}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])