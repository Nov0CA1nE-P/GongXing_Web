import { API_BASE_URL } from './runtime'

export function adminRequest(path: string, init: RequestInit = {}) {
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'same-origin',
    cache: 'no-store',
  })
}

export async function getApiError(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // 非 JSON 错误响应使用调用方提供的安全提示。
  }
  return fallback
}
