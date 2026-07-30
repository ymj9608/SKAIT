export function compareSessionOrder(first, second) {
  const firstOrder = Number.isFinite(Number(first.sort_order)) ? Number(first.sort_order) : 0
  const secondOrder = Number.isFinite(Number(second.sort_order)) ? Number(second.sort_order) : 0
  if (firstOrder !== secondOrder) return firstOrder - secondOrder

  const firstCreatedAt = Date.parse(first.created_at || '') || 0
  const secondCreatedAt = Date.parse(second.created_at || '') || 0
  if (firstCreatedAt !== secondCreatedAt) return secondCreatedAt - firstCreatedAt
  return String(first.id || '').localeCompare(String(second.id || ''))
}

export function buildVisibleCategoryGroups(
  categories,
  sessions,
  activeId = '',
  collapsedCategoryIds = new Set(),
) {
  const validIds = new Set(categories.map((category) => category.id))
  const childrenByParent = new Map()
  const sessionsByCategory = new Map()
  const visited = new Set()
  const groups = []

  sessions.forEach((session) => {
    if (!session.category_id || !validIds.has(session.category_id)) return
    const items = sessionsByCategory.get(session.category_id) || []
    items.push(session)
    sessionsByCategory.set(session.category_id, items)
  })
  sessionsByCategory.forEach((items) => items.sort(compareSessionOrder))
  categories.forEach((category) => {
    const parentId = category.parent_id && validIds.has(category.parent_id)
      ? category.parent_id
      : ''
    const children = childrenByParent.get(parentId) || []
    children.push(category)
    childrenByParent.set(parentId, children)
  })

  function containsActiveSession(categoryId, checking = new Set()) {
    if (checking.has(categoryId)) return false
    if ((sessionsByCategory.get(categoryId) || []).some((session) => session.id === activeId)) {
      return true
    }
    const nextChecking = new Set(checking).add(categoryId)
    return (childrenByParent.get(categoryId) || []).some(
      (child) => containsActiveSession(child.id, nextChecking),
    )
  }

  function visit(category, depth) {
    if (visited.has(category.id)) return
    visited.add(category.id)
    const children = childrenByParent.get(category.id) || []
    groups.push({
      ...category,
      depth,
      sessions: sessionsByCategory.get(category.id) || [],
      containsActiveSession: containsActiveSession(category.id),
    })
    if (!collapsedCategoryIds.has(category.id)) {
      children.forEach((child) => visit(child, depth + 1))
    }
  }

  ;(childrenByParent.get('') || []).forEach((category) => visit(category, 0))
  return groups
}
