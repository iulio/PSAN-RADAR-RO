/**
 * NationalRadarMap.jsx
 * ====================
 *
 * MapLibre GL JS choropleth map for all 3,181 Romanian UATs with
 * Composite Rural Vulnerability Index (RVI) visualization.
 *
 * Features:
 * - Romania bounds: [[20.26, 43.62], [29.71, 48.27]]
 * - Source with promoteId: "siruta" for O(1) feature state access
 * - Choropleth fill layer interpolating rvi_score from #22c55e (0.0) to #ef4444 (0.8+)
 * - County filtering dropdown with dynamic setFilter
 * - Fast hover card using feature-state
 * - onSelectUAT(properties) callback on polygon click
 */

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Map, ChevronDown, X, AlertTriangle, Droplet, Zap, GraduationCap, MapPin } from "lucide-react";

// -----------------------------------------------------------------------------
// CONSTANTS
// -----------------------------------------------------------------------------

const ROMANIA_BOUNDS = [
  [20.26, 43.62], // SW
  [29.71, 48.27], // NE
];

const ROMANIA_CENTER = [24.9668, 45.9432]; // Approximate center of Romania
const INITIAL_ZOOM = 6.5;

const GEOJSON_URL = "/api/v1/geo/romania-uat-national";
const COUNTIES_URL = "/api/v1/geo/counties";

// RVI color stops: green (0.0) → yellow (0.4) → orange (0.6) → red (0.8+)
const RVI_COLOR_STOPS = [
  [0.0, "#22c55e"],   // green-500
  [0.2, "#84cc16"],   // lime-500
  [0.4, "#eab308"],   // yellow-500
  [0.5, "#f59e0b"],   // amber-500
  [0.6, "#f97316"],   // orange-500
  [0.7, "#ef4444"],   // red-500
  [0.8, "#dc2626"],   // red-600
  [1.0, "#991b1b"],   // red-800
];

const PRIORITY_TIER_COLORS = {
  CRITICAL: "#991b1b",
  HIGH: "#ef4444",
  MODERATE: "#f59e0b",
};

const INDICATOR_LABELS = {
  i_sewage: { label: "Sewage Deficit", icon: Droplet, color: "#3b82f6" },
  i_water: { label: "Water Deficit", icon: Droplet, color: "#06b6d4" },
  i_energy: { label: "Energy Poverty", icon: Zap, color: "#f59e0b" },
  i_education: { label: "Education Risk", icon: GraduationCap, color: "#8b5cf6" },
  i_isolation: { label: "Isolation Index", icon: MapPin, color: "#64748b" },
};

// -----------------------------------------------------------------------------
// UTILITY FUNCTIONS
// -----------------------------------------------------------------------------

function formatPercent(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatRVI(value) {
  return value.toFixed(3);
}

function getPriorityTier(rvi) {
  if (rvi >= 0.75) return "CRITICAL";
  if (rvi >= 0.50) return "HIGH";
  return "MODERATE";
}

// -----------------------------------------------------------------------------
// HOVER CARD COMPONENT
// -----------------------------------------------------------------------------

function HoverCard({ feature, visible }) {
  if (!visible || !feature) return null;

  const props = feature.properties;
  const rvi = props.rvi_score ?? 0;
  const tier = props.priority_tier ?? getPriorityTier(rvi);

  return (
    <div
      className="fixed z-50 pointer-events-none transition-opacity duration-150"
      style={{
        left: feature.screenX + 16,
        top: feature.screenY + 16,
        opacity: visible ? 1 : 0,
      }}
    >
      <div className="bg-white/95 backdrop-blur-sm rounded-xl shadow-xl border border-slate-200 p-4 min-w-[280px] max-w-[360px]">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex-1 min-w-0">
            <h4 className="font-semibold text-slate-900 truncate">{props.uat_name}</h4>
            <p className="text-sm text-slate-500">Județul {props.county}</p>
          </div>
          <span
            className="px-2 py-1 text-xs font-medium rounded-full whitespace-nowrap shrink-0"
            style={{
              backgroundColor: `${PRIORITY_TIER_COLORS[tier]}20`,
              color: PRIORITY_TIER_COLORS[tier],
            }}
          >
            {tier}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="text-xs text-slate-500 uppercase tracking-wide">RVI Score</p>
            <p className="text-2xl font-bold text-slate-900" style={{ color: getRVIColor(rvi) }}>
              {formatRVI(rvi)}
            </p>
          </div>
          <div className="bg-slate-50 rounded-lg p-3">
            <p className="text-xs text-slate-500 uppercase tracking-wide">SIRUTA</p>
            <p className="text-lg font-mono font-semibold text-slate-900">{props.siruta}</p>
          </div>
        </div>

        <div className="space-y-2 border-t border-slate-100 pt-3">
          <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Deficit Breakdown</p>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(INDICATOR_LABELS).map(([key, { label, icon: Icon, color }]) => {
              const value = props[key];
              if (value === undefined) return null;
              return (
                <div key={key} className="flex items-center gap-2 text-sm">
                  <Icon className="w-4 h-4 flex-shrink-0" style={{ color }} />
                  <span className="text-slate-600 truncate">{label}</span>
                  <span className="font-mono font-semibold ml-auto" style={{ color }}>
                    {formatPercent(value)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-slate-100 flex items-center gap-2 text-xs text-slate-500">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>Click to open detailed dossier</span>
        </div>
      </div>
    </div>
  );
}

function getRVIColor(rvi) {
  if (rvi >= 0.8) return "#991b1b";
  if (rvi >= 0.7) return "#dc2626";
  if (rvi >= 0.6) return "#ef4444";
  if (rvi >= 0.5) return "#f97316";
  if (rvi >= 0.4) return "#f59e0b";
  if (rvi >= 0.2) return "#eab308";
  if (rvi >= 0.1) return "#84cc16";
  return "#22c55e";
}

// -----------------------------------------------------------------------------
// COUNTY FILTER DROPDOWN
// -----------------------------------------------------------------------------

function CountyFilter({ counties, selectedCounty, onChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 bg-white/90 backdrop-blur-sm border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="truncate flex-1">
          {selectedCounty ? `Județul ${selectedCounty}` : "Toate județele"}
        </span>
        <ChevronDown className={`w-4 h-4 text-slate-500 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-64 overflow-auto">
          <button
            onClick={() => onChange(null)}
            className={`w-full px-3 py-2 text-left text-sm transition-colors ${
              !selectedCounty
                ? "bg-blue-50 text-blue-700 font-medium"
                : "text-slate-700 hover:bg-slate-50"
            }`}
          >
            Toate județele
          </button>
          {counties.map((county) => (
            <button
              key={county}
              onClick={() => onChange(county)}
              className={`w-full px-3 py-2 text-left text-sm transition-colors ${
                selectedCounty === county
                  ? "bg-blue-50 text-blue-700 font-medium"
                  : "text-slate-700 hover:bg-slate-50"
              }`}
            >
              Județul {county}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// -----------------------------------------------------------------------------
// LEGEND COMPONENT
// -----------------------------------------------------------------------------

function Legend() {
  return (
    <div className="bg-white/90 backdrop-blur-sm border border-slate-200 rounded-lg p-3 shadow-sm">
      <p className="text-xs font-medium text-slate-700 mb-2">RVI Score</p>
      <div className="flex items-center gap-1">
        {RVI_COLOR_STOPS.slice(0, -1).map(([stop, color], i) => (
          <div
            key={i}
            className="flex-1 h-3"
            style={{
              background: `linear-gradient(to right, ${color}, ${RVI_COLOR_STOPS[i + 1][1]})`,
            }}
          />
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-slate-500 mt-1">
        <span>0.0</span>
        <span>0.2</span>
        <span>0.4</span>
        <span>0.6</span>
        <span>0.8</span>
        <span>1.0</span>
      </div>
      <div className="flex flex-wrap gap-2 mt-2 text-xs">
        {Object.entries(PRIORITY_TIER_COLORS).map(([tier, color]) => (
          <span key={tier} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: color }} />
            {tier}
          </span>
        ))}
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------------
// MAIN COMPONENT
// -----------------------------------------------------------------------------

export default function NationalRadarMap({ onSelectUAT }) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const sourceLoadedRef = useRef(false);

  const [counties, setCounties] = useState([]);
  const [selectedCounty, setSelectedCounty] = useState(null);
  const [hoveredFeature, setHoveredFeature] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch counties on mount
  useEffect(() => {
      const controller = new AbortController();
      async function fetchCounties() {
        try {
          const res = await fetch(COUNTIES_URL, { signal: controller.signal });
          if (!res.ok) throw new Error("Failed to fetch counties");
          const data = await res.json();
          setCounties(data);
        } catch (err) {
          if (err.name !== "AbortError") {
            console.error("County fetch error:", err);
          }
        }
      }
      fetchCounties();
      return () => controller.abort();
    }, []);

  // Initialize MapLibre GL map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {},
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": "#f8fafc" },
          },
        ],
      },
      center: ROMANIA_CENTER,
      zoom: INITIAL_ZOOM,
      maxBounds: ROMANIA_BOUNDS,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution: "© OpenStreetMap contributors, ANCPI/geo-spatial.org",
      }),
      "bottom-right"
    );

    mapRef.current = map;

    // Load GeoJSON source and layers after map loads
    map.on("load", () => {
      loadMapData(map);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      sourceLoadedRef.current = false;
    };
  }, []);

  // Load GeoJSON data and add layers
  const loadMapData = useCallback(async (map) => {
      let sourcedataListener = null;
      try {
        setIsLoading(true);

        // Add source with promoteId for feature-state
        map.addSource("uat-national", {
          type: "geojson",
          data: GEOJSON_URL,
          promoteId: "siruta",
          generateId: true,
        });

        // Wait for source to load
        await new Promise((resolve, reject) => {
          if (map.isSourceLoaded("uat-national")) {
            resolve();
          } else {
            sourcedataListener = (e) => {
              if (e.sourceId === "uat-national" && e.isSourceLoaded) {
                map.off("sourcedata", sourcedataListener);
                resolve();
              }
            };
            map.on("sourcedata", sourcedataListener);
          }
        });

        // Add choropleth fill layer
        map.addLayer({
          id: "uat-fill",
          type: "fill",
          source: "uat-national",
          paint: {
            "fill-color": [
              "interpolate",
              ["linear"],
              ["get", "rvi_score"],
              ...RVI_COLOR_STOPS.flat(),
            ],
            "fill-opacity": 0.75,
            "fill-outline-color": "#ffffff",
          },
        });

        // Add highlight layer for hover
        map.addLayer({
          id: "uat-hover",
          type: "fill",
          source: "uat-national",
          paint: {
            "fill-color": "#ffffff",
            "fill-opacity": 0.5,
            "fill-outline-color": "#1e293b",
          },
          filter: ["==", "siruta", ""],
        });

        // Add border layer
        map.addLayer({
          id: "uat-border",
          type: "line",
          source: "uat-national",
          paint: {
            "line-color": "#ffffff",
            "line-width": 0.5,
            "line-opacity": 0.6,
          },
        });

        sourceLoadedRef.current = true;
        setIsLoading(false);
      } catch (err) {
        console.error("Map data load error:", err);
        setError(err.message);
        setIsLoading(false);
      } finally {
        if (sourcedataListener) {
          map.off("sourcedata", sourcedataListener);
        }
      }
    }, []);

  // Update county filter
  useEffect(() => {
    if (!mapRef.current || !sourceLoadedRef.current) return;

    const map = mapRef.current;
    const filter = selectedCounty
      ? ["==", ["get", "county"], selectedCounty]
      : null;

    ["uat-fill", "uat-hover", "uat-border"].forEach((layerId) => {
      if (map.getLayer(layerId)) {
        map.setFilter(layerId, filter);
      }
    });
  }, [selectedCounty]);

  // Handle hover interactions
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !sourceLoadedRef.current) return;

    let currentHoveredSiruta = null;

    const handleMouseMove = (e) => {
      const features = map.queryRenderedFeatures(e.point, { layers: ["uat-fill"] });
      const feature = features[0];

      if (feature) {
        const siruta = feature.properties.siruta;
        if (siruta !== currentHoveredSiruta) {
          currentHoveredSiruta = siruta;
          map.setFilter("uat-hover", ["==", "siruta", siruta]);
            // Store only necessary properties + screen position (avoid geometry in state)
            const { properties } = feature;
            setHoveredFeature({
              properties: {
                siruta: properties.siruta,
                uat_name: properties.uat_name,
                county: properties.county,
                rvi_score: properties.rvi_score,
                priority_tier: properties.priority_tier,
                i_sewage: properties.i_sewage,
                i_water: properties.i_water,
                i_energy: properties.i_energy,
                i_education: properties.i_education,
                i_isolation: properties.i_isolation,
              },
              screenX: e.point.x,
              screenY: e.point.y,
            });
            map.getCanvas().style.cursor = "pointer";
          }
        } else if (currentHoveredSiruta !== null) {
          currentHoveredSiruta = null;
          map.setFilter("uat-hover", ["==", "siruta", ""]);
          setHoveredFeature(null);
          map.getCanvas().style.cursor = "";
        }
      };

      const handleMouseLeave = () => {
        currentHoveredSiruta = null;
        map.setFilter("uat-hover", ["==", "siruta", ""]);
        setHoveredFeature(null);
        map.getCanvas().style.cursor = "";
    };

      const handleClick = (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ["uat-fill"] });
        if (features[0] && onSelectUAT) {
          onSelectUAT(features[0].properties);
        }
      };

      map.on("mousemove", handleMouseMove);
      map.on("mouseleave", handleMouseLeave);
      map.on("click", handleClick);

      return () => {
        map.off("mousemove", handleMouseMove);
        map.off("mouseleave", handleMouseLeave);
        map.off("click", handleClick);
      };
    }, [onSelectUAT]);

  // Render
  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-50">
        <div className="text-center p-6">
          <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-3" />
          <p className="text-slate-600">Failed to load map data</p>
          <p className="text-sm text-slate-400 mt-1">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex-1 flex flex-col bg-slate-50">
      {/* Map Container */}
      <div
        ref={mapContainerRef}
        className="flex-1 w-full"
        style={{ minHeight: 400 }}
      />

      {/* Loading Overlay */}
      {isLoading && (
        <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-20">
          <div className="text-center">
            <div className="w-10 h-10 border-3 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-slate-600">Loading national UAT data...</p>
          </div>
        </div>
      )}

      {/* Top Controls */}
      <div className="absolute top-4 left-4 right-4 z-10 flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between max-w-5xl mx-auto">
        <div className="bg-white/90 backdrop-blur-sm border border-slate-200 rounded-lg p-3 shadow-sm flex-1 max-w-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Filter by County</p>
          <CountyFilter
            counties={counties}
            selectedCounty={selectedCounty}
            onChange={setSelectedCounty}
          />
        </div>

        <div className="flex-1 max-w-md" />
        <Legend />
      </div>

      {/* Hover Card */}
      <HoverCard feature={hoveredFeature} visible={!!hoveredFeature} />

      {/* Bottom Attribution */}
      <div className="absolute bottom-2 left-2 right-2 z-10 flex justify-center">
        <div className="bg-white/80 backdrop-blur-sm border border-slate-200 rounded-full px-3 py-1 text-xs text-slate-500 shadow-sm">
          Source: ANCPI / geo-spatial.org · {counties.length} counties · ~3,181 UATs
        </div>
      </div>
    </div>
  );
}