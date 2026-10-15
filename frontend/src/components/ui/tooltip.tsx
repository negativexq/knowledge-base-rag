import type { ComponentProps } from "react"
import { Tooltip as TooltipPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

// shadcn/ui Tooltip on Radix, styled with the console's color tokens.
// Each Tooltip carries its own provider so call sites stay one element.
export function Tooltip({ delayDuration = 200, ...props }: ComponentProps<typeof TooltipPrimitive.Root>) {
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration}>
      <TooltipPrimitive.Root {...props} />
    </TooltipPrimitive.Provider>
  )
}

export function TooltipTrigger(props: ComponentProps<typeof TooltipPrimitive.Trigger>) {
  return <TooltipPrimitive.Trigger {...props} />
}

export function TooltipContent({
  className,
  sideOffset = 4,
  ...props
}: ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-xs rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-2 py-1 text-[11px] text-[var(--color-foreground)] shadow-md",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  )
}
