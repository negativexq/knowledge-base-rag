import type { DocumentRecord } from "@/api/types"

export interface LocalProject { id: string; name: string; description: string; createdAt: string; updatedAt: string }
export interface DocumentReference { sourceType: string; sourceId: string }
export interface LocalCollection extends LocalProject { documents: DocumentReference[] }
export interface Organization { projects: LocalProject[]; collections: LocalCollection[]; assignments: Record<string, string> }
export const ORGANIZATION_EVENT = "kb-console:organization-change"
export const RESEARCH_EVENT = "kb-console:research-change"
export const organizationKey = (scope: string) => `${scope}:organization.v1`
export const documentKey = (document: DocumentReference) => JSON.stringify([document.sourceType, document.sourceId])
export const documentReference = (document: DocumentRecord): DocumentReference => ({ sourceType: document.source_type, sourceId: document.source_id })
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null
const isGroup = (value: unknown): value is LocalProject => isRecord(value) && typeof value.id === "string" && typeof value.name === "string" && typeof value.description === "string" && typeof value.createdAt === "string" && typeof value.updatedAt === "string"
const isDocument = (value: unknown): value is DocumentReference => isRecord(value) && typeof value.sourceType === "string" && typeof value.sourceId === "string"

export function readOrganization(scope: string, snapshot?: string): Organization {
  try {
    const value: unknown = JSON.parse(snapshot ?? localStorage.getItem(organizationKey(scope)) ?? "null")
    if (!isRecord(value)) return { projects: [], collections: [], assignments: {} }
    const projects = Array.isArray(value.projects) ? value.projects.filter(isGroup) : []
    const collections = Array.isArray(value.collections) ? value.collections.filter((item): item is LocalCollection => isGroup(item) && isRecord(item) && Array.isArray(item.documents) && item.documents.every(isDocument)) : []
    const assignments = isRecord(value.assignments) ? Object.fromEntries(Object.entries(value.assignments).filter(([, id]) => projects.some((project) => project.id === id))) as Record<string, string> : {}
    return { projects, collections, assignments }
  } catch { return { projects: [], collections: [], assignments: {} } }
}

export function writeOrganization(scope: string, update: (value: Organization) => Organization): boolean {
  try {
    localStorage.setItem(organizationKey(scope), JSON.stringify(update(readOrganization(scope))))
    window.dispatchEvent(new Event(ORGANIZATION_EVENT))
    return true
  } catch { return false }
}

export function queueResearch(scope: string, sessionId: string | null, projectId: string | null): boolean {
  try { sessionStorage.setItem(`${scope}:launch`, JSON.stringify({ sessionId, projectId })); return true }
  catch { return false }
}
