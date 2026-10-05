"""
PSAN Radar — Phase 10: Real-Time IoT Telemetry & WebSocket Alert Engine
=======================================================================

Provides real-time monitoring of deployed off-grid PV/BESS kits, constructed
wetlands, and solar EduPod hubs across vulnerable Romanian UATs.
Broadcasts instant WebSocket alerts when:
  - Battery State of Charge (SoC) drops below 20% LiFePO4 safety reserve
  - Battery/inverter enclosure temperature exceeds 45.0 °C
  - Constructed wetland hydraulic water level exceeds 85.0 cm (overflow risk)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/telemetry", tags=["IoT Telemetry & Alerts"])

CRITICAL_SOC_THRESHOLD = 20.0      # % LiFePO4 minimum safe reserve
HIGH_TEMP_THRESHOLD_C = 45.0       # °C thermal runaway warning threshold
WETLAND_OVERFLOW_CM = 85.0         # cm HSSF gravel bed surcharge limit
CO2_FACTOR_KG_PER_KWH = 0.265      # kg CO2 avoided per kWh (Romanian grid factor)


# =============================================================================
# PYDANTIC SCHEMAS (Pydantic v2)
# =============================================================================

class SolarTelemetryPacket(BaseModel):
    asset_id: str = Field(..., min_length=1, description="Unique identifier of the deployed solar/BESS node")
    siruta: int = Field(..., ge=1000, le=999999, description="Romanian SIRUTA code of the host UAT")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 packet timestamp",
    )
    battery_soc_percent: float = Field(..., ge=0.0, le=100.0, description="Battery State of Charge (%)")
    pv_power_watts: float = Field(0.0, ge=0.0, description="Instantaneous PV generation (W)")
    load_power_watts: float = Field(0.0, ge=0.0, description="Instantaneous household/community load (W)")
    temperature_celsius: float = Field(22.0, ge=-40.0, le=85.0, description="Battery enclosure temperature (°C)")


class WaterTelemetryPacket(BaseModel):
    asset_id: str = Field(..., min_length=1, description="Unique identifier of the constructed wetland node")
    siruta: int = Field(..., ge=1000, le=999999, description="Romanian SIRUTA code of the host UAT")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 packet timestamp",
    )
    influent_flow_m3_day: float = Field(5.0, ge=0.0, description="Daily hydraulic flow rate (m³/day)")
    water_level_cm: float = Field(52.0, ge=0.0, le=150.0, description="Sub-surface bed water level (cm)")
    effluent_bod5_mg_l: float = Field(18.0, ge=0.0, description="Effluent BOD5 concentration (mg/L, NTPA-001 <= 25)")
    water_temperature_celsius: float = Field(11.5, ge=-10.0, le=45.0, description="Wetland water temperature (°C)")


class TelemetryIngestPayload(BaseModel):
    asset_id: str = Field(..., min_length=1, description="Unique identifier of the deployed telemetry node")
    siruta: int = Field(..., ge=1000, le=999999, description="Romanian SIRUTA code of the host UAT")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 packet timestamp",
    )
    battery_soc_percent: float = Field(80.0, ge=0.0, le=100.0, description="Battery State of Charge (%)")
    pv_power_watts: float = Field(0.0, ge=0.0, description="Instantaneous PV generation (W)")
    load_power_watts: float = Field(0.0, ge=0.0, description="Instantaneous household/community load (W)")
    temperature_celsius: float = Field(22.0, ge=-40.0, le=85.0, description="Battery enclosure temperature (°C)")
    water_level_cm: Optional[float] = Field(None, ge=0.0, le=150.0, description="Optional wetland water level (cm)")
    influent_flow_m3_day: Optional[float] = Field(None, ge=0.0, description="Optional wetland daily treated flow (m³/day)")


class TelemetryAssetStatus(BaseModel):
    asset_id: str
    siruta: int
    uat_name: str
    county: str
    asset_type: str
    battery_soc_percent: float
    pv_power_watts: float
    load_power_watts: float
    temperature_celsius: float
    cumulative_kwh: float
    co2_avoided_kg: float
    treated_water_m3: float = 0.0
    status: str  # NOMINAL | WARNING | CRITICAL
    last_seen: str


class TelemetryAlert(BaseModel):
    type: str = "alert"
    alert_type: str = "critical_battery"
    severity: str = "CRITICAL"
    asset_id: str
    siruta: int
    battery_soc_percent: float
    pv_power_watts: float
    load_power_watts: float
    temperature_celsius: float
    message: str
    timestamp: str


class TelemetrySummaryResponse(BaseModel):
    active_assets_count: int
    total_kwh_generated: float
    co2_avoided_kg: float
    total_treated_water_m3: float
    critical_alerts_count: int
    active_alerts: List[TelemetryAlert]
    assets: List[TelemetryAssetStatus]
    timestamp: str


# =============================================================================
# IN-MEMORY STATE & WEBSOCKET CONNECTION MANAGER
# =============================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


INITIAL_ASSETS: Dict[str, Dict[str, Any]] = {
    "ewb-pv-240009-01": {
        "asset_id": "ewb-pv-240009-01",
        "siruta": 240009,
        "uat_name": "Comuna Ceatalchioi",
        "county": "Tulcea",
        "asset_type": "OFFGRID_PV_BESS_5KWP",
        "battery_soc_percent": 84.5,
        "pv_power_watts": 3420.0,
        "load_power_watts": 910.0,
        "temperature_celsius": 24.2,
        "cumulative_kwh": 4820.5,
        "co2_avoided_kg": round(4820.5 * CO2_FACTOR_KG_PER_KWH, 2),
        "treated_water_m3": 0.0,
        "status": "NOMINAL",
        "last_seen": _now_iso(),
    },
    "ewb-pv-210003-01": {
        "asset_id": "ewb-pv-210003-01",
        "siruta": 210003,
        "uat_name": "Comuna Pungești",
        "county": "Vaslui",
        "asset_type": "EDUPOD_SOLAR_HUB",
        "battery_soc_percent": 78.0,
        "pv_power_watts": 2890.0,
        "load_power_watts": 1150.0,
        "temperature_celsius": 23.1,
        "cumulative_kwh": 3610.0,
        "co2_avoided_kg": round(3610.0 * CO2_FACTOR_KG_PER_KWH, 2),
        "treated_water_m3": 0.0,
        "status": "NOMINAL",
        "last_seen": _now_iso(),
    },
    "ewb-pv-200001-01": {
        "asset_id": "ewb-pv-200001-01",
        "siruta": 200001,
        "uat_name": "Comuna Chiojdeni",
        "county": "Vrancea",
        "asset_type": "OFFGRID_PV_BESS_3KWP",
        "battery_soc_percent": 91.2,
        "pv_power_watts": 2150.0,
        "load_power_watts": 640.0,
        "temperature_celsius": 21.8,
        "cumulative_kwh": 2945.8,
        "co2_avoided_kg": round(2945.8 * CO2_FACTOR_KG_PER_KWH, 2),
        "treated_water_m3": 0.0,
        "status": "NOMINAL",
        "last_seen": _now_iso(),
    },
    "ewb-cw-210004-01": {
        "asset_id": "ewb-cw-210004-01",
        "siruta": 210004,
        "uat_name": "Comuna Băcești",
        "county": "Vaslui",
        "asset_type": "HSSF_CONSTRUCTED_WETLAND_50PE",
        "battery_soc_percent": 88.0,
        "pv_power_watts": 650.0,
        "load_power_watts": 180.0,
        "temperature_celsius": 19.5,
        "cumulative_kwh": 1223.7,
        "co2_avoided_kg": round(1223.7 * CO2_FACTOR_KG_PER_KWH, 2),
        "treated_water_m3": 1840.5,
        "status": "NOMINAL",
        "last_seen": _now_iso(),
    },
}

_assets_store: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in INITIAL_ASSETS.items()}
_alerts_history: List[TelemetryAlert] = []


class TelemetryConnectionManager:
    """Manages active WebSocket subscribers for real-time telemetry alerts."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast_json(self, payload: Dict[str, Any]) -> None:
        stale: List[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(payload)
            except Exception:
                stale.append(connection)
        for conn in stale:
            self.disconnect(conn)


manager = TelemetryConnectionManager()


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/assets", response_model=List[TelemetryAssetStatus])
async def list_telemetry_assets(siruta: Optional[int] = None) -> List[TelemetryAssetStatus]:
    """Return all monitored IoT telemetry assets, optionally filtered by SIRUTA."""
    assets = list(_assets_store.values())
    if siruta is not None:
        assets = [a for a in assets if a["siruta"] == siruta]
    return [TelemetryAssetStatus(**a) for a in assets]


@router.get("/summary", response_model=TelemetrySummaryResponse)
async def get_telemetry_summary() -> TelemetrySummaryResponse:
    """Return live aggregated energy, CO2 avoidance (0.265 kg CO2/kWh), and treated water metrics."""
    assets = [TelemetryAssetStatus(**a) for a in _assets_store.values()]
    total_kwh = round(sum(a.cumulative_kwh for a in assets), 2)
    total_co2 = round(total_kwh * CO2_FACTOR_KG_PER_KWH, 2)
    total_water = round(sum(a.treated_water_m3 for a in assets), 2)
    critical_alerts = [a for a in _alerts_history[-10:] if a.severity == "CRITICAL"]
    return TelemetrySummaryResponse(
        active_assets_count=len(assets),
        total_kwh_generated=total_kwh,
        co2_avoided_kg=total_co2,
        total_treated_water_m3=total_water,
        critical_alerts_count=len(critical_alerts),
        active_alerts=critical_alerts,
        assets=assets,
        timestamp=_now_iso(),
    )


@router.post("/ingest", status_code=status.HTTP_200_OK)
async def ingest_telemetry_packet(payload: TelemetryIngestPayload) -> Dict[str, Any]:
    """
    Ingest a real-time IoT telemetry packet from an off-grid solar/BESS or wetland node.
    Evaluates deterministic alert rules:
      1. battery_soc_percent < 20.0% -> critical_battery
      2. temperature_celsius > 45.0°C -> high_temperature
      3. water_level_cm > 85.0 cm -> wetland_overflow
    """
    existing = _assets_store.get(payload.asset_id)
    incremental_kwh = round((payload.pv_power_watts / 1000.0) * 0.25, 3)
    prev_kwh = existing["cumulative_kwh"] if existing else 1250.0
    new_kwh = round(prev_kwh + incremental_kwh, 2)
    new_co2 = round(new_kwh * CO2_FACTOR_KG_PER_KWH, 2)
    prev_water = existing.get("treated_water_m3", 0.0) if existing else 0.0
    inc_water = round((payload.influent_flow_m3_day or 0.0) / 96.0, 3)
    new_water = round(prev_water + inc_water, 2)

    is_low_soc = payload.battery_soc_percent < CRITICAL_SOC_THRESHOLD
    is_high_temp = payload.temperature_celsius > HIGH_TEMP_THRESHOLD_C
    is_overflow = payload.water_level_cm is not None and payload.water_level_cm > WETLAND_OVERFLOW_CM

    if is_low_soc or is_high_temp or is_overflow:
        node_status = "CRITICAL"
    elif payload.battery_soc_percent < 35.0:
        node_status = "WARNING"
    else:
        node_status = "NOMINAL"

    asset_record = {
        "asset_id": payload.asset_id,
        "siruta": payload.siruta,
        "uat_name": existing["uat_name"] if existing else f"UAT {payload.siruta}",
        "county": existing["county"] if existing else "România",
        "asset_type": existing["asset_type"] if existing else "OFFGRID_PV_BESS_KIT",
        "battery_soc_percent": payload.battery_soc_percent,
        "pv_power_watts": payload.pv_power_watts,
        "load_power_watts": payload.load_power_watts,
        "temperature_celsius": payload.temperature_celsius,
        "cumulative_kwh": new_kwh,
        "co2_avoided_kg": new_co2,
        "treated_water_m3": new_water,
        "status": node_status,
        "last_seen": payload.timestamp,
    }
    _assets_store[payload.asset_id] = asset_record

    alert_emitted: Optional[Dict[str, Any]] = None
    if is_low_soc or is_high_temp or is_overflow:
        if is_low_soc:
            alert_type = "critical_battery"
            msg = (
                f"CRITICAL BATTERY ALERT: Node {payload.asset_id} (SIRUTA {payload.siruta}) "
                f"SoC dropped to {payload.battery_soc_percent:.1f}% (< {CRITICAL_SOC_THRESHOLD:.0f}% LiFePO4 reserve)."
            )
        elif is_high_temp:
            alert_type = "high_temperature"
            msg = (
                f"CRITICAL THERMAL ALERT: Node {payload.asset_id} (SIRUTA {payload.siruta}) "
                f"enclosure temperature reached {payload.temperature_celsius:.1f}°C (> {HIGH_TEMP_THRESHOLD_C:.0f}°C)."
            )
        else:
            alert_type = "wetland_overflow"
            msg = (
                f"CRITICAL WETLAND OVERFLOW ALERT: Node {payload.asset_id} (SIRUTA {payload.siruta}) "
                f"bed level reached {payload.water_level_cm:.1f} cm (> {WETLAND_OVERFLOW_CM:.0f} cm)."
            )

        alert = TelemetryAlert(
            type="alert",
            alert_type=alert_type,
            severity="CRITICAL",
            asset_id=payload.asset_id,
            siruta=payload.siruta,
            battery_soc_percent=payload.battery_soc_percent,
            pv_power_watts=payload.pv_power_watts,
            load_power_watts=payload.load_power_watts,
            temperature_celsius=payload.temperature_celsius,
            message=msg,
            timestamp=payload.timestamp,
        )
        _alerts_history.append(alert)
        alert_emitted = alert.model_dump()
        await manager.broadcast_json(alert_emitted)
    else:
        await manager.broadcast_json({
            "type": "telemetry_update",
            "asset": asset_record,
            "timestamp": payload.timestamp,
        })

    return {
        "status": "ingested",
        "asset": asset_record,
        "alert_triggered": alert_emitted is not None,
        "alert": alert_emitted,
    }


@router.post("/clear-alerts", status_code=status.HTTP_200_OK)
async def clear_telemetry_alerts() -> Dict[str, Any]:
    """Clear active telemetry alerts and restore demo nodes to nominal SoC."""
    _alerts_history.clear()
    for asset_id, asset in _assets_store.items():
        if asset["battery_soc_percent"] < CRITICAL_SOC_THRESHOLD:
            asset["battery_soc_percent"] = 82.0
            asset["status"] = "NOMINAL"
    return {"status": "cleared", "active_alerts": 0}


@router.websocket("/ws")
async def telemetry_websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time WebSocket stream for telemetry updates and critical alerts."""
    await manager.connect(websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg.strip().lower() == "ping":
                await websocket.send_json({"type": "pong", "timestamp": _now_iso()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
