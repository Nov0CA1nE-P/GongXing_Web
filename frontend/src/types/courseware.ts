export interface PublicCoursewareItem {
  id: number
  title: string
  description?: string
  pdf_path?: string
  file_path: string
  file_type: 'pdf' | 'pptx' | 'docx' | 'jpg'
  display_mode: 'inline' | 'download'
  tags?: string
}

export interface AdminCoursewareItem {
  id: number
  title: string
  description?: string
  tags?: string
  date: string
  pdf_path?: string
  pptx_path?: string
  file_path: string
  file_type: string
  display_mode: string
  created_at?: string
}

function isOptionalString(value: unknown) {
  return value === undefined || typeof value === 'string'
}

function isSafePublicFileName(value: unknown) {
  return (
    typeof value === 'string'
    && value.length > 0
    && !value.includes('/')
    && !value.includes('\\')
    && !value.includes('\0')
    && /\.(pdf|pptx|docx|jpg)$/i.test(value)
  )
}

function isPublicCoursewareItem(
  value: unknown,
): value is PublicCoursewareItem {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  const filePath = typeof item.file_path === 'string' ? item.file_path : ''
  const fileType = item.file_type
  return (
    Number.isInteger(item.id)
    && typeof item.title === 'string'
    && isSafePublicFileName(filePath)
    && ['pdf', 'pptx', 'docx', 'jpg'].includes(String(fileType))
    && (fileType === 'pdf' || fileType === 'jpg'
      ? item.display_mode === 'inline'
      : item.display_mode === 'download')
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
    && typeof item.file_path === 'string'
    && typeof item.file_type === 'string'
    && typeof item.display_mode === 'string'
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
