import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Dialog } from "radix-ui"
import { useState } from "react"
import { researchApi } from "@/api/research"
import type { DocumentPolicy } from "@/api/types"

export function DocumentPermissions({ scope }: { scope: string }) {
  const [open, setOpen] = useState(false)
  const [offset, setOffset] = useState(0)
  const [draft, setDraft] = useState<DocumentPolicy | null>(null)
  const [users, setUsers] = useState("")
  const [groups, setGroups] = useState("")
  const client = useQueryClient()
  const policies = useQuery({ queryKey: ["document-permissions", scope, offset], queryFn: () => researchApi.permissions(offset), enabled: open })
  const save = useMutation({
    mutationFn: researchApi.setPermissions,
    onSuccess: (policy) => {
      setDraft(policy)
      for (const key of ["document-permissions", "documents", "sources", "overview", "document-read"]) void client.invalidateQueries({ queryKey: [key] })
    },
  })
  function select(policy: DocumentPolicy) {
    setDraft(policy); setUsers(policy.user_ids.join("\n")); setGroups(policy.group_ids.join("\n")); save.reset()
  }
  const principals = (text: string) => [...new Set(text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean))]
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger className="self-end rounded border border-[var(--color-border)] px-3 py-2 text-xs">Document permissions</Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-black/25" /><Dialog.Content aria-describedby="permission-description" className="fixed inset-y-0 right-0 z-50 w-full max-w-lg overflow-y-auto bg-[var(--color-surface)] p-6 shadow-pop">
      <Dialog.Title className="mb-2 font-medium">Document permissions</Dialog.Title>
      <p id="permission-description" className="mb-4 text-xs">Restricted documents are visible only to listed users or groups. Tenant-wide access includes everyone in this organization. Administrators need a grant to read restricted content too.</p>
      <Dialog.Close className="mb-4 text-xs underline">Close permissions</Dialog.Close>
      {policies.isPending && <p>Loading permissions…</p>}
      {policies.isError && <p role="alert">Could not load permissions. <button onClick={() => void policies.refetch()}>Retry</button></p>}
      {policies.data?.length === 0 && <p>No documents on this page.</p>}
      <ul className="mb-4 space-y-2">{policies.data?.map((policy) => <li key={`${policy.source_type}:${policy.source_id}`}><button disabled={save.isPending} className="w-full rounded border border-[var(--color-border)] p-2 text-left text-xs" onClick={() => select(policy)}>Edit permissions: {policy.source_type} / {policy.source_id} · {policy.access}</button></li>)}</ul>
      <div className="mb-4 flex gap-4 text-xs"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous documents</button><button disabled={policies.data?.length !== 50} onClick={() => setOffset(offset + 50)}>Next documents</button></div>
      {draft && <form className="space-y-3 text-xs" onSubmit={(e) => {
        e.preventDefault()
        save.mutate({ ...draft, user_ids: draft.access === "restricted" ? principals(users) : [], group_ids: draft.access === "restricted" ? principals(groups) : [] })
      }}><fieldset disabled={save.isPending} className="space-y-3">
        <p className="break-all font-medium">{draft.source_id}</p>
        <label className="block">Access <select value={draft.access} onChange={(e) => { setDraft({ ...draft, access: e.target.value as DocumentPolicy["access"] }); save.reset() }}><option value="restricted">Restricted</option><option value="tenant">Tenant-wide</option></select></label>
        {draft.access === "restricted" && <><label className="block">User IDs<textarea className="mt-1 block w-full rounded border p-2" value={users} onChange={(e) => { setUsers(e.target.value); save.reset() }} placeholder="One ID per line" /></label><label className="block">Group IDs<textarea className="mt-1 block w-full rounded border p-2" value={groups} onChange={(e) => { setGroups(e.target.value); save.reset() }} placeholder="One ID per line" /></label><p>An empty grant list denies everyone.</p></>}
        <button className="rounded border px-3 py-2" type="submit">{save.isPending ? "Saving…" : "Save permissions"}</button>
      </fieldset>{save.isError && <p role="alert">{save.error.message} <button type="button" onClick={() => { setDraft(null); save.reset(); void policies.refetch() }}>Reload permissions</button></p>}{save.isSuccess && <p role="status">Permissions saved.</p>}</form>}
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>
}
