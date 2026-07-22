const KOREAN_TEXT_PATTERN = /[가-힣]/
const LATIN_TEXT_PATTERN = /[A-Za-z]/
const PARENTHESIZED_TERM_PATTERN = /^\s*([^()]*)\(\s*([^()]*)\s*\)\s*$/

export function canonicalTermTitle(title) {
  const normalized = String(title || '').trim()
  const match = normalized.match(PARENTHESIZED_TERM_PATTERN)
  if (!match) return normalized

  const [, outer, parenthesized] = match
  const englishTitle = parenthesized.trim()
  if (
    KOREAN_TEXT_PATTERN.test(outer)
    && LATIN_TEXT_PATTERN.test(englishTitle)
    && !KOREAN_TEXT_PATTERN.test(englishTitle)
  ) {
    return englishTitle
  }
  return normalized
}
