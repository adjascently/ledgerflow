export function formatCategoryLabel(category?: string | null) {
  if (!category) return 'Miscellaneous'
  return category === 'Uncategorized' ? 'Miscellaneous' : category
}
