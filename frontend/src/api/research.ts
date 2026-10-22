import { getToken } from "@/api/auth"
import { api, API_BASE_URL, ApiError } from "@/api/client"
import type { DocumentReadRequest, DocumentReadResult, EvaluationCandidate, FeedbackSubmission, FeedbackRecord, DocumentPolicy } from "@/api/types"

export const researchApi = {
  permissions: (offset = 0) => api.get<DocumentPolicy[]>(`/research/document-permissions?offset=${offset}`),
  setPermissions: (body: DocumentPolicy) => api.put<DocumentPolicy>("/research/document-permissions", body),
  feedback: (body: FeedbackSubmission) => api.post<FeedbackRecord>("/research/feedback", body),
  reports: (reviewer: boolean, offset = 0, status = "") => api.get<FeedbackRecord[]>(`/research/feedback${reviewer ? "" : "/mine"}?offset=${offset}${status ? `&status=${encodeURIComponent(status)}` : ""}`),
  review: (id: string, status: "triaged" | "resolved" | "dismissed", note: string) => api.post<FeedbackRecord>(`/research/feedback/${encodeURIComponent(id)}/review`, { status, note }),
  read: (body: DocumentReadRequest) => api.post<DocumentReadResult>("/research/documents/read", body),
  promote: (id: string, expectedAnswer: string) => api.post<EvaluationCandidate>(`/research/feedback/${encodeURIComponent(id)}/promote`, { expected_answer: expectedAnswer }),
}

// Reviewed evaluation candidates as JSONL text, for the benchmark set.
export async function fetchEvaluationCandidates(): Promise<string> {
  const token = getToken()
  const response = await fetch(`${API_BASE_URL}/research/evaluation-candidates.jsonl`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!response.ok) throw new ApiError(response.status, `Export failed (${response.status})`, null)
  return response.text()
}

export interface PagePreviewRequest { source_type: string; source_id: string; document_version: string; page: number; highlight?: string }

// The cited page as an image (a blob URL the caller revokes) and whether the
// cited text was found and highlighted on it.
export async function fetchPagePreview(params: PagePreviewRequest, signal?: AbortSignal): Promise<{ url: string; found: boolean }> {
  const query = new URLSearchParams({ source_type: params.source_type, source_id: params.source_id, document_version: params.document_version, page: String(params.page) })
  if (params.highlight) query.set("highlight", params.highlight.slice(0, 600))
  const token = getToken()
  const response = await fetch(`${API_BASE_URL}/research/documents/page?${query}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}, signal,
  })
  if (!response.ok) throw new ApiError(response.status, `Page preview failed (${response.status})`, null)
  return { url: URL.createObjectURL(await response.blob()), found: response.headers.get("X-Highlight-Found") === "1" }
}
