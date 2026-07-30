import assert from 'node:assert/strict'
import test from 'node:test'

import { getRecordingActionLabel } from '../src/utils/recordingAction.js'

test('처음 시작하는 수업은 학습 시작으로 표시한다', () => {
  assert.equal(
    getRecordingActionLabel({ status: 'ready', duration_seconds: 0 }, false),
    '학습 시작',
  )
})

test('녹음 중인 수업은 학습 중지로 표시한다', () => {
  assert.equal(
    getRecordingActionLabel({ status: 'recording', duration_seconds: 30 }, true),
    '학습 중지',
  )
})

test('한 번 중지한 수업은 학습 재개로 표시한다', () => {
  assert.equal(
    getRecordingActionLabel({ status: 'completed', duration_seconds: 30 }, false),
    '학습 재개',
  )
})

test('비정상 종료 뒤 남은 녹음 상태나 누적 시간이 있어도 학습 재개로 표시한다', () => {
  assert.equal(
    getRecordingActionLabel({ status: 'recording', duration_seconds: 0 }, false),
    '학습 재개',
  )
  assert.equal(
    getRecordingActionLabel({ status: 'ready', duration_seconds: 30 }, false),
    '학습 재개',
  )
})
