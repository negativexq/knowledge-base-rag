import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { sourcesApi } from "@/api/sources"
import { Button } from "@/components/ui/button"

export function ComparisonComposer({ disabled, onCompare }: {
  disabled: boolean; onCompare: (question: string, ids: string[]) => void
}) {
  const documents = useQuery({ queryKey: ["comparison-documents"], queryFn: () => sourcesApi.documents() })
  const [selected, setSelected] = useState<string[]>([])
  const [question, setQuestion] = useState("")
  const available = documents.data?.filter((doc) => doc.status === "active") ?? []
  return <form aria-label="Compare documents" onSubmit={(event) => {
    event.preventDefault()
    if (selected.length >= 2 && question.trim()) onCompare(question.trim(), selected)
  }} className="space-y-3 rounded-lg border border-[var(--color-border)] p-4">
    <p className="text-sm font-medium">Compare documents</p>
    <p className="text-xs text-[var(--color-muted-foreground)]">Choose two to five documents and describe what to compare.</p>
    {documents.isPending && <p role="status">Loading documents…</p>}
    {documents.isError && <p role="alert">Documents could not be loaded. <button type="button" onClick={() => void documents.refetch()}>Retry</button></p>}
    <div className="max-h-44 overflow-y-auto">{available.map((doc) => <label className="flex items-center gap-2 py-1 text-xs" key={`${doc.source_type}:${doc.source_id}`}><input type="checkbox" checked={selected.includes(doc.source_id)} disabled={disabled || (!selected.includes(doc.source_id) && selected.length >= 5)} onChange={() => setSelected((prev) => prev.includes(doc.source_id) ? prev.filter((id) => id !== doc.source_id) : [...prev, doc.source_id])} />{doc.source_id}</label>)}</div>
    {documents.isSuccess && available.length < 2 && <p className="text-xs">At least two active documents are needed.</p>}
    <label className="block text-xs">What should be compared?<input value={question} maxLength={2000} onChange={(event) => setQuestion(event.target.value)} placeholder="Compare the supported platforms and installation steps" className="mt-1 w-full rounded border border-[var(--color-border)] bg-transparent p-2 text-sm" /></label>
    <Button size="sm" disabled={disabled || selected.length < 2 || !question.trim()}>Compare selected documents</Button>
  </form>
}
