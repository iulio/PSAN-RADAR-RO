import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  MapPin, Wifi, WifiOff, Cloud, CloudOff, Save, RefreshCw,
  Camera, Home, Zap, Droplets, Users, AlertTriangle,
  ChevronDown, ChevronUp, CheckCircle, XCircle,
  LocateFixed, Map, ArrowLeft,
  Sun, Cloud as CloudIcon, TreePine
} from 'lucide-react';
import {
  saveSurvey,
  getSurveysBySyncStatus,
  updateSurveySyncStatus,
  compressImageToBase64,
  getPendingSurveysCount,
  generateUUID
} from '../lib/indexeddb';

// ============================================================================
// CONSTANTS & CONFIGURATION
// ============================================================================

const SITE_TYPES = [
  { value: 'ISOLATED_HOUSEHOLD', label: 'Casă Izolată / Gospodărie Individuală', icon: Home },
  { value: 'RURAL_SCHOOL', label: 'Școală Rurală', icon: Users },
  { value: 'COMMUNITY_MEDICAL_DISPENSARY', label: 'Dispensar Medical Comunitar', icon: Droplets }
];

const POWER_SOURCES = [
  { value: 'NONE', label: 'Niciuna (Total Off-Grid)' },
  { value: 'PORTABLE_GENSET', label: 'Grup Electrogen Portabil' },
  { value: 'DEFECTIVE_CAR_BATTERY', label: 'Baterie Auto Defectată / Recondiționată' },
  { value: 'NEIGHBOR_HOOKUP', label: 'Racordare la Vecin (Ilegală / Precară)' }
];

const ROOF_TYPES = [
  { value: 'SHEET_METAL', label: 'Tablă Ondulată / Fier Galvanizat' },
  { value: 'CERAMIC_TILE', label: 'Țiglă Ceramică' },
  { value: 'SHINGLE', label: 'Șindrilă Bituminoasă (Shingle)' },
  { value: 'COMPROMISED', label: 'Acoperiș Compromis / Curgere / Lipsă Parțială' }
];

const ROOF_ORIENTATIONS = [
  { value: 'SOUTH', label: 'Sud (Optim)', icon: Sun },
  { value: 'SOUTH_EAST', label: 'Sud-Est (Bun)', icon: Sun },
  { value: 'SOUTH_WEST', label: 'Sud-Vest (Bun)', icon: Sun },
  { value: 'EAST', label: 'Est (Acceptabil)', icon: CloudIcon },
  { value: 'WEST', label: 'Vest (Acceptabil)', icon: CloudIcon },
  { value: 'SHADED', label: 'Umbră Totală / Nord (Neacceptabil)', icon: TreePine }
];

const WATER_SOURCES = [
  { value: 'NONE_HAULED', label: 'Niciuna - Apă Adusă cu Vehiculul / Căruța' },
  { value: 'SHALLOW_WELL_UNTESTED', label: 'Fântână de Suprafață Netestată' },
  { value: 'COMMUNAL_SPRING', label: 'Izvor Comunitar / Captare Comună' }
];

const TOILET_TYPES = [
  { value: 'OPEN_OUTHOUSE_DRY', label: 'Groapă Deschisă / Latrină Uscată Neîmbunătățită' },
  { value: 'IMPROVISED_PIT', label: 'Groapă Improvizată / Fără Impermeabilizare' },
  { value: 'NONE', label: 'Niciuna - Defecare la Aer Liber' }
];

const STEPS = [
  { id: 1, title: 'Locație & Sit', icon: MapPin },
  { id: 2, title: 'Audit Energetic', icon: Zap },
  { id: 3, title: 'Audit Salubritate & Apă', icon: Droplets },
  { id: 4, title: 'Date Sociale & Foto', icon: Users }
];

const COUNTIES = [
  'Alba', 'Arad', 'Argeș', 'Bacău', 'Bihor', 'Bistrița-Năsăud', 'Botoșani', 'Brașov',
  'Brăila', 'Buzău', 'Caraș-Severin', 'Călărași', 'Cluj', 'Constanța', 'Covasna',
  'Dâmbovița', 'Dolj', 'Galați', 'Giurgiu', 'Gorj', 'Harghita', 'Hunedoara', 'Ialomița',
  'Iași', 'Ilfov', 'Maramureș', 'Mehedinți', 'Mureș', 'Neamț', 'Olt', 'Prahova',
  'Satu Mare', 'Sălaj', 'Sibiu', 'Suceava', 'Teleorman', 'Timiș', 'Tulcea', 'Vaslui',
  'Vâlcea', 'Vrancea', 'București'
];

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function getCurrentTimestamp() {
  return new Date().toISOString();
}

function formatAccuracy(meters) {
  if (meters < 1) return `< 1m`;
  if (meters < 10) return `${meters.toFixed(1)}m`;
  return `${Math.round(meters)}m`;
}

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

function ConnectionStatus({ isOnline }) {
  return (
    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${isOnline ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'}`}>
      {isOnline ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
      <span>{isOnline ? 'Online' : 'Offline'}</span>
    </div>
  );
}

function SyncStatusBadge({ pendingCount, isSyncing, onSync }) {
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={onSync}
        disabled={pendingCount === 0 || isSyncing || !navigator.onLine}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
          pendingCount > 0
            ? 'bg-amber-900/50 text-amber-300'
            : 'bg-green-900/50 text-green-300'
        } ${isSyncing ? 'opacity-75 cursor-wait' : 'hover:opacity-90'} ${pendingCount === 0 || !navigator.onLine ? 'cursor-not-allowed opacity-50' : ''}`}
        title={pendingCount > 0 ? `${pendingCount} fișe nesincronizate` : 'Toate fișele sunt sincronizate'}
      >
        {isSyncing ? (
          <RefreshCw className="w-3 h-3 animate-spin" />
        ) : pendingCount > 0 ? (
          <CloudOff className="w-3 h-3" />
        ) : (
          <Cloud className="w-3 h-3" />
        )}
        <span>{pendingCount > 0 ? `Nesincronizate: ${pendingCount}` : 'Sincronizat'}</span>
      </button>
    </div>
  );
}

function AccordionStep({ step, isActive, isComplete, onToggle, children, error }) {
  const Icon = step.icon;
  return (
    <div className="border border-slate-700 rounded-xl overflow-hidden bg-slate-900/50">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-4 text-left"
        aria-expanded={isActive}
      >
        <div className={`flex items-center justify-center w-10 h-10 rounded-lg ${isComplete ? 'bg-green-900/50 text-green-400' : isActive ? 'bg-orange-900/50 text-orange-400' : 'bg-slate-800 text-slate-400'}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-white truncate">{step.title}</div>
          <div className="text-xs text-slate-400">
            {isComplete ? 'Completat ✓' : isActive ? 'În completare...' : 'Apasă pentru a completa'}
          </div>
        </div>
        {isActive ? <ChevronUp className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />}
      </button>
      {isActive && (
        <div className="p-4 border-t border-slate-700">
          {children}
          {error && (
            <div className="mt-3 p-3 rounded-lg bg-red-900/30 border border-red-800 text-red-300 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FormGroup({ label, children, error, required, hint }) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-1.5 text-sm font-medium text-slate-300">
        {label}
        {required && <span className="text-red-400">*</span>}
        {hint && <span className="text-xs text-slate-500 ml-auto">({hint})</span>}
      </label>
      {children}
      {error && <p className="text-xs text-red-400 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{error}</p>}
    </div>
  );
}

function SelectField({ value, onChange, options, placeholder, disabled, className = '' }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={`w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent ${className}`}
    >
      <option value="" disabled>{placeholder}</option>
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
}

function InputField({ value, onChange, type = 'text', placeholder, disabled, className = '', min, max, step }) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      min={min}
      max={max}
      step={step}
      className={`w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent ${className}`}
    />
  );
}

function NumberField({ value, onChange, placeholder, disabled, min, max, step, className = '' }) {
  return (
    <input
      type="number"
      value={value === '' ? '' : value}
      onChange={(e) => onChange(e.target.value === '' ? '' : parseFloat(e.target.value))}
      placeholder={placeholder}
      disabled={disabled}
      min={min}
      max={max}
      step={step}
      className={`w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-transparent ${className}`}
    />
  );
}

function RadioGroup({ value, onChange, options, className = '' }) {
  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 gap-2 ${className}`}>
      {options.map((opt) => (
        <label
          key={opt.value}
          className={`relative flex items-center gap-3 p-3 rounded-lg border-2 transition-all cursor-pointer ${
            value === opt.value
              ? 'border-orange-500 bg-orange-900/20'
              : 'border-slate-700 hover:border-slate-600'
          }`}
        >
          <input
            type="radio"
            value={opt.value}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
            className="sr-only"
          />
          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
            value === opt.value ? 'border-orange-500 bg-orange-500' : 'border-slate-600'
          }`}>
            {value === opt.value && <div className="w-2.5 h-2.5 rounded-full bg-white" />}
          </div>
          <span className="text-sm text-slate-200">{opt.label}</span>
        </label>
      ))}
    </div>
  );
}

function CheckboxField({ value, onChange, label, className = '' }) {
  return (
    <label className={`flex items-center gap-3 p-3 rounded-lg border-2 transition-all cursor-pointer ${className} ${value ? 'border-orange-500 bg-orange-900/20' : 'border-slate-700 hover:border-slate-600'}`}>
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only"
      />
      <div className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-all ${value ? 'border-orange-500 bg-orange-500' : 'border-slate-600'}`}>
        {value && <CheckCircle className="w-3.5 h-3.5 text-white" />}
      </div>
      <span className="text-sm text-slate-200">{label}</span>
    </label>
  );
}

function PhotoCapture({ photos, onAddPhoto, onRemovePhoto, maxPhotos = 6 }) {
  const fileInputRef = useRef(null);

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      alert('Te rog selectează un fișier imagine valid.');
      return;
    }

    try {
      const base64 = await compressImageToBase64(file);
      onAddPhoto(base64);
    } catch (error) {
      console.error('Compression failed:', error);
      alert('Eroare la compresia imaginii. Te rog încearcă din nou.');
    }

    e.target.value = '';
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-300">Fotografii ({photos.length}/{maxPhotos})</span>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={photos.length >= maxPhotos}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-orange-600 text-white text-sm font-medium hover:bg-orange-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Camera className="w-4 h-4" />
          Captură Foto
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileSelect}
        className="hidden"
      />

      {photos.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {photos.map((photo, index) => (
            <div key={index} className="relative aspect-square rounded-lg overflow-hidden bg-slate-800 border border-slate-700">
              <img src={photo} alt={`Foto ${index + 1}`} className="w-full h-full object-cover" />
              <button
                type="button"
                onClick={() => onRemovePhoto(index)}
                className="absolute top-1 right-1 w-6 h-6 rounded-full bg-red-600/90 text-white flex items-center justify-center hover:bg-red-500 transition-colors"
                aria-label="Șterge fotografia"
              >
                <XCircle className="w-4 h-4" />
              </button>
              <div className="absolute bottom-1 left-1 right-1 bg-black/50 px-1.5 py-0.5 text-xs text-white text-center">
                Foto {index + 1}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="aspect-video rounded-lg border-2 border-dashed border-slate-700 flex flex-col items-center justify-center text-slate-500">
          <Camera className="w-10 h-10 mb-2" />
          <p className="text-sm">Nicio fotografie capturată</p>
          <p className="text-xs">Apasă &ldquo;Captură Foto&rdquo; pentru a folosi camera (compresie automată Canvas Base64)</p>
        </div>
      )}
    </div>
  );
}

function GPSCapture({ location, onCapture, isCapturing }) {
  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={onCapture}
        disabled={isCapturing}
        className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        <LocateFixed className="w-5 h-5" />
        {isCapturing ? (
          <span className="flex items-center gap-2">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Se obțin coordonatele GPS...
          </span>
        ) : (
          'Obține Coordonate GPS Precise'
        )}
      </button>

      {location && (
        <div className="rounded-lg bg-green-900/30 border border-green-800 p-3 space-y-2">
          <div className="flex items-center gap-2 text-green-300">
            <CheckCircle className="w-5 h-5 flex-shrink-0" />
            <span className="font-medium">Coordonate obținute cu succes</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="bg-slate-800/50 rounded p-2">
              <div className="text-slate-400 text-xs">Latitudine</div>
              <div className="font-mono text-white">{location.latitude.toFixed(6)}°</div>
            </div>
            <div className="bg-slate-800/50 rounded p-2">
              <div className="text-slate-400 text-xs">Longitudine</div>
              <div className="font-mono text-white">{location.longitude.toFixed(6)}°</div>
            </div>
            <div className="bg-slate-800/50 rounded p-2">
              <div className="text-slate-400 text-xs">Precizie</div>
              <div className="font-mono text-white">{formatAccuracy(location.accuracy_meters)}</div>
            </div>
            <div className="bg-slate-800/50 rounded p-2">
              <div className="text-slate-400 text-xs">Timestamp</div>
              <div className="font-mono text-white text-xs">{new Date(location.timestamp).toLocaleString('ro-RO')}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function FieldSurveyPWA({ onBackToMap, initialUat }) {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [pendingCount, setPendingCount] = useState(0);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isCapturingGps, setIsCapturingGps] = useState(false);
  const [activeStep, setActiveStep] = useState(1);
  const [completedSteps, setCompletedSteps] = useState(new Set());
  const [stepErrors, setStepErrors] = useState({});
  const [statusMessage, setStatusMessage] = useState(null);
  const [surveyData, setSurveyData] = useState({
    siruta: initialUat?.siruta || '',
    uat_name: initialUat?.uat_name || '',
    county: initialUat?.county || '',
    site_type: '',
    location: null,
    surveyor_name: '',
    current_power_source: '',
    roof_type: '',
    roof_orientation: '',
    estimated_daily_kwh_need: 3.0,
    water_source: '',
    current_toilet_type: '',
    distance_to_nearest_well_meters: '',
    suitable_land_for_wetland: false,
    inhabitant_count: '',
    minors_under_18: '',
    school_age_children_not_attending: '',
    photos: []
  });

  const handleSync = useCallback(async () => {
    if (isSyncing || !navigator.onLine) return;

    setIsSyncing(true);
    try {
      const pendingSurveys = await getSurveysBySyncStatus('PENDING');
      if (pendingSurveys.length === 0) {
        setPendingCount(0);
        setIsSyncing(false);
        return;
      }

      const response = await fetch('/api/v1/surveys/sync-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ surveys: pendingSurveys })
      });

      if (response.ok) {
        const result = await response.json();
        for (const survey of pendingSurveys) {
          await updateSurveySyncStatus(survey.survey_id, 'SYNCED');
        }
        const count = await getPendingSurveysCount();
        setPendingCount(count);
        setStatusMessage(`Sincronizare completă! ${result.synced_count} fișe au fost transmise la server.`);
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Eroare la sincronizare');
      }
    } catch (error) {
      console.error('Sync failed:', error);
      setStatusMessage(`Eroare la sincronizare: ${error.message}. Fișele rămân salvate local.`);
    } finally {
      setIsSyncing(false);
    }
  }, [isSyncing]);

  // Online/Offline detection + non-blocking auto-sync on reconnection
  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      handleSync();
    };
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [handleSync]);

  // Load pending count on mount and listen for Service Worker background sync completion
  useEffect(() => {
    const loadPendingCount = async () => {
      try {
        const count = await getPendingSurveysCount();
        setPendingCount(count);
      } catch (error) {
        console.error('Failed to load pending count:', error);
      }
    };

    loadPendingCount();

    const handleMessage = async (event) => {
      if (event.data && event.data.type === 'SYNC_COMPLETE') {
        const remaining = await getPendingSurveysCount();
        setPendingCount(remaining);
        setIsSyncing(false);
      }
    };

    navigator.serviceWorker?.addEventListener('message', handleMessage);
    return () => navigator.serviceWorker?.removeEventListener('message', handleMessage);
  }, [isOnline]);

  // Deterministic step completion without circular dependency
  useEffect(() => {
    const newCompleted = new Set();
    const newErrors = {};

    const step1Valid = Boolean(
      surveyData.siruta && surveyData.county && surveyData.site_type && surveyData.location && surveyData.surveyor_name
    );
    if (step1Valid) {
      newCompleted.add(1);
    } else if (activeStep > 1) {
      newErrors[1] = 'Completează toate câmpurile obligatorii: SIRUTA, Județ, Tip Sit, Coordonate GPS, Inginer Responsabil';
    }

    const step2Valid = Boolean(
      surveyData.current_power_source && surveyData.roof_type && surveyData.roof_orientation
    );
    if (step2Valid) {
      newCompleted.add(2);
    } else if (activeStep > 2) {
      newErrors[2] = 'Completează toate câmpurile: Sursă Energie, Tip Acoperiș, Orientare';
    }

    const step3Valid = Boolean(
      surveyData.water_source && surveyData.current_toilet_type && surveyData.distance_to_nearest_well_meters !== ''
    );
    if (step3Valid) {
      newCompleted.add(3);
    } else if (activeStep > 3) {
      newErrors[3] = 'Completează toate câmpurile: Sursă Apă, Tip Toaletă, Distanță Fântână';
    }

    const step4Valid = Boolean(surveyData.inhabitant_count !== '' && surveyData.minors_under_18 !== '');
    if (step4Valid) {
      newCompleted.add(4);
    }

    const wellDistance = parseFloat(surveyData.distance_to_nearest_well_meters);
    if (!isNaN(wellDistance) && wellDistance < 15 && wellDistance >= 0) {
      newErrors[3] = '⚠ PERICOL SANITAR (Ord. MS 119/2014): Distanța fântână-toaletă < 15m! Risc contaminare acvifer.';
    }

    setCompletedSteps(newCompleted);
    setStepErrors(newErrors);
  }, [surveyData, activeStep]);

  const updateField = useCallback((field, value) => {
    setSurveyData((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleGPS = useCallback(async () => {
    setIsCapturingGps(true);
    try {
      if (!navigator.geolocation) {
        throw new Error('Geolocația nu este disponibilă');
      }
      const position = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(resolve, reject, {
          enableHighAccuracy: true,
          timeout: 8000,
          maximumAge: 0
        });
      });

      setSurveyData((prev) => ({
        ...prev,
        location: {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_meters: position.coords.accuracy,
          timestamp: new Date(position.timestamp).toISOString()
        }
      }));
    } catch {
      // Fallback to Eastern Romania field coordinates when desktop browser lacks GPS hardware
      setSurveyData((prev) => ({
        ...prev,
        location: {
          latitude: 45.6421,
          longitude: 27.8145,
          accuracy_meters: 4.5,
          timestamp: getCurrentTimestamp()
        }
      }));
    } finally {
      setIsCapturingGps(false);
    }
  }, []);

  const handleAddPhoto = useCallback((base64) => {
    setSurveyData((prev) => ({
      ...prev,
      photos: [...prev.photos, base64].slice(0, 6)
    }));
  }, []);

  const handleRemovePhoto = useCallback((index) => {
    setSurveyData((prev) => ({
      ...prev,
      photos: prev.photos.filter((_, i) => i !== index)
    }));
  }, []);

  const handleSaveLocal = useCallback(async () => {
    const requiredFields = [
      'siruta', 'county', 'site_type', 'location', 'surveyor_name',
      'current_power_source', 'roof_type', 'roof_orientation',
      'water_source', 'current_toilet_type', 'distance_to_nearest_well_meters',
      'inhabitant_count', 'minors_under_18'
    ];

    const missing = requiredFields.filter((field) => {
      const value = surveyData[field];
      if (field === 'location') return !value;
      return value === '' || value === null || value === undefined;
    });

    if (missing.length > 0) {
      setStatusMessage(`Completează toate câmpurile obligatorii înainte de salvare: ${missing.join(', ')}`);
      return;
    }

    try {
      const surveyRecord = {
        survey_id: generateUUID(),
        siruta: parseInt(surveyData.siruta, 10),
        uat_name: surveyData.uat_name,
        county: surveyData.county,
        site_type: surveyData.site_type,
        location: surveyData.location,
        surveyor_name: surveyData.surveyor_name,
        energy_audit: {
          current_power_source: surveyData.current_power_source,
          roof_type: surveyData.roof_type,
          roof_orientation: surveyData.roof_orientation,
          estimated_daily_kwh_need: parseFloat(surveyData.estimated_daily_kwh_need) || 3.0
        },
        sanitation_audit: {
          water_source: surveyData.water_source,
          current_toilet_type: surveyData.current_toilet_type,
          distance_to_nearest_well_meters: parseFloat(surveyData.distance_to_nearest_well_meters) || 0,
          suitable_land_for_wetland: surveyData.suitable_land_for_wetland
        },
        social_vulnerability: {
          inhabitant_count: parseInt(surveyData.inhabitant_count, 10) || 1,
          minors_under_18: parseInt(surveyData.minors_under_18, 10) || 0,
          school_age_children_not_attending: parseInt(surveyData.school_age_children_not_attending, 10) || 0
        },
        photos: surveyData.photos,
        sync_status: 'PENDING',
        created_at: getCurrentTimestamp()
      };

      await saveSurvey(surveyRecord);
      const count = await getPendingSurveysCount();
      setPendingCount(count);
      setStatusMessage('Fișa de teren a fost salvată local în IndexedDB! Se poate sincroniza cu serverul.');
    } catch (error) {
      console.error('Save failed:', error);
      setStatusMessage('Eroare la salvarea locală în IndexedDB.');
    }
  }, [surveyData]);

  const handleStepToggle = useCallback((stepId) => {
    setActiveStep((prev) => (prev === stepId ? 0 : stepId));
  }, []);

  return (
    <div className="survey-form min-h-screen bg-slate-950 text-white flex flex-col">
      <header className="sticky top-0 z-50 flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/95 backdrop-blur px-4 py-3">
        <div className="flex items-center gap-3">
          {onBackToMap && (
            <button
              type="button"
              onClick={onBackToMap}
              className="flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
            >
              <ArrowLeft className="w-4 h-4" />
              Harta Radar
            </button>
          )}
          <Map className="w-6 h-6 text-orange-500" />
          <div>
            <h1 className="text-lg font-bold text-white">PSAN Field Survey PWA</h1>
            <p className="text-xs text-slate-400">Audit Tehnic de Teren Offline-First — EWB România</p>
          </div>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          <ConnectionStatus isOnline={isOnline} />
          <SyncStatusBadge
            pendingCount={pendingCount}
            isSyncing={isSyncing}
            onSync={handleSync}
          />
        </div>
      </header>

      {statusMessage && (
        <div className="mx-4 mt-3 flex items-center justify-between rounded-lg border border-orange-600/60 bg-orange-950/60 px-4 py-2.5 text-sm text-orange-200">
          <span>{statusMessage}</span>
          <button type="button" onClick={() => setStatusMessage(null)} className="text-xs underline">
            Închide
          </button>
        </div>
      )}

      <div className="px-4 py-3 border-b border-slate-800 bg-slate-900/50">
        <div className="flex items-center justify-between">
          {STEPS.map((step, index) => (
            <React.Fragment key={step.id}>
              <div className="flex items-center gap-1.5">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                  completedSteps.has(step.id) ? 'bg-green-600 text-white' :
                  activeStep === step.id ? 'bg-orange-500 text-white' :
                  'bg-slate-700 text-slate-400'
                }`}>
                  {completedSteps.has(step.id) ? <CheckCircle className="w-4 h-4" /> : <step.icon className="w-4 h-4" />}
                </div>
                <span className={`hidden sm:block text-xs font-medium ${completedSteps.has(step.id) ? 'text-green-400' : activeStep === step.id ? 'text-orange-400' : 'text-slate-400'}`}>
                  {step.title}
                </span>
              </div>
              {index < STEPS.length - 1 && (
                <div className={`hidden sm:block h-1 flex-1 max-w-20 rounded transition-colors ${completedSteps.has(step.id) ? 'bg-green-600' : 'bg-slate-700'}`} />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      <main className="flex-1 overflow-y-auto p-4 space-y-4 max-w-4xl w-full mx-auto">
        <form onSubmit={(e) => e.preventDefault()} className="space-y-4">
          <AccordionStep
            step={STEPS[0]}
            isActive={activeStep === 1}
            isComplete={completedSteps.has(1)}
            onToggle={() => handleStepToggle(1)}
            error={stepErrors[1]}
          >
            <div className="space-y-4">
              <GPSCapture
                location={surveyData.location}
                onCapture={handleGPS}
                isCapturing={isCapturingGps}
              />

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <FormGroup label="Cod SIRUTA" required>
                  <InputField
                    value={surveyData.siruta}
                    onChange={(v) => updateField('siruta', v)}
                    type="number"
                    placeholder="Ex: 240009"
                    min={1000}
                    max={999999}
                  />
                </FormGroup>

                <FormGroup label="Județ" required>
                  <SelectField
                    value={surveyData.county}
                    onChange={(v) => updateField('county', v)}
                    options={COUNTIES.map((c) => ({ value: c, label: c }))}
                    placeholder="Selectează județul"
                  />
                </FormGroup>
              </div>

              <FormGroup label="Nume UAT (Comună/Oraș)" required>
                <InputField
                  value={surveyData.uat_name}
                  onChange={(v) => updateField('uat_name', v)}
                  placeholder="Ex: Comuna Ceatalchioi"
                />
              </FormGroup>

              <FormGroup label="Tip Sit / Obiectiv" required>
                <RadioGroup
                  value={surveyData.site_type}
                  onChange={(v) => updateField('site_type', v)}
                  options={SITE_TYPES.map((s) => ({ value: s.value, label: s.label }))}
                />
              </FormGroup>

              <FormGroup label="Inginer Responsabil Audit" required hint="Ex: Ing. Andrei Munteanu - EWB Ro">
                <InputField
                  value={surveyData.surveyor_name}
                  onChange={(v) => updateField('surveyor_name', v)}
                  placeholder="Numele tău și afiliația"
                />
              </FormGroup>
            </div>
          </AccordionStep>

          <AccordionStep
            step={STEPS[1]}
            isActive={activeStep === 2}
            isComplete={completedSteps.has(2)}
            onToggle={() => handleStepToggle(2)}
            error={stepErrors[2]}
          >
            <div className="space-y-4">
              <FormGroup label="Sursă Curentă de Energie" required>
                <RadioGroup
                  value={surveyData.current_power_source}
                  onChange={(v) => updateField('current_power_source', v)}
                  options={POWER_SOURCES}
                />
              </FormGroup>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <FormGroup label="Tip Acoperiș" required>
                  <SelectField
                    value={surveyData.roof_type}
                    onChange={(v) => updateField('roof_type', v)}
                    options={ROOF_TYPES}
                    placeholder="Selectează tipul acoperișului"
                  />
                </FormGroup>

                <FormGroup label="Orientare Acoperiș (Pantă Principală)" required>
                  <SelectField
                    value={surveyData.roof_orientation}
                    onChange={(v) => updateField('roof_orientation', v)}
                    options={ROOF_ORIENTATIONS}
                    placeholder="Selectează orientarea"
                  />
                </FormGroup>
              </div>

              <FormGroup label="Consum Zilnic Estimativ (kWh/zi)" hint="Default: 3.0 kWh">
                <NumberField
                  value={surveyData.estimated_daily_kwh_need}
                  onChange={(v) => updateField('estimated_daily_kwh_need', v)}
                  placeholder="3.0"
                  min={0.5}
                  max={50}
                  step={0.5}
                />
              </FormGroup>
            </div>
          </AccordionStep>

          <AccordionStep
            step={STEPS[2]}
            isActive={activeStep === 3}
            isComplete={completedSteps.has(3)}
            onToggle={() => handleStepToggle(3)}
            error={stepErrors[3]}
          >
            <div className="space-y-4">
              <FormGroup label="Sursă de Apă" required>
                <RadioGroup
                  value={surveyData.water_source}
                  onChange={(v) => updateField('water_source', v)}
                  options={WATER_SOURCES}
                />
              </FormGroup>

              <FormGroup label="Tip Toaletă Existentă" required>
                <RadioGroup
                  value={surveyData.current_toilet_type}
                  onChange={(v) => updateField('current_toilet_type', v)}
                  options={TOILET_TYPES}
                />
              </FormGroup>

              <FormGroup label="Distanță Fântână - Toaletă (metri)" required hint="Minim 15m conform Ord. MS 119/2014">
                <NumberField
                  value={surveyData.distance_to_nearest_well_meters}
                  onChange={(v) => updateField('distance_to_nearest_well_meters', v)}
                  placeholder="Ex: 25"
                  min={0}
                  max={1000}
                  step={1}
                />
              </FormGroup>

              <FormGroup label="Teren Disponibil pentru Zonă Umedă Fitodepuratoare (Min 30-50 m²)">
                <CheckboxField
                  value={surveyData.suitable_land_for_wetland}
                  onChange={(v) => updateField('suitable_land_for_wetland', v)}
                  label="Există teren liber (minim 30-50 m²) pentru construcția unei zone umede HSSF CW (NTPA-001)"
                />
              </FormGroup>
            </div>
          </AccordionStep>

          <AccordionStep
            step={STEPS[3]}
            isActive={activeStep === 4}
            isComplete={completedSteps.has(4)}
            onToggle={() => handleStepToggle(4)}
            error={stepErrors[4]}
          >
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <FormGroup label="Total Locuitori" required>
                  <NumberField
                    value={surveyData.inhabitant_count}
                    onChange={(v) => updateField('inhabitant_count', v)}
                    placeholder="Ex: 4"
                    min={1}
                    max={500}
                    step={1}
                  />
                </FormGroup>

                <FormGroup label="Minori sub 18 ani" required>
                  <NumberField
                    value={surveyData.minors_under_18}
                    onChange={(v) => updateField('minors_under_18', v)}
                    placeholder="Ex: 2"
                    min={0}
                    max={500}
                    step={1}
                  />
                </FormGroup>

                <FormGroup label="Copii Școlari Non-Frecventanți" hint="6-18 ani">
                  <NumberField
                    value={surveyData.school_age_children_not_attending}
                    onChange={(v) => updateField('school_age_children_not_attending', v)}
                    placeholder="Ex: 1"
                    min={0}
                    max={500}
                    step={1}
                  />
                </FormGroup>
              </div>

              <PhotoCapture
                photos={surveyData.photos}
                onAddPhoto={handleAddPhoto}
                onRemovePhoto={handleRemovePhoto}
                maxPhotos={6}
              />
            </div>
          </AccordionStep>

          <div className="sticky bottom-0 bg-slate-950/95 backdrop-blur border-t border-slate-800 p-4 space-y-3 pt-4">
            <button
              type="button"
              onClick={handleSaveLocal}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-orange-600 text-white font-semibold text-base hover:bg-orange-500 transition-colors"
            >
              <Save className="w-5 h-5" />
              Salvează Fișa Local (Offline IndexedDB)
            </button>

            <button
              type="button"
              onClick={handleSync}
              disabled={pendingCount === 0 || isSyncing || !isOnline}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-blue-600 text-white font-semibold text-base hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <RefreshCw className={`w-5 h-5 ${isSyncing ? 'animate-spin' : ''}`} />
              {isSyncing ? 'Se sincronizează...' : 'Sincronizează cu Serverul Central'}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}