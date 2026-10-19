import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { researchApi } from "@/api/research"
import { DocumentPermissions } from "@/components/DocumentPermissions"

vi.mock("@/api/research", () => ({ researchApi: { permissions: vi.fn(), setPermissions: vi.fn() } }))
const policy = { source_type: "filesystem", source_id: "private.pdf", access: "restricted" as const, user_ids: [], group_ids: [], revision: 0 }
function page() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DocumentPermissions scope="tenant:user" /></QueryClientProvider>)
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(researchApi.permissions).mockResolvedValue([policy]) })

describe("Document permissions", () => {
  it("sends explicit user/group grants and the server revision", async () => {
    vi.mocked(researchApi.setPermissions).mockResolvedValue({ ...policy, user_ids: ["alice"], group_ids: ["engineering"], revision: 1 })
    page()
    expect(researchApi.permissions).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText("Document permissions"))
    fireEvent.click(await screen.findByRole("button", { name: /Edit permissions:/ }))
    fireEvent.change(screen.getByLabelText("User IDs"), { target: { value: "alice\nalice" } })
    fireEvent.change(screen.getByLabelText("Group IDs"), { target: { value: "engineering" } })
    fireEvent.click(screen.getByRole("button", { name: "Save permissions" }))
    await screen.findByRole("status")
    expect(researchApi.setPermissions).toHaveBeenCalledWith({ ...policy, user_ids: ["alice"], group_ids: ["engineering"] }, expect.anything())
  })

  it("shows policy conflicts without retrying a stale write", async () => {
    vi.mocked(researchApi.setPermissions).mockRejectedValue(new Error("Permissions changed; reload before saving"))
    page()
    fireEvent.click(screen.getByText("Document permissions"))
    fireEvent.click(await screen.findByRole("button", { name: /Edit permissions:/ }))
    fireEvent.click(screen.getByRole("button", { name: "Save permissions" }))
    expect(await screen.findByRole("alert")).toHaveTextContent("Permissions changed")
    expect(researchApi.setPermissions).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole("button", { name: "Reload permissions" }))
    await waitFor(() => expect(researchApi.permissions).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole("button", { name: "Save permissions" })).not.toBeInTheDocument()
  })
})
