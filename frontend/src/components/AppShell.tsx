import { type ReactNode, useState } from "react"

import { CommandPalette } from "@/components/CommandPalette"
import { Sidebar } from "@/components/Sidebar"
import { TopBar } from "@/components/TopBar"
import { ThemeProvider } from "@/lib/theme"

const COLLAPSED_KEY = "kb-console.sidebar-collapsed"

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "true"
  } catch {
    return false
  }
}

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const [paletteOpen, setPaletteOpen] = useState(false)

  function toggleSidebar() {
    setCollapsed((value) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, String(!value))
      } catch {
        // Storage unavailable: the sidebar state lasts for this page only.
      }
      return !value
    })
  }

  return (
    <ThemeProvider>
      <div className="flex h-dvh overflow-hidden">
        <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <TopBar onOpenPalette={() => setPaletteOpen(true)} />
          <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
        </div>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </ThemeProvider>
  )
}
