import type { SyncRun } from "@/api/types"
import { StatusBadge } from "@/components/StatusBadge"
import { formatRelativeTime } from "@/lib/utils"

export function SyncRunTable({
  runs,
  onSelect,
}: {
  runs: SyncRun[]
  onSelect: (run: SyncRun) => void
}) {
  return (
    <table className="w-full text-left text-xs">
      <thead>
        <tr className="border-b border-[var(--color-border)] text-[var(--color-muted-foreground)]">
          <th className="py-2 pr-3 font-medium">Status</th>
          <th className="py-2 pr-3 font-medium">Source</th>
          <th className="py-2 pr-3 font-medium">Trigger</th>
          <th className="py-2 pr-3 font-medium">Changes</th>
          <th className="py-2 pr-3 font-medium">Duration</th>
          <th className="py-2 font-medium">Started</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => {
          const durationMs =
            run.finished_at && run.started_at
              ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
              : null
          return (
            <tr
              key={run.id}
              onClick={() => onSelect(run)}
              className="cursor-pointer border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-hover)]"
            >
              <td className="py-2 pr-3">
                <StatusBadge status={run.status} />
              </td>
              <td className="py-2 pr-3 font-technical capitalize text-[var(--color-foreground)]">
                {run.source_type}
              </td>
              <td className="py-2 pr-3 text-[var(--color-muted-foreground)]">{run.trigger}</td>
              <td className="py-2 pr-3 font-technical text-[var(--color-muted-foreground)]">
                +{run.files_processed} ~{run.files_skipped} -{run.files_deleted}
              </td>
              <td className="py-2 pr-3 font-technical text-[var(--color-muted-foreground)]">
                {durationMs !== null ? `${(durationMs / 1000).toFixed(1)}s` : "—"}
              </td>
              <td className="py-2 text-[var(--color-subtle-foreground)]">
                {formatRelativeTime(run.started_at)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
