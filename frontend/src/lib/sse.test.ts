import { describe, expect, it, vi } from "vitest"

import { streamChat } from "@/lib/sse"

function responseFor(text: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text))
      controller.close()
    },
  })
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } })
}

describe("chat SSE contract", () => {
  it("handles metadata, tokens, sources, retrieval, security, grounding, done, error and unknown events", async () => {
    const onToken = vi.fn()
    const onSources = vi.fn()
    const onRetrieval = vi.fn()
    const onSecurity = vi.fn()
    const onMetadata = vi.fn()
    const onGrounding = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()
    const onUnknownEvent = vi.fn()

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      responseFor(
        [
          'event: metadata\ndata: {"trace_id":"trace-1"}\n\n',
          'data: {"token":"Hello"}\n\n',
          'data: {"token":" world"}\n\n',
          'event: sources\ndata: {"sources":[{"rank":1}]}\n\n',
          'event: retrieval\ndata: {"stages":[]}\n\n',
          'event: security\ndata: {"acl_applied":true}\n\n',
          'event: grounding\ndata: {"grounded":true}\n\n',
          'event: error\ndata: {"message":"late backend warning"}\n\n',
          'event: future_event\ndata: {"safe":true}\n\n',
          'event: done\ndata: {}\n\n',
        ].join(""),
      ),
    )

    await streamChat("http://api.test/chat", "token-user-a", "Question", {
      onToken,
      onSources,
      onRetrieval,
      onSecurity,
      onMetadata,
      onGrounding,
      onDone,
      onError,
      onUnknownEvent,
    })

    expect(onMetadata).toHaveBeenCalledWith({ trace_id: "trace-1" })
    expect(onToken.mock.calls.flat().join("")).toBe("Hello world")
    expect(onSources).toHaveBeenCalledWith([{ rank: 1 }])
    expect(onRetrieval).toHaveBeenCalledWith({ stages: [] })
    expect(onSecurity).toHaveBeenCalledWith({ acl_applied: true })
    expect(onUnknownEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event: "future_event", data: { safe: true } }),
    )
    expect(onGrounding).toHaveBeenCalledWith({ grounded: true })
    expect(onError).toHaveBeenCalledWith("late backend warning")
    expect(onDone).toHaveBeenCalledOnce()
  })

  it("posts the question together with the conversation history", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => responseFor('event: done\ndata: {}\n\n'))
    const handlers = {
      onToken: vi.fn(),
      onSources: vi.fn(),
      onRetrieval: vi.fn(),
      onMetadata: vi.fn(),
      onGrounding: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    }
    const history = [
      { role: "user" as const, content: "How do I install it?" },
      { role: "assistant" as const, content: "Run brew install nimbus." },
    ]

    await streamChat("http://api.test/chat", "token", "And log out?", handlers, undefined, history)
    await streamChat("http://api.test/chat", "token", "Fresh question", handlers)

    const bodies = fetchSpy.mock.calls.slice(-2).map(([, init]) => JSON.parse(String(init?.body)))
    expect(bodies[0]).toEqual({ question: "And log out?", history })
    expect(bodies[1]).toEqual({ question: "Fresh question", history: [] })
  })

  it("reports an interrupted transport as an error instead of throwing", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("network down"))
    const onError = vi.fn()

    await streamChat("http://api.test/chat", null, "Question", {
      onToken: vi.fn(),
      onSources: vi.fn(),
      onRetrieval: vi.fn(),
      onSecurity: vi.fn(),
      onMetadata: vi.fn(),
      onGrounding: vi.fn(),
      onDone: vi.fn(),
      onError,
    })

    expect(onError).toHaveBeenCalledWith("Could not reach the backend. Is the API running?")
  })

  it("shows the retry delay when the backend rate-limits the user", async () => {
    const onError = vi.fn()
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Too many chat requests; retry later." }), {
        status: 429,
        headers: { "Content-Type": "application/json", "Retry-After": "42" },
      }),
    )

    await streamChat("http://api.test/chat", "token", "hi", handlersWith(onError))

    expect(onError).toHaveBeenCalledWith(
      "Too many chat requests. Try again in 42 seconds.",
    )
  })

  it("shows the backend's reason when the question is rejected", async () => {
    const onError = vi.fn()
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ detail: "Question is too long: 2500 characters, maximum is 2000." }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      ),
    )

    await streamChat("http://api.test/chat", "token", "x", handlersWith(onError))

    expect(onError).toHaveBeenCalledWith(
      "Question is too long: 2500 characters, maximum is 2000.",
    )
  })
})

function handlersWith(onError: (message: string) => void) {
  return {
    onToken: vi.fn(),
    onSources: vi.fn(),
    onRetrieval: vi.fn(),
    onMetadata: vi.fn(),
    onGrounding: vi.fn(),
    onDone: vi.fn(),
    onError,
  }
}

it("preserves progress event names across arbitrary transport chunk boundaries", async () => {
  const text = 'event: research_progress\ndata: {"id":"s1","operation":"search","status":"running"}\n\nevent: clarification\ndata: {"question":"Platform?","options":[]}\n\nevent: done\ndata: {}\n\n'
  const stream = new ReadableStream<Uint8Array>({ start(controller) {
    for (const character of text) controller.enqueue(new TextEncoder().encode(character))
    controller.close()
  } })
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(stream))
  const handlers = { onToken: vi.fn(), onSources: vi.fn(), onRetrieval: vi.fn(), onMetadata: vi.fn(), onGrounding: vi.fn(), onDone: vi.fn(), onError: vi.fn(), onProgress: vi.fn(), onClarification: vi.fn() }
  await streamChat("http://api.test/chat", null, "Question", handlers, undefined, [], { source_ids: ["manual"], clarification: { question: "Platform?", answer: "Linux" } })
  expect(handlers.onProgress).toHaveBeenCalledWith({ id: "s1", operation: "search", status: "running" })
  expect(handlers.onClarification).toHaveBeenCalledWith({ question: "Platform?", options: [] })
  expect(handlers.onDone).toHaveBeenCalledOnce()
  expect(handlers.onError).not.toHaveBeenCalled()
  const request = vi.mocked(fetch).mock.calls.at(-1)![1]!
  expect(JSON.parse(request.body as string)).toMatchObject({ source_ids: ["manual"], clarification: { answer: "Linux" } })
})
