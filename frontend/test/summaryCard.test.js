import assert from 'node:assert/strict'
import test from 'node:test'

import { summaryCardKeyPoints } from '../src/utils/summaryCard.js'

test('combines key points from every topic without duplicates or blanks', () => {
  const card = {
    topics: [
      { key_points: ['첫 번째 핵심', ' 공통 핵심 '] },
      { key_points: ['공통 핵심', '', '두 번째 핵심'] },
    ],
  }

  assert.deepEqual(
    summaryCardKeyPoints(card),
    ['첫 번째 핵심', '공통 핵심', '두 번째 핵심'],
  )
})

test('returns an empty list when a summary card has no key points', () => {
  assert.deepEqual(summaryCardKeyPoints({ topics: [{ key_points: [] }] }), [])
  assert.deepEqual(summaryCardKeyPoints(null), [])
})
