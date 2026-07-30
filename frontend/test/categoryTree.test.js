import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildVisibleCategoryGroups,
  compareSessionOrder,
} from '../src/utils/categoryTree.js'

const categories = [
  { id: 'parent', name: '개발', parent_id: null },
  { id: 'child', name: '백엔드', parent_id: 'parent' },
  { id: 'grandchild', name: 'Spring', parent_id: 'child' },
]
const sessions = [
  { id: 'session-1', category_id: 'grandchild' },
]

test('shows nested categories in depth order when their parents are open', () => {
  const groups = buildVisibleCategoryGroups(categories, sessions)

  assert.deepEqual(
    groups.map(({ id, depth }) => ({ id, depth })),
    [
      { id: 'parent', depth: 0 },
      { id: 'child', depth: 1 },
      { id: 'grandchild', depth: 2 },
    ],
  )
})

test('hides every descendant when a parent category is collapsed', () => {
  const groups = buildVisibleCategoryGroups(
    categories,
    sessions,
    '',
    new Set(['parent']),
  )

  assert.deepEqual(groups.map((group) => group.id), ['parent'])
})

test('sorts sessions by the persisted manual order instead of their date', () => {
  const ordered = [
    { id: 'newer', sort_order: 20, created_at: '2026-07-30T00:00:00Z' },
    { id: 'older', sort_order: -5, created_at: '2026-07-01T00:00:00Z' },
  ].sort(compareSessionOrder)

  assert.deepEqual(ordered.map((session) => session.id), ['older', 'newer'])
})

test('places an uncategorized session in the default repository', () => {
  const groups = buildVisibleCategoryGroups(
    [
      { id: 'default', name: '내 수업', parent_id: null, is_default: true },
      { id: 'other', name: '백엔드', parent_id: null, is_default: false },
    ],
    [{ id: 'session-1', category_id: null }],
  )

  assert.deepEqual(
    groups.find((group) => group.id === 'default').sessions.map((session) => session.id),
    ['session-1'],
  )
})
