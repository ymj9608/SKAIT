import assert from 'node:assert/strict'
import test from 'node:test'

import {
  APP_SETTINGS_STORAGE_KEY,
  DEFAULT_APP_SETTINGS,
  loadAppSettings,
  normalizeAppSettings,
  resetAppSettings,
  saveAppSettings,
} from '../src/utils/appSettings.js'

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
    }),
    DEFAULT_APP_SETTINGS,
  )
})

test('사용자 설정을 브라우저 저장소에 저장하고 다시 불러온다', () => {
  const storage = memoryStorage()
  const settings = {
    fontSize: 14,
    summaryBatchSeconds: 73,
  }

  saveAppSettings(settings, storage)

  assert.deepEqual(loadAppSettings(storage), settings)
})

test('설정 초기화는 글자 크기와 요약 생성 주기를 모두 기본값으로 되돌린다', () => {
  assert.deepEqual(
    resetAppSettings(),
    DEFAULT_APP_SETTINGS,
  )
  assert.equal(resetAppSettings().fontSize, 8)
  assert.equal(resetAppSettings().summaryBatchSeconds, 120)
})
