import { createContext, type ReactNode, useContext, useState } from "react"

import { cn } from "@/lib/utils"

interface TabsContextValue {
  value: string
  setValue: (value: string) => void
}

const TabsContext = createContext<TabsContextValue | null>(null)

export function Tabs({
  defaultValue,
  value: controlledValue,
  onValueChange,
  children,
  className,
}: {
  defaultValue?: string
  value?: string
  onValueChange?: (value: string) => void
  children: ReactNode
  className?: string
}) {
  const [internal, setInternal] = useState(defaultValue ?? "")
  const value = controlledValue ?? internal
  const setValue = (next: string) => {
    setInternal(next)
    onValueChange?.(next)
  }
  return (
    <TabsContext.Provider value={{ value, setValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-0.5",
        className,
      )}
    >
      {children}
    </div>
  )
}

export function TabsTrigger({
  value,
  children,
  className,
}: {
  value: string
  children: ReactNode
  className?: string
}) {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error("TabsTrigger must be used within Tabs")
  const active = ctx.value === value
  return (
    <button
      role="tab"
      type="button"
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      onClick={() => ctx.setValue(value)}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          const tabs = Array.from(
            (e.currentTarget.closest('[role="tablist"]') ?? document).querySelectorAll(
              '[role="tab"]',
            ),
          ) as HTMLButtonElement[]
          const idx = tabs.indexOf(e.currentTarget)
          const next = e.key === "ArrowRight" ? (idx + 1) % tabs.length : (idx - 1 + tabs.length) % tabs.length
          tabs[next]?.focus()
          tabs[next]?.click()
        }
      }}
      className={cn(
        "rounded-md px-3 py-1 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
        active
          ? "bg-[var(--color-surface)] text-[var(--color-foreground)] shadow-card"
          : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]",
        className,
      )}
    >
      {children}
    </button>
  )
}

export function TabsContent({
  value,
  children,
  className,
}: {
  value: string
  children: ReactNode
  className?: string
}) {
  const ctx = useContext(TabsContext)
  if (!ctx) throw new Error("TabsContent must be used within Tabs")
  if (ctx.value !== value) return null
  return (
    <div role="tabpanel" className={className}>
      {children}
    </div>
  )
}
