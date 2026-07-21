export const MAX_QUIZ_ITEMS = 10

function normalizeQuizText(value) {
  return String(value || '')
    .normalize('NFKC')
    .toLocaleLowerCase()
    .replace(/[([][^()[\]]*[)\]]/g, ' ')
    .replace(/[^0-9a-z가-힣]+/g, '')
}

function bigrams(value) {
  if (!value) return new Set()
  if (value.length < 2) return new Set([value])

  const result = new Set()
  for (let index = 0; index < value.length - 1; index += 1) {
    result.add(value.slice(index, index + 2))
  }
  return result
}

function diceSimilarity(left, right) {
  if (!left || !right) return 0
  if (left === right) return 1

  const leftPairs = bigrams(left)
  const rightPairs = bigrams(right)
  let intersection = 0
  leftPairs.forEach((pair) => {
    if (rightPairs.has(pair)) intersection += 1
  })
  return (2 * intersection) / (leftPairs.size + rightPairs.size)
}

function isSimilarQuizItem(left, right) {
  const leftTitle = normalizeQuizText(left.title)
  const rightTitle = normalizeQuizText(right.title)
  const shorterTitleLength = Math.min(leftTitle.length, rightTitle.length)
  const longerTitleLength = Math.max(leftTitle.length, rightTitle.length)
  const titleIsExtension = shorterTitleLength >= 4
    && (leftTitle.includes(rightTitle) || rightTitle.includes(leftTitle))
    && shorterTitleLength / longerTitleLength >= 0.6

  if (titleIsExtension || diceSimilarity(leftTitle, rightTitle) >= 0.72) return true

  const leftExplanation = normalizeQuizText(left.explanation)
  const rightExplanation = normalizeQuizText(right.explanation)
  return Math.min(leftExplanation.length, rightExplanation.length) >= 12
    && diceSimilarity(leftExplanation, rightExplanation) >= 0.88
}

export function selectQuizItems(items, limit = MAX_QUIZ_ITEMS) {
  const selected = []

  for (const item of items || []) {
    if (!item?.title || !item?.explanation) continue
    if (selected.some((selectedItem) => isSimilarQuizItem(item, selectedItem))) continue

    selected.push(item)
    if (selected.length >= limit) break
  }

  return selected
}
