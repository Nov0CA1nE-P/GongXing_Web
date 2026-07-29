export type JsonLoadResult<T> =
  | { ok: true; data: T }
  | {
      ok: false
      kind: 'http' | 'invalid-response' | 'network'
      message: string
      status?: number
    }
  | { ok: false; kind: 'aborted' }

interface LoadJsonOptions<T> {
  request: (signal: AbortSignal) => Promise<Response>
  validate: (value: unknown) => value is T
  getHttpError: (response: Response) => Promise<string>
  invalidMessage: string
  networkMessage: string
}

export async function loadJson<T>(
  options: LoadJsonOptions<T>,
  signal: AbortSignal,
): Promise<JsonLoadResult<T>> {
  try {
    const response = await options.request(signal)
    if (!response.ok) {
      return {
        ok: false,
        kind: 'http',
        status: response.status,
        message: await options.getHttpError(response),
      }
    }

    let data: unknown
    try {
      data = await response.json()
    } catch {
      return {
        ok: false,
        kind: 'invalid-response',
        message: options.invalidMessage,
      }
    }

    if (!options.validate(data)) {
      return {
        ok: false,
        kind: 'invalid-response',
        message: options.invalidMessage,
      }
    }

    return { ok: true, data }
  } catch (error) {
    if (
      signal.aborted
      || (error instanceof DOMException && error.name === 'AbortError')
    ) {
      return { ok: false, kind: 'aborted' }
    }
    return {
      ok: false,
      kind: 'network',
      message: options.networkMessage,
    }
  }
}
