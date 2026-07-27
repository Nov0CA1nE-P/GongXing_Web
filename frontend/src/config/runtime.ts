function normalizeBaseUrl(value: string | undefined, fallback: string) {
  const configuredValue = value?.trim() || fallback
  return configuredValue.replace(/\/+$/, '')
}

export const API_BASE_URL = normalizeBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  '/api',
)

export const FILE_BASE_URL = normalizeBaseUrl(
  import.meta.env.VITE_FILE_BASE_URL,
  '/data',
)

export function getUploadedFileUrl(storedPath: string) {
  if (!storedPath) return ''
  if (/^https?:\/\//i.test(storedPath)) return storedPath

  const fileName = storedPath.split(/[\\/]/).pop()
  if (!fileName) return ''

  return `${FILE_BASE_URL}/uploads/${encodeURIComponent(fileName)}`
}
