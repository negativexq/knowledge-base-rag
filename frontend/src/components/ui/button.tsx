import { type ButtonHTMLAttributes, forwardRef } from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-background)] disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--color-accent)] text-[var(--color-accent-foreground)] hover:opacity-90",
        secondary:
          "bg-[var(--color-surface-raised)] text-[var(--color-foreground)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]",
        ghost: "text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]",
        destructive: "bg-[var(--color-error)] text-[var(--color-background)] hover:opacity-90",
      },
      size: {
        default: "h-9 px-3.5",
        sm: "h-8 px-2.5 text-xs",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
)
Button.displayName = "Button"
