import assert from 'node:assert/strict'
import test from 'node:test'

import { isLlmModelLocked } from '../src/utils/aiActivity.js'

test('AI 작업이 없으면 모델 변경을 허용한다', () => {
  assert.equal(isLlmModelLocked(), false)
})

test('학습 녹음이나 후속 오디오 처리가 진행 중이면 모델 변경을 잠근다', () => {
  assert.equal(isLlmModelLocked({ recordingSessionId: 'session-1' }), true)
  assert.equal(isLlmModelLocked({ recorderProcessing: true }), true)
})

test('퀴즈·질문 답변·AI 노트 생성이 진행 중이면 모델 변경을 잠근다', () => {
  assert.equal(isLlmModelLocked({ coachAiBusy: true }), true)
  assert.equal(isLlmModelLocked({ appAiRequestCount: 1 }), true)
})
