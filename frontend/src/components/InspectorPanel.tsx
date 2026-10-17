import { useRef, useState, useSyncExternalStore, type ReactNode } from "react"
import { Dialog } from "radix-ui"
import { PanelRight, X } from "lucide-react"

const mobileQuery = "(max-width: 1023px)"
const subscribe = (callback: () => void) => {
  const media = window.matchMedia?.(mobileQuery)
  media?.addEventListener("change", callback)
  return () => media?.removeEventListener("change", callback)
}
const isMobile = () => window.matchMedia?.(mobileQuery).matches ?? false
const clampWidth = (width: number) => Math.max(320, Math.min(620, width))

/** A docked desktop inspector and a focus-trapped sheet on small screens. */
export function InspectorPanel({ open, onOpenChange, children }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
}) {
  const mobile = useSyncExternalStore(subscribe, isMobile, () => false)
  const [width, setWidth] = useState(420)
  const drag = useRef<{ x: number; width: number } | null>(null)
  const closeRef = useRef<HTMLButtonElement | null>(null)

  const header = (
    <div className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border)] px-4">
      <div className="flex items-center gap-2 text-xs font-semibold">
        <PanelRight className="h-3.5 w-3.5 text-[var(--color-subtle-foreground)]" /> Evidence inspector
      </div>
      <button ref={closeRef} type="button" aria-label="Close evidence inspector" onClick={() => onOpenChange(false)}
        className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-muted-foreground)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
        <X className="h-4 w-4" />
      </button>
    </div>
  )

  if (mobile) return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/25 backdrop-blur-sm" />
        <Dialog.Content id="evidence-inspector" aria-describedby={undefined}
          onOpenAutoFocus={(event) => { event.preventDefault(); closeRef.current?.focus() }}
          onCloseAutoFocus={(event) => { event.preventDefault(); document.querySelector<HTMLButtonElement>('[aria-controls="evidence-inspector"]')?.focus() }}
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col bg-[var(--color-surface)] shadow-pop">
          <Dialog.Title className="sr-only">Evidence inspector</Dialog.Title>
          {header}
          <div className="min-h-0 flex-1">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )

  if (!open) return null
  return (
    <aside id="evidence-inspector" aria-label="Evidence inspector" style={{ width }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          onOpenChange(false)
          document.querySelector<HTMLButtonElement>('[aria-controls="evidence-inspector"]')?.focus()
        }
      }}
      className="relative flex max-w-[52%] shrink-0 flex-col border-l border-[var(--color-border)] bg-[var(--color-surface)]">
      <div role="separator" tabIndex={0} aria-label="Resize evidence inspector" aria-orientation="vertical"
        aria-valuemin={320} aria-valuemax={620} aria-valuenow={width}
        onPointerDown={(event) => { drag.current = { x: event.clientX, width }; event.currentTarget.setPointerCapture(event.pointerId) }}
        onPointerMove={(event) => { if (drag.current) setWidth(clampWidth(drag.current.width + drag.current.x - event.clientX)) }}
        onPointerUp={(event) => { drag.current = null; event.currentTarget.releasePointerCapture(event.pointerId) }}
        onPointerCancel={() => { drag.current = null }}
        onLostPointerCapture={() => { drag.current = null }}
        onKeyDown={(event) => {
          if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
            event.preventDefault()
            setWidth((value) => event.key === "Home" ? 320 : event.key === "End" ? 620 : clampWidth(value + (event.key === "ArrowLeft" ? 20 : -20)))
          }
        }}
        className="absolute inset-y-0 -left-1 z-10 w-2 touch-none cursor-col-resize transition-colors hover:bg-[var(--color-accent-muted)] focus-visible:bg-[var(--color-accent-muted)] focus-visible:outline-none" />
      {header}
      <div className="min-h-0 flex-1">{children}</div>
    </aside>
  )
}
