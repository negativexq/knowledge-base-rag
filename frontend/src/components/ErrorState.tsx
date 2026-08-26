import { AlertTriangle, Lock, ShieldOff, WifiOff } from "lucide-react"

import type { ApiErrorKind } from "@/api/client"

const COPY: Record<ApiErrorKind, { title: string; description: string; icon: typeof AlertTriangle }> = {
  unauthenticated: {
    title: "Not signed in",
    description: "Choose a development identity from the top bar to continue.",
    icon: Lock,
  },
  forbidden: {
    title: "Not authorized",
    description: "Your current role or tenant doesn't have access to this.",
    icon: ShieldOff,
  },
  not_found: {
    title: "Not found",
    description: "This resource doesn't exist, or hasn't been created yet.",
    icon: AlertTriangle,
  },
  conflict: {
    title: "Already in progress",
    description: "This action is already running — try again shortly.",
    icon: AlertTriangle,
  },
  unreachable: {
    title: "Backend unreachable",
    description: "Could not reach the API. Check that it's running and CORS is configured.",
    icon: WifiOff,
  },
  server_error: {
    title: "Something went wrong on the server",
    description: "The API returned an error. Check the backend logs for details.",
    icon: AlertTriangle,
  },
  unknown: {
    title: "Something went wrong",
    description: "An unexpected error occurred.",
    icon: AlertTriangle,
  },
}

export function ErrorState({ kind, detail }: { kind: ApiErrorKind; detail?: string }) {
  const copy = COPY[kind]
  const Icon = copy.icon
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error-muted)] px-6 py-10 text-center">
      <Icon className="mb-1 h-6 w-6 text-[var(--color-error)]" strokeWidth={1.75} />
      <p className="text-sm font-medium text-[var(--color-foreground)]">{copy.title}</p>
      <p className="max-w-sm text-xs text-[var(--color-muted-foreground)]">{copy.description}</p>
      {detail && (
        <code className="mt-1 max-w-md truncate rounded bg-black/20 px-2 py-1 font-technical text-[11px] text-[var(--color-subtle-foreground)]">
          {detail}
        </code>
      )}
    </div>
  )
}
