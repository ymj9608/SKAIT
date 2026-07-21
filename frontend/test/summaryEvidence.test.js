import assert from 'node:assert/strict'
import test from 'node:test'

import {
  findSummaryCardForSource,
  sourcesWithSummaryCards,
} from '../src/utils/summaryEvidence.js'

const cards = [
  {
    id: 'first-card',
    start_seconds: 0,
    end_seconds: 120,
    source_segment_ids: ['segment-a'],
  },
  {
    id: 'second-card',
    start_seconds: 120,
    end_seconds: 240,
    source_segment_ids: ['segment-b'],
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
