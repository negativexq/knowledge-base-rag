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
})
