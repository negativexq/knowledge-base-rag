import type { EvaluationMetricEntry } from "@/api/types"

export function EvaluationMetric({ metric }: { metric: EvaluationMetricEntry }) {
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
      <div className="text-xs text-[var(--color-muted-foreground)]">{metric.label}</div>
      <div className="mt-1 font-technical text-xl font-semibold text-[var(--color-foreground)]">
        {metric.value !== null ? metric.value.toFixed(4) : "—"}
      </div>
      {metric.stddev !== null && metric.runs !== null && (
        <div className="mt-0.5 font-technical text-[11px] text-[var(--color-subtle-foreground)]">
          σ {metric.stddev.toFixed(4)} · {metric.runs} runs
        </div>
      )}
    </div>
  )
}
