export const APP_SETTINGS_STORAGE_KEY = 'skait-app-settings'

export const DEFAULT_APP_SETTINGS = Object.freeze({
  fontSize: 8,
  summaryBatchSeconds: 120,
})

const MIN_FONT_SIZE = 8
const MAX_FONT_SIZE = 14
const MIN_SUMMARY_BATCH_SECONDS = 60
const MAX_SUMMARY_BATCH_SECONDS = 300

export function normalizeAppSettings(value = {}) {
  const fontSize = Number(value.fontSize)
  const summaryBatchSeconds = Number(value.summaryBatchSeconds)
  return {
    fontSize: Number.isInteger(fontSize)
      && fontSize >= MIN_FONT_SIZE
      && fontSize <= MAX_FONT_SIZE
      ? fontSize
      : DEFAULT_APP_SETTINGS.fontSize,
    summaryBatchSeconds: Number.isInteger(summaryBatchSeconds)
      && summaryBatchSeconds >= MIN_SUMMARY_BATCH_SECONDS
      && summaryBatchSeconds <= MAX_SUMMARY_BATCH_SECONDS
      ? summaryBatchSeconds
      : DEFAULT_APP_SETTINGS.summaryBatchSeconds,
  }
}

export function loadAppSettings(storage = globalThis.localStorage) {
  if (!storage) return { ...DEFAULT_APP_SETTINGS }
  try {
    return normalizeAppSettings(JSON.parse(storage.getItem(APP_SETTINGS_STORAGE_KEY) || '{}'))
  } catch {
    storage.removeItem(APP_SETTINGS_STORAGE_KEY)
    return { ...DEFAULT_APP_SETTINGS }
  }
}

export function saveAppSettings(settings, storage = globalThis.localStorage) {
  const normalized = normalizeAppSettings(settings)
  storage?.setItem(APP_SETTINGS_STORAGE_KEY, JSON.stringify(normalized))
  return normalized
}

export function resetAppSettings() {
  return { ...DEFAULT_APP_SETTINGS }
}
