export function compareSessionOrder(first, second) {
  const firstOrder = Number.isFinite(Number(first.sort_order)) ? Number(first.sort_order) : 0
  const secondOrder = Number.isFinite(Number(second.sort_order)) ? Number(second.sort_order) : 0
  if (firstOrder !== secondOrder) return firstOrder - secondOrder

  const firstCreatedAt = Date.parse(first.created_at || '') || 0
  const secondCreatedAt = Date.parse(second.created_at || '') || 0
  if (firstCreatedAt !== secondCreatedAt) return secondCreatedAt - firstCreatedAt
  return String(first.id || '').localeCompare(String(second.id || ''))
}

export function compareCategoryOrder(first, second) {
  const firstOrder = Number.isFinite(Number(first.sort_order)) ? Number(first.sort_order) : 0
  const secondOrder = Number.isFinite(Number(second.sort_order)) ? Number(second.sort_order) : 0
  if (firstOrder !== secondOrder) return firstOrder - secondOrder

  const firstCreatedAt = Date.parse(first.created_at || '') || 0
  const secondCreatedAt = Date.parse(second.created_at || '') || 0
  if (firstCreatedAt !== secondCreatedAt) return firstCreatedAt - secondCreatedAt
  return String(first.id || '').localeCompare(String(second.id || ''))
}

export function canPlaceCategory(categories, categoryId, parentId) {
  const categoryById = new Map(categories.map((category) => [category.id, category]))
  const category = categoryById.get(categoryId)
  if (!category) return false

  const normalizedParentId = parentId || null
  if (!normalizedParentId) return true

  let ancestor = categoryById.get(normalizedParentId)
  const visited = new Set()
  while (ancestor && !visited.has(ancestor.id)) {
    if (ancestor.id === categoryId) return false
    visited.add(ancestor.id)
    ancestor = ancestor.parent_id
      ? categoryById.get(ancestor.parent_id)
      : null
  }
  return categoryById.has(normalizedParentId)
}

export function canMoveCategory(categories, categoryId, parentId) {
  const category = categories.find((item) => item.id === categoryId)
  if (!category || (category.parent_id || null) === (parentId || null)) return false
  return canPlaceCategory(categories, categoryId, parentId)
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
  const defaultCategoryId = (
    categories.find((category) => category.is_default)?.id
    || categories[0]?.id
    || ''
  )

  sessions.forEach((session) => {
    const categoryId = validIds.has(session.category_id)
      ? session.category_id
      : defaultCategoryId
    if (!categoryId) return
    const items = sessionsByCategory.get(categoryId) || []
    items.push(session)
    sessionsByCategory.set(categoryId, items)
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
  childrenByParent.forEach((children) => children.sort(compareCategoryOrder))

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
      hasChildCategories: children.length > 0,
      containsActiveSession: containsActiveSession(category.id),
    })
    if (!collapsedCategoryIds.has(category.id)) {
      children.forEach((child) => visit(child, depth + 1))
    }
  }

  ;(childrenByParent.get('') || []).forEach((category) => visit(category, 0))
  return groups
}
