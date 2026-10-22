import { Calculator } from "lucide-react"
import type { CalculationSummary, SupportUnitRef } from "@/api/types"

// Shows how an application-computed answer was derived: the formula, each
// input with its source citation, and the result. Nothing here is model text.
export function CalculationCard({ calculation, units, onCite }: {
  calculation: CalculationSummary
  units: SupportUnitRef[]
  onCite: (rank: number, supportId: string) => void
}) {
  const unitById = new Map(units.map((unit) => [unit.support_id, unit]))
  const named = calculation.inputs.filter((input) => input.name && input.value !== null)
  return <section aria-label="How this was calculated" className="rounded-lg border border-[var(--color-border)] p-3 text-xs">
    <div className="mb-2 flex items-center gap-2 font-medium text-[var(--color-foreground)]">
      <Calculator aria-hidden="true" className="h-3.5 w-3.5 text-[var(--color-accent)]" /> How this was calculated
    </div>
    {named.length > 0 && <dl className="mb-2 space-y-1">
      {named.map((input) => {
        const unit = input.support_id ? unitById.get(input.support_id) : undefined
        return <div key={input.name} className="flex flex-wrap items-baseline gap-x-2">
          <dt className="font-technical text-[var(--color-muted-foreground)]">{input.name}</dt>
          <dd className="flex flex-wrap items-baseline gap-x-2">
            <span>{input.label}</span>
            <span className="font-technical text-[var(--color-foreground)]">{[input.value, input.unit].filter(Boolean).join(" ")}</span>
            {unit && <button type="button" onClick={() => onCite(unit.source_rank, unit.support_id)}
              aria-label={`Open the source of ${input.name}`}
              className="rounded border border-[var(--color-border)] px-1 text-[10px] text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
              {unit.page_number ? `p. ${unit.page_number}` : unit.support_id}
            </button>}
          </dd>
        </div>
      })}
    </dl>}
    <p className="font-technical text-[var(--color-foreground)]">
      {calculation.expression} = <strong>{[calculation.result, calculation.unit].filter(Boolean).join(" ")}</strong>
    </p>
    <p className="mt-1 text-[var(--color-subtle-foreground)]">Computed by the application from the cited values, not by the model.</p>
  </section>
}
