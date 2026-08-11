import assert from 'node:assert/strict'
import test from 'node:test'

import {
  APP_SETTINGS_STORAGE_KEY,
  DEFAULT_APP_SETTINGS,
  LLM_MODEL_OPTIONS,
  hasStoredLlmModel,
  loadAppSettings,
  normalizeAppSettings,
  resetAppSettings,
  saveAppSettings,
} from '../src/utils/appSettings.js'

test('지원하는 Qwen 모델 세 가지를 선택할 수 있다', () => {
  assert.deepEqual(LLM_MODEL_OPTIONS, [
    'qwen3:4b-instruct-2507-q4_K_M',
    'qwen3:8b-q4_K_M',
    'qwen3.5:9b-q4_K_M',
  ])
})

function memoryStorage(initialValue = null) {
  let value = initialValue
  return {
    getItem: () => value,
    setItem: (key, nextValue) => {
      assert.equal(key, APP_SETTINGS_STORAGE_KEY)
      value = nextValue
    },
    removeItem: () => {
      value = null
    },
  }
}

test('잘못된 설정값은 안전한 기본값으로 정규화한다', () => {
  assert.deepEqual(
    normalizeAppSettings({
      fontSize: 99,
      summaryBatchSeconds: 30,
      llmModel: 'qwen4:turbo',
    }),
    DEFAULT_APP_SETTINGS,
  )
})

test('사용자 설정을 브라우저 저장소에 저장하고 다시 불러온다', () => {
  const storage = memoryStorage()
  const settings = {
    fontSize: 14,
    summaryBatchSeconds: 73,
    llmModel: 'qwen3.5:9b-q4_K_M',
  }

  saveAppSettings(settings, storage)

  assert.deepEqual(loadAppSettings(storage), settings)
  assert.equal(hasStoredLlmModel(storage), true)
})

test('이전 버전 저장값은 LLM 모델을 명시적으로 선택한 것으로 보지 않는다', () => {
  const storage = memoryStorage(JSON.stringify({ fontSize: 10, summaryBatchSeconds: 90 }))

  assert.equal(hasStoredLlmModel(storage), false)
  assert.equal(loadAppSettings(storage).llmModel, 'qwen3:4b-instruct-2507-q4_K_M')
})

test('설정 초기화는 글자 크기와 요약 생성 주기를 모두 기본값으로 되돌린다', () => {
  assert.deepEqual(
    resetAppSettings(),
    DEFAULT_APP_SETTINGS,
  )
  assert.equal(resetAppSettings().fontSize, 8)
  assert.equal(resetAppSettings().summaryBatchSeconds, 120)
  assert.equal(resetAppSettings().llmModel, 'qwen3:4b-instruct-2507-q4_K_M')
})
