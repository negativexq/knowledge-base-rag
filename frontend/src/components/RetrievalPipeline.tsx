import { ArrowDown } from "lucide-react"

import type { RetrievalReportPayload } from "@/api/types"
import { formatMs, formatScore } from "@/lib/utils"

const STAGE_LABEL: Record<string, string> = {
  query_embedding: "Query embedding",
  sparse_encoding: "Sparse BM25 encoding",
  hybrid_retrieval: "Dense + sparse → RRF fusion",
  rerank: "Reranker",
  truncate_to_top_n: "Top-k selection",
}

export function RetrievalPipeline({ report }: { report: RetrievalReportPayload }) {
  return (
    <div className="flex flex-col gap-1">
      {report.stages.map((stage, i) => (
        <div key={stage.name}>
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-[var(--color-foreground)]">
                {STAGE_LABEL[stage.name] ?? stage.name}
              </span>
              <span className="font-technical text-xs text-[var(--color-accent)]">
                {formatMs(stage.duration_ms)}
              </span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-technical text-[11px] text-[var(--color-muted-foreground)]">
              <span>in: {stage.candidates_in ?? "—"}</span>
              <span>out: {stage.candidates_out ?? "—"}</span>
              <span>top score: {formatScore(stage.top_score)}</span>
              {Object.entries(stage.detail).map(([key, value]) => (
                <span key={key} className="text-[var(--color-subtle-foreground)]">
                  {key}: {String(value)}
                </span>
              ))}
            </div>
          </div>
          {i < report.stages.length - 1 && (
            <div className="flex justify-center py-0.5">
              <ArrowDown className="h-3 w-3 text-[var(--color-subtle-foreground)]" />
            </div>
          )}
        </div>
      ))}
      <div className="mt-2 flex items-center justify-between rounded-md border border-dashed border-[var(--color-border)] px-3 py-2 text-xs">
        <span className="text-[var(--color-muted-foreground)]">Total retrieval time</span>
        <span className="font-technical font-medium text-[var(--color-foreground)]">
          {formatMs(report.total_duration_ms)}
        </span>
      </div>
    </div>
  )
}
