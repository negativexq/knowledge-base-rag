import type { ReactNode } from "react"
import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"

import type { RetrievedSource, SupportUnitRef } from "@/api/types"
import { CitationChip } from "@/components/CitationChip"
import { type AnswerSegment, splitAnswerIntoSegments } from "@/lib/citations"

const CITE_PREFIX = "#cite-"

/** The answer as Markdown (lists, inline code, bold, tables) with each
 * citation rendered as a CitationChip. Citations are resolved first, by
 * splitAnswerIntoSegments, then stand in the Markdown as links to
 * "#cite-<n>" so the parser keeps them in place inside any block. */
export function AnswerBody({
  answer,
  sources,
  supportUnits,
  onCite,
}: {
  answer: string
  sources: RetrievedSource[]
  supportUnits: SupportUnitRef[]
  onCite: (rank: number, supportId: string | null) => void
}) {
  const segments = splitAnswerIntoSegments(answer, sources, supportUnits)
  const citations: AnswerSegment[] = []
  const markdown = segments
    .map((segment) => {
      if (segment.type === "text") return segment.text
      citations.push(segment)
      return `[cite](${CITE_PREFIX}${citations.length - 1})`
    })
    .join("")

  return (
    <div className="answer-markdown flex flex-col gap-2">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const citation = href?.startsWith(CITE_PREFIX)
              ? citations[Number(href.slice(CITE_PREFIX.length))]
              : undefined
            if (!citation) {
              return (
                <a href={href} target="_blank" rel="noreferrer" className="text-[var(--color-accent)] underline">
                  {children}
                </a>
              )
            }
            return (
              <CitationChip
                rank={citation.source?.rank}
                supportId={citation.unit?.support_id}
                preview={citation.valid ? citation.unit : undefined}
                valid={citation.valid}
                onClick={() =>
                  citation.source && onCite(citation.source.rank, citation.unit?.support_id ?? null)
                }
              />
            )
          },
          code: ({ children }) => (
            <code className="rounded bg-[var(--color-surface-raised)] px-1 py-0.5 font-technical text-[12px]">
              {children as ReactNode}
            </code>
          ),
          ul: ({ children }) => <ul className="ml-4 list-disc space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="ml-4 list-decimal space-y-1">{children}</ol>,
          p: ({ children }) => <p>{children}</p>,
        }}
      >
        {markdown}
      </Markdown>
    </div>
  )
}
