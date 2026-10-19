import { getToken } from "@/api/auth"
import { API_BASE_URL } from "@/api/client"
import { type ChatRequestOptions, type ChatHistoryTurn, type ChatStreamHandlers, streamChat } from "@/lib/sse"

export const chatApi = {
  ask: (
    question: string,
    history: ChatHistoryTurn[],
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
    options?: ChatRequestOptions,
  ) => streamChat(`${API_BASE_URL}/chat`, getToken(), question, handlers, signal, history, options),
}
