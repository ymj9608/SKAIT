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
