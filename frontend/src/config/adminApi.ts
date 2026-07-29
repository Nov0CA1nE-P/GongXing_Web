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
    if (
      response.status === 429
      && body?.code === 'rate_limit_exceeded'
    ) {
      const seconds = Math.max(
        1,
        Math.ceil(
          Number(response.headers.get('Retry-After'))
          || Number(body.retry_after)
          || 1,
        ),
      )
      const wait = seconds < 60
        ? `${seconds} 秒`
        : `${Math.ceil(seconds / 60)} 分钟`
      return `登录尝试过于频繁，请在 ${wait}后重试`
    }
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // 非 JSON 错误响应使用调用方提供的安全提示。
  }
  return fallback
}
