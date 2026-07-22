export function findSummaryCardForSource(summaryCards = [], source = null) {
  if (!source) return null

  const directMatch = summaryCards.find((card) =>
    card.source_segment_ids?.includes(source.segment_id),
  )
  if (directMatch) return directMatch

  const sourceSeconds = Number(source.start_seconds)
  if (!Number.isFinite(sourceSeconds)) return null

  return [...summaryCards]
    .filter((card) => (
      Number(card.start_seconds) <= sourceSeconds
      && sourceSeconds <= Number(card.end_seconds)
    ))
    .sort((left, right) => Number(right.start_seconds) - Number(left.start_seconds))[0] || null
}

export function sourcesWithSummaryCards(summaryCards = [], sources = []) {
  return sources.filter((source) => findSummaryCardForSource(summaryCards, source))
}

function shortened(text, maxLength = 140) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim()
  if (normalized.length <= maxLength) return normalized
  return `${normalized.slice(0, maxLength).trimEnd()}…`
}

export function summaryEvidenceItems(summaryCards = [], sources = []) {
  const seenCardIds = new Set()
  const items = []

  for (const source of sources) {
    const card = findSummaryCardForSource(summaryCards, source)
    if (!card || seenCardIds.has(card.id)) continue

    seenCardIds.add(card.id)
    const topics = card.topics || []
    const title = topics.map((topic) => topic.title?.trim()).filter(Boolean).join(' · ')
    const preview = topics.map((topic) => topic.summary?.trim()).filter(Boolean).join(' ')
    items.push({
      cardId: card.id,
      source,
      title: title || '수업 요약',
      preview: shortened(preview),
    })
  }

  return items
}
