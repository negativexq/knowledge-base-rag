import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { researchApi } from "@/api/research"
import type { FeedbackRecord } from "@/api/types"
import { useIdentity } from "@/hooks/useIdentity"
import { Button } from "@/components/ui/button"

function Report({ report, reviewer, onReviewed }: { report: FeedbackRecord; reviewer: boolean; onReviewed: () => void }) {
  const [note, setNote] = useState(report.reviewer_note)
  const [status, setStatus] = useState<"triaged" | "resolved" | "dismissed">(report.status === "open" ? "triaged" : report.status)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(false)
  async function review() {
    setSaving(true); setError(false)
    try { await researchApi.review(report.id, status, note); onReviewed() }
    catch { setError(true) }
    finally { setSaving(false) }
  }
  return <article className="space-y-3 rounded-lg border border-[var(--color-border)] p-4">
    <div className="flex flex-wrap justify-between gap-2 text-xs"><span>{report.reason} · {report.status}</span><time>{new Date(report.created_at).toLocaleString()}</time></div>
    <h2 className="text-sm font-medium">{report.question}</h2>
    {report.claim && <blockquote className="whitespace-pre-wrap border-l-2 border-[var(--color-warning)] pl-3 text-sm">{report.claim}</blockquote>}
    {report.note && <p className="whitespace-pre-wrap text-sm">{report.note}</p>}
    <details className="text-xs"><summary className="cursor-pointer">Submitted answer snapshot</summary><p className="mt-2 text-[var(--color-muted-foreground)]">User-submitted report; this snapshot is not independently verified evidence.</p><pre className="mt-2 whitespace-pre-wrap font-sans">{report.answer}</pre>{report.support_ids.length > 0 && <p className="mt-2 break-all">Reported citations: {report.support_ids.join(", ")}</p>}{report.trace_id && <p className="mt-2 break-all">Trace: {report.trace_id}</p>}</details>
    {reviewer ? <form className="space-y-2 border-t border-[var(--color-border)] pt-3" onSubmit={(event) => { event.preventDefault(); void review() }}>
      <label className="block text-xs">Review status<select value={status} onChange={(event) => setStatus(event.target.value as typeof status)} className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-1"><option value="triaged">Triaged</option><option value="resolved">Resolved</option><option value="dismissed">Dismissed</option></select></label>
      <label className="block text-xs">Reviewer note<textarea value={note} maxLength={4000} onChange={(event) => setNote(event.target.value)} className="mt-1 block w-full rounded border border-[var(--color-border)] bg-transparent p-2" /></label>
      {error && <p role="alert" className="text-xs">Review could not be saved.</p>}
      <Button size="sm" disabled={saving}>{saving ? "Saving…" : "Save review"}</Button>
    </form> : report.reviewer_note && <p className="text-xs">Reviewer response: {report.reviewer_note}</p>}
  </article>
}

export default function Feedback() {
  const identity = useIdentity()
  const reviewer = Boolean(identity.data?.can_sync)
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState("")
  const client = useQueryClient()
  const reports = useQuery({ queryKey: ["feedback", identity.data?.tenant_id, identity.data?.user_id, reviewer, offset, status],
    queryFn: () => researchApi.reports(reviewer, offset, status), enabled: Boolean(identity.data) })
  if (identity.isError) return <p role="alert" className="p-6">Your identity could not be loaded.</p>
  return <div className="mx-auto max-w-4xl space-y-4 p-6">
    <h1 className="text-xl font-semibold">Answer feedback</h1>
    <p className="text-sm text-[var(--color-muted-foreground)]">{reviewer ? "Review reported answer issues within your organization." : "Your submitted issues and reviewer responses."}</p>
    {reviewer && <label className="block text-xs">Filter status<select value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0) }} className="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-1"><option value="">All</option>{["open", "triaged", "resolved", "dismissed"].map((item) => <option key={item}>{item}</option>)}</select></label>}
    {reports.isPending && <p role="status">Loading feedback…</p>}
    {reports.isError && <p role="alert">Feedback could not be loaded. <button type="button" onClick={() => void reports.refetch()}>Retry</button></p>}
    {reports.data?.length === 0 && <p>No reports on this page.</p>}
    {reports.data?.map((report) => <Report key={`${report.id}:${report.updated_at}`} report={report} reviewer={reviewer} onReviewed={() => void client.invalidateQueries({ queryKey: ["feedback"] })} />)}
    <div className="flex gap-2"><Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button><Button size="sm" variant="secondary" disabled={reports.data?.length !== 50} onClick={() => setOffset(offset + 50)}>Next</Button></div>
  </div>
}
