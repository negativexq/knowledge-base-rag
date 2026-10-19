import type { ResearchStep } from "@/api/types"

const labels: Record<string, string> = {
  search: "Searching sources", read_document_section: "Inspecting evidence",
  navigate_document: "Reading document", calculate: "Checking calculation",
  resolve_calculation: "Resolving calculation inputs", read_pages: "Reading page images",
  find_documents: "Finding documents", list_document_elements: "Locating tables and images",
  inspect_table: "Reading table cells", inspect_region: "Inspecting page region",
  compare_evidence: "Comparing evidence",
  read: "Reading evidence", inspect: "Locating tables and images",
  extract: "Extracting source data", collect: "Collecting and checking source inputs",
  validation: "Validating answer", research: "Research", retrieval: "Finding initial evidence",
}
export function ResearchActivity({ steps, streaming }: { steps: ResearchStep[]; streaming: boolean }) {
  if (!steps.length) return null
  return <details className="rounded-lg border border-[var(--color-border)] p-3 text-xs" open={streaming || undefined}>
    <summary className="cursor-pointer font-medium">Research activity · {steps.length} steps</summary>
    <ol aria-label="Research activity" aria-live="polite" className="mt-3 space-y-2">
      {steps.map((step) => <li key={step.id} className="flex items-center justify-between gap-3">
        <span>{labels[step.operation] ?? "Research operation"}</span>
        <span className="text-[var(--color-muted-foreground)]">{step.status === "running" && !streaming ? "Stopped" : step.status}</span>
      </li>)}
    </ol>
  </details>
}
