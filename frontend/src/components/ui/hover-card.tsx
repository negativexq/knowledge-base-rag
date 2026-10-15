import type { ComponentProps } from "react"
import { HoverCard as HoverCardPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"

// shadcn/ui HoverCard on Radix, styled with the console's color tokens.
// Opens on pointer hover and on keyboard focus of the trigger.
export function HoverCard({ openDelay = 150, closeDelay = 100, ...props }: ComponentProps<typeof HoverCardPrimitive.Root>) {
  return <HoverCardPrimitive.Root openDelay={openDelay} closeDelay={closeDelay} {...props} />
}

export function HoverCardTrigger(props: ComponentProps<typeof HoverCardPrimitive.Trigger>) {
  return <HoverCardPrimitive.Trigger {...props} />
}

export function HoverCardContent({
  className,
  align = "center",
  sideOffset = 6,
  ...props
}: ComponentProps<typeof HoverCardPrimitive.Content>) {
  return (
    <HoverCardPrimitive.Portal>
      <HoverCardPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-50 w-80 rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-surface-raised)] p-3 text-xs text-[var(--color-foreground)] shadow-lg outline-none",
          className,
        )}
        {...props}
      />
    </HoverCardPrimitive.Portal>
  )
}
