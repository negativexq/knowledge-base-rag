import { useMemo, useState, useSyncExternalStore } from "react"
import { documentKey, ORGANIZATION_EVENT, organizationKey, readOrganization, writeOrganization, type DocumentReference, type LocalCollection, type LocalProject, type Organization } from "@/lib/organization"

function subscribe(listener: () => void) {
  window.addEventListener("storage", listener)
  window.addEventListener(ORGANIZATION_EVENT, listener)
  return () => { window.removeEventListener("storage", listener); window.removeEventListener(ORGANIZATION_EVENT, listener) }
}
export function useOrganization(scope: string) {
  const snapshot = useSyncExternalStore(subscribe, () => {
    try { return localStorage.getItem(organizationKey(scope)) ?? "null" } catch { return "null" }
  }, () => "null")
  const data = useMemo(() => readOrganization(scope, snapshot), [scope, snapshot])
  const [error, setError] = useState("")
  function update(fn: (value: Organization) => Organization): boolean {
    const saved = writeOrganization(scope, fn)
    setError(saved ? "" : "Changes could not be saved. Browser storage is unavailable or full.")
    return saved
  }
  function create(kind: "projects" | "collections", name: string, description: string, documents: DocumentReference[] = []): LocalProject | null {
    if (!name.trim()) return null
    const now = new Date().toISOString()
    const group = { id: crypto.randomUUID(), name: name.trim().slice(0, 80), description: description.trim().slice(0, 1000), createdAt: now, updatedAt: now }
    const saved = update((value) => kind === "projects" ? { ...value, projects: [...value.projects, group] } : { ...value, collections: [...value.collections, { ...group, documents: [...new Map(documents.map((document) => [documentKey(document), document])).values()] }] })
    return saved ? group : null
  }
  function edit(kind: "projects" | "collections", id: string, name: string, description: string) {
    if (!name.trim()) return false
    const change = (group: LocalProject) => ({ ...group, name: name.trim().slice(0, 80), description: description.trim().slice(0, 1000), updatedAt: new Date().toISOString() })
    return update((value) => kind === "projects" ? { ...value, projects: value.projects.map((group) => group.id === id ? change(group) : group) } : { ...value, collections: value.collections.map((group) => group.id === id ? { ...group, ...change(group) } : group) })
  }
  function assign(sessionId: string, projectId: string | null) {
    return update((value) => ({ ...value, assignments: Object.fromEntries([...Object.entries(value.assignments).filter(([id]) => id !== sessionId), ...(projectId && value.projects.some((project) => project.id === projectId) ? [[sessionId, projectId]] : [])]) }))
  }
  function remove(kind: "projects" | "collections", id: string): (() => void) | null {
    const group = data[kind].find((item) => item.id === id)
    if (!group) return null
    const assignments = Object.entries(data.assignments).filter(([, projectId]) => projectId === id)
    if (!update((value) => kind === "projects" ? { ...value, projects: value.projects.filter((item) => item.id !== id), assignments: Object.fromEntries(Object.entries(value.assignments).filter(([, projectId]) => projectId !== id)) } : { ...value, collections: value.collections.filter((item) => item.id !== id) })) return null
    return () => { update((value) => kind === "projects" ? { ...value, projects: value.projects.some((item) => item.id === id) ? value.projects : [...value.projects, group], assignments: { ...Object.fromEntries(assignments), ...value.assignments } } : { ...value, collections: value.collections.some((item) => item.id === id) ? value.collections : [...value.collections, group as LocalCollection] }) }
  }
  function addDocuments(id: string, documents: DocumentReference[]) {
    return update((value) => ({ ...value, collections: value.collections.map((collection) => collection.id === id ? { ...collection, updatedAt: new Date().toISOString(), documents: [...new Map([...collection.documents, ...documents].map((document) => [documentKey(document), document])).values()] } : collection) }))
  }
  function removeDocument(id: string, document: DocumentReference) {
    return update((value) => ({ ...value, collections: value.collections.map((collection) => collection.id === id ? { ...collection, documents: collection.documents.filter((item) => documentKey(item) !== documentKey(document)), updatedAt: new Date().toISOString() } : collection) }))
  }
  return { ...data, error, create, edit, assign, remove, addDocuments, removeDocument }
}
