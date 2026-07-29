export interface PublicCoursewareItem {
  id: number
  title: string
  description?: string
  pdf_path: string
  tags?: string
}

export interface AdminCoursewareItem extends PublicCoursewareItem {
  date: string
  pdf_path: string
  pptx_path?: string
  created_at?: string
}

function isOptionalString(value: unknown) {
  return value === undefined || typeof value === 'string'
}

function isPublicCoursewareItem(
  value: unknown,
): value is PublicCoursewareItem {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return (
    Number.isInteger(item.id)
    && typeof item.title === 'string'
    && typeof item.pdf_path === 'string'
    && item.pdf_path.toLowerCase().endsWith('.pdf')
    && isOptionalString(item.description)
    && isOptionalString(item.tags)
    && item.date === undefined
    && item.pptx_path === undefined
  )
}

function isAdminCoursewareItem(
  value: unknown,
): value is AdminCoursewareItem {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return (
    Number.isInteger(item.id)
    && typeof item.title === 'string'
    && typeof item.date === 'string'
    && isOptionalString(item.description)
    && isOptionalString(item.pdf_path)
    && isOptionalString(item.pptx_path)
    && isOptionalString(item.tags)
    && isOptionalString(item.created_at)
  )
}

export function isPublicCoursewareList(
  value: unknown,
): value is PublicCoursewareItem[] {
  return Array.isArray(value) && value.every(isPublicCoursewareItem)
}

export function isAdminCoursewareList(
  value: unknown,
): value is AdminCoursewareItem[] {
  return Array.isArray(value) && value.every(isAdminCoursewareItem)
}
