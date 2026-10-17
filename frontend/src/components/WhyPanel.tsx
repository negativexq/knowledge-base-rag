import { ChevronRight } from "lucide-react"
import type { ReactNode } from "react"

import type {
  AnswerValidation,
  ChatMetadata,
  RetrievalReportPayload,
  RetrievedSource,
} from "@/api/types"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { type AnswerStatus, describeDoneReason, explainSkip } from "@/lib/answerStatus"
import { formatMs } from "@/lib/utils"

const number = (value: number) => value.toLocaleString("en-US")

function Step({ title, summary, children }: { title: string; summary: ReactNode; children?: ReactNode }) {
  return (
    <li className="border-b border-[var(--color-border)]">
      <Collapsible>
        <CollapsibleTrigger
          disabled={!children}
          className="group flex w-full items-start gap-2 p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:cursor-default"
        >
          <ChevronRight
            className={`mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--color-subtle-foreground)] transition-transform group-data-[state=open]:rotate-90 ${children ? "" : "invisible"}`}
          />
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] uppercase tracking-wide text-[var(--color-subtle-foreground)]">{title}</span>
            <span className="text-xs text-[var(--color-foreground)]">{summary}</span>
          </div>
        </CollapsibleTrigger>
        {children && (
          <CollapsibleContent className="px-3 pb-3 pl-8 text-xs text-[var(--color-muted-foreground)]">
            {children}
          </CollapsibleContent>
        )}
      </Collapsible>
    </li>
  )
}

/** One answer's path, step by step: the search query, retrieval, the
 * evidence, how the prompt was fitted, how the model call ended and the
 * validator's verdict. Every figure comes from the stream; a step the
 * stream did not report says so instead of guessing. */
export function WhyPanel({
  question,
  report,
  sources,
  metadata,
  validation,
  status,
}: {
  question: string
  report: RetrievalReportPayload | null
  sources: RetrievedSource[]
  metadata: ChatMetadata | null
  validation: AnswerValidation | null
  status: AnswerStatus | null
}) {
  const stage = (name: string) => report?.stages.find((s) => s.name === name)
  const rewrite = stage("query_rewrite")
  const searchQuery = rewrite?.detail?.search_query
  const retrieved = stage("hybrid_retrieval")
  const reranked = stage("rerank")
  const fit = metadata?.prompt_fit
  const generation = validation?.generation
  const skipped = metadata?.generation_skipped

  return (
    <ol aria-label="Why this answer" className="flex flex-col gap-2">
      <Step
        title="Question"
        summary={typeof searchQuery === "string" ? `Searched as: ${searchQuery}` : "Searched as asked"}
      >
        <p>Asked: {question}</p>
        {rewrite && (
          <p>
            Rewrite: {String(rewrite.detail?.outcome ?? "unknown")} · {formatMs(rewrite.duration_ms)}
          </p>
        )}
      </Step>
      <Step
        title="Retrieval"
        summary={
          retrieved?.candidates_out == null
            ? "Not reported"
            : reranked?.candidates_out != null
              ? `${retrieved.candidates_out} candidates → ${reranked.candidates_out} after reranking`
              : `${retrieved.candidates_out} candidates`
        }
      >
        {report?.stages.map((s) => (
          <p key={s.name}>
            {s.name}: {formatMs(s.duration_ms)}
          </p>
        ))}
        {report?.answerability && <p>Answerability: {report.answerability.reason}</p>}
      </Step>
      <Step title="Evidence" summary={`${sources.length} ${sources.length === 1 ? "source" : "sources"}`}>
        {sources.map((source) => (
          <p key={source.rank}>
            #{source.rank} {source.source_id}
            {source.section_labels && source.section_labels.length > 1
              ? ` · ${source.section_labels.length} sections`
              : ""}
          </p>
        ))}
      </Step>
      <Step
        title="Prompt"
        summary={
          skipped
            ? "Model not called"
            : fit
              ? `${number(fit.prompt_tokens)} / ${number(fit.prompt_token_limit)} prompt tokens · ${fit.units_sent} passages sent${
                  fit.units_dropped > 0 ? `, ${fit.units_dropped} lowest-ranked left out to fit` : ""
                }`
              : "Not reported"
        }
      >
        {fit && !skipped && (
          <>
            <div
              className="mb-1.5 h-1.5 w-full overflow-hidden rounded bg-[var(--color-surface)]"
              role="meter"
              aria-label="Prompt size"
              aria-valuemin={0}
              aria-valuemax={fit.prompt_token_limit}
              aria-valuenow={fit.prompt_tokens}
            >
              <div
                className="h-full bg-[var(--color-accent)]"
                style={{ width: `${Math.min(100, (fit.prompt_tokens / fit.prompt_token_limit) * 100)}%` }}
              />
            </div>
            <p>
              {Math.round((fit.prompt_tokens / fit.prompt_token_limit) * 100)}% of the prompt budget; the rest of
              the context window is reserved for the answer.
            </p>
          </>
        )}
      </Step>
      <Step
        title="Model"
        summary={
          skipped
            ? explainSkip(skipped)
            : generation
              ? `${describeDoneReason(generation.done_reason)}${
                  generation.output_tokens != null ? ` · ${number(generation.output_tokens)} output tokens` : ""
                }`
              : "Not reported"
        }
      >
        {generation?.prompt_tokens != null && <p>Prompt as counted by the model: {number(generation.prompt_tokens)} tokens</p>}
      </Step>
      <Step title="Validation" summary={status?.title ?? "Pending"}>
        {status && status.reasons.length > 0 && (
          <ul className="list-disc pl-4">
            {status.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        {validation && validation.validator_failure_codes.length > 0 && (
          <p className="font-technical">{validation.validator_failure_codes.join(", ")}</p>
        )}
      </Step>
    </ol>
  )
}
