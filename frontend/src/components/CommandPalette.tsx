import { useEffect, useId, useMemo, useState } from "react"
import { Dialog as DialogPrimitive } from "radix-ui"
import { type LucideIcon, Moon, Search, Sun } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { ALL_NAV_ITEMS } from "@/lib/nav"
import { themeSwitchLabel, useTheme } from "@/lib/theme"
import { cn } from "@/lib/utils"

interface Command {
  id: string
  group: "Go to" | "Preferences"
  label: string
  hint?: string
  icon: LucideIcon
  run: () => void
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const listId = useId()

  // Cmd+K / Ctrl+K toggles the palette from anywhere in the console.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        onOpenChange(!open)
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [open, onOpenChange])

  const commands = useMemo<Command[]>(
    () => [
      ...ALL_NAV_ITEMS.map((item) => ({
        id: item.to,
        group: "Go to" as const,
        label: item.label,
        hint: item.description,
        icon: item.icon,
        run: () => navigate(item.to),
      })),
      {
        id: "theme",
        group: "Preferences" as const,
        label: themeSwitchLabel(theme),
        icon: theme === "dark" ? Sun : Moon,
        run: toggleTheme,
      },
    ],
    [navigate, theme, toggleTheme],
  )

  const needle = query.trim().toLowerCase()
  const matches = needle
    ? commands.filter((command) => command.label.toLowerCase().includes(needle))
    : commands
  const activeIndex = Math.min(active, Math.max(matches.length - 1, 0))

  function close() {
    onOpenChange(false)
    setQuery("")
    setActive(0)
  }

  function run(command: Command | undefined) {
    if (!command) return
    close()
    command.run()
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="animate-in fixed left-1/2 top-[18vh] z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-pop focus:outline-none"
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <div className="flex items-center gap-2.5 border-b border-[var(--color-border)] px-4">
            <Search className="h-4 w-4 shrink-0 text-[var(--color-subtle-foreground)]" />
            <input
              role="combobox"
              aria-label="Search commands"
              aria-expanded="true"
              aria-controls={listId}
              aria-activedescendant={matches[activeIndex] ? `${listId}-${activeIndex}` : undefined}
              autoFocus
              value={query}
              placeholder="Search pages and actions…"
              onChange={(event) => {
                setQuery(event.target.value)
                setActive(0)
              }}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") {
                  event.preventDefault()
                  setActive((activeIndex + 1) % Math.max(matches.length, 1))
                } else if (event.key === "ArrowUp") {
                  event.preventDefault()
                  setActive((activeIndex - 1 + matches.length) % Math.max(matches.length, 1))
                } else if (event.key === "Enter") {
                  event.preventDefault()
                  run(matches[activeIndex])
                }
              }}
              className="h-12 flex-1 bg-transparent text-sm text-[var(--color-foreground)] outline-none placeholder:text-[var(--color-subtle-foreground)]"
            />
            <kbd className="rounded border border-[var(--color-border)] px-1.5 py-0.5 font-technical text-[10px] text-[var(--color-subtle-foreground)]">
              Esc
            </kbd>
          </div>

          <div id={listId} role="listbox" aria-label="Commands" className="max-h-[min(420px,60vh)] overflow-y-auto p-1.5">
            {matches.length === 0 && (
              <p className="px-3 py-6 text-center text-sm text-[var(--color-muted-foreground)]">
                No matching command
              </p>
            )}
            {matches.map((command, index) => {
              const Icon = command.icon
              const firstOfGroup = index === 0 || matches[index - 1].group !== command.group
              return (
                <div key={command.id}>
                  {firstOfGroup && (
                    <div
                      aria-hidden="true"
                      className="px-2.5 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wider text-[var(--color-subtle-foreground)]"
                    >
                      {command.group}
                    </div>
                  )}
                  <div
                    id={`${listId}-${index}`}
                    role="option"
                    aria-selected={index === activeIndex}
                    aria-label={command.label}
                    onMouseMove={() => setActive(index)}
                    onClick={() => run(command)}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm",
                      index === activeIndex
                        ? "bg-[var(--color-surface-hover)] text-[var(--color-foreground)]"
                        : "text-[var(--color-muted-foreground)]",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
                    <span className="font-medium text-[var(--color-foreground)]">{command.label}</span>
                    {command.hint && (
                      <span
                        aria-hidden="true"
                        className="ml-auto truncate text-xs text-[var(--color-subtle-foreground)]"
                        data-hint
                      >
                        {command.hint}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
