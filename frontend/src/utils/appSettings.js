export const APP_SETTINGS_STORAGE_KEY = 'skait-app-settings'

export const DEFAULT_APP_SETTINGS = Object.freeze({
  fontSize: 8,
  summaryBatchSeconds: 120,
  llmModel: 'qwen3.5:4b-q4_K_M',
})

export const LLM_MODEL_OPTIONS = Object.freeze([
  'qwen3.5:0.8b-q8_0',
  'qwen3.5:2b-q4_K_M',
  'qwen3.5:4b-q4_K_M',
  'qwen3.5:9b-q4_K_M',
])

const MIN_FONT_SIZE = 8
const MAX_FONT_SIZE = 14
const MIN_SUMMARY_BATCH_SECONDS = 60
const MAX_SUMMARY_BATCH_SECONDS = 300
const KNOWN_LLM_MODELS = new Set([...LLM_MODEL_OPTIONS, 'qwen3:8b'])

export function normalizeAppSettings(value = {}) {
  const fontSize = Number(value.fontSize)
  const summaryBatchSeconds = Number(value.summaryBatchSeconds)
  const llmModel = String(value.llmModel || '')
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
    llmModel: KNOWN_LLM_MODELS.has(llmModel)
      ? llmModel
      : DEFAULT_APP_SETTINGS.llmModel,
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

export function hasStoredLlmModel(storage = globalThis.localStorage) {
  if (!storage) return false
  try {
    const stored = JSON.parse(storage.getItem(APP_SETTINGS_STORAGE_KEY) || '{}')
    return KNOWN_LLM_MODELS.has(String(stored.llmModel || ''))
  } catch {
    return false
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
