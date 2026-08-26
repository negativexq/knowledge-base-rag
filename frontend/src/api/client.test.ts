import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiError, api, classifyError } from "@/api/client"
import { clearToken, setToken } from "@/api/auth"

describe("API client security boundary", () => {
  afterEach(() => {
    clearToken()
    vi.restoreAllMocks()
  })

  it("applies the stored development token as a bearer header", async () => {
    setToken("token-user-a")
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )

    await api.get<{ ok: boolean }>("/ui/overview")

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/ui/overview",
      expect.objectContaining({
        method: "GET",
        headers: expect.any(Headers),
      }),
    )
    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect((request.headers as Headers).get("Authorization")).toBe("Bearer token-user-a")
  })

  it("classifies missing identity and server authorization failures distinctly", async () => {
    expect(classifyError(new ApiError(401, "missing", null))).toBe("unauthenticated")
    expect(classifyError(new ApiError(403, "forbidden", null))).toBe("forbidden")

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid or unknown token" }), { status: 401 }),
    )
    await expect(api.get("/ui/identity")).rejects.toMatchObject({ status: 401 })
  })
})
