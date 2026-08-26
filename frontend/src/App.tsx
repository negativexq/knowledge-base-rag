import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/AppShell"
import { getToken } from "@/api/auth"
import Evaluations from "@/pages/Evaluations"
import Knowledge from "@/pages/Knowledge"
import Overview from "@/pages/Overview"
import Playground from "@/pages/Playground"
import SettingsPage from "@/pages/Settings"
import SignIn from "@/pages/SignIn"
import SyncRuns from "@/pages/SyncRuns"
import Traces from "@/pages/Traces"

function RequireIdentity({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/sign-in" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/sign-in" element={<SignIn />} />
        <Route
          path="/*"
          element={
            <RequireIdentity>
              <AppShell>
                <Routes>
                  <Route path="/" element={<Overview />} />
                  <Route path="/playground" element={<Playground />} />
                  <Route path="/knowledge" element={<Knowledge />} />
                  <Route path="/sync-runs" element={<SyncRuns />} />
                  <Route path="/evaluations" element={<Evaluations />} />
                  <Route path="/traces" element={<Traces />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </AppShell>
            </RequireIdentity>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
