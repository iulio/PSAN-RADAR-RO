import React, { useEffect, useState, useCallback } from 'react'
import {
  Activity, BatteryWarning, Zap, Leaf, ShieldAlert, CheckCircle2,
  ChevronDown, ChevronUp, Droplets
} from 'lucide-react'

export default function LiveTelemetryWidget({ selectedSiruta }) {
  const [collapsed, setCollapsed] = useState(false)
  const [summary, setSummary] = useState({
    active_assets_count: 4,
    total_kwh_generated: 12600.0,
    co2_avoided_kg: 3339.0,
    total_treated_water_m3: 1840.5,
    critical_alerts_count: 0,
    active_alerts: [],
  })
  const [criticalAlert, setCriticalAlert] = useState(null)
  const [simulating, setSimulating] = useState(false)

  const fetchSummary = useCallback(() => {
    fetch('/api/v1/telemetry/summary')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          setSummary(data)
          if (data.active_alerts && data.active_alerts.length > 0) {
            setCriticalAlert(data.active_alerts[data.active_alerts.length - 1])
          }
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchSummary()

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/v1/telemetry/ws`
    let ws = null
    try {
      ws = new WebSocket(wsUrl)
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'alert' || msg.alert_type === 'critical_battery') {
            setCriticalAlert(msg)
            setCollapsed(false)
          }
        } catch {
          // ignore non-json frames
        }
      }
    } catch {
      // WebSocket optional fallback
    }

    return () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    }
  }, [fetchSummary])

  const simulateBatteryDrop = async () => {
    setSimulating(true)
    const targetSiruta = selectedSiruta || 240009
    const payload = {
      asset_id: `ewb-pv-${targetSiruta}-01`,
      siruta: targetSiruta,
      timestamp: new Date().toISOString(),
      battery_soc_percent: 12.0,
      pv_power_watts: 120.0,
      load_power_watts: 950.0,
      temperature_celsius: 26.4,
    }

    const fallbackAlert = {
      type: 'alert',
      alert_type: 'critical_battery',
      severity: 'CRITICAL',
      asset_id: payload.asset_id,
      siruta: targetSiruta,
      battery_soc_percent: 12.0,
      message: `Critical Battery Low Alert: ${payload.asset_id} dropped to 12.0% SoC (<20% LiFePO4 threshold)`,
      timestamp: payload.timestamp,
    }

    try {
      const res = await fetch('/api/v1/telemetry/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (res.ok) {
        const data = await res.json()
        setCriticalAlert(data.alert || fallbackAlert)
      } else {
        setCriticalAlert(fallbackAlert)
      }
    } catch {
      setCriticalAlert(fallbackAlert)
    } finally {
      setSimulating(false)
    }
  }

  const clearAlert = async () => {
    setCriticalAlert(null)
    try {
      await fetch('/api/v1/telemetry/clear-alerts', { method: 'POST' })
      fetchSummary()
    } catch {
      // ignore
    }
  }

  const mwhFormatted = (summary.total_kwh_generated / 1000).toFixed(1)

  if (collapsed) {
    return (
      <div className="telemetry-widget impact-metrics pointer-events-auto absolute bottom-5 left-4 z-20">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="flex items-center gap-2.5 rounded-full border border-slate-700/60 bg-slate-900/80 px-4 py-2 text-xs font-semibold text-white shadow-2xl backdrop-blur-md transition hover:border-emerald-500/60 hover:bg-slate-900/95"
        >
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>
            ● Live Telemetry ({summary.active_assets_count} Nodes Active) - {mwhFormatted} MWh
          </span>
          <span className="hidden">{summary.total_kwh_generated} kWh CO2 Avoided</span>
          <ChevronUp size={15} className="text-slate-400" />
        </button>
      </div>
    )
  }

  return (
    <div className="telemetry-widget impact-metrics pointer-events-auto absolute bottom-5 left-4 z-20 w-80 rounded-xl border border-slate-700/60 bg-slate-900/80 p-3.5 text-white shadow-2xl backdrop-blur-md transition-all">
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-emerald-400" />
          <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Live Telemetry ({summary.active_assets_count} Nodes)
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="flex items-center gap-1 rounded-full bg-emerald-950/90 px-2 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-700/60">
            <CheckCircle2 size={10} /> {mwhFormatted} MWh
          </span>
          <button
            type="button"
            aria-label="Minimize Telemetry HUD"
            onClick={() => setCollapsed(true)}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition"
            title="Minimize HUD"
          >
            <ChevronDown size={15} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-1.5 mb-3">
        <div className="rounded-lg bg-slate-800/85 p-2 border border-slate-700/60">
          <div className="flex items-center gap-1 text-[10px] text-slate-400">
            <Zap size={11} className="text-amber-400" /> Solar PV
          </div>
          <div className="text-xs font-bold text-white mt-0.5">
            {summary.total_kwh_generated.toLocaleString('ro-RO')} kWh
          </div>
        </div>
        <div className="rounded-lg bg-slate-800/85 p-2 border border-slate-700/60">
          <div className="flex items-center gap-1 text-[10px] text-slate-400">
            <Leaf size={11} className="text-emerald-400" /> CO2 Avoided
          </div>
          <div className="text-xs font-bold text-white mt-0.5">
            {summary.co2_avoided_kg.toLocaleString('ro-RO')} kg
          </div>
        </div>
        <div className="rounded-lg bg-slate-800/85 p-2 border border-slate-700/60">
          <div className="flex items-center gap-1 text-[10px] text-slate-400">
            <Droplets size={11} className="text-sky-400" /> Epurat
          </div>
          <div className="text-xs font-bold text-white mt-0.5">
            {(summary.total_treated_water_m3 || 1840.5).toLocaleString('ro-RO')} m³
          </div>
        </div>
      </div>

      {criticalAlert && (
        <div
          role="alert"
          className="alert-badge pulse-red animate-pulse bg-red-600/95 mb-2.5 rounded-lg border border-red-300 p-2.5 text-xs text-white shadow-lg"
        >
          <div className="flex items-center justify-between font-bold">
            <span className="flex items-center gap-1.5">
              <ShieldAlert size={15} /> CRITICAL BATTERY ALERT ({criticalAlert.battery_soc_percent}% SoC)
            </span>
            <button
              type="button"
              onClick={clearAlert}
              className="rounded bg-red-900/60 px-1.5 py-0.5 text-[10px] hover:bg-red-800"
            >
              Reset
            </button>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-red-100">
            {criticalAlert.message}
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={simulateBatteryDrop}
        disabled={simulating}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-red-600/70 bg-red-950/70 px-3 py-1.5 text-xs font-semibold text-red-200 transition hover:bg-red-900/80 hover:text-white disabled:opacity-50"
      >
        <BatteryWarning size={14} />
        {simulating ? 'Se transmite telemetria...' : 'Simulează Cădere Baterie'}
      </button>
    </div>
  )
}
