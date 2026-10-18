import type { ClarificationReply } from "@/api/types"

// Sprint 24: SSE client for POST /chat — follows the SSE parsing rule
// exactly (an optional `event: <name>` line, one or more
// `data:` lines, terminated by a blank line) and app/api/chat.py's real
// event set: sources, retrieval, metadata, token (unnamed/"message"),
// grounding, done, plus an `error` this client synthesizes itself on a
// stream failure. Unknown event names are surfaced via onUnknownEvent
// so the caller can log them without crashing — the SSE contract may
// grow new event types the client doesn't understand yet.

export interface SSEEvent {
  event: string
  data: unknown
}

export function parseSSEChunk(buffer: string): { events: SSEEvent[]; rest: string } {
  const events: SSEEvent[] = []
  let rest = buffer.replace(/\r\n/g, "\n")
  let boundary: number
  while ((boundary = rest.indexOf("\n\n")) >= 0) {
    const block = rest.slice(0, boundary)
    rest = rest.slice(boundary + 2)
    let event = "message"
    const data: string[] = []
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim()
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""))
    }
    if (data.length) {
      try { events.push({ event, data: JSON.parse(data.join("\n")) }) }
      catch { /* Ignore malformed events and preserve the following frames. */ }
    }
  }
  return { events, rest }
}

// One earlier turn of the conversation, oldest first. The backend uses
// these only to rewrite a follow-up into a standalone search query.
export interface ChatHistoryTurn {
  role: "user" | "assistant"
  content: string
}

export interface ChatRequestOptions {
  source_ids?: string[]
  clarification?: ClarificationReply
}

export interface ChatStreamHandlers {
  onProgress?: (step: unknown) => void
  onClarification?: (clarification: unknown) => void
  onComparison?: (comparison: unknown) => void
  onToken: (content: string) => void
  onSources: (sources: unknown) => void
  onRetrieval: (report: unknown) => void
  onSecurity?: (security: unknown) => void
  onMetadata: (metadata: unknown) => void
  onGrounding: (grounding: unknown) => void
  onDone: () => void
  onError: (message: string) => void
  onUnknownEvent?: (event: SSEEvent) => void
}

async function errorDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    return typeof body.detail === "string" ? body.detail : null
  } catch {
    return null
  }
}

export async function streamChat(
  url: string,
  token: string | null,
  question: string,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
  history: ChatHistoryTurn[] = [],
  options: ChatRequestOptions = {},
): Promise<void> {
  const headers = new Headers({ "Content-Type": "application/json" })
  if (token) headers.set("Authorization", `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ question, history, ...options }),
      signal,
    })
  } catch {
    if (signal?.aborted) return
    handlers.onError("Could not reach the backend. Is the API running?")
    return
  }

  if (!response.ok || !response.body) {
    if (response.status === 401) {
      handlers.onError("Not authenticated — sign in with a development identity.")
    } else if (response.status === 403) {
      handlers.onError("You do not have permission to do this.")
    } else if (response.status === 429) {
      const retryAfter = response.headers.get("Retry-After")
      handlers.onError(
        retryAfter
          ? `Too many chat requests. Try again in ${retryAfter} seconds.`
          : "Too many chat requests. Try again shortly.",
      )
    } else if (response.status === 422) {
      // Backend input guardrails (empty or too-long question) explain
      // themselves in `detail`; show that instead of a bare status code.
      handlers.onError((await errorDetail(response)) ?? "The question was rejected.")
    } else {
      handlers.onError(`Request failed (${response.status}).`)
    }
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  let terminal = false
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const { events, rest } = parseSSEChunk(buffer)
      buffer = rest
      for (const evt of events) {
        if (evt.event === "done" || evt.event === "error") terminal = true
        dispatch(evt, handlers)
      }
    }
  } catch {
    if (signal?.aborted) return
    terminal = true
    handlers.onError("The response stream was interrupted.")
  } finally {
    reader.releaseLock()
  }
  if (!terminal && !signal?.aborted) handlers.onError("The response stream ended before completion.")
}

function dispatch(evt: SSEEvent, handlers: ChatStreamHandlers): void {
  switch (evt.event) {
    case "message": {
      const token = (evt.data as { token?: string })?.token
      if (typeof token === "string") handlers.onToken(token)
      break
    }
    case "research_progress":
      handlers.onProgress?.(evt.data)
      break
    case "clarification":
      handlers.onClarification?.(evt.data)
      break
    case "comparison":
      handlers.onComparison?.(evt.data)
      break
    case "sources":
      handlers.onSources((evt.data as { sources?: unknown })?.sources ?? [])
      break
    case "retrieval":
      handlers.onRetrieval(evt.data)
      break
    case "security":
      handlers.onSecurity?.(evt.data)
      break
    case "metadata":
      handlers.onMetadata(evt.data)
      break
    case "grounding":
      handlers.onGrounding(evt.data)
      break
    case "error": {
      const payload = evt.data as { message?: unknown; error?: unknown }
      const message =
        typeof payload?.message === "string"
          ? payload.message
          : typeof payload?.error === "string"
            ? payload.error
            : "The backend reported a stream error."
      handlers.onError(message)
      break
    }
    case "done":
      handlers.onDone()
      break
    default:
      handlers.onUnknownEvent?.(evt)
  }
}
