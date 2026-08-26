import { getToken } from "@/api/auth"

// Sprint 24: base URL is configurable via VITE_API_BASE_URL, never
// hardcoded — see .env.example / docs. Defaults to the FastAPI dev
// server's own default port.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

/** Every real failure mode this console must render explicitly, per
 * Sprint 24 section 32 — never collapsed into one generic message. */
export type ApiErrorKind =
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unreachable"
  | "server_error"
  | "unknown"

export function classifyError(error: unknown): ApiErrorKind {
  if (error instanceof ApiError) {
    if (error.status === 401) return "unauthenticated"
    if (error.status === 403) return "forbidden"
    if (error.status === 404) return "not_found"
    if (error.status === 409) return "conflict"
    if (error.status >= 500) return "server_error"
    return "unknown"
  }
  if (error instanceof TypeError) return "unreachable" // fetch network failure
  return "unknown"
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers = new Headers(init.headers)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })

  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // non-JSON error body — leave as null
    }
    const message =
      (body as { detail?: string })?.detail ?? `Request to ${path} failed (${response.status})`
    throw new ApiError(response.status, message, body)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
}
