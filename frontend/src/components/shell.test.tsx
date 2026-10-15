import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { Identity } from "@/api/types"
import { AppShell } from "@/components/AppShell"
import { useIdentity } from "@/hooks/useIdentity"

vi.mock("@/hooks/useIdentity", () => ({ useIdentity: vi.fn() }))
vi.mock("@/api/health", () => ({
  healthApi: { readiness: vi.fn().mockResolvedValue({ ready: true }) },
}))

const identity: Identity = {
  user_id: "user_a",
  tenant_id: "tenant-a",
  roles: ["USER"],
  can_sync: false,
  is_admin: false,
  auth_enabled: true,
}

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>
}

function renderShell(path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AppShell>
          <Routes>
            <Route path="*" element={<Where />} />
          </Routes>
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("console shell", () => {
  beforeEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.theme
    vi.mocked(useIdentity).mockReturnValue({ data: identity } as ReturnType<typeof useIdentity>)
  })

  it("groups the navigation and names the current page", () => {
    renderShell("/evaluations")

    const nav = screen.getByRole("navigation", { name: "Main" })
    for (const group of ["Ask", "Data", "Quality"]) {
      expect(within(nav).getByText(group)).toBeInTheDocument()
    }
    expect(within(nav).getByRole("link", { name: "Evaluations" })).toHaveAttribute(
      "aria-current",
      "page",
    )
    expect(screen.getByRole("heading", { level: 1, name: "Evaluations" })).toBeInTheDocument()
  })

  it("switches between dark and light themes and remembers the choice", () => {
    renderShell()

    fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }))
    expect(document.documentElement.dataset.theme).toBe("light")
    expect(localStorage.getItem("kb-console.theme")).toBe("light")

    fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }))
    expect(document.documentElement.dataset.theme).toBe("dark")
    expect(localStorage.getItem("kb-console.theme")).toBe("dark")
  })

  it("collapses the sidebar to icons and keeps links reachable by name", () => {
    renderShell()

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }))

    const nav = screen.getByRole("navigation", { name: "Main" })
    expect(within(nav).queryByText("Ask")).not.toBeInTheDocument()
    expect(within(nav).getByRole("link", { name: "Playground" })).toBeInTheDocument()
    expect(localStorage.getItem("kb-console.sidebar-collapsed")).toBe("true")
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument()
  })

  it("opens a command palette with Cmd+K that filters and navigates", () => {
    renderShell()

    fireEvent.keyDown(document, { key: "k", metaKey: true })

    const palette = screen.getByRole("dialog", { name: "Command palette" })
    const search = within(palette).getByRole("combobox", { name: "Search commands" })
    fireEvent.change(search, { target: { value: "trac" } })

    const options = within(palette).getAllByRole("option")
    expect(options.map((option) => option.getAttribute("aria-label"))).toEqual(["Traces"])

    fireEvent.keyDown(search, { key: "Enter" })
    expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument()
    expect(screen.getByTestId("where")).toHaveTextContent("/traces")
  })

  it("can switch the theme from the command palette", () => {
    renderShell()

    fireEvent.click(screen.getByRole("button", { name: "Search or jump to…" }))
    const palette = screen.getByRole("dialog", { name: "Command palette" })
    fireEvent.change(within(palette).getByRole("combobox"), { target: { value: "light" } })
    fireEvent.click(within(palette).getByRole("option", { name: "Switch to light theme" }))

    expect(document.documentElement.dataset.theme).toBe("light")
  })
})
