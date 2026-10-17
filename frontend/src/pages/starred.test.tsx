import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { Identity } from "@/api/types"
import { Sidebar } from "@/components/Sidebar"
import { WorkspaceCommandsProvider } from "@/components/WorkspaceCommandsProvider"
import { useIdentity } from "@/hooks/useIdentity"
import { newResearchSession, readResearchSessions, researchScope } from "@/lib/research"
import Starred from "@/pages/Starred"

vi.mock("@/hooks/useIdentity", () => ({ useIdentity: vi.fn() }))
const identity: Identity = { user_id: "star-user", tenant_id: "tenant-a", roles: ["USER"], can_sync: false, is_admin: false, auth_enabled: true }
const scope = researchScope(identity)
function seed(title: string, starred: boolean) {
  const session = { ...newResearchSession(), title, starred, notes: [{ id: crypto.randomUUID(), text: "A saved note", evidence: null, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }] }
  localStorage.setItem(scope, JSON.stringify([...readResearchSessions(scope), session]))
  return session
}
function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/starred"]}><WorkspaceCommandsProvider><Sidebar collapsed={false} onToggle={() => {}} /><Routes><Route path="/starred" element={<Starred />} /><Route path="/playground" element={<p>Research opened</p>} /></Routes></WorkspaceCommandsProvider></MemoryRouter></QueryClientProvider>)
}
describe("Starred research", () => {
  beforeEach(() => { vi.mocked(useIdentity).mockReturnValue({ data: identity } as ReturnType<typeof useIdentity>) })
  it("lists only starred research, filters titles and opens the saved conversation", () => {
    const saved = seed("Deployment review", true)
    seed("Incident notes", true)
    seed("Unstarred session", false)
    renderPage()
    expect(screen.getByRole("link", { name: "Starred" })).toHaveAttribute("href", "/starred")
    const list = screen.getByRole("list", { name: "Starred conversations" })
    expect(list).toHaveTextContent("Deployment review")
    expect(list).not.toHaveTextContent("Unstarred session")
    fireEvent.change(screen.getByRole("textbox", { name: "Search starred conversations" }), { target: { value: "deployment" } })
    expect(list).not.toHaveTextContent("Incident notes")
    fireEvent.click(list.querySelector("button")!)
    expect(screen.getByText("Research opened")).toBeInTheDocument()
    expect(JSON.parse(sessionStorage.getItem(`${scope}:launch`)!)).toEqual({ sessionId: saved.id, projectId: null })
  })
  it("persists unstar without deleting the conversation and supports undo", async () => {
    seed("Deployment review", true)
    renderPage()
    fireEvent.click(screen.getByRole("button", { name: "Unstar Deployment review" }))
    expect(screen.getByText("No starred conversations yet")).toBeInTheDocument()
    await waitFor(() => expect(readResearchSessions(scope)).toMatchObject([{ title: "Deployment review", starred: false }]))
    fireEvent.click(screen.getByRole("button", { name: "Undo unstar" }))
    expect(screen.getByRole("list", { name: "Starred conversations" })).toHaveTextContent("Deployment review")
    await waitFor(() => expect(readResearchSessions(scope)[0]?.starred).toBe(true))
  })
  it("keeps another identity's stars out of the page", () => {
    seed("Private review", true)
    vi.mocked(useIdentity).mockReturnValue({ data: { ...identity, user_id: "another-user" } } as ReturnType<typeof useIdentity>)
    renderPage()
    expect(screen.getByText("No starred conversations yet")).toBeInTheDocument()
    expect(screen.queryByText("Private review")).not.toBeInTheDocument()
  })
})
