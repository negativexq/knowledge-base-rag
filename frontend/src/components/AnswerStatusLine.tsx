import { CheckCircle2, Info, XCircle } from "lucide-react"

import type { AnswerStatus } from "@/lib/answerStatus"
import { cn } from "@/lib/utils"

const STYLE = {
  verified: { icon: CheckCircle2, className: "bg-[var(--color-success-muted)] text-[var(--color-success)]" },
  unverified: { icon: XCircle, className: "bg-[var(--color-error-muted)] text-[var(--color-error)]" },
  not_found: { icon: Info, className: "bg-[var(--color-surface-raised)] text-[var(--color-muted-foreground)]" },
  no_evidence: { icon: Info, className: "bg-[var(--color-surface-raised)] text-[var(--color-muted-foreground)]" },
} as const

/** The answer's verdict under it: a badge, plus the plain-language reasons
 * when the answer could not be verified or the model was not called. */
export function AnswerStatusLine({ status }: { status: AnswerStatus }) {
  const { icon: Icon, className } = STYLE[status.kind]
  return (
    <div className="flex flex-col gap-1">
      <div className={cn("flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-xs", className)}>
        <Icon className="h-3 w-3" />
        {status.title}
      </div>
      {status.reasons.length > 0 && (
        <ul className="ml-1 flex flex-col gap-0.5 text-xs text-[var(--color-muted-foreground)]">
          {status.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
