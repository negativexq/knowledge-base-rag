// Sprint 24: LOCAL DEV ONLY demo identity selector — mirrors
// app/security/auth.py::DEFAULT_DEV_TOKENS exactly (a literal copy, not
// a shared import, since the frontend and backend are separate
// deployables). Never a real credential; never hardcode a production
// token here. A real deployment replaces this whole module with a real
// login flow — the rest of the app only depends on `getToken()`
// returning SOME bearer token, never on how it was obtained.

export interface DevIdentityOption {
  label: string
  token: string
}

export const DEV_IDENTITIES: DevIdentityOption[] = [
  { label: "tenant-a — user", token: "token-user-a" },
  { label: "tenant-a — operator", token: "token-operator-a" },
  { label: "tenant-a — admin", token: "token-admin-a" },
  { label: "tenant-b — user", token: "token-user-b" },
  { label: "tenant-b — operator", token: "token-operator-b" },
]

const STORAGE_KEY = "kb-console.dev-token"

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(STORAGE_KEY)
}
