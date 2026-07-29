import { API_BASE_URL } from './runtime'

let csrfToken: string | null = null

export function setAdminCsrfToken(token: unknown) {
  csrfToken = typeof token === 'string' && token.length > 0 ? token : null
}

export function clearAdminCsrfToken() {
  csrfToken = null
}

export function adminRequest(path: string, init: RequestInit = {}) {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (
    csrfToken
    && path !== '/admin/login'
    && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)
  ) {
    headers.set('X-CSRF-Token', csrfToken)
  }
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
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
