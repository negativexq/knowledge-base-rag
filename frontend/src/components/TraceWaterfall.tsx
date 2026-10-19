import { ExternalLink } from "lucide-react"
import type { TraceDetail, TraceSpan } from "@/api/types"
import { EmptyState } from "@/components/EmptyState"
import { formatMs } from "@/lib/utils"

function depth(span: TraceSpan, all: TraceSpan[]): number {
  let parent = span.parent_span_id, result = 0
  const seen = new Set([span.span_id])
  while (parent && !seen.has(parent) && result < 8) {
    seen.add(parent)
    const found = all.find((item) => item.span_id === parent)
    if (!found) break
    result++; parent = found.parent_span_id
  }
  return result
}

export function TraceWaterfall({ trace }: { trace: TraceDetail }) {
  if (!trace.available || trace.spans.length === 0) return <EmptyState title="Trace not indexed yet" description="The request may still be running, or trace export is pending. Retry in a moment." />
  const totalMs = Math.max(1, ...trace.spans.map((s) => s.offset_ms + s.duration_ms))
  const calls = trace.spans.filter((s) => s.name === "llm.request")
  const usage = trace.request?.usage
  const tokens = (key: string) => calls.reduce((sum, call) => sum + Number(call.attributes?.[key] ?? 0), 0)
  const priced = calls.filter((s) => s.attributes?.["cost.status"] === "estimated")
  const complete = usage?.cost_complete ?? (calls.length > 0 && priced.length === calls.length)
  const cost = usage?.known_cost_usd ?? priced.reduce((sum, s) => sum + Number(s.attributes?.["cost.usd"] ?? 0), 0)
  const partialUsage = usage ? !usage.usage_complete : calls.some((call) => call.attributes?.["usage.available"] !== true)
  const request = trace.request
  return <div className="flex flex-col gap-3">
    <div className="break-all font-technical text-xs">Trace {trace.trace_id}</div>
    {request && <p className="text-xs">{request.pipeline} · {request.outcome}{request.error_type ? ` · ${request.error_type}` : ""}</p>}
    {request?.parent_trace_id && <a className="text-xs text-[var(--color-accent)] underline" href={`/traces?trace=${encodeURIComponent(request.parent_trace_id)}`}>Previous clarification trace</a>}
    <dl className="grid grid-cols-2 gap-2 rounded-lg border border-[var(--color-border)] p-3 text-xs">
      <div><dt>Model calls</dt><dd>{usage?.llm_requests ?? calls.length}</dd></div>
      <div><dt>Input / output tokens</dt><dd>{usage?.input_tokens ?? tokens("gen_ai.usage.input_tokens")} / {usage?.output_tokens ?? tokens("gen_ai.usage.output_tokens")}{partialUsage ? " (partial)" : ""}</dd></div>
      <div><dt>Tool calls / retries</dt><dd>{usage?.tool_calls ?? trace.spans.filter((s) => s.name.startsWith("tool.")).length} / {usage?.retries ?? "—"}</dd></div>
      <div><dt>Estimated cost (USD)</dt><dd>{complete ? `$${cost.toFixed(6)}` : "Unknown"}{!complete && cost > 0 && <span> · known subtotal ${cost.toFixed(6)}</span>}</dd></div>
    </dl>
    <p className="text-[11px] text-[var(--color-muted-foreground)]">Expand a step for safe operational metadata. Content and raw error messages are excluded. Cost requires configured model prices and reported usage.</p>
    <ol aria-label="Trace steps" className="space-y-2">
      {trace.spans.map((span, index) => {
        const attrs = span.attributes ?? {}
        const state = String(attrs["research.outcome"] ?? span.status ?? "unset")
        const error = span.status === "error" || ["failed", "rejected", "timeout", "budget_exceeded"].includes(state)
        return <li key={span.span_id ?? `${span.name}-${index}`} style={{ paddingLeft: depth(span, trace.spans) * 10 }}>
          <details className="rounded border border-[var(--color-border)] p-2">
            <summary className="cursor-pointer text-xs">
              <span className="break-words font-medium">{span.name}</span> <span className={error ? "text-[var(--color-error)]" : "text-[var(--color-muted-foreground)]"}>{state}</span> <span className="float-right font-technical">{formatMs(span.duration_ms)}</span>
              <div className="relative mt-2 h-2 rounded bg-[var(--color-surface-raised)]"><div className={`absolute h-full rounded ${error ? "bg-[var(--color-error)]" : "bg-[var(--color-accent)]"}`} style={{ left: `${span.offset_ms / totalMs * 100}%`, width: `${Math.max(span.duration_ms / totalMs * 100, 0.5)}%` }} /></div>
            </summary>
            <dl className="mt-3 space-y-1 break-all text-[11px]">
              <div><dt className="inline font-medium">Span: </dt><dd className="inline">{span.span_id ?? "Unavailable"}</dd></div>
              <div><dt className="inline font-medium">Parent: </dt><dd className="inline">{span.parent_span_id ?? "Root"}</dd></div>
              {Object.entries(attrs).map(([key, value]) => <div key={key}><dt className="inline font-medium">{key}: </dt><dd className="inline">{Array.isArray(value) ? value.join(", ") : String(value)}</dd></div>)}
            </dl>
          </details>
        </li>
      })}
    </ol>
    {trace.can_open_external && <a href={`${trace.jaeger_url}/trace/${trace.trace_id}`} target="_blank" rel="noreferrer" className="inline-flex w-fit items-center gap-1.5 text-xs text-[var(--color-accent)] hover:underline"><ExternalLink className="h-3 w-3" />Open in Jaeger</a>}
  </div>
}
