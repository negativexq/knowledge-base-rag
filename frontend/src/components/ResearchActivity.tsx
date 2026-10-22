import { useEffect, useState } from "react"
import { Check, Loader2, RotateCcw, X } from "lucide-react"
import type { ResearchStep } from "@/api/types"

const labels: Record<string, string> = {
  search: "Searching sources", read_document_section: "Inspecting evidence",
  navigate_document: "Reading document", calculate: "Checking calculation",
  resolve_calculation: "Resolving calculation inputs", read_pages: "Reading page images",
  find_documents: "Finding documents", list_document_elements: "Locating tables and images",
  inspect_table: "Reading table cells", inspect_region: "Inspecting page region",
  compare_evidence: "Comparing evidence",
  read: "Inspecting evidence", inspect: "Locating tables and images",
  extract: "Extracting source data", collect: "Collecting and checking source inputs",
  validation: "Validating answer", research: "Research", retrieval: "Finding initial evidence",
}

export type ResearchOutcome = "answered" | "unverified" | "stopped"

const RECENT_STAGES = 5

function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`
}

function seconds(ms: number): string {
  return `${Math.max(0, Math.round(ms / 1000))} s`
}

// Nested work hands control back to its parent stage; show such a return as
// one continuous row instead of a repeated entry.
function stageRows(steps: ResearchStep[]): ResearchStep[] {
  const rows: ResearchStep[] = []
  for (const step of steps) {
    if (step.kind !== "stage") continue
    const last = rows[rows.length - 1]
    if (last && last.stage === step.stage && last.status !== "retrying") {
      rows[rows.length - 1] = {
        ...step,
        receivedAt: last.receivedAt ?? step.receivedAt,
        duration_ms: (last.duration_ms ?? 0) + (step.duration_ms ?? 0) || step.duration_ms,
      }
    } else rows.push(step)
  }
  return rows
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

function StageIcon({ status }: { status: ResearchStep["status"] }) {
  const className = "h-3.5 w-3.5 shrink-0"
  if (status === "running") return <Loader2 aria-hidden="true" className={`${className} animate-spin text-[var(--color-accent)]`} />
  if (status === "retrying") return <RotateCcw aria-hidden="true" className={`${className} text-[var(--color-warning)]`} />
  if (status === "failed") return <X aria-hidden="true" className={`${className} text-[var(--color-error)]`} />
  return <Check aria-hidden="true" className={`${className} text-[var(--color-success)]`} />
}

function StageList({ rows, live, now }: { rows: ResearchStep[]; live: boolean; now: number }) {
  return <ol aria-label="Research stages" aria-live="polite" className="space-y-1.5">
    {rows.map((row) => {
      const running = row.status === "running" && live
      return <li key={row.id} data-status={row.status} aria-current={running ? "step" : undefined}
        className={`flex items-start gap-2 ${running ? "font-medium text-[var(--color-foreground)]" : "text-[var(--color-muted-foreground)]"}`}>
        <span className="mt-0.5"><StageIcon status={row.status === "running" && !live ? "failed" : row.status} /></span>
        <span className="min-w-0 flex-1">{row.message}</span>
        {row.status === "retrying" && <span className="shrink-0 text-[var(--color-warning)]">Needed another look</span>}
        {row.status === "running" && !live && <span className="shrink-0">Stopped</span>}
        {running && row.receivedAt !== undefined && <span className="shrink-0 tabular-nums">{seconds(now - row.receivedAt)}</span>}
      </li>
    })}
  </ol>
}

function TechnicalDetails({ steps, rows }: { steps: ResearchStep[]; rows: ResearchStep[] }) {
  const operations = steps.filter((step) => step.kind !== "stage")
  return <details className="mt-3">
    <summary className="cursor-pointer text-[var(--color-muted-foreground)]">Technical details</summary>
    <ul className="mt-2 space-y-1 font-mono text-[11px] text-[var(--color-muted-foreground)]">
      {operations.map((step) => <li key={step.id} className="flex flex-wrap gap-x-3">
        <span>{labels[step.operation ?? ""] ?? "Research operation"}</span>
        <span>{step.status}</span>
        {!!step.added_evidence && <span>+{step.added_evidence} evidence</span>}
        {step.failure_codes?.map((code) => <span key={code}>{code}</span>)}
      </li>)}
      {rows.map((row) => <li key={row.id} className="flex flex-wrap gap-x-3">
        <span>{row.stage}</span>
        <span>{row.status}</span>
        {row.duration_ms !== undefined && <span>{row.duration_ms} ms</span>}
        {row.reason && <span>{row.reason}</span>}
      </li>)}
    </ul>
  </details>
}

function summary(outcome: ResearchOutcome | undefined, elapsed: number | null, count: number): string {
  const title = outcome === "unverified" ? "Sufficient evidence could not be verified"
    : outcome === "stopped" ? "Research stopped" : "Research completed"
  return [title, elapsed !== null ? seconds(elapsed) : null, `${count} ${count === 1 ? "stage" : "stages"}`]
    .filter(Boolean).join(" · ")
}

export function ResearchActivity({ steps, streaming, startedAt, finishedAt, outcome }: {
  steps: ResearchStep[]
  streaming: boolean
  // Client clock (Date.now()) for the request; durations are never estimated.
  startedAt?: number | null
  finishedAt?: number | null
  outcome?: ResearchOutcome
}) {
  const now = useNow(streaming)
  if (!steps.length) return null
  const rows = stageRows(steps)

  // Operation-only research (the fixed agent path) keeps its plain list.
  if (!rows.length) {
    return <details className="rounded-lg border border-[var(--color-border)] p-3 text-xs" open={streaming || undefined}>
      <summary className="cursor-pointer font-medium">Research activity · {steps.length} steps</summary>
      <ol aria-label="Research activity" aria-live="polite" className="mt-3 space-y-2">
        {steps.map((step) => <li key={step.id} className="flex items-center justify-between gap-3">
          <span>{labels[step.operation ?? ""] ?? "Research operation"}</span>
          <span className="text-[var(--color-muted-foreground)]">{step.status === "running" && !streaming ? "Stopped" : step.status}</span>
        </li>)}
      </ol>
    </details>
  }

  if (streaming) {
    const hidden = Math.max(0, rows.length - RECENT_STAGES)
    return <section aria-label="Research progress" className="rounded-lg border border-[var(--color-border)] p-3 text-xs">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <span className="font-medium text-[var(--color-foreground)]">Researching the documents</span>
        {startedAt != null && <span className="tabular-nums text-[var(--color-muted-foreground)]">{clock(now - startedAt)}</span>}
      </div>
      {hidden > 0 && <p className="mb-1.5 text-[var(--color-subtle-foreground)]">{hidden} earlier {hidden === 1 ? "stage" : "stages"} completed</p>}
      <StageList rows={rows.slice(-RECENT_STAGES)} live now={now} />
      <TechnicalDetails steps={steps} rows={rows} />
    </section>
  }

  const elapsed = startedAt != null && finishedAt != null ? finishedAt - startedAt : null
  return <details className="rounded-lg border border-[var(--color-border)] p-3 text-xs">
    <summary className="cursor-pointer font-medium">{summary(outcome, elapsed, rows.length)}</summary>
    <div className="mt-3"><StageList rows={rows} live={false} now={now} /></div>
    <TechnicalDetails steps={steps} rows={rows} />
  </details>
}
