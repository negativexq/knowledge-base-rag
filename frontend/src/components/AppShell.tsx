import type { ReactNode } from "react"

import { Sidebar } from "@/components/Sidebar"
import { TopBar } from "@/components/TopBar"

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  )
}
