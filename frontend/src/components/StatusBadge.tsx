import { Badge } from "@/components/ui/badge"

const STATUS_VARIANT: Record<string, "success" | "warning" | "error" | "default" | "accent"> = {
  success: "success",
  healthy: "success",
  ready: "success",
  enabled: "success",
  disabled: "error",
  running: "accent",
  pending: "warning",
  degraded: "warning",
  rejected: "warning",
  error: "error",
  failed: "error",
  cancelled: "error",
  unavailable: "error",
}

export function StatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase()
  const variant = STATUS_VARIANT[key] ?? "default"
  return (
    <Badge variant={variant} className="capitalize">
      <span
        className="h-1.5 w-1.5 rounded-full bg-current"
        aria-hidden="true"
      />
      {status}
    </Badge>
  )
}
