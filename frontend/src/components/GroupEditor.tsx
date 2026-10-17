import { useState } from "react"
import { Dialog } from "radix-ui"
import { X } from "lucide-react"
import type { LocalProject } from "@/lib/organization"

export function GroupEditor({ kind, initial, onSave, onClose }: {
  kind: "project" | "collection"
  initial: LocalProject | null
  onSave: (name: string, description: string) => boolean
  onClose: () => void
}) {
  const [name, setName] = useState(initial?.name ?? "")
  const [description, setDescription] = useState(initial?.description ?? "")
  return <Dialog.Root open onOpenChange={(open) => { if (!open) onClose() }}><Dialog.Portal>
    <Dialog.Overlay className="fixed inset-0 z-40 bg-black/25 backdrop-blur-sm" />
    <Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-pop">
      <div className="mb-5 flex items-center justify-between"><Dialog.Title className="text-base font-semibold">{initial ? "Edit" : "New"} {kind}</Dialog.Title><Dialog.Close aria-label={`Close ${kind} editor`} className="rounded p-1.5 hover:bg-[var(--color-surface-hover)]"><X className="h-4 w-4" /></Dialog.Close></div>
      <form onSubmit={(event) => { event.preventDefault(); if (name.trim() && onSave(name, description)) onClose() }} className="space-y-4">
        <label className="block text-xs font-medium">Name<input aria-label={`${kind} name`} autoFocus maxLength={80} value={name} onChange={(event) => setName(event.target.value)} className="mt-1.5 h-10 w-full rounded-md border border-[var(--color-border)] bg-transparent px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]" /></label>
        <label className="block text-xs font-medium">Description<textarea aria-label={`${kind} description`} maxLength={1000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} className="mt-1.5 w-full resize-y rounded-md border border-[var(--color-border)] bg-transparent p-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]" /></label>
        <div className="flex justify-end gap-3"><Dialog.Close className="px-2 py-2 text-xs text-[var(--color-muted-foreground)]">Cancel</Dialog.Close><button type="submit" disabled={!name.trim()} className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-xs font-medium text-[var(--color-accent-foreground)] disabled:opacity-40">{initial ? "Save changes" : `Create ${kind}`}</button></div>
      </form>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>
}
