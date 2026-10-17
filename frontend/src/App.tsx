import { lazy, Suspense } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/AppShell"
import { getToken } from "@/api/auth"
import { LoadingRows } from "@/components/LoadingSkeleton"

// Load page code on demand while keeping the navigation shell visible.
const Playground = lazy(() => import("@/pages/Playground"))
const Starred = lazy(() => import("@/pages/Starred"))
const Projects = lazy(() => import("@/pages/Projects"))
const Collections = lazy(() => import("@/pages/Collections"))
const HistoryPage = lazy(() => import("@/pages/History"))
const Evaluations = lazy(() => import("@/pages/Evaluations"))
const Knowledge = lazy(() => import("@/pages/Knowledge"))
const Overview = lazy(() => import("@/pages/Overview"))
const SettingsPage = lazy(() => import("@/pages/Settings"))
const SignIn = lazy(() => import("@/pages/SignIn"))
const SyncRuns = lazy(() => import("@/pages/SyncRuns"))
const Traces = lazy(() => import("@/pages/Traces"))

function RequireIdentity({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/sign-in" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/sign-in" element={<Suspense fallback={<LoadingRows rows={4} />}><SignIn /></Suspense>} />
        <Route
          path="/*"
          element={
            <RequireIdentity>
              <AppShell>
                <Suspense fallback={<LoadingRows rows={4} />}>
                  <Routes>
                    <Route path="/" element={<Overview />} />
                    <Route path="/playground" element={<Playground />} />
                    <Route path="/starred" element={<Starred />} />
                    <Route path="/projects" element={<Projects />} />
                    <Route path="/collections" element={<Collections />} />
                    <Route path="/playground/history" element={<HistoryPage />} />
                    <Route path="/knowledge" element={<Knowledge />} />
                    <Route path="/sync-runs" element={<SyncRuns />} />
                    <Route path="/evaluations" element={<Evaluations />} />
                    <Route path="/traces" element={<Traces />} />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Suspense>
              </AppShell>
            </RequireIdentity>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
