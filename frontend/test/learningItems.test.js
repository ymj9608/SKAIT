import assert from 'node:assert/strict'
import test from 'node:test'

import { canonicalTermTitle } from '../src/utils/learningItems.js'

test('shows only the English title when a term contains Korean and parenthesized English', () => {
  assert.equal(canonicalTermTitle('키페어 캐시(Keypair Cache)'), 'Keypair Cache')
  assert.equal(
    canonicalTermTitle('어텐션 점 연산(Attention Dot Product Operation)'),
    'Attention Dot Product Operation',
  )
  assert.equal(canonicalTermTitle('컨텍스트 길이(Context Length)'), 'Context Length')
})

test('preserves titles that do not contain a Korean and English pair', () => {
  assert.equal(canonicalTermTitle('REST API'), 'REST API')
  assert.equal(canonicalTermTitle('상관계수'), '상관계수')
  assert.equal(canonicalTermTitle('API (Application Programming Interface)'), 'API (Application Programming Interface)')
})
