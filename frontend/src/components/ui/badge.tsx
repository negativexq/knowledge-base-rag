import type { HTMLAttributes } from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "bg-[var(--color-surface-raised)] text-[var(--color-muted-foreground)] border border-[var(--color-border)]",
        accent: "bg-[var(--color-accent-muted)] text-[var(--color-accent)]",
        success: "bg-[var(--color-success-muted)] text-[var(--color-success)]",
        warning: "bg-[var(--color-warning-muted)] text-[var(--color-warning)]",
        error: "bg-[var(--color-error-muted)] text-[var(--color-error)]",
      },
    },
    defaultVariants: { variant: "default" },
  },
)

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
