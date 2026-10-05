// Service Worker for PSAN Field Survey PWA
// Provides offline-first caching for app shell and assets

const CACHE_NAME = 'psan-field-survey-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

const API_CACHE_NAME = 'psan-api-cache-v1';
const TILE_CACHE_NAME = 'psan-tile-cache-v1';

// Install event - cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME && name !== API_CACHE_NAME && name !== TILE_CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch event - serve from cache when offline
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Handle API requests - Network First with cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirstStrategy(request, API_CACHE_NAME));
    return;
  }

  // Handle CartoDB / Esri / OSM tile requests - Cache First
  if (
    url.hostname.includes('basemaps.cartocdn.com') ||
    url.hostname.includes('tile.openstreetmap.org') ||
    url.hostname.includes('arcgisonline.com')
  ) {
    event.respondWith(cacheFirstStrategy(request, TILE_CACHE_NAME));
    return;
  }

  // Handle static assets - Cache First
  event.respondWith(cacheFirstStrategy(request, CACHE_NAME));
});

// Cache First Strategy - for static assets and tiles
async function cacheFirstStrategy(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);

  if (cachedResponse) {
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    // Return offline fallback for navigation requests
    if (request.mode === 'navigate') {
      return cache.match('/index.html');
    }
    throw error;
  }
}

// Network First Strategy - for API requests
async function networkFirstStrategy(request, cacheName) {
  const cache = await caches.open(cacheName);

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    const cachedResponse = await cache.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // Return offline response for API
    return new Response(
      JSON.stringify({ error: 'Offline', message: 'Nu există conexiune la internet' }),
      {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

// Background Sync for pending surveys
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-surveys') {
    event.waitUntil(syncPendingSurveys());
  }
});

// Sync pending surveys when online
async function syncPendingSurveys() {
  try {
    const db = await openIndexedDB();
    const pendingSurveys = await getPendingSurveys(db);

    if (pendingSurveys.length === 0) {
      return;
    }

    const response = await fetch('/api/v1/surveys/sync-batch', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ surveys: pendingSurveys })
    });

    if (response.ok) {
      const result = await response.json();
      // Mark surveys as synced
      for (const survey of pendingSurveys) {
        await updateSurveySyncStatus(db, survey.survey_id, 'SYNCED');
      }
      // Notify clients
      self.clients.matchAll().then((clients) => {
        clients.forEach((client) => {
          client.postMessage({
            type: 'SYNC_COMPLETE',
            syncedCount: result.synced_count
          });
        });
      });
    }
  } catch (error) {
    console.error('Sync failed:', error);
  }
}

// IndexedDB helpers for service worker
function openIndexedDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('psan-field-surveys', 1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('surveys')) {
        db.createObjectStore('surveys', { keyPath: 'survey_id' });
      }
      if (!db.objectStoreNames.contains('sync-queue')) {
        db.createObjectStore('sync-queue', { keyPath: 'id', autoIncrement: true });
      }
    };
  });
}

function getPendingSurveys(db) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('surveys', 'readonly');
    const store = transaction.objectStore('surveys');
    const request = store.getAll();
    request.onsuccess = () => {
      const pending = request.result.filter((s) => s.sync_status === 'PENDING');
      resolve(pending);
    };
    request.onerror = () => reject(request.error);
  });
}

function updateSurveySyncStatus(db, surveyId, status) {
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('surveys', 'readwrite');
    const store = transaction.objectStore('surveys');
    const getRequest = store.get(surveyId);
    getRequest.onsuccess = () => {
      const survey = getRequest.result;
      if (survey) {
        survey.sync_status = status;
        survey.last_sync_attempt = new Date().toISOString();
        const putRequest = store.put(survey);
        putRequest.onsuccess = () => resolve();
        putRequest.onerror = () => reject(putRequest.error);
      } else {
        resolve();
      }
    };
    getRequest.onerror = () => reject(getRequest.error);
  });
}

// Listen for messages from clients
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'SYNC_NOW') {
    syncPendingSurveys();
  }
});