import {
  BarChart3,
  Database,
  FolderOpen,
  Folders,
  History,
  LayoutDashboard,
  type LucideIcon,
  RefreshCw,
  Settings,
  Sparkles,
  Star,
  Waypoints,
} from "lucide-react"

export interface NavItem {
  to: string
  label: string
  description: string
  icon: LucideIcon
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

// One source for the sidebar, the page title in the top bar and the
// command palette, so the three never disagree on names.
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Ask",
    items: [
      {
        to: "/",
        label: "Overview",
        description: "Corpus, sync and service health at a glance",
        icon: LayoutDashboard,
      },
      {
        to: "/playground",
        label: "Research",
        description: "Ask the knowledge base and inspect the evidence",
        icon: Sparkles,
      },
      { to: "/starred", label: "Starred", description: "Your starred research conversations", icon: Star },
      { to: "/projects", label: "Projects", description: "Personal projects for conversations, notes and sources", icon: FolderOpen },
    ],
  },
  {
    label: "Data",
    items: [
      { to: "/collections", label: "Collections", description: "Personal document groups by topic or department", icon: Folders },
      {
        to: "/knowledge",
        label: "Knowledge",
        description: "Connected sources and their documents",
        icon: Database,
      },
      {
        to: "/sync-runs",
        label: "Sync Runs",
        description: "Ingestion history per source",
        icon: RefreshCw,
      },
    ],
  },
  {
    label: "Quality",
    items: [
      {
        to: "/evaluations",
        label: "Evaluations",
        description: "Benchmarks behind the production configuration",
        icon: BarChart3,
      },
      {
        to: "/traces",
        label: "Traces",
        description: "Recent requests, stage by stage",
        icon: Waypoints,
      },
    ],
  },
]

export const SETTINGS_ITEM: NavItem = {
  to: "/settings",
  label: "Settings",
  description: "Effective configuration of this deployment",
  icon: Settings,
}

export const HISTORY_ITEM: NavItem = { to: "/playground/history", label: "History", description: "Saved conversations and research notes", icon: History }

export const ALL_NAV_ITEMS: NavItem[] = [...NAV_GROUPS.flatMap((g) => g.items), HISTORY_ITEM, SETTINGS_ITEM]

export function navItemFor(pathname: string): NavItem | undefined {
  if (pathname === HISTORY_ITEM.to) return HISTORY_ITEM
  if (pathname === "/") return ALL_NAV_ITEMS[0]
  return ALL_NAV_ITEMS.find((item) => item.to !== "/" && pathname.startsWith(item.to))
}
