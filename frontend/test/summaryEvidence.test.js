import assert from 'node:assert/strict'
import test from 'node:test'

import {
  findSummaryCardForSource,
  summaryEvidenceItems,
  sourcesWithSummaryCards,
} from '../src/utils/summaryEvidence.js'

const cards = [
  {
    id: 'first-card',
    start_seconds: 0,
    end_seconds: 120,
    source_segment_ids: ['segment-a'],
    topics: [{ title: 'Pydantic 검증', summary: '입력 데이터의 타입과 규칙을 검증합니다.' }],
  },
  {
    id: 'second-card',
    start_seconds: 120,
    end_seconds: 240,
    source_segment_ids: ['segment-b'],
    topics: [{ title: 'FastAPI 요청', summary: '요청 데이터를 모델로 받아 처리합니다.' }],
  },
]

test('finds the summary card containing the selected source segment', () => {
  const card = findSummaryCardForSource(cards, {
    segment_id: 'segment-b',
    start_seconds: 135,
  })

  assert.equal(card.id, 'second-card')
})

test('uses the latest matching time range for legacy summary cards', () => {
  const card = findSummaryCardForSource(cards, {
    segment_id: 'legacy-segment',
    start_seconds: 120,
  })

  assert.equal(card.id, 'second-card')
})

test('hides sources that cannot point to a visible summary card', () => {
  const sources = sourcesWithSummaryCards(cards, [
    { segment_id: 'segment-a', start_seconds: 30 },
    { segment_id: 'missing-segment', start_seconds: 500 },
  ])

  assert.deepEqual(sources.map((source) => source.segment_id), ['segment-a'])
})

test('builds concise evidence from summary cards without exposing transcript excerpts', () => {
  const evidence = summaryEvidenceItems(cards, [
    { segment_id: 'segment-a', start_seconds: 30, excerpt: '교수님이 말한 원문' },
    { segment_id: 'segment-a', start_seconds: 45, excerpt: '같은 카드의 다른 원문' },
  ])

  assert.equal(evidence.length, 1)
  assert.equal(evidence[0].title, 'Pydantic 검증')
  assert.equal(evidence[0].preview, '입력 데이터의 타입과 규칙을 검증합니다.')
  assert.equal('excerpt' in evidence[0], false)
})
