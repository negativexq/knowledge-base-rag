// Sprint 24: SSE client for POST /chat — mirrors app/ui/sse_client.py's
// parsing rule exactly (an optional `event: <name>` line, one or more
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
  const lines = buffer.split("\n")
  // Keep the last (possibly incomplete) line in `rest` — mirrors
  // buffering a raw byte stream into complete lines before parsing.
  const rest = lines.pop() ?? ""

  let eventType = "message"
  let dataLines: string[] = []

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, "")
    if (line === "") {
      if (dataLines.length > 0) {
        try {
          events.push({ event: eventType, data: JSON.parse(dataLines.join("\n")) })
        } catch {
          // malformed data payload — skip this event rather than crash
          // the whole stream.
        }
      }
      eventType = "message"
      dataLines = []
      continue
    }
    if (line.startsWith("event:")) {
      eventType = line.slice("event:".length).trim()
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim())
    }
  }

  return { events, rest }
}

export interface ChatStreamHandlers {
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

export async function streamChat(
  url: string,
  token: string | null,
  question: string,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers = new Headers({ "Content-Type": "application/json" })
  if (token) headers.set("Authorization", `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ question }),
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
    } else {
      handlers.onError(`Request failed (${response.status}).`)
    }
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const { events, rest } = parseSSEChunk(buffer)
      buffer = rest
      for (const evt of events) dispatch(evt, handlers)
    }
  } catch {
    if (signal?.aborted) return
    handlers.onError("The response stream was interrupted.")
  }
}

function dispatch(evt: SSEEvent, handlers: ChatStreamHandlers): void {
  switch (evt.event) {
    case "message": {
      const token = (evt.data as { token?: string })?.token
      if (typeof token === "string") handlers.onToken(token)
      break
    }
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
