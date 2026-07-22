export function quizQuestionSnapshot(items) {
  return (items || []).map((item) => ({
    ...item,
    options: [...(item.options || [])],
  }))
}
