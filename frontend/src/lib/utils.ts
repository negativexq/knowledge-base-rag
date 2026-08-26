import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—"
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—"
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffSeconds = Math.max(0, Math.round((now - then) / 1000))
  if (diffSeconds < 60) return `${diffSeconds}s ago`
  const diffMinutes = Math.round(diffSeconds / 60)
  if (diffMinutes < 60) return `${diffMinutes}m ago`
  const diffHours = Math.round(diffMinutes / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.round(diffHours / 24)
  return `${diffDays}d ago`
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—"
  return score.toFixed(3)
}
