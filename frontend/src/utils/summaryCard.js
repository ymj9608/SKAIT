export function summaryCardKeyPoints(card) {
  const seen = new Set()
  return (card?.topics || [])
    .flatMap((topic) => topic.key_points || [])
    .map((point) => point.trim())
    .filter((point) => {
      if (!point || seen.has(point)) return false
      seen.add(point)
      return true
    })
}
