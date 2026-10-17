import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react"

export type Theme = "dark" | "light"

const THEME_KEY = "kb-console.theme"

// index.html sets data-theme before first paint (saved choice, else light); start from whatever it decided so the two agree.
function initialTheme(): Theme {
  const applied = document.documentElement.dataset.theme
  if (applied === "light" || applied === "dark") return applied
  try {
    const saved = localStorage.getItem(THEME_KEY)
    if (saved === "light" || saved === "dark") return saved
  } catch {
    // Storage unavailable: fall through to the default theme.
  }
  return "light"
}

interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(initialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      // Storage unavailable: the choice lasts for this page only.
    }
  }, [])

  const toggleTheme = useCallback(
    () => setTheme(theme === "dark" ? "light" : "dark"),
    [theme, setTheme],
  )

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider")
  return ctx
}

// eslint-disable-next-line react-refresh/only-export-components
export function themeSwitchLabel(theme: Theme): string {
  return theme === "dark" ? "Switch to light theme" : "Switch to dark theme"
}
