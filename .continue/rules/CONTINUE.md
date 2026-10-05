# PSAN Radar - Project Guide

## Project Overview

**PSAN Radar** (Poverty & Sanitation Assessment Navigator) is a mission-critical GIS decision-support platform for **Engineers Without Borders Romania (Ingineri Fără Frontiere)**. It provides deterministic engineering sizing, permitting compliance, volunteer dispatch, EU grant preparation, and real-time IoT telemetry for rural infrastructure projects across Eastern & North-Eastern Romania.

### Key Technologies
- **Backend**: FastAPI (Python 3.11+), GeoPandas, Shapely, Pandas, NumPy
- **Frontend**: React 18, Vite, Tailwind CSS, Leaflet (react-leaflet), Lucide React
- **Database**: GeoJSON file-based storage with O(1) in-memory SIRUTA hash map index
- **Real-time**: WebSocket telemetry engine with alerting
- **Deployment**: Docker Compose (backend + frontend + nginx)
- **Testing**: pytest (async), Playwright for E2E

### High-Level Architecture
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   Backend       │────▶│   GeoJSON Data  │
│   (React/Vite)  │     │   (FastAPI)     │     │   (UAT Polygons)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Modular Routers│
                    │  • Field Surveys│
                    │  • Telemetry    │
                    │  • Volunteers   │
                    │  • Marketplace  │
                    └─────────────────┘
```

---

## Getting Started

### Prerequisites
- **Docker** & **Docker Compose** (recommended)
- **Python 3.11+** (for local backend development)
- **Node.js 20+** (for local frontend development)
- **Ollama** (optional, for local LLM grant narrative generation)

### Quick Start with Docker
```bash
# Clone and start all services
git clone <repo-url>
cd psan-radar
docker-compose up --build -d

# Verify services
curl http://localhost:8000/api/v1/health
# Frontend available at http://localhost:8080
```

### Local Development

#### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Generate/refresh GeoJSON data (first run)
python scripts/download_real_boundaries.py

# Start development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend
```bash
cd frontend
npm install
npm run dev  # Starts Vite dev server on http://localhost:5173
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_BASE_URL` | Ollama API base URL | `http://host.docker.internal:11434` |
| `LLM_MODEL` | Model name for grant narratives | `qwen2.5:7b` |
| `LLM_API_MODE` | `ollama` or `openai` | `ollama` |
| `LLM_TIMEOUT` | Request timeout (seconds) | `120` |

### Running Tests
```bash
# Full E2E test suite (requires running services)
./run_e2e_tests.sh

# Backend tests only
cd tests && python -m pytest test_backend_e2e.py -v

# Frontend tests only
cd tests && python -m pytest test_frontend_e2e.py -v
```

---

## Project Structure

```
psan-radar/
├── .continue/rules/           # Continue rules (this file)
├── backend/
│   ├── data/                  # GeoJSON data files (gitignored large files)
│   │   ├── romania_uat_raw.geojson
│   │   └── uat_vulnerability.geojson
│   ├── scripts/
│   │   └── download_real_boundaries.py  # Fetches real ANCPI boundaries
│   ├── main.py                # FastAPI app entry point (2000+ lines)
│   ├── compliance_navigator.py       # Module 1: Permitting roadmap
│   ├── engineering_sizing.py         # Phase 8: BOM & CAPEX calculator
│   ├── field_surveys.py              # Phase 9: Field survey sync + PWA
│   ├── grant_narrative_agent.py      # LLM grant narrative generator
│   ├── ingest_real_data.py           # Legacy data ingestion
│   ├── materials_marketplace.py      # Module 3: CSR marketplace
│   ├── pdf_generator.py              # PDF dossier export (ReportLab)
│   ├── telemetry_engine.py           # Phase 10: IoT WebSocket engine
│   ├── volunteer_dispatch.py         # Module 2: Volunteer matcher
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── FieldSurveyPWA.jsx      # Offline-capable survey form
│   │   │   └── LiveTelemetryWidget.jsx # Real-time WebSocket dashboard
│   │   ├── lib/                        # Utilities, API client
│   │   ├── App.jsx                     # Main app (large, map-centric)
│   │   ├── main.jsx
│   │   └── index.css
│   ├── public/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── nginx.conf
│   └── Dockerfile
├── tests/
│   ├── test_backend_e2e.py      # Comprehensive async pytest suite
│   ├── test_frontend_e2e.py     # Playwright E2E tests
│   └── pytest.ini
├── docker-compose.yml
├── run_e2e_tests.sh
└── plan.md
```

### Key Files & Responsibilities

| File | Purpose |
|------|---------|
| `backend/main.py` | Core API, O(1) SIRUTA index, dossier generation, BOM, PDF, grant narrative |
| `backend/engineering_sizing.py` | Deterministic BOM calculations for PV, sanitation, education |
| `backend/field_surveys.py` | PWA sync engine, SQLite offline queue, cache invalidation hook |
| `backend/telemetry_engine.py` | WebSocket server, battery threshold alerts, asset registry |
| `backend/compliance_navigator.py` | Romanian permitting checklist (Legea 50/1991, ANRE, NTPA-001/011) |
| `backend/volunteer_dispatch.py` | Haversine-based volunteer matching |
| `backend/materials_marketplace.py` | CSR lot management, allocation, SQLite persistence |
| `frontend/src/App.jsx` | Map UI, filtering, dossier panel, BOM calculator, grant narrative |
| `frontend/src/components/FieldSurveyPWA.jsx` | Offline-first survey form with IndexedDB |
| `frontend/src/components/LiveTelemetryWidget.jsx` | Real-time telemetry dashboard |
| `backend/scripts/download_real_boundaries.py` | Downloads real ANCPI boundaries from geoBoundaries |

---

## Development Workflow

### Coding Standards
- **Python**: Type hints mandatory (Pydantic v2), async/await for I/O
- **JavaScript/React**: Functional components, hooks, Tailwind for styling
- **API**: RFC 7807 Problem Details for errors, RESTful design
- **GeoJSON**: RFC 7946 compliance, EPSG:4326 (WGS84)

### Testing Approach
1. **Unit/Integration**: pytest-asyncio for backend endpoints
2. **E2E**: Playwright for frontend user flows
3. **Deterministic**: Fixed seeds (42) for reproducible BOM calculations
4. **Isolation**: Each test uses fresh SIRUTA from live GeoJSON

### Build & Deployment
```bash
# Production build
docker-compose -f docker-compose.yml up --build -d

# Frontend production build (static files served by nginx)
cd frontend && npm run build

# Backend production (Gunicorn + Uvicorn workers)
cd backend && gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

### Contribution Guidelines
1. Run `./run_e2e_tests.sh` before submitting PR
2. Follow existing code patterns in `main.py` for new endpoints
3. Add Pydantic models for all request/response bodies
4. Update GeoJSON schema docs if adding properties

---

## Key Concepts

### Domain Terminology
| Term | Definition |
|------|------------|
| **UAT** | Unitatea Administrativ-Teritorială (Romanian LAU2: commune, town, municipality) |
| **SIRUTA** | Sistemul Informațional al Registrului Unităților Teritoriale (unique 6-digit integer code) |
| **RVI** | Radar Vulnerability Index (0-100): weighted composite of sanitation, energy, education, marginalization |
| **Priority Tier** | CRITICAL (≥75), HIGH (50-74), MODERATE (<50) |
| **i_sanitation** | Normalized deficit index for sanitation access (0-1) |
| **i_energy** | Normalized deficit index for off-grid/unelectrified households (0-1) |
| **i_education** | Normalized deficit index for school dropout risk (0-1) |
| **i_marginalization** | Composite socio-economic marginalization index (0-1) |
| **BOM** | Bill of Materials - itemized equipment + labor + contingency |
| **CAPEX** | Capital Expenditure - total project cost in EUR |
| **ETF** | Evaluare Tehnică și Financiară (MySMIS technical-financial scorecard) |

### Core Abstractions
1. **O(1) SIRUTA Hash Map** - `_siruta_index` dict in `main.py` for instant UAT lookup
2. **Cached GeoJSON** - `_cached_geojson_dict` serialized FeatureCollection for fast responses
3. **Deterministic Engineering** - Pure functions in `engineering_sizing.py` with fixed coefficients
4. **Modular Routers** - Feature-separated routers mounted in `main.py`
5. **Cache Invalidation Hook** - `register_geojson_update_callback` for live data updates

### Design Patterns
- **Dependency Injection**: FastAPI `Depends` for HTTP clients, fixtures in tests
- **Repository Pattern**: Implicit via GeoPandas + in-memory index
- **Observer Pattern**: GeoJSON update callbacks for cache invalidation
- **Factory Pattern**: `generate_dossier_for_uat()` creates complete EU project dossiers
- **Strategy Pattern**: `InterventionType` enum drives BOM calculation branching

---

## Common Tasks

### Add a New UAT Property to GeoJSON
1. Update `download_real_boundaries.py` to compute/assign the property
2. Regenerate data: `python scripts/download_real_boundaries.py`
3. Add property to `UATProfile` model in `main.py` if exposed via API
4. Update frontend TypeScript interfaces (if using TS) or component props

### Add a New Intervention Type
1. Add enum value to `InterventionType` in `engineering_sizing.py`
2. Implement calculation logic in `calculate_bom()` function
3. Add Pydantic models for new parameters
4. Add endpoint handling in `main.py` `/calculate-bom`
5. Update frontend BOM calculator component

### Create a New Module (Router)
1. Create `backend/new_module.py` with `router = APIRouter(prefix="/api/v1/new-module", tags=["New Module"])`
2. Define Pydantic models, endpoints
3. Import and mount in `main.py`: `app.include_router(new_module.router)`
4. Add tests in `tests/test_backend_e2e.py`

### Run GeoJSON Regeneration
```bash
cd backend
python scripts/download_real_boundaries.py
# Outputs: data/romania_uat_raw.geojson, data/uat_vulnerability.geojson
# Restart backend to reload cache
```

### Debug WebSocket Telemetry
```bash
# Connect manually
wscat -c ws://localhost:8000/api/v1/telemetry/ws

# Ingest test packet
curl -X POST http://localhost:8000/api/v1/telemetry/ingest \
  -H "Content-Type: application/json" \
  -d '{"asset_id":"test-1","siruta":240009,"battery_soc_percent":15.0,"pv_power_watts":1000,"load_power_watts":500}'
```

---

## Troubleshooting

### Backend Won't Start
| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: geopandas` | Install system deps: `apt-get install libgdal-dev gdal-bin` then `pip install -r requirements.txt` |
| `GeoJSON file missing` | Run `python scripts/download_real_boundaries.py` |
| `Port 8000 in use` | `lsof -ti:8000 | xargs kill -9` or change port in `uvicorn` command |

### Frontend Issues
| Issue | Solution |
|-------|----------|
| Map not loading | Check Leaflet CSS import in `main.jsx`: `import 'leaflet/dist/leaflet.css'` |
| API calls failing | Verify `VITE_API_BASE_URL` or proxy config in `vite.config.js` |
| Tailwind not applying | Ensure `@tailwind base; @tailwind components; @tailwind utilities;` in `index.css` |

### Data Issues
| Issue | Solution |
|-------|----------|
| Empty GeoJSON | Re-run `download_real_boundaries.py` - check network access to geoBoundaries |
| Wrong SIRUTA codes | Verify `COUNTY_SIRUTA_PREFIX` mapping matches official codes |
| RVI calculation off | Check `compute_rvi_and_tier()` weights: 0.30*san + 0.30*ene + 0.25*edu + 0.15*marg |

### Test Failures
| Issue | Solution |
|-------|----------|
| Backend tests timeout | Increase `TIMEOUT` in `test_backend_e2e.py`, check server logs |
| Playwright browser missing | Run `python -m playwright install chromium` |
| WebSocket tests skipped | Ensure telemetry engine is running and WebSocket endpoint implemented |

---

## References

### Official Documentation
- [FastAPI](https://fastapi.tiangolo.com/)
- [GeoPandas](https://geopandas.org/)
- [React Leaflet](https://react-leaflet.js.org/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Playwright Python](https://playwright.dev/python/)

### Romanian Regulatory References
- **Legea 50/1991 Art. 11 lit. m** - Construction authorization for isolated households
- **ANRE Ordin 11/2023** - Technical connection conditions for prosumers
- **NTPA-001/011** - Wastewater discharge limits (Apele Române)
- **HG 907/2016** - Eligible expenditure categories for EU funds
- **SR EN 62124** - Photovoltaic standalone systems design verification

### Project-Specific
- **geoBoundaries Romania** - Source for official ADM1/ADM2 boundaries
- **MySMIS 2021+** - Romanian EU funds management system
- **PoIDS 2021-2027** - Programul Operațional Infrastructură De Dezvoltare Socială
- **PNRR Componenta 15** - Educație (EduPod digital hubs)
- **Fondul pentru Modernizare** - Off-grid electrification grants

---

## Notes for Maintainers

> **⚠️ Verification Needed**: The following sections are based on code analysis and may need verification against actual deployment:
> - Production deployment specifics (SSL, domain, monitoring)
> - Exact CI/CD pipeline configuration
> - LLM integration details (prompt engineering, fallback behavior)
> - CSR marketplace SQLite schema evolution strategy
> - Volunteer database seeding and maintenance process

> **🔧 Extending the Guide**: Create additional `.md` files in `.continue/rules/` for component-specific documentation (e.g., `field-surveys.md`, `telemetry.md`, `grant-narrative.md`) and they will be automatically loaded by Continue when working in those directories.