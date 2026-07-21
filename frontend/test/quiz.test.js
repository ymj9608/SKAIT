import assert from 'node:assert/strict'
import test from 'node:test'

import { MAX_QUIZ_ITEMS, selectQuizItems } from '../src/utils/quiz.js'

test('keeps the newest distinct quiz items and limits the quiz to ten questions', () => {
  const titles = [
    '회귀 분석',
    '분류 모델',
    '데이터 정규화',
    '오버피팅',
    '언더피팅',
    '손실 함수',
    '경사 하강법',
    '혼동 행렬',
    '정밀도',
    '재현율',
    '특이도',
    '교차 검증',
  ]
  const items = titles.map((title, index) => ({
    title,
    explanation: `설명 ${index}`,
  }))

  const selected = selectQuizItems(items)

  assert.equal(selected.length, MAX_QUIZ_ITEMS)
  assert.deepEqual(selected.map((item) => item.title), titles.slice(0, MAX_QUIZ_ITEMS))
})

test('removes questions with equivalent titles or nearly identical explanations', () => {
  const items = [
    {
      title: 'Train Set (학습 데이터)',
      explanation: '모델의 규칙을 학습시키는 데 사용하는 데이터 집합입니다.',
    },
    {
      title: 'train-set',
      explanation: '다른 문장이어도 같은 제목으로 판단되어야 합니다.',
    },
    {
      title: '학습용 표본',
      explanation: '모델의 규칙을 학습시키는 데 사용하는 데이터 집합입니다.',
    },
    {
      title: 'Test Set',
      explanation: '학습이 끝난 모델의 성능을 최종 평가하는 데이터입니다.',
    },
  ]

  const selected = selectQuizItems(items)

  assert.deepEqual(selected.map((item) => item.title), [
    'Train Set (학습 데이터)',
    'Test Set',
  ])
})
