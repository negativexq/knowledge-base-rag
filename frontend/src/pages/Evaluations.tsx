import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, XCircle } from "lucide-react"

import { classifyError } from "@/api/client"
import { uiApi } from "@/api/ui"
import { EmptyState } from "@/components/EmptyState"
import { ErrorState } from "@/components/ErrorState"
import { EvaluationMetric } from "@/components/EvaluationMetric"
import { LoadingRows } from "@/components/LoadingSkeleton"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

// Sprint 24 section 24: metrics this platform doesn't measure YET —
// shown as a disabled placeholder row so the page's design communicates
// where the metric surface grows next, without pretending the numbers
// exist today.
const PLANNED_METRICS = [
  "Reranker lift",
  "Abstention accuracy",
  "Faithfulness",
  "Citation precision",
  "Claim support",
  "Injection resistance",
]

function formatMetric(value: number | null | undefined) {
  return typeof value === "number" ? value.toFixed(4) : "—"
}

function formatLatency(value: number | string | null | undefined) {
  return typeof value === "number" ? `${value.toFixed(1)} ms` : value ?? "—"
}

function formatCount(value: number | string | null | undefined) {
  return typeof value === "number" ? value.toFixed(1) : value ?? "—"
}

export default function Evaluations() {
  const query = useQuery({ queryKey: ["evaluations"], queryFn: uiApi.evaluations })

  if (query.isLoading) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <LoadingRows rows={4} />
      </div>
    )
  }
  if (query.isError) {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <ErrorState kind={classifyError(query.error)} detail={(query.error as Error).message} />
      </div>
    )
  }

  const data = query.data!

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <h1 className="text-lg font-semibold text-[var(--color-foreground)]">Evaluations</h1>

      <Card>
        <CardHeader>
          <CardTitle>Current Production Baseline</CardTitle>
        </CardHeader>
        <CardContent>
          {!data.baseline ? (
            <EmptyState
              title="No benchmark artifact available"
              description="Run scripts/benchmark_stability.py to produce artifacts/embedding-benchmark-sprint21/stability.json."
            />
          ) : (
            <>
              <p className="mb-3 text-xs text-[var(--color-muted-foreground)]">
                {data.baseline.config} · source: {data.baseline.source}
              </p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {data.baseline.metrics.map((metric) => (
                  <EvaluationMetric key={metric.key} metric={metric} />
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Reranker Decision</CardTitle>
        </CardHeader>
        <CardContent>
          {!data.reranker_decision ? (
            <EmptyState
              title="Reranker benchmark not available"
              description="Run python -m scripts.benchmark_rerankers to produce the Sprint 26 artifact."
            />
          ) : (
            <>
              <p className="mb-3 text-xs text-[var(--color-muted-foreground)]">
                {data.reranker_decision.question_count} questions · recommendation: {data.reranker_decision.recommendation} · source: {data.reranker_decision.source}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-[var(--color-muted-foreground)]">
                    <tr>
                      <th className="pb-2 pr-3">Config</th>
                      <th className="pb-2 pr-3">Cross R@5</th>
                      <th className="pb-2 pr-3">Cross MRR</th>
                      <th className="pb-2 pr-3">Mono R@5</th>
                      <th className="pb-2">Total p95</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.reranker_decision.configs.map((config) => (
                      <tr key={config.config} className="border-t border-[var(--color-border)]">
                        <td className="py-2 pr-3 font-medium">{config.config}</td>
                        <td className="py-2 pr-3 font-technical">{formatMetric(config.cross_lingual.recall_at_5)}</td>
                        <td className="py-2 pr-3 font-technical">{formatMetric(config.cross_lingual.mrr)}</td>
                        <td className="py-2 pr-3 font-technical">{formatMetric(config.mono_lingual.recall_at_5)}</td>
                        <td className="py-2 font-technical">{formatLatency(config.latency.total_retrieval_p95_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-[11px] text-[var(--color-subtle-foreground)]">{data.reranker_decision.rule}</p>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Chunking Decision</CardTitle>
        </CardHeader>
        <CardContent>
          {!data.chunking_decision ? (
            <EmptyState
              title="Chunking benchmark not available"
              description="Run python -m scripts.benchmark_chunking to produce the Sprint 27 artifact."
            />
          ) : (
            <>
              <p className="mb-3 text-xs text-[var(--color-muted-foreground)]">
                {data.chunking_decision.question_count} questions · recommendation: {data.chunking_decision.recommendation} · source: {data.chunking_decision.source}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-[var(--color-muted-foreground)]">
                    <tr>
                      <th className="pb-2 pr-3">Config</th>
                      <th className="pb-2 pr-3">R@5</th>
                      <th className="pb-2 pr-3">Cross R@5</th>
                      <th className="pb-2 pr-3">Avg context</th>
                      <th className="pb-2">Chunks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.chunking_decision.configs.map((config) => (
                      <tr key={config.config} className="border-t border-[var(--color-border)]">
                        <td className="py-2 pr-3 font-medium">{config.config}</td>
                        <td className="py-2 pr-3 font-technical">{formatMetric(config.overall.recall_at_5)}</td>
                        <td className="py-2 pr-3 font-technical">{formatMetric(config.cross_lingual.recall_at_5)}</td>
                        <td className="py-2 pr-3 font-technical">{formatCount(config.context_efficiency.avg_top5_context_tokens)}</td>
                        <td className="py-2 font-technical">{String(config.chunk_stats.total_chunks ?? "—")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-[11px] text-[var(--color-subtle-foreground)]">{data.chunking_decision.rule}</p>
            </>
          )}
        </CardContent>
      </Card>

      {data.migration_quality_gate && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Migration Quality Gate</CardTitle>
            <Badge variant={data.migration_quality_gate.passed ? "success" : "error"}>
              {data.migration_quality_gate.passed ? (
                <CheckCircle2 className="h-3 w-3" />
              ) : (
                <XCircle className="h-3 w-3" />
              )}
              {data.migration_quality_gate.passed ? "Passed" : "Failed"}
            </Badge>
          </CardHeader>
          <CardContent>
            <p className="mb-3 text-xs text-[var(--color-muted-foreground)]">
              {data.migration_quality_gate.question_count} questions · tolerance{" "}
              {data.migration_quality_gate.tolerance}
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["Cross Recall@5", data.migration_quality_gate.cross_recall_at_5],
                ["Cross MRR", data.migration_quality_gate.cross_mrr],
                ["Mono Recall@5", data.migration_quality_gate.mono_recall_at_5],
                ["nDCG@5", data.migration_quality_gate.ndcg_at_5],
              ].map(([label, value]) => (
                <EvaluationMetric
                  key={label as string}
                  metric={{ key: label as string, label: label as string, value: value as number, stddev: null, runs: null }}
                />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Prompt Injection</CardTitle>
        </CardHeader>
        <CardContent>
          {!data.prompt_injection ? (
            <EmptyState
              title="Security evaluation not available"
              description="Run python -m scripts.evaluate_prompt_injection to produce the Sprint 25 artifact."
            />
          ) : (
            <>
              <p className="mb-3 text-xs text-[var(--color-muted-foreground)]">
                {data.prompt_injection.case_count} cases · {data.prompt_injection.prompt_version} · {data.prompt_injection.mode} · source: {data.prompt_injection.source}
              </p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {[
                  ["Injection success rate", "injection_success_rate"],
                  ["Citation spoof rate", "citation_spoof_success_rate"],
                  ["Citation suppression rate", "citation_suppression_success_rate"],
                  ["Unauthorized citation rate", "unauthorized_citation_rate"],
                  ["Cross-tenant exfiltration", "cross_tenant_exfiltration_rate"],
                  ["Benign answer success", "benign_answer_success_rate"],
                ].map(([label, key]) => (
                  <EvaluationMetric
                    key={key}
                    metric={{
                      key,
                      label,
                      value: data.prompt_injection!.metrics[key] ?? null,
                      stddev: null,
                      runs: null,
                    }}
                  />
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Embedding Decision History</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-3 border-l border-[var(--color-border)] pl-4">
            {data.timeline.map((entry) => (
              <li key={entry.sprint} className="relative">
                <span
                  className={cn(
                    "absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full",
                    entry.available ? "bg-[var(--color-accent)]" : "bg-[var(--color-border-strong)]",
                  )}
                />
                <div className="flex items-center gap-2">
                  <span className="font-technical text-xs text-[var(--color-subtle-foreground)]">
                    Sprint {entry.sprint}
                  </span>
                  <span className="text-sm font-medium text-[var(--color-foreground)]">
                    {entry.title}
                  </span>
                  {!entry.available && <Badge>artifact not present</Badge>}
                </div>
                <p className="text-xs text-[var(--color-muted-foreground)]">{entry.question}</p>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Planned metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {PLANNED_METRICS.map((metric) => (
              <Badge key={metric} className="opacity-60">
                {metric} — not yet measured
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
