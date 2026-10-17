import { useState } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { InspectorPanel } from "@/components/InspectorPanel"

function Workspace() {
  const [open, setOpen] = useState(false)
  return <>
    <button aria-controls="evidence-inspector" onClick={() => setOpen(true)}>Evidence</button>
    <InspectorPanel open={open} onOpenChange={setOpen}><p>A supporting passage</p></InspectorPanel>
  </>
}

afterEach(() => vi.unstubAllGlobals())

describe("Evidence inspector layout", () => {
  it("opens on demand, supports keyboard resizing and closes with Escape", () => {
    render(<Workspace />)
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }))
    const separator = screen.getByRole("separator", { name: "Resize evidence inspector" })
    fireEvent.keyDown(separator, { key: "ArrowLeft" })
    expect(separator).toHaveAttribute("aria-valuenow", "440")
    fireEvent.keyDown(separator, { key: "Home" })
    expect(separator).toHaveAttribute("aria-valuenow", "320")
    fireEvent.keyDown(separator, { key: "ArrowRight" })
    expect(separator).toHaveAttribute("aria-valuenow", "320")
    fireEvent.keyDown(separator, { key: "Escape" })
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Evidence" })).toHaveFocus()
  })

  it("uses a modal sheet on mobile and returns focus when dismissed", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    render(<Workspace />)
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }))
    expect(screen.getByRole("dialog", { name: "Evidence inspector" })).toBeInTheDocument()
    expect(screen.queryByRole("separator")).not.toBeInTheDocument()
    const close = screen.getByRole("button", { name: "Close evidence inspector" })
    expect(close).toHaveFocus()
    fireEvent.click(close)
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(screen.getByRole("button", { name: "Evidence" })).toHaveFocus()
  })
})
