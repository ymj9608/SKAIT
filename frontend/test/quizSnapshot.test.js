import assert from 'node:assert/strict'
import test from 'node:test'

import { quizQuestionSnapshot } from '../src/utils/quizSnapshot.js'

test('퀴즈를 연 시점의 문항은 이후 수업 상태 변경과 분리된다', () => {
  const liveQuestions = [{ id: 'q1', question: '기존 문제', options: ['A', 'B', 'C', 'D'] }]
  const snapshot = quizQuestionSnapshot(liveQuestions)

  liveQuestions[0].question = '녹음 처리 중 바뀐 문제'
  liveQuestions[0].options[0] = '변경된 보기'
  liveQuestions.splice(0)

  assert.equal(snapshot.length, 1)
  assert.equal(snapshot[0].question, '기존 문제')
  assert.equal(snapshot[0].options[0], 'A')
})
