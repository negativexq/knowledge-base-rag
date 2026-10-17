import { useState } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import { BookOpen } from "lucide-react"
import { WorkspaceCommandsProvider } from "@/components/WorkspaceCommandsProvider"
import { CommandPalette } from "@/components/CommandPalette"
import { ShareViewButton } from "@/components/ShareViewButton"
import { useRegisterWorkspaceCommands } from "@/lib/workspaceCommands"
import { ThemeProvider } from "@/lib/theme"

function Actions({ onRun }: { onRun: () => void }) {
  useRegisterWorkspaceCommands([
    { id: "notes", label: "Open research notes", icon: BookOpen, run: onRun },
    { id: "export", label: "Export research as Markdown", icon: BookOpen, disabled: true, run: onRun },
  ])
  return null
}

describe("Research actions and view sharing", () => {
  it("registers contextual commands and prevents unavailable actions", () => {
    const run = vi.fn()
    function Workspace() {
      const [open, setOpen] = useState(true)
      return <><Actions onRun={run} /><CommandPalette open={open} onOpenChange={setOpen} /></>
    }
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><ThemeProvider><WorkspaceCommandsProvider><Workspace /></WorkspaceCommandsProvider></ThemeProvider></MemoryRouter></QueryClientProvider>)
    const palette = screen.getByRole("dialog", { name: "Command palette" })
    fireEvent.change(within(palette).getByRole("combobox"), { target: { value: "Export research" } })
    const disabled = within(palette).getByRole("option", { name: "Export research as Markdown" })
    expect(disabled).toHaveAttribute("aria-disabled", "true")
    fireEvent.click(disabled)
    expect(run).not.toHaveBeenCalled()
    fireEvent.change(within(palette).getByRole("combobox"), { target: { value: "Open research notes" } })
    fireEvent.keyDown(within(palette).getByRole("combobox"), { key: "Enter" })
    expect(run).toHaveBeenCalledOnce()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("shows a floating copy notice and dismisses it automatically", async () => {
    vi.useFakeTimers()
    const previous = Object.getOwnPropertyDescriptor(navigator, "clipboard")
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } })
    try {
      render(<ShareViewButton values={{ mode: "research" }} />)
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Copy view link" })) })
      expect(screen.getByRole("status")).toHaveClass("absolute")
      expect(screen.getByRole("status")).toHaveTextContent("View link copied")
      act(() => vi.advanceTimersByTime(2500))
      expect(screen.queryByRole("status")).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
      if (previous) Object.defineProperty(navigator, "clipboard", previous); else Reflect.deleteProperty(navigator, "clipboard")
    }
  })

  it("copies only view settings and offers a manual link when clipboard access fails", async () => {
    const previous = Object.getOwnPropertyDescriptor(navigator, "clipboard")
    const write = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: write } })
    try {
      window.history.replaceState(null, "", "/playground?token=private&answer=private")
      const view = render(<ShareViewButton values={{ mode: "research", panel: "notes", inspector: "open" }} />)
      fireEvent.click(screen.getByRole("button", { name: "Copy view link" }))
      expect(await screen.findByRole("status")).toHaveTextContent("View link copied")
      const copied = new URL(write.mock.calls[0][0])
      expect([...copied.searchParams.keys()]).toEqual(["mode", "panel", "inspector"])
      expect(copied.href).not.toContain("private")
      write.mockRejectedValue(new Error("Clipboard unavailable"))
      view.rerender(<ShareViewButton values={{ mode: "inspect", panel: "why", inspector: "open" }} />)
      expect(screen.queryByRole("status")).not.toBeInTheDocument()
      fireEvent.click(screen.getByRole("button", { name: "Copy view link" }))
      expect((await screen.findByRole("textbox", { name: "View link to copy" }) as HTMLInputElement).value).toContain("panel=why")
    } finally { if (previous) Object.defineProperty(navigator, "clipboard", previous); else Reflect.deleteProperty(navigator, "clipboard") }
  })
})
