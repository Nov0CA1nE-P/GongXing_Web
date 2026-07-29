export interface CoursewareItem {
  id: number
  title: string
  date: string
  description?: string
  pdf_path?: string
  pptx_path?: string
  tags?: string
}

function isOptionalString(value: unknown) {
  return value === undefined || typeof value === 'string'
}

function isCoursewareItem(value: unknown): value is CoursewareItem {
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
  )
}

export function isCoursewareList(value: unknown): value is CoursewareItem[] {
  return Array.isArray(value) && value.every(isCoursewareItem)
}
