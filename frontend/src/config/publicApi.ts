import { API_BASE_URL } from './runtime'

export function publicRequest(path: string, init: RequestInit = {}) {
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: 'same-origin',
  })
}

function formatRetryAfter(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.ceil(seconds / 60)} 分钟`
}

export async function getPublicApiError(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const body = await response.json()
    if (
      response.status === 429
      && body?.code === 'rate_limit_exceeded'
    ) {
      const headerSeconds = Number(response.headers.get('Retry-After'))
      const bodySeconds = Number(body.retry_after)
      const seconds = Number.isFinite(headerSeconds) && headerSeconds > 0
        ? Math.ceil(headerSeconds)
        : Math.max(1, Math.ceil(bodySeconds || 1))
      return `请求过于频繁，请在 ${formatRetryAfter(seconds)}后重试`
    }
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    // 非 JSON 错误响应使用调用方提供的安全提示。
  }
  return fallback
}
