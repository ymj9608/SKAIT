import assert from 'node:assert/strict'
import test from 'node:test'

import { buildWebSocketUrl } from '../src/services/api.js'

test('builds a proxied WebSocket URL for the local frontend', () => {
  assert.equal(
    buildWebSocketUrl('/api', 'http://127.0.0.1:5173'),
    'ws://127.0.0.1:5173/api/client/connection',
  )
})

test('preserves an explicit backend host and secure WebSocket protocol', () => {
  assert.equal(
    buildWebSocketUrl('https://example.test/backend/api/', 'https://app.test'),
    'wss://example.test/backend/api/client/connection',
  )
})
