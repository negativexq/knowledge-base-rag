import { BookOpen, ShieldAlert } from "lucide-react"
import { Navigate } from "react-router-dom"

import { DEV_IDENTITIES, getToken, setToken } from "@/api/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function SignIn() {
  if (getToken()) return <Navigate to="/" replace />

  return (
    <div className="flex h-screen items-center justify-center bg-[var(--color-background)] px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <BookOpen className="mb-1 h-6 w-6 text-[var(--color-accent)]" strokeWidth={1.75} />
          <CardTitle className="text-base">Knowledge Base Operations Console</CardTitle>
          <CardDescription>Choose a development identity to continue.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {DEV_IDENTITIES.map((identity) => (
            <Button
              key={identity.token}
              variant="secondary"
              className="justify-start font-technical"
              onClick={() => {
                setToken(identity.token)
                window.location.href = "/"
              }}
            >
              {identity.label}
            </Button>
          ))}
          <div className="mt-3 flex items-start gap-2 rounded-md border border-[var(--color-warning)]/30 bg-[var(--color-warning-muted)] p-2.5 text-left">
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--color-warning)]" />
            <p className="text-[11px] leading-snug text-[var(--color-muted-foreground)]">
              These are demo development tokens (app/security/auth.py::DEFAULT_DEV_TOKENS) — never
              real credentials. A production deployment replaces this screen with a real login
              flow.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
