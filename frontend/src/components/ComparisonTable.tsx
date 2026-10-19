import type { ComparisonRow, RetrievedSource, SupportUnitRef } from "@/api/types"
import { AnswerBody } from "@/components/AnswerBody"

export function ComparisonTable({ rows, sources, units, onCite }: {
  rows: ComparisonRow[]; sources: RetrievedSource[]; units: SupportUnitRef[]
  onCite: (rank: number, supportId: string | null) => void
}) {
  const documents = [...new Set(rows.flatMap((row) => row.cells.map((cell) => cell.source_id)))]
  return <div className="overflow-x-auto"><table aria-label="Document comparison" className="w-full border-collapse text-left text-sm">
    <caption className="pb-3 text-left text-xs text-[var(--color-muted-foreground)]">Supported differences. An empty cell means no supported comparison was provided.</caption>
    <thead><tr><th className="border-b border-[var(--color-border)] p-3">Aspect</th>{documents.map((doc) => <th key={doc} className="border-b border-[var(--color-border)] p-3">{doc}</th>)}</tr></thead>
    <tbody>{rows.map((row, index) => <tr key={index}><th className="border-b border-[var(--color-border)] p-3 align-top">{row.aspect}</th>{documents.map((doc) => {
      const cell = row.cells.find((item) => item.source_id === doc)
      return <td key={doc} className="min-w-48 border-b border-[var(--color-border)] p-3 align-top">{cell ? <AnswerBody answer={`${cell.text} ${cell.support_ids.map((id) => `[${id}]`).join(" ")}`} sources={sources} supportUnits={units} onCite={onCite} /> : "—"}</td>
    })}</tr>)}</tbody>
  </table></div>
}
