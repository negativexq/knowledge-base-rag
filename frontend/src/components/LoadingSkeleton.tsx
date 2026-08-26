import { cn } from "@/lib/utils"

export function LoadingSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-[var(--color-surface-raised)]",
        className,
      )}
    />
  )
}

export function LoadingRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <LoadingSkeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  )
}
