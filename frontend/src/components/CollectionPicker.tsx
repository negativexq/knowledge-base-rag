import { useState } from "react"
import { Popover } from "radix-ui"
import { FolderPlus } from "lucide-react"
import { useOrganization } from "@/hooks/useOrganization"
import type { DocumentReference } from "@/lib/organization"

export function CollectionPicker({ scope, documents, onAdded }: { scope: string; documents: DocumentReference[]; onAdded: () => void }) {
  const organization = useOrganization(scope)
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState("")
  const [name, setName] = useState("")
  return <Popover.Root open={open} onOpenChange={setOpen}><Popover.Trigger disabled={!documents.length} className="flex min-h-8 items-center gap-2 rounded-md border border-[var(--color-border)] px-3 text-xs disabled:opacity-40"><FolderPlus className="h-3.5 w-3.5" />Add to collection</Popover.Trigger>
    <Popover.Portal><Popover.Content align="end" sideOffset={6} aria-label="Add documents to collection" className="z-40 w-80 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 shadow-pop">
      <h3 className="text-sm font-medium">Collect {documents.length} documents</h3>
      <form className="mt-3 space-y-3" onSubmit={(event) => { event.preventDefault(); const saved = name.trim() ? Boolean(organization.create("collections", name, "", documents)) : selected ? organization.addDocuments(selected, documents) : false; if (saved) { setOpen(false); setName(""); onAdded() } }}>
        <select aria-label="Destination collection" value={selected} disabled={Boolean(name.trim())} onChange={(event) => setSelected(event.target.value)} className="h-9 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs"><option value="">Choose a collection…</option>{organization.collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select>
        <label className="block text-xs text-[var(--color-muted-foreground)]">Or create a collection<input aria-label="New collection name" maxLength={80} value={name} onChange={(event) => setName(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-[var(--color-border)] bg-transparent px-2 text-sm" /></label>
        <button type="submit" disabled={!selected && !name.trim()} className="rounded-md bg-[var(--color-accent)] px-3 py-2 text-xs text-[var(--color-accent-foreground)] disabled:opacity-40">{name.trim() ? "Create and add documents" : "Add documents"}</button>
        {organization.error && <p role="status" className="text-xs text-[var(--color-warning)]">{organization.error}</p>}
      </form>
    </Popover.Content></Popover.Portal>
  </Popover.Root>
}
