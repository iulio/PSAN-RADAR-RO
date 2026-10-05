// IndexedDB Helper for PSAN Field Survey
// Provides offline storage for survey records, photos, and sync queue

const DB_NAME = 'psan-field-surveys';
const DB_VERSION = 1;
const STORES = {
  SURVEYS: 'surveys',
  PHOTOS: 'photos',
  SYNC_QUEUE: 'sync-queue'
};

let dbPromise = null;

/**
 * Initialize and open the IndexedDB database
 * @returns {Promise<IDBDatabase>} Database instance
 */
export async function initDB() {
  if (dbPromise) {
    return dbPromise;
  }

  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => {
      dbPromise = null;
      reject(new Error(`Failed to open IndexedDB: ${request.error}`));
    };

    request.onsuccess = () => {
      resolve(request.result);
    };

    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      // Surveys store - main survey records
      if (!db.objectStoreNames.contains(STORES.SURVEYS)) {
        const surveyStore = db.createObjectStore(STORES.SURVEYS, { keyPath: 'survey_id' });
        surveyStore.createIndex('sync_status', 'sync_status', { unique: false });
        surveyStore.createIndex('siruta', 'siruta', { unique: false });
        surveyStore.createIndex('created_at', 'created_at', { unique: false });
      }

      // Photos store - compressed photo blobs
      if (!db.objectStoreNames.contains(STORES.PHOTOS)) {
        const photoStore = db.createObjectStore(STORES.PHOTOS, { keyPath: 'photo_id' });
        photoStore.createIndex('survey_id', 'survey_id', { unique: false });
      }

      // Sync queue store - tracks pending sync operations
      if (!db.objectStoreNames.contains(STORES.SYNC_QUEUE)) {
        const syncStore = db.createObjectStore(STORES.SYNC_QUEUE, { keyPath: 'id', autoIncrement: true });
        syncStore.createIndex('survey_id', 'survey_id', { unique: false });
        syncStore.createIndex('status', 'status', { unique: false });
        syncStore.createIndex('created_at', 'created_at', { unique: false });
      }
    };
  });

  return dbPromise;
}

/**
 * Get database instance, initializing if needed
 * @returns {Promise<IDBDatabase>}
 */
export async function getDB() {
  if (!dbPromise) {
    return initDB();
  }
  return dbPromise;
}

/**
 * Generate a UUID v4
 * @returns {string}
 */
export function generateUUID() {
  return crypto.randomUUID();
}

/**
 * Compress an image file to base64 string under target size
 * @param {File} file - Image file to compress
 * @param {number} maxSizeKB - Maximum size in KB (default 300)
 * @param {number} quality - JPEG quality 0-1 (default 0.7)
 * @returns {Promise<string>} Base64 encoded compressed image
 */
export async function compressImageToBase64(file, maxSizeKB = 300, quality = 0.7) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');

        // Calculate new dimensions maintaining aspect ratio
        let { width, height } = img;
        const maxDimension = 1200;

        if (width > maxDimension || height > maxDimension) {
          if (width > height) {
            height = (height / width) * maxDimension;
            width = maxDimension;
          } else {
            width = (width / height) * maxDimension;
            height = maxDimension;
          }
        }

        canvas.width = width;
        canvas.height = height;
        ctx.drawImage(img, 0, 0, width, height);

        // Try different quality levels to get under size limit
        let currentQuality = quality;
        let base64 = canvas.toDataURL('image/jpeg', currentQuality);

        // Reduce quality until under size limit
        while (base64.length > maxSizeKB * 1024 && currentQuality > 0.1) {
          currentQuality -= 0.1;
          base64 = canvas.toDataURL('image/jpeg', currentQuality);
        }

        // If still too large, reduce dimensions
        while (base64.length > maxSizeKB * 1024 && width > 400) {
          width *= 0.8;
          height *= 0.8;
          canvas.width = width;
          canvas.height = height;
          ctx.drawImage(img, 0, 0, width, height);
          base64 = canvas.toDataURL('image/jpeg', currentQuality);
        }

        resolve(base64);
      };
      img.onerror = () => reject(new Error('Failed to load image'));
      img.src = e.target.result;
    };
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsDataURL(file);
  });
}

/**
 * Save a survey record to IndexedDB
 * @param {Object} survey - Survey record to save
 * @returns {Promise<string>} Survey ID
 */
export async function saveSurvey(survey) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SURVEYS, 'readwrite');
    const store = transaction.objectStore(STORES.SURVEYS);

    const surveyToSave = {
      ...survey,
      survey_id: survey.survey_id || generateUUID(),
      created_at: survey.created_at || new Date().toISOString(),
      updated_at: new Date().toISOString(),
      sync_status: survey.sync_status || 'PENDING'
    };

    const request = store.put(surveyToSave);
    request.onsuccess = () => resolve(surveyToSave.survey_id);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Get a survey by ID
 * @param {string} surveyId - Survey ID
 * @returns {Promise<Object|null>} Survey record or null
 */
export async function getSurvey(surveyId) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SURVEYS, 'readonly');
    const store = transaction.objectStore(STORES.SURVEYS);
    const request = store.get(surveyId);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Get all surveys
 * @returns {Promise<Array>} Array of survey records
 */
export async function getAllSurveys() {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SURVEYS, 'readonly');
    const store = transaction.objectStore(STORES.SURVEYS);
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Get surveys by sync status
 * @param {string} status - Sync status (PENDING, SYNCED, SYNC_FAILED)
 * @returns {Promise<Array>} Array of survey records
 */
export async function getSurveysBySyncStatus(status) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SURVEYS, 'readonly');
    const store = transaction.objectStore(STORES.SURVEYS);
    const index = store.index('sync_status');
    const request = index.getAll(status);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Update survey sync status
 * @param {string} surveyId - Survey ID
 * @param {string} status - New sync status
 * @returns {Promise<void>}
 */
export async function updateSurveySyncStatus(surveyId, status) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SURVEYS, 'readwrite');
    const store = transaction.objectStore(STORES.SURVEYS);
    const getRequest = store.get(surveyId);
    getRequest.onsuccess = () => {
      const survey = getRequest.result;
      if (survey) {
        survey.sync_status = status;
        survey.last_sync_attempt = new Date().toISOString();
        if (status === 'SYNCED') {
          survey.synced_at = new Date().toISOString();
        }
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

/**
 * Delete a survey
 * @param {string} surveyId - Survey ID
 * @returns {Promise<void>}
 */
export async function deleteSurvey(surveyId) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SURVEYS, 'readwrite');
    const store = transaction.objectStore(STORES.SURVEYS);
    const request = store.delete(surveyId);
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
  });
}

/**
 * Save a photo to IndexedDB
 * @param {Object} photo - Photo record
 * @returns {Promise<string>} Photo ID
 */
export async function savePhoto(photo) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.PHOTOS, 'readwrite');
    const store = transaction.objectStore(STORES.PHOTOS);

    const photoToSave = {
      ...photo,
      photo_id: photo.photo_id || generateUUID(),
      created_at: photo.created_at || new Date().toISOString()
    };

    const request = store.put(photoToSave);
    request.onsuccess = () => resolve(photoToSave.photo_id);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Get photos for a survey
 * @param {string} surveyId - Survey ID
 * @returns {Promise<Array>} Array of photo records
 */
export async function getPhotosForSurvey(surveyId) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.PHOTOS, 'readonly');
    const store = transaction.objectStore(STORES.PHOTOS);
    const index = store.index('survey_id');
    const request = index.getAll(surveyId);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Add survey to sync queue
 * @param {string} surveyId - Survey ID
 * @returns {Promise<number>} Queue entry ID
 */
export async function addToSyncQueue(surveyId) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SYNC_QUEUE, 'readwrite');
    const store = transaction.objectStore(STORES.SYNC_QUEUE);
    const request = store.add({
      survey_id: surveyId,
      status: 'PENDING',
      created_at: new Date().toISOString(),
      attempts: 0
    });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Get pending sync queue entries
 * @returns {Promise<Array>} Array of sync queue entries
 */
export async function getPendingSyncQueue() {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SYNC_QUEUE, 'readonly');
    const store = transaction.objectStore(STORES.SYNC_QUEUE);
    const index = store.index('status');
    const request = index.getAll('PENDING');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Update sync queue entry status
 * @param {number} queueId - Queue entry ID
 * @param {string} status - New status
 * @returns {Promise<void>}
 */
export async function updateSyncQueueStatus(queueId, status) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SYNC_QUEUE, 'readwrite');
    const store = transaction.objectStore(STORES.SYNC_QUEUE);
    const getRequest = store.get(queueId);
    getRequest.onsuccess = () => {
      const entry = getRequest.result;
      if (entry) {
        entry.status = status;
        entry.updated_at = new Date().toISOString();
        if (status === 'SYNCED' || status === 'FAILED') {
          entry.completed_at = new Date().toISOString();
        }
        const putRequest = store.put(entry);
        putRequest.onsuccess = () => resolve();
        putRequest.onerror = () => reject(putRequest.error);
      } else {
        resolve();
      }
    };
    getRequest.onerror = () => reject(getRequest.error);
  });
}

/**
 * Increment sync attempt counter
 * @param {number} queueId - Queue entry ID
 * @returns {Promise<void>}
 */
export async function incrementSyncAttempts(queueId) {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORES.SYNC_QUEUE, 'readwrite');
    const store = transaction.objectStore(STORES.SYNC_QUEUE);
    const getRequest = store.get(queueId);
    getRequest.onsuccess = () => {
      const entry = getRequest.result;
      if (entry) {
        entry.attempts = (entry.attempts || 0) + 1;
        entry.last_attempt = new Date().toISOString();
        const putRequest = store.put(entry);
        putRequest.onsuccess = () => resolve();
        putRequest.onerror = () => reject(putRequest.error);
      } else {
        resolve();
      }
    };
    getRequest.onerror = () => reject(getRequest.error);
  });
}

/**
 * Get count of pending surveys
 * @returns {Promise<number>} Count of pending surveys
 */
export async function getPendingSurveysCount() {
  const surveys = await getSurveysBySyncStatus('PENDING');
  return surveys.length;
}

/**
 * Clear all data (for testing/reset)
 * @returns {Promise<void>}
 */
export async function clearAllData() {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction([STORES.SURVEYS, STORES.PHOTOS, STORES.SYNC_QUEUE], 'readwrite');
    const surveysStore = transaction.objectStore(STORES.SURVEYS);
    const photosStore = transaction.objectStore(STORES.PHOTOS);
    const syncStore = transaction.objectStore(STORES.SYNC_QUEUE);

    surveysStore.clear();
    photosStore.clear();
    syncStore.clear();

    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
}

/**
 * Export all surveys as JSON
 * @returns {Promise<string>} JSON string of all surveys
 */
export async function exportSurveysAsJSON() {
  const surveys = await getAllSurveys();
  return JSON.stringify(surveys, null, 2);
}

/**
 * Import surveys from JSON
 * @param {string} jsonString - JSON string of surveys
 * @returns {Promise<number>} Number of imported surveys
 */
export async function importSurveysFromJSON(jsonString) {
  const surveys = JSON.parse(jsonString);
  let count = 0;
  for (const survey of surveys) {
    await saveSurvey(survey);
    count++;
  }
  return count;
}