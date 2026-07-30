import assert from 'node:assert/strict'
import test from 'node:test'

import {
  mergeSessionResponse,
  preserveNewerChatHistory,
} from '../src/utils/sessionState.js'

test('preserves newer chat history when an older session response arrives late', () => {
  const current = {
    id: 'session-1',
    chat_messages: [
      { id: 'message-1', role: 'user', text: 'JPA가 뭐야?' },
      { id: 'message-2', role: 'assistant', text: 'JPA를 설명합니다.' },
    ],
  }
  const staleIncoming = {
    id: 'session-1',
    duration_seconds: 90,
    chat_messages: [],
  }

  assert.deepEqual(
    preserveNewerChatHistory(staleIncoming, current),
    {
      ...staleIncoming,
      chat_messages: current.chat_messages,
    },
  )
})

test('accepts an incoming session with newer chat history', () => {
  const current = {
    id: 'session-1',
    chat_messages: [{ id: 'message-1', role: 'user', text: '첫 질문' }],
  }
  const incoming = {
    id: 'session-1',
    chat_messages: [
      ...current.chat_messages,
      { id: 'message-2', role: 'assistant', text: '첫 답변' },
    ],
  }

  assert.equal(preserveNewerChatHistory(incoming, current), incoming)
})

test('rejects an older session response even when it arrives last', () => {
  const current = {
    id: 'session-1',
    session_revision: 8,
    status: 'completed',
    duration_seconds: 120,
  }
  const staleIncoming = {
    id: 'session-1',
    session_revision: 7,
    status: 'recording',
    duration_seconds: 90,
  }

  assert.equal(mergeSessionResponse(staleIncoming, current), current)
})

test('accepts a session response with the latest revision', () => {
  const current = { id: 'session-1', session_revision: 8 }
  const incoming = { id: 'session-1', session_revision: 9 }

  assert.equal(mergeSessionResponse(incoming, current), incoming)
})
