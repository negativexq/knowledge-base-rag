import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { PagePreview } from "@/components/PagePreview"

const VERSION = "a".repeat(64)

describe("PagePreview", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("requests the version-pinned page with the cited text and says whether it was found", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(["png"]), { headers: { "X-Highlight-Found": "1" } }))
    vi.stubGlobal("fetch", fetchMock)
    URL.createObjectURL = vi.fn(() => "blob:page")
    URL.revokeObjectURL = vi.fn()
    render(<PagePreview sourceId="report.pdf" documentVersion={VERSION} page={4} highlight="Revenue 4,087" />)
    expect(await screen.findByAltText("Page 4 of report.pdf")).toHaveAttribute("src", "blob:page")
    expect(screen.getByText(/highlighted on the original page/)).toBeInTheDocument()
    const url = new URL(fetchMock.mock.calls[0][0])
    expect(url.pathname).toBe("/research/documents/page")
    expect(Object.fromEntries(url.searchParams)).toEqual({ source_type: "filesystem", source_id: "report.pdf", document_version: VERSION, page: "4", highlight: "Revenue 4,087" })
  })

  it("explains when the page cannot be shown", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 404 })))
    render(<PagePreview sourceId="report.pdf" documentVersion={VERSION} page={4} />)
    expect(await screen.findByText(/not available for this version/)).toBeInTheDocument()
  })
})
