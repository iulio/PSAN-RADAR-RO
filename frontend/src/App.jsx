import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import {
  Radar, Filter, FileDown, Sparkles, Droplets, Zap, GraduationCap,
  AlertTriangle, Loader2, X, ClipboardCheck, Calculator, Scale,
  Users, PackageCheck, CheckCircle2, MapPin, ShieldCheck, Layers,
  Plus, Trash2, Truck, RotateCcw, Map, Globe, ChevronLeft, ChevronRight
} from 'lucide-react'
import FieldSurveyPWA from './components/FieldSurveyPWA'
import LiveTelemetryWidget from './components/LiveTelemetryWidget'
import NationalRadarMap from './components/NationalRadarMap'

const CSR_CATEGORIES = [
  { value: 'SOLAR_PV', label: 'Panouri Fotovoltaice 450Wp Tier-1', unit: 'pcs', defaultPrice: 185 },
  { value: 'BATTERY_STORAGE', label: 'Stocare Baterii LiFePO4 (kWh)', unit: 'kWh', defaultPrice: 420 },
  { value: 'HDPE_GEOMEMBRANE', label: 'Geomembrană HDPE 1.5mm + Geotextil', unit: 'm2', defaultPrice: 12.5 },
  { value: 'PVC_PIPING', label: 'Tubulatură PVC-KG SN4 DN110/DN160', unit: 'm', defaultPrice: 22 },
  { value: 'GRAVEL_AGGREGATE', label: 'Pietriș Spălat 10-20mm & 40-80mm', unit: 'm3', defaultPrice: 37.5 },
  { value: 'IMHOFF_TANK', label: 'Decantor Primar Imhoff Prefabricat', unit: 'm3', defaultPrice: 420 },
  { value: 'ISO_CONTAINER', label: 'Container Maritim 20ft High-Cube ISO 6346', unit: 'pcs', defaultPrice: 4200 },
  { value: 'IT_EDUPOD', label: 'Stație Studiu Digitală EduPod Completă', unit: 'pcs', defaultPrice: 650 },
]

const ROMANIAN_DEPOT_CITIES = [
  'Iași', 'Bacău', 'Galați', 'Brăila', 'Focșani', 'Vaslui', 'Bârlad',
  'Botoșani', 'Suceava', 'Piatra Neamț', 'Roman', 'Tulcea', 'Constanța',
  'București', 'Buzău', 'Ploiești', 'Brașov', 'Cluj-Napoca', 'Timișoara',
  'Craiova', 'Sibiu', 'Oradea', 'Slobozia', 'Călărași'
]

// ============================================================================
// TACTICAL DESIGN SYSTEM & HELPERS
// ============================================================================

const TIER_STYLES = {
  CRITICAL: { fill: '#ef4444', border: '#dc2626', badge: 'bg-red-600', label: 'CRITICAL' },
  HIGH: { fill: '#f97316', border: '#ea580c', badge: 'bg-orange-600', label: 'HIGH' },
  MODERATE: { fill: '#eab308', border: '#ca8a04', badge: 'bg-yellow-600', label: 'MODERATE' },
}

// ============================================================================
// UI SUB-COMPONENTS
// ============================================================================

function StatCard({ icon: Icon, label, value, tone }) {
  return (
    <div className="stat-card flex items-center gap-3 rounded-lg bg-slate-800/90 p-3 border border-slate-700/60">
      <div className={`rounded-md p-2 ${tone}`}>
        <Icon size={18} className="text-white" />
      </div>
      <div className="flex-1">
        <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
        <div className="text-lg font-semibold text-white">{value}</div>
      </div>
    </div>
  )
}

function DossierPanel({ siruta, onClose, onStartSurvey }) {
  const [activeTab, setActiveTab] = useState('overview')
  const [dossier, setDossier] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Grant Narrative state
  const [fundingLine, setFundingLine] = useState('PoIDS')
  const [narrative, setNarrative] = useState(null)
  const [narrativeLoading, setNarrativeLoading] = useState(false)

  // BOM Calculator state
  const [bomType, setBomType] = useState('OFFGRID_PV')
  const [bomData, setBomData] = useState(null)
  const [bomLoading, setBomLoading] = useState(false)

  // Permitting Roadmap state
  const [roadmap, setRoadmap] = useState(null)
  const [roadmapLoading, setRoadmapLoading] = useState(false)

  // Volunteer Dispatch & CSR Marketplace state
  const [dispatchData, setDispatchData] = useState(null)
  const [csrData, setCsrData] = useState(null)
  const [dispatchLoading, setDispatchLoading] = useState(false)
  const [showAddCsrForm, setShowAddCsrForm] = useState(false)
  const [csrActionLoading, setCsrActionLoading] = useState(false)
  const [newLotForm, setNewLotForm] = useState({
    donor_company: '',
    donor_cui: '',
    material_category: 'SOLAR_PV',
    item_name: 'Panouri Fotovoltaice Monocristaline 450Wp Tier-1',
    quantity_available: 48,
    market_unit_value_eur: 185,
    depot_city: 'Iași',
    freight_rate_eur_per_km: 1.55,
  })

  useEffect(() => {
    setLoading(true)
    setError(null)
    setNarrative(null)
    setBomData(null)
    setRoadmap(null)
    setDispatchData(null)
    setCsrData(null)
    setShowAddCsrForm(false)

    fetch(`/api/v1/radar/uat/${siruta}/dossier`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setDossier)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [siruta])

  const generateNarrative = (lineOverride) => {
    const targetLine = typeof lineOverride === 'string' ? lineOverride : fundingLine
    if (typeof lineOverride === 'string') {
      setFundingLine(lineOverride)
    }
    setNarrativeLoading(true)
    setActiveTab('overview')
    fetch(`/api/v1/radar/uat/${siruta}/grant-narrative?funding_line=${encodeURIComponent(targetLine)}`, {
      method: 'POST',
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setNarrative)
      .catch((e) => setError(e.message))
      .finally(() => setNarrativeLoading(false))
  }

  const downloadMysmisMarkdown = () => {
    if (!narrative?.mysmis_markdown_export) return
    const blob = new Blob([narrative.mysmis_markdown_export], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `Cerere_Finantare_MySMIS_${siruta}_${(narrative.funding_line || 'PoIDS').replace(/\s+/g, '_')}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const runBomCalculation = (typeOverride) => {
    const targetType = typeOverride || bomType
    setBomLoading(true)
    fetch(`/api/v1/radar/uat/${siruta}/calculate-bom`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intervention_type: targetType }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setBomData)
      .catch((e) => setError(e.message))
      .finally(() => setBomLoading(false))
  }

  const loadPermittingRoadmap = () => {
    setActiveTab('permitting')
    if (roadmap) return
    setRoadmapLoading(true)
    fetch(`/api/v1/radar/uat/${siruta}/permitting-roadmap`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(setRoadmap)
      .catch((e) => setError(e.message))
      .finally(() => setRoadmapLoading(false))
  }

  const refreshCsrMarketplace = () => {
    return fetch(`/api/v1/radar/uat/${siruta}/csr-marketplace`)
      .then((r) => (r.ok ? r.json() : null))
      .then((csrRes) => {
        if (csrRes) setCsrData(csrRes)
      })
  }

  const triggerVolunteerDispatch = () => {
    setActiveTab('dispatch')
    setDispatchLoading(true)
    Promise.all([
      fetch(`/api/v1/radar/uat/${siruta}/dispatch-team`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ max_team_size: 4 }),
      }).then((r) => (r.ok ? r.json() : null)),
      fetch(`/api/v1/radar/uat/${siruta}/csr-marketplace`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([teamRes, csrRes]) => {
        if (teamRes) setDispatchData(teamRes)
        if (csrRes) setCsrData(csrRes)
      })
      .catch((e) => setError(e.message))
      .finally(() => setDispatchLoading(false))
  }

  const handleCreateCsrLot = (e) => {
    e.preventDefault()
    setCsrActionLoading(true)
    setError(null)
    fetch('/api/v1/marketplace/lots', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        donor_company: newLotForm.donor_company,
        donor_cui: newLotForm.donor_cui || null,
        material_category: newLotForm.material_category,
        item_name: newLotForm.item_name,
        quantity_available: Number(newLotForm.quantity_available),
        market_unit_value_eur: Number(newLotForm.market_unit_value_eur),
        depot_city: newLotForm.depot_city,
        freight_rate_eur_per_km: Number(newLotForm.freight_rate_eur_per_km),
      }),
    })
      .then(async (r) => {
        if (!r.ok) {
          const errBody = await r.json().catch(() => ({}))
          throw new Error(errBody.detail || `HTTP ${r.status}`)
        }
        return r.json()
      })
      .then(() => {
        setShowAddCsrForm(false)
        setNewLotForm((prev) => ({ ...prev, donor_company: '', donor_cui: '' }))
        return refreshCsrMarketplace()
      })
      .catch((err) => setError(err.message))
      .finally(() => setCsrActionLoading(false))
  }

  const handleAllocateLot = (lotId, usableQty) => {
    setCsrActionLoading(true)
    setError(null)
    fetch(`/api/v1/radar/uat/${siruta}/csr-allocations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lot_id: lotId, quantity: usableQty }),
    })
      .then(async (r) => {
        if (!r.ok) {
          const errBody = await r.json().catch(() => ({}))
          throw new Error(errBody.detail || `HTTP ${r.status}`)
        }
        return r.json()
      })
      .then(() => refreshCsrMarketplace())
      .catch((err) => setError(err.message))
      .finally(() => setCsrActionLoading(false))
  }

  const handleRevokeAllocation = (allocationId) => {
    setCsrActionLoading(true)
    setError(null)
    fetch(`/api/v1/radar/uat/${siruta}/csr-allocations/${allocationId}`, {
      method: 'DELETE',
    })
      .then(async (r) => {
        if (!r.ok) {
          const errBody = await r.json().catch(() => ({}))
          throw new Error(errBody.detail || `HTTP ${r.status}`)
        }
        return r.json()
      })
      .then(() => refreshCsrMarketplace())
      .catch((err) => setError(err.message))
      .finally(() => setCsrActionLoading(false))
  }

  const handleDeleteLot = (lotId) => {
    setCsrActionLoading(true)
    setError(null)
    fetch(`/api/v1/marketplace/lots/${lotId}`, {
      method: 'DELETE',
    })
      .then(async (r) => {
        if (!r.ok) {
          const errBody = await r.json().catch(() => ({}))
          throw new Error(errBody.detail || `HTTP ${r.status}`)
        }
        return r.json()
      })
      .then(() => refreshCsrMarketplace())
      .catch((err) => setError(err.message))
      .finally(() => setCsrActionLoading(false))
  }

  return (
    <div
      role="dialog"
      aria-label="EU Project Dossier"
      className="drawer sidebar absolute right-0 top-0 z-20 flex h-full w-full max-w-lg flex-col overflow-y-auto border-l border-slate-800 bg-slate-900/95 p-5 shadow-2xl backdrop-blur transition-all"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold text-white">EU Project Dossier</h2>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="close-button rounded p-1 text-slate-400 hover:bg-slate-700 hover:text-white"
        >
          <X size={20} />
        </button>
      </div>

      {loading && (
        <div className="space-y-3 py-4">
          <div className="flex items-center gap-2 text-slate-300">
            <Loader2 className="animate-spin text-orange-500" size={18} /> Loading dossier…
          </div>
          <div className="h-16 animate-pulse rounded-lg bg-slate-800" />
          <div className="h-24 animate-pulse rounded-lg bg-slate-800" />
          <div className="h-32 animate-pulse rounded-lg bg-slate-800" />
        </div>
      )}

      {error && (
        <div className="mb-3 rounded bg-red-900/50 p-3 text-sm text-red-200 border border-red-700">
          Backend error: {error}
        </div>
      )}

      {dossier && (
        <div className="space-y-4">
          {/* Header Profile */}
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xl font-bold text-white">{dossier.uat_profile.uat_name}</h3>
              <span className={`rounded px-2 py-0.5 text-xs font-bold text-white ${tierStyle(dossier.uat_profile.priority_tier).badge}`}>
                {dossier.uat_profile.priority_tier}
              </span>
            </div>
            <p className="text-sm text-slate-400">
              {dossier.uat_profile.county} · SIRUTA {dossier.uat_profile.siruta} · RVI {dossier.uat_profile.rvi_score.toFixed(1)} · {dossier.uat_profile.population.toLocaleString('ro-RO')} loc.
            </p>
          </div>

          {/* Core Deficit StatCards (always visible for E2E & quick triage) */}
          <div className="grid grid-cols-1 gap-2">
            <StatCard icon={Droplets} label="Fără canalizare" value={pct(dossier.identified_deficits.sanitation_percent / 100)} tone="bg-blue-600" />
            <StatCard icon={Zap} label="Neelectrificate" value={pct(dossier.identified_deficits.offgrid_percent / 100)} tone="bg-amber-600" />
            <StatCard icon={GraduationCap} label="Risc abandon școlar" value={pct(dossier.identified_deficits.education_risk_percent / 100)} tone="bg-purple-600" />
          </div>

          {/* Primary Action Bar (Export PDF & Grant Narrative always visible) */}
          <div className="flex flex-wrap gap-2">
            <a
              href={`/api/v1/radar/uat/${siruta}/export-pdf`}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-orange-600 px-3 py-2 text-sm font-semibold text-white hover:bg-orange-500 transition"
            >
              <FileDown size={16} /> Export PDF
            </a>
            <button
              type="button"
              onClick={generateNarrative}
              disabled={narrativeLoading}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50 transition"
            >
              {narrativeLoading ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}
              Grant Narrative
            </button>
          </div>

          {/* Module Navigation Tabs */}
          <div className="grid grid-cols-4 gap-1 rounded-lg bg-slate-800/90 p-1 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setActiveTab('overview')}
              className={`rounded-md py-1.5 px-2 transition ${activeTab === 'overview' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-white'}`}
            >
              Dosar UE
            </button>
            <button
              type="button"
              onClick={() => {
                setActiveTab('bom')
                if (!bomData) runBomCalculation('OFFGRID_PV')
              }}
              className={`flex items-center justify-center gap-1 rounded-md py-1.5 px-2 transition ${activeTab === 'bom' ? 'bg-orange-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}
            >
              <Calculator size={12} /> BOM
            </button>
            <button
              type="button"
              onClick={loadPermittingRoadmap}
              className={`flex items-center justify-center gap-1 rounded-md py-1.5 px-2 transition ${activeTab === 'permitting' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}
            >
              <Scale size={12} /> Avize
            </button>
            <button
              type="button"
              onClick={triggerVolunteerDispatch}
              className={`flex items-center justify-center gap-1 rounded-md py-1.5 px-2 transition ${activeTab === 'dispatch' ? 'bg-indigo-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}
            >
              <Users size={12} /> Echipă
            </button>
          </div>

          {/* TAB 1: OVERVIEW, EU FUNDING MATRIX & MYSMIS 2021+ FINANCIAL ENGINE */}
          {activeTab === 'overview' && (
            <div className="space-y-4">
              <div>
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Justificare inginerească și încadrare strategică
                </h4>
                <p className="rounded-lg bg-slate-800/80 p-3 text-xs leading-relaxed text-slate-200 border border-slate-700/60">
                  {dossier.engineering_justification.text}
                </p>
              </div>

              {dossier.recommended_interventions.length > 0 && (
                <div>
                  <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Intervenții tehnice dimensionate
                  </h4>
                  <ul className="list-inside list-disc space-y-1 rounded-lg bg-slate-800/80 p-3 text-xs text-slate-200 border border-slate-700/60">
                    {dossier.recommended_interventions.map((iv, i) => (
                      <li key={i}>{iv.description}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Interactive Multi-Programme EU Funding Eligibility Matrix */}
              {dossier.eligible_eu_funding_lines.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Apeluri de Finanțare UE &amp; Naționale Eligibile ({dossier.eligible_eu_funding_lines.length})
                    </h4>
                    <span className="text-[10px] text-sky-400">Click pe apel pentru simulare MySMIS</span>
                  </div>
                  <div className="space-y-2">
                    {dossier.eligible_eu_funding_lines.map((f, i) => {
                      const progKey = f.programme_key || 'PoIDS'
                      const isSelected = fundingLine === progKey
                      return (
                        <div
                          key={i}
                          onClick={() => generateNarrative(progKey)}
                          className={`cursor-pointer rounded-lg p-2.5 border transition text-xs space-y-1.5 ${
                            isSelected
                              ? 'bg-blue-950/70 border-blue-500 shadow-md shadow-blue-950/50'
                              : 'bg-slate-800/80 border-slate-700/70 hover:border-slate-500'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span className="font-bold text-white leading-snug">{f.name}</span>
                            <span className="shrink-0 rounded bg-emerald-600/90 px-1.5 py-0.5 font-mono text-[10px] font-bold text-white">
                              ETF {Number(f.estimated_etf_score ?? 85).toFixed(1)}/100
                            </span>
                          </div>
                          {f.description && (
                            <p className="text-[11px] text-slate-300 leading-relaxed">{f.description}</p>
                          )}
                          <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[10px]">
                            <span className="rounded bg-slate-900 px-1.5 py-0.5 font-mono text-sky-300 border border-slate-700">
                              {f.call_code || 'MYSMIS-2025'}
                            </span>
                            <span className="rounded bg-emerald-950/80 px-1.5 py-0.5 font-semibold text-emerald-300 border border-emerald-700/50">
                              Grant: {Number(f.grant_intensity_pct ?? 98).toFixed(0)}% (Cofin. UAT: {Number(f.uat_cofinancing_pct ?? 2).toFixed(0)}%)
                            </span>
                            <span className="rounded bg-amber-950/80 px-1.5 py-0.5 font-mono text-amber-300 border border-amber-700/50">
                              Plafon: {Number(f.max_grant_eur ?? 2000000).toLocaleString('ro-RO')} EUR
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Target Programme Selector + Generate Button */}
              <div className="flex items-center justify-between gap-2 rounded-lg bg-slate-800/80 p-2.5 border border-slate-700">
                <span className="text-xs font-medium text-slate-300">Apel Țintă MySMIS:</span>
                <select
                  value={fundingLine}
                  onChange={(e) => {
                    setFundingLine(e.target.value)
                    generateNarrative(e.target.value)
                  }}
                  className="flex-1 rounded bg-slate-900 px-2.5 py-1.5 text-xs font-semibold text-white border border-slate-700"
                >
                  <option value="PoIDS">PoIDS 2021–2027 (98% Grant FSE+/FEDR · Max 2M EUR)</option>
                  <option value="Fondul pentru Modernizare">Fondul pentru Modernizare / AFM (100% Grant PV Off-Grid)</option>
                  <option value="AFIR Fitodepurare">PNRR C1 / AFIR DR-27 (95% Grant Fitodepurare NTPA-001)</option>
                  <option value="PNRAS">PNRAS / PNRR C15 (100% Grant EduPod Digital · Max 300k EUR)</option>
                  <option value="Programul Regional">Programul Regional 2021–2027 (98% Grant FEDR Micro-Rețele)</option>
                </select>
              </div>

              {narrative && (
                <div className="space-y-3 rounded-lg bg-slate-900/95 p-3.5 border border-blue-600/60 shadow-xl">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
                    <div>
                      <span className="text-[11px] font-bold uppercase tracking-wider text-blue-400 block">
                        Dosar Cerere de Finanțare MySMIS 2021+ ({narrative.generated_by})
                      </span>
                      <span className="text-xs font-semibold text-white">
                        {narrative.financial_plan?.call_code || narrative.funding_line} · {narrative.financial_plan?.managing_authority}
                      </span>
                    </div>
                    {narrative.mysmis_markdown_export && (
                      <button
                        type="button"
                        onClick={downloadMysmisMarkdown}
                        className="flex items-center gap-1 rounded-md bg-emerald-600 hover:bg-emerald-500 px-2.5 py-1 text-[11px] font-bold text-white transition shadow"
                      >
                        <FileDown size={13} /> Export MySMIS (.md)
                      </button>
                    )}
                  </div>

                  {/* 1. MySMIS Co-Financing & HG 907/2016 Financial Plan */}
                  {narrative.financial_plan && (
                    <div className="space-y-2 rounded-lg bg-slate-800/90 p-3 border border-slate-700 text-xs">
                      <div className="flex items-center justify-between font-bold text-amber-300">
                        <span>1. Structura de Finanțare &amp; Co-Finanțare UAT</span>
                        <span className="rounded bg-emerald-900/80 px-2 py-0.5 text-[10px] text-emerald-200 border border-emerald-600/50">
                          Grant {narrative.financial_plan.grant_intensity_pct}%
                        </span>
                      </div>

                      <div className="space-y-1 text-[11px]">
                        <div className="flex justify-between text-slate-300">
                          <span>Valoare Brută Deviz Tehnic (BOM):</span>
                          <span className="font-mono text-white">{eur(narrative.financial_plan.gross_bom_capex_eur)}</span>
                        </div>
                        <div className="flex justify-between text-emerald-400">
                          <span>Deducere Stocuri CSR Alocate (Aport în Natură):</span>
                          <span className="font-mono font-semibold">-{eur(narrative.financial_plan.csr_in_kind_deduction_eur)}</span>
                        </div>
                        <div className="flex justify-between text-slate-200">
                          <span>Valoare Eligibilă Nerambursabilă (HG 907/2016):</span>
                          <span className="font-mono font-semibold">{eur(narrative.financial_plan.eligible_expenditure_eur)}</span>
                        </div>
                        <div className="flex justify-between border-t border-slate-700 pt-1 text-emerald-300 font-bold text-xs">
                          <span>GRANT NERAMBURSABIL UE / NAȚIONAL ({narrative.financial_plan.grant_intensity_pct}%):</span>
                          <span className="font-mono">{eur(narrative.financial_plan.eu_grant_amount_eur)}</span>
                        </div>
                        <div className="flex justify-between text-amber-300 font-semibold">
                          <span>Cofinanțare Locală UAT ({narrative.financial_plan.uat_cofinancing_pct}% + neeligibil):</span>
                          <span className="font-mono">{eur(narrative.financial_plan.uat_cofinancing_eur)}</span>
                        </div>
                      </div>

                      {/* HG 907/2016 Deviz General Chapters Table */}
                      {narrative.financial_plan.hg907_chapters && (
                        <div className="mt-2 overflow-x-auto rounded border border-slate-700 bg-slate-950/80">
                          <table className="w-full text-left text-[10px] text-slate-300">
                            <thead className="bg-slate-800 text-slate-400 uppercase">
                              <tr>
                                <th className="p-1.5">Cap. HG 907</th>
                                <th className="p-1.5">Denumire Capitol</th>
                                <th className="p-1.5 text-right">Eligibil</th>
                                <th className="p-1.5 text-right">Total EUR</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800">
                              {narrative.financial_plan.hg907_chapters.map((ch) => (
                                <tr key={ch.chapter_code}>
                                  <td className="p-1.5 font-mono font-bold text-sky-300 whitespace-nowrap">{ch.chapter_code}</td>
                                  <td className="p-1.5">{ch.chapter_name}</td>
                                  <td className="p-1.5 text-right font-mono text-emerald-300">{ch.eligible_eur.toLocaleString('ro-RO')}</td>
                                  <td className="p-1.5 text-right font-mono font-semibold text-white">{ch.total_eur.toLocaleString('ro-RO')}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 2. ETF Evaluation Grid Scorecard (0-100 points) */}
                  {narrative.etf_scorecard && (
                    <div className="space-y-2 rounded-lg bg-slate-800/90 p-3 border border-slate-700 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-sky-300">2. Grila de Evaluare ETF (MySMIS 2021+)</span>
                        <span className="rounded bg-emerald-600 px-2 py-0.5 font-mono text-xs font-bold text-white">
                          {narrative.etf_scorecard.total_score} / 100 pct
                        </span>
                      </div>
                      <div className="text-[10px] text-emerald-300 font-semibold">
                        Statut: {narrative.etf_scorecard.status_label} (Prag minim: {narrative.etf_scorecard.quality_threshold} pct)
                      </div>
                      <div className="space-y-1.5 pt-1">
                        {narrative.etf_scorecard.criteria.map((c) => (
                          <div key={c.code} className="rounded bg-slate-900/90 p-2 border border-slate-800 text-[10px]">
                            <div className="flex justify-between font-semibold text-white">
                              <span>{c.code}. {c.title}</span>
                              <span className="font-mono text-emerald-400 shrink-0 ml-2">{c.score} / {c.max_score}p</span>
                            </div>
                            <p className="text-slate-400 mt-0.5">{c.justification}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 3. DNSH Compliance Matrix (Reg. EU 2020/852 Art. 17) */}
                  {narrative.dnsh_matrix && (
                    <div className="space-y-1.5 rounded-lg bg-slate-800/90 p-3 border border-slate-700 text-xs">
                      <div className="flex items-center justify-between font-bold text-emerald-300">
                        <span>3. Matricea DNSH (Reg. UE 2020/852 Art. 17)</span>
                        <span className="text-[10px] bg-emerald-950 border border-emerald-700 px-1.5 py-0.5 rounded text-emerald-300">
                          6/6 Obiective Conforme
                        </span>
                      </div>
                      <div className="grid grid-cols-1 gap-1.5 text-[10px]">
                        {narrative.dnsh_matrix.map((d) => (
                          <div key={d.objective_code} className="rounded bg-slate-900/80 p-2 border border-slate-800">
                            <div className="flex justify-between font-semibold text-white">
                              <span>{d.objective_name}</span>
                              <span className="text-emerald-400 font-bold">CONFORM</span>
                            </div>
                            <p className="text-slate-400 mt-0.5">{d.technical_compliance_justification}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 4. Formal MySMIS 2021+ Narrative Sections */}
                  <div className="space-y-2.5 pt-1">
                    <div className="text-xs font-bold text-blue-300">
                      4. Secțiunile Narative ale Cererii de Finanțare
                    </div>
                    {[
                      ['Justificarea Nevoii', narrative.justificarea_nevoii],
                      ['Descrierea Activităților', narrative.descrierea_activitatilor],
                      ['Rezultate și Indicatori', narrative.rezultate_si_indicatori],
                      ['Sustenabilitate', narrative.sustenabilitate],
                      ['Buget Sumar', narrative.buget_sumar],
                    ].map(([title, body]) => (
                      <div key={title} className="rounded bg-slate-800/80 p-2.5 border border-slate-700/70">
                        <h5 className="text-xs font-bold uppercase text-white">{title}</h5>
                        <p className="mt-1 text-xs leading-relaxed text-slate-300">{body}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {onStartSurvey && (
                <button
                  type="button"
                  onClick={() => onStartSurvey(dossier.uat_profile)}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                >
                  <ClipboardCheck size={15} /> Deschide Fișa de Audit Teren (PWA) pentru {dossier.uat_profile.uat_name}
                </button>
              )}
            </div>
          )}

          {/* TAB 2: DETERMINISTIC ENGINEERING SIZING & BOM */}
          {activeTab === 'bom' && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <select
                  value={bomType}
                  onChange={(e) => {
                    setBomType(e.target.value)
                    runBomCalculation(e.target.value)
                  }}
                  className="flex-1 rounded-lg bg-slate-800 px-3 py-2 text-xs font-semibold text-white border border-slate-700"
                >
                  <option value="OFFGRID_PV">Solar PV + Stocare LiFePO4 (SR EN 62124)</option>
                  <option value="SANITATION">Fitodepurare HSSF CW + Imhoff (NTPA-001)</option>
                  <option value="EDUCATION">Centru Digital EduPod Containerizat</option>
                  <option value="INTEGRATED">Intervenție Integrată Completă (UAT)</option>
                </select>
              </div>

              {bomLoading && (
                <div className="flex items-center gap-2 text-xs text-slate-300 py-4">
                  <Loader2 size={16} className="animate-spin text-orange-400" /> Se dimensionează devizul tehnic...
                </div>
              )}

              {bomData && (
                <div className="space-y-3">
                  <div className="rounded-lg bg-slate-800/90 p-3 border border-slate-700">
                    <div className="text-xs font-bold uppercase text-orange-400 mb-2">
                      Parametri Tehnici Dimensionați
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {bomData.engineering_parameters.pv_kwp && (
                        <div className="bg-slate-900/70 p-2 rounded">
                          <span className="text-slate-400 block">Putere PV Instalată</span>
                          <span className="font-bold text-white">{bomData.engineering_parameters.pv_kwp} kWp (PSH iarnă: {bomData.engineering_parameters.winter_psh}h)</span>
                        </div>
                      )}
                      {bomData.engineering_parameters.battery_kwh && (
                        <div className="bg-slate-900/70 p-2 rounded">
                          <span className="text-slate-400 block">Baterie LiFePO4 (DoD 80%)</span>
                          <span className="font-bold text-white">{bomData.engineering_parameters.battery_kwh} kWh</span>
                        </div>
                      )}
                      {bomData.engineering_parameters.inverter_kva && (
                        <div className="bg-slate-900/70 p-2 rounded">
                          <span className="text-slate-400 block">Invertor Hibrid (Surge 2.5x)</span>
                          <span className="font-bold text-white">{bomData.engineering_parameters.inverter_kva} kVA (vârf {bomData.engineering_parameters.inverter_surge_kva} kVA)</span>
                        </div>
                      )}
                      {bomData.engineering_parameters.wetland_area_m2 && (
                        <div className="bg-slate-900/70 p-2 rounded">
                          <span className="text-slate-400 block">Bazin Fitodepurare (NTPA-001)</span>
                          <span className="font-bold text-white">{bomData.engineering_parameters.wetland_area_m2} m² ({bomData.engineering_parameters.connected_pe} l.e.)</span>
                        </div>
                      )}
                      {bomData.engineering_parameters.student_stations && (
                        <div className="bg-slate-900/70 p-2 rounded">
                          <span className="text-slate-400 block">Stații Studiu EduPod</span>
                          <span className="font-bold text-white">{bomData.engineering_parameters.student_stations} posturi ({bomData.engineering_parameters.container_size_ft}ft HC)</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-800/90 p-3 border border-slate-700 space-y-1.5 text-xs">
                    <div className="flex justify-between text-slate-300">
                      <span>Echipamente &amp; Materiale:</span>
                      <span className="font-mono">{eur(bomData.subtotal_equipment_eur)}</span>
                    </div>
                    <div className="flex justify-between text-slate-300">
                      <span>Manoperă, Proiectare &amp; Avize:</span>
                      <span className="font-mono">{eur(bomData.subtotal_works_labor_eur)}</span>
                    </div>
                    <div className="flex justify-between text-slate-300">
                      <span>Rezervă Neprevăzute (10%):</span>
                      <span className="font-mono">{eur(bomData.contingency_reserve_eur)}</span>
                    </div>
                    <div className="flex justify-between border-t border-slate-700 pt-1.5 text-sm font-bold text-orange-400">
                      <span>TOTAL CAPEX INVESTIȚIE:</span>
                      <span className="font-mono">{eur(bomData.total_project_capex_eur)}</span>
                    </div>
                  </div>

                  <div className="max-h-56 overflow-y-auto rounded-lg border border-slate-700 bg-slate-900/80">
                    <table className="w-full text-left text-[11px] text-slate-300">
                      <thead className="bg-slate-800 text-slate-400 uppercase">
                        <tr>
                          <th className="p-2">Articol Deviz</th>
                          <th className="p-2 text-right">Cant.</th>
                          <th className="p-2 text-right">Total EUR</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {bomData.itemized_bom.map((item, idx) => (
                          <tr key={idx}>
                            <td className="p-2">{item.description}</td>
                            <td className="p-2 text-right font-mono">{item.qty} {item.unit}</td>
                            <td className="p-2 text-right font-mono text-white">{item.total_eur.toLocaleString('ro-RO')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: PERMITTING ROADMAP (Compliance Navigator) */}
          {activeTab === 'permitting' && (
            <div className="space-y-3">
              {roadmapLoading && (
                <div className="flex items-center gap-2 text-xs text-slate-300 py-4">
                  <Loader2 size={16} className="animate-spin text-emerald-400" /> Se generează foaia de parcurs legislativă...
                </div>
              )}
              {roadmap && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between rounded-lg bg-emerald-950/60 border border-emerald-700/60 p-2.5 text-xs">
                    <span className="flex items-center gap-1.5 text-emerald-300 font-semibold">
                      <ShieldCheck size={16} /> Drum Critic Avizare: ~{roadmap.total_estimated_critical_path_days} zile
                    </span>
                    {roadmap.fast_track_solar_exemption && (
                      <span className="rounded bg-emerald-700/80 px-2 py-0.5 text-[10px] font-bold text-white">
                        Exceptare AC Legea 50/1991 Art. 11(m)
                      </span>
                    )}
                  </div>

                  <div className="space-y-2">
                    {roadmap.steps.map((s) => (
                      <div key={s.step_number} className="rounded-lg bg-slate-800/90 p-3 border border-slate-700 text-xs space-y-1">
                        <div className="flex items-center justify-between font-bold text-white">
                          <span>{s.step_number}. {s.document_name}</span>
                          <span className="text-[11px] text-orange-400">{s.estimated_days} zile</span>
                        </div>
                        <div className="text-slate-400">
                          <strong>Autoritate:</strong> {s.issuing_authority}
                        </div>
                        <div className="text-slate-400">
                          <strong>Temei Legal:</strong> {s.legal_basis}
                        </div>
                        <div className="text-emerald-300">
                          <strong>Asumare / Semnătură:</strong> {s.mandatory_signoff}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div>
                    <h5 className="mb-1 text-xs font-bold uppercase text-slate-400">
                      Dosar Administrativ Pre-Completat (Markdown)
                    </h5>
                    <pre className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-3 text-[11px] text-slate-300 border border-slate-800 font-mono">
                      {roadmap.administrative_dossier_markdown}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: PRO BONO VOLUNTEER DISPATCH & CSR MARKETPLACE */}
          {activeTab === 'dispatch' && (
            <div className="space-y-3">
              {dispatchLoading && (
                <div className="flex items-center gap-2 text-xs text-slate-300 py-4">
                  <Loader2 size={16} className="animate-spin text-indigo-400" /> Se calculează distanțele Haversine și stocurile CSR...
                </div>
              )}

              {dispatchData && (
                <div className="space-y-2.5">
                  <div className="rounded-lg bg-indigo-950/60 border border-indigo-700/60 p-2.5 text-xs">
                    <div className="flex items-center justify-between font-bold text-indigo-200">
                      <span>Echipă Pro Bono Mobilizată ({dispatchData.dispatched_team.length} ingineri)</span>
                      <span className="rounded bg-indigo-600 px-2 py-0.5 text-white">
                        Readiness: {dispatchData.readiness_score_pct}%
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-indigo-300">{dispatchData.mobilization_order_summary}</p>
                  </div>

                  {dispatchData.dispatched_team.map((m) => (
                    <div key={m.volunteer.id} className="rounded-lg bg-slate-800/90 p-2.5 border border-slate-700 text-xs flex items-center justify-between">
                      <div>
                        <div className="font-bold text-white">{m.volunteer.name}</div>
                        <div className="text-slate-400 text-[11px]">
                          {m.volunteer.county} · {m.matched_roles.join(', ')}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-mono font-bold text-emerald-400 flex items-center gap-1 justify-end">
                          <MapPin size={12} /> {m.distance_km} km
                        </div>
                        <div className="text-[10px] text-slate-400">~{m.estimated_travel_hours}h deplasare</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {csrData && (
                <div className="space-y-3 pt-3 border-t border-slate-800">
                  {/* Header + Add Lot Toggle */}
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs font-bold text-amber-300">
                      <PackageCheck size={15} /> Stocuri CSR &amp; Alocare Deviz (BOM)
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowAddCsrForm((v) => !v)}
                      className="flex items-center gap-1 rounded-md bg-amber-600/90 hover:bg-amber-500 px-2.5 py-1 text-[11px] font-bold text-slate-950 transition shadow"
                    >
                      <Plus size={12} /> {showAddCsrForm ? 'Închide Formular' : 'Adaugă Lot CSR'}
                    </button>
                  </div>

                  {/* Financial Impact Balance Card */}
                  <div className="rounded-lg bg-slate-800/90 p-2.5 border border-slate-700 text-[11px] space-y-1">
                    <div className="flex justify-between text-slate-300">
                      <span>CAPEX Deviz Tehnic Inițial (BOM):</span>
                      <span className="font-mono font-semibold text-white">{eur(csrData.original_bom_capex_eur)}</span>
                    </div>
                    <div className="flex justify-between text-emerald-400">
                      <span>Economie Netă CSR Alocată ({csrData.allocations?.length || 0} loturi):</span>
                      <span className="font-mono font-bold">-{eur(csrData.allocated_net_capex_savings_eur)}</span>
                    </div>
                    <div className="flex justify-between text-amber-300">
                      <span>Potențial Suplimentar din Stoc Disponibil:</span>
                      <span className="font-mono">-{eur(csrData.potential_additional_savings_eur)}</span>
                    </div>
                    <div className="flex justify-between border-t border-slate-700 pt-1 text-xs font-bold text-sky-300">
                      <span>CAPEX Net Rămas de Finanțat:</span>
                      <span className="font-mono">{eur(csrData.adjusted_net_capex_eur)}</span>
                    </div>
                  </div>

                  {/* Add New CSR Lot Form */}
                  {showAddCsrForm && (
                    <form
                      onSubmit={handleCreateCsrLot}
                      className="rounded-lg bg-slate-950/90 p-3 border border-amber-500/50 space-y-2.5 text-xs"
                    >
                      <div className="font-bold text-amber-300 uppercase tracking-wide text-[11px]">
                        Înregistrare Donație / Stoc CSR în Depozit (SQLite)
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-0.5">Companie Donatoare *</label>
                          <input
                            type="text"
                            required
                            placeholder="ex: Dedeman / Holcim / Engie"
                            value={newLotForm.donor_company}
                            onChange={(e) => setNewLotForm((f) => ({ ...f, donor_company: e.target.value }))}
                            className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-white text-xs"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-0.5">CUI / CIF Sponsor (Opțional)</label>
                          <input
                            type="text"
                            placeholder="ex: RO2816464"
                            value={newLotForm.donor_cui}
                            onChange={(e) => setNewLotForm((f) => ({ ...f, donor_cui: e.target.value }))}
                            className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-white text-xs"
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-0.5">Categorie Deviz (BOM) *</label>
                          <select
                            value={newLotForm.material_category}
                            onChange={(e) => {
                              const cat = CSR_CATEGORIES.find((c) => c.value === e.target.value)
                              setNewLotForm((f) => ({
                                ...f,
                                material_category: e.target.value,
                                item_name: cat ? cat.label : f.item_name,
                                market_unit_value_eur: cat ? cat.defaultPrice : f.market_unit_value_eur,
                              }))
                            }}
                            className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-white text-xs"
                          >
                            {CSR_CATEGORIES.map((c) => (
                              <option key={c.value} value={c.value}>{c.label} ({c.unit})</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-0.5">Oraș Depozit (Geocodare Auto) *</label>
                          <select
                            value={newLotForm.depot_city}
                            onChange={(e) => setNewLotForm((f) => ({ ...f, depot_city: e.target.value }))}
                            className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-white text-xs"
                          >
                            {ROMANIAN_DEPOT_CITIES.map((city) => (
                              <option key={city} value={city}>{city}</option>
                            ))}
                          </select>
                        </div>
                      </div>

                      <div>
                        <label className="block text-[10px] text-slate-400 mb-0.5">Specificație Tehnică Material *</label>
                        <input
                          type="text"
                          required
                          value={newLotForm.item_name}
                          onChange={(e) => setNewLotForm((f) => ({ ...f, item_name: e.target.value }))}
                          className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-white text-xs"
                        />
                      </div>

                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-0.5">Cantitate *</label>
                          <input
                            type="number"
                            step="0.1"
                            min="1"
                            required
                            value={newLotForm.quantity_available}
                            onChange={(e) => setNewLotForm((f) => ({ ...f, quantity_available: e.target.value }))}
                            className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-white text-xs font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-0.5">Valoare Unitară (EUR)</label>
                          <input
                            type="number"
                            step="0.1"
                            min="0.5"
                            required
                            value={newLotForm.market_unit_value_eur}
                            onChange={(e) => setNewLotForm((f) => ({ ...f, market_unit_value_eur: e.target.value }))}
                            className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-white text-xs font-mono"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-slate-400 mb-0.5">Tarif Camion (EUR/km)</label>
                          <input
                            type="number"
                            step="0.05"
                            min="0.2"
                            required
                            value={newLotForm.freight_rate_eur_per_km}
                            onChange={(e) => setNewLotForm((f) => ({ ...f, freight_rate_eur_per_km: e.target.value }))}
                            className="w-full rounded bg-slate-900 border border-slate-700 px-2 py-1 text-white text-xs font-mono"
                          />
                        </div>
                      </div>

                      <button
                        type="submit"
                        disabled={csrActionLoading}
                        className="w-full flex items-center justify-center gap-1.5 rounded bg-emerald-600 hover:bg-emerald-500 py-1.5 font-bold text-white transition disabled:opacity-50"
                      >
                        {csrActionLoading ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                        Salvează Lot CSR în Baza de Date
                      </button>
                    </form>
                  )}

                  {/* UAT Engineering BOM Coverage Breakdown */}
                  {csrData.uat_bom_requirements && (
                    <div className="rounded-lg bg-slate-900/80 p-2.5 border border-slate-800 space-y-1.5">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Necesar Cantitativ Deviz (BOM) pentru {csrData.uat_name}
                      </div>
                      <div className="grid grid-cols-2 gap-1.5 text-[10px]">
                        {csrData.uat_bom_requirements.map((req) => {
                          const covPct = req.required_quantity > 0
                            ? Math.min(100, Math.round((req.allocated_quantity / req.required_quantity) * 100))
                            : 0
                          return (
                            <div key={req.material_category} className="rounded bg-slate-800/80 p-1.5 border border-slate-700/60">
                              <div className="flex justify-between text-slate-200 font-medium truncate">
                                <span className="truncate" title={req.label}>{req.label}</span>
                              </div>
                              <div className="flex justify-between font-mono text-[10px] mt-0.5">
                                <span className={covPct >= 100 ? 'text-emerald-400 font-bold' : 'text-amber-300'}>
                                  {req.allocated_quantity} / {req.required_quantity} {req.unit}
                                </span>
                                <span className="text-slate-400">{covPct}%</span>
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* Active CSR Allocations for this UAT */}
                  {csrData.allocations && csrData.allocations.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-[11px] font-bold text-emerald-400 flex items-center gap-1">
                        <CheckCircle2 size={13} /> Materiale CSR Rezervate &amp; Alocate UAT-ului
                      </div>
                      {csrData.allocations.map((alloc) => (
                        <div key={alloc.allocation_id} className="rounded-lg bg-emerald-950/40 p-2.5 border border-emerald-700/60 text-[11px] space-y-1">
                          <div className="flex justify-between font-semibold text-white">
                            <span>{alloc.item_name} ({alloc.quantity_allocated} {alloc.unit})</span>
                            <span className="text-emerald-300 font-mono">-{eur(alloc.net_capex_saving_eur)}</span>
                          </div>
                          <div className="flex items-center justify-between text-slate-300 text-[10px]">
                            <span>
                              Donator: <b>{alloc.donor_company}</b> · {alloc.road_distance_km} km ({alloc.num_trucks} camioane · Transport: {eur(alloc.logistics_cost_eur)})
                            </span>
                            <button
                              type="button"
                              disabled={csrActionLoading}
                              onClick={() => handleRevokeAllocation(alloc.allocation_id)}
                              className="flex items-center gap-1 rounded bg-red-900/70 hover:bg-red-800 px-2 py-0.5 text-[10px] font-semibold text-red-200 transition"
                            >
                              <RotateCcw size={10} /> Anulează
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Available CSR Warehouse Lots Matched to UAT Deficit */}
                  <div className="space-y-1.5">
                    <div className="text-[11px] font-bold text-slate-300">
                      Loturi Disponibile în Depozit Compatibile cu Devizul UAT ({csrData.matched_lots.length})
                    </div>
                    {csrData.matched_lots.length === 0 ? (
                      <div className="rounded-lg bg-slate-900/70 p-3 border border-dashed border-slate-700 text-center text-xs text-slate-400">
                        Niciun lot CSR în stoc pentru categoriile rămase neacoperite. Apăsați <b>«+ Adaugă Lot CSR»</b> pentru a înregistra un stoc real în baza de date SQLite.
                      </div>
                    ) : (
                      csrData.matched_lots.map((q) => (
                        <div key={q.lot.lot_id} className="rounded-lg bg-slate-800/80 p-2.5 border border-slate-700 text-[11px] space-y-1.5">
                          <div className="flex justify-between font-semibold text-white">
                            <span>{q.lot.item_name}</span>
                            <span className="text-emerald-400 font-mono font-bold">-{eur(q.net_capex_savings_eur)}</span>
                          </div>
                          <div className="text-slate-300 text-[10px] flex flex-wrap gap-x-3 gap-y-0.5">
                            <span>Donator: <b>{q.lot.donor_company}</b> ({q.lot.depot_city})</span>
                            <span>Stoc: <b>{q.lot.quantity_available} {q.lot.unit}</b></span>
                            <span>Utilizabil BOM UAT: <b>{q.usable_quantity} {q.lot.unit}</b></span>
                          </div>
                          <div className="flex items-center justify-between pt-1 border-t border-slate-700/60">
                            <span className="text-[10px] text-slate-400 flex items-center gap-1">
                              <Truck size={11} className="text-amber-400" />
                              {q.estimated_road_km} km rutier · {q.num_trucks} camion ({q.total_weight_tonnes} t) · Transport: {eur(q.logistics_transit_cost_eur)}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                disabled={csrActionLoading}
                                onClick={() => handleAllocateLot(q.lot.lot_id, q.usable_quantity)}
                                className="rounded bg-emerald-600 hover:bg-emerald-500 px-2.5 py-1 text-[10px] font-bold text-white transition"
                              >
                                Alocă {q.usable_quantity} {q.lot.unit}
                              </button>
                              <button
                                type="button"
                                title="Șterge lotul din baza de date"
                                disabled={csrActionLoading}
                                onClick={() => handleDeleteLot(q.lot.lot_id)}
                                className="rounded bg-slate-700 hover:bg-red-700 p-1 text-slate-300 hover:text-white transition"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// MAIN APP
// ============================================================================

export default function App() {
  const [activeView, setActiveView] = useState('map') // 'map' | 'survey'
    const [surveyInitialUat, setSurveyInitialUat] = useState(null)
    const [minRvi, setMinRvi] = useState(0)
    const [county, setCounty] = useState('')
    const [tier, setTier] = useState('')
    const [requireOffgrid, setRequireOffgrid] = useState(false)
    const [requireSanitation, setRequireSanitation] = useState(false)
    const [requireEducation, setRequireEducation] = useState(false)
    const [selected, setSelected] = useState(null)
    const [backendOk, setBackendOk] = useState(true)
    const [sidebarOpen, setSidebarOpen] = useState(true)
    const [nationalCounties, setNationalCounties] = useState([])

    // Fetch counties for the filter dropdown (from national endpoint)
    useEffect(() => {
      fetch('/api/v1/geo/counties')
        .then(r => r.ok ? r.json() : [])
        .then(data => setNationalCounties(data))
        .catch(() => setNationalCounties([]))
    }, [])

    const handleUATSelect = useCallback((properties) => {
      setSelected(properties.siruta)
      setSidebarOpen(true)
    }, [])

  if (activeView === 'survey') {
      return (
        <FieldSurveyPWA
          initialUat={surveyInitialUat}
          onBackToMap={() => setActiveView('map')}
        />
      )
    }

    return (
    <div className="relative flex h-full flex-col bg-slate-950">
      <header className="z-20 flex flex-wrap items-center gap-3 border-b border-slate-800 bg-slate-900 px-5 py-3">
        <Radar className="text-orange-500" size={24} />
        <div>
          <h1 className="text-lg font-bold text-white">PSAN Radar</h1>
          <p className="text-xs text-slate-400">
            Poverty &amp; Social Actions Needed — Engineers Without Borders România
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {!backendOk && (
            <span className="flex items-center gap-1 rounded bg-amber-900/60 px-2.5 py-1 text-xs text-amber-200">
              <AlertTriangle size={14} /> Offline demo data
            </span>
          )}
          <button
            type="button"
            onClick={() => {
              setSurveyInitialUat(null)
              setActiveView('survey')
            }}
            className="flex items-center gap-1.5 rounded-lg bg-orange-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-orange-500 transition shadow"
          >
            <ClipboardCheck size={15} /> Field Survey
          </button>
                  <button
                    type="button"
                    onClick={() => setSidebarOpen(v => !v)}
                    className="flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white border border-slate-600 hover:border-slate-400 transition"
                  >
                    {sidebarOpen ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
                  </button>
                </div>
      </header>

      <div className="z-20 flex flex-wrap items-center gap-4 border-b border-slate-800 bg-slate-900/95 px-5 py-2.5">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
          <Filter size={16} className="text-orange-400" />
          <label className="flex items-center gap-2">
            <span className="min-w-[4.5rem] font-semibold text-white">RVI ≥ {minRvi}</span>
            <input
              type="range"
              min="0"
              max="100"
              value={minRvi}
              onChange={(e) => setMinRvi(Number(e.target.value))}
              className="rvi-slider align-middle accent-orange-500"
            />
          </label>
        </div>

        <select
          aria-label="County Filter"
          value={county}
          onChange={(e) => setCounty(e.target.value)}
          className="rounded-lg bg-slate-800 px-2.5 py-1 text-sm font-medium text-white border border-slate-600 focus:border-sky-400 focus:outline-none"
        >
          <option value="">Toate județele (County)</option>
                  {nationalCounties.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>

        <select
          aria-label="Priority Tier Filter"
          value={tier}
          onChange={(e) => setTier(e.target.value)}
          className="rounded-lg bg-slate-800 px-2.5 py-1 text-sm font-medium text-white border border-slate-600 focus:border-sky-400 focus:outline-none"
        >
          <option value="">Toate nivelurile</option>
          <option value="CRITICAL">CRITICAL</option>
          <option value="HIGH">HIGH</option>
          <option value="MODERATE">MODERATE</option>
        </select>

        <div className="flex items-center gap-2 text-xs">
          <button
            type="button"
            onClick={() => setRequireOffgrid((v) => !v)}
            className={`rounded-full px-3 py-1 font-semibold transition border ${
              requireOffgrid
                ? 'bg-amber-500 text-slate-950 border-amber-300 shadow-md shadow-amber-500/20'
                : 'bg-slate-800 text-slate-200 border-slate-600 hover:border-slate-400'
            }`}
          >
            ⚡ Off-Grid ≥50%
          </button>
          <button
            type="button"
            onClick={() => setRequireSanitation((v) => !v)}
            className={`rounded-full px-3 py-1 font-semibold transition border ${
              requireSanitation
                ? 'bg-sky-500 text-slate-950 border-sky-300 shadow-md shadow-sky-500/20'
                : 'bg-slate-800 text-slate-200 border-slate-600 hover:border-slate-400'
            }`}
          >
            💧 Fără Canalizare ≥50%
          </button>
          <button
            type="button"
            onClick={() => setRequireEducation((v) => !v)}
            className={`rounded-full px-3 py-1 font-semibold transition border ${
              requireEducation
                ? 'bg-purple-500 text-white border-purple-300 shadow-md shadow-purple-500/20'
                : 'bg-slate-800 text-slate-200 border-slate-600 hover:border-slate-400'
            }`}
          >
            🎓 Risc Școlar ≥50%
          </button>
        </div>

                <span className="ml-auto rounded-full border border-emerald-500/40 bg-emerald-950/70 px-3 py-1 text-xs font-bold text-emerald-300">
          {nationalCounties.length > 0 ? 'Național: 3,181 UAT-uri' : '…'}
        </span>
      </div>

      <div className="relative flex-1 flex overflow-hidden">
        {/* National Radar Map - Left Panel */}
        <div className={`flex-1 transition-all duration-300 ${sidebarOpen ? 'w-3/4' : 'w-full'}`}>
          <NationalRadarMap
            onSelectUAT={handleUATSelect}
            initialCounty={county || undefined}
            initialMinRvi={minRvi / 100}
          />
        </div>

        {/* Right Sidebar - UAT Detail Panel */}
        {sidebarOpen && (
          <div className="w-1/4 min-w-[380px] max-w-[480px] border-l border-slate-800 bg-slate-900/95 flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <h2 className="text-lg font-semibold text-white">Detalii UAT</h2>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 transition"
                aria-label="Close sidebar"
              >
                <X size={18} />
              </button>
            </div>

            {selected ? (
              <DossierPanel
                siruta={selected}
                onClose={() => setSelected(null)}
                onStartSurvey={(uatProfile) => {
                  setSurveyInitialUat(uatProfile)
                  setActiveView('survey')
                }}
              />
            ) : (
              <div className="flex-1 flex items-center justify-center p-6">
                <div className="text-center text-slate-500">
                  <MapPin size={48} className="mx-auto mb-4 opacity-30" />
                  <p className="text-base font-medium text-slate-300">Selectează un UAT</p>
                  <p className="text-sm mt-1">Click pe hartă pentru detalii complete</p>
                </div>
              </div>
            )}
          </div>
        )}

        <LiveTelemetryWidget selectedSiruta={selected} />
      </div>
    </div>
  )
}