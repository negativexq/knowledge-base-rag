import { useSyncExternalStore } from "react"

import { RESEARCH_EVENT } from "@/lib/organization"
import { newResearchSession, readResearchSessions, researchOutcome, type ResearchSession, type ResearchTurn } from "@/lib/research"

// Research that keeps running while the person opens another session or
// leaves the page. Streams live here, outside any component, so unmounting
// the workspace no longer cancels them. A finished turn is handed to the
// mounted research library for its scope, or written to browser storage
// when none is mounted.

export interface FinishedRun { scope: string; sessionId: string; question: string; outcome: "answered" | "unverified" | "stopped"; at: number }

interface Run { scope: string; sessionId: string; turn: ResearchTurn; controller: AbortController }

export interface RunsSnapshot { live: ReadonlyMap<string, ResearchTurn>; running: { scope: string; sessionId: string; question: string }[]; finished: FinishedRun[] }

export interface RunHandle {
  signal: AbortSignal
  update: (fn: (turn: ResearchTurn) => ResearchTurn) => void
  finish: (patch?: Partial<ResearchTurn>) => void
}

export const OPEN_RESEARCH_EVENT = "kb-console.open-research"

type Saver = (sessionId: string, turn: ResearchTurn) => void

const runs = new Map<string, Run>()
const savers = new Map<string, Saver>()
const listeners = new Set<() => void>()
let finished: FinishedRun[] = []
let viewing: string | null = null
let snapshot: RunsSnapshot = { live: new Map(), running: [], finished }

function emit() {
  snapshot = {
    live: new Map([...runs].map(([id, run]) => [id, run.turn])),
    running: [...runs.values()].map((run) => ({ scope: run.scope, sessionId: run.sessionId, question: run.turn.question })),
    finished,
  }
  listeners.forEach((listener) => listener())
}

export function appendTurn(session: ResearchSession, turn: ResearchTurn): ResearchSession {
  const turns = [...session.turns, turn]
  return { ...session, turns, title: session.customTitle ? session.title : (turns[0]?.question.slice(0, 100) || session.title), updatedAt: new Date().toISOString() }
}

function writeToStorage(scope: string, sessionId: string, turn: ResearchTurn) {
  try {
    const sessions = readResearchSessions(scope)
    const existing = sessions.find((session) => session.id === sessionId)
    const next = existing
      ? sessions.map((session) => session.id === sessionId ? appendTurn(session, turn) : session)
      : [...sessions, appendTurn({ ...newResearchSession(), id: sessionId }, turn)]
    localStorage.setItem(scope, JSON.stringify(next))
    window.dispatchEvent(new Event(RESEARCH_EVENT))
  } catch { /* Storage unavailable: the finished answer is lost with this visit. */ }
}

function notify(run: Run, turn: ResearchTurn) {
  const outcome = researchOutcome(turn) ?? "stopped"
  const hidden = typeof document !== "undefined" && document.hidden
  if (viewing === run.sessionId && !hidden) return
  finished = [...finished.filter((item) => item.sessionId !== run.sessionId), { scope: run.scope, sessionId: run.sessionId, question: turn.question, outcome, at: Date.now() }]
  if (hidden && typeof Notification !== "undefined" && Notification.permission === "granted") {
    try {
      const notice = new Notification("Research finished", { body: turn.question.slice(0, 140), tag: run.sessionId })
      notice.onclick = () => window.focus()
    } catch { /* Some browsers only allow notifications from a service worker. */ }
  }
}

export function startRun(scope: string, sessionId: string, turn: ResearchTurn): RunHandle {
  runs.get(sessionId)?.controller.abort()
  const controller = new AbortController()
  const run: Run = { scope, sessionId, turn: { ...turn, streaming: true }, controller }
  runs.set(sessionId, run)
  finished = finished.filter((item) => item.sessionId !== sessionId)
  emit()
  // Late events from a cancelled or replaced stream are ignored.
  const own = () => runs.get(sessionId) === run
  return {
    signal: controller.signal,
    update(fn) {
      if (!own()) return
      run.turn = fn(run.turn)
      emit()
    },
    finish(patch = {}) {
      if (!own()) return
      runs.delete(sessionId)
      const done = { ...run.turn, ...patch, streaming: false, researchFinishedAt: Date.now() }
      const saver = savers.get(scope)
      if (saver) saver(sessionId, done); else writeToStorage(scope, sessionId, done)
      if (done.errorMessage !== "Cancelled.") notify(run, done)
      emit()
    },
  }
}

export function cancelRun(sessionId: string) {
  const run = runs.get(sessionId)
  if (!run) return
  run.controller.abort()
  const saver = savers.get(run.scope)
  runs.delete(sessionId)
  const done = { ...run.turn, streaming: false, errorMessage: "Cancelled.", researchFinishedAt: Date.now() }
  if (saver) saver(sessionId, done); else writeToStorage(run.scope, sessionId, done)
  emit()
}

export function isRunning(sessionId: string): boolean { return runs.has(sessionId) }

// The mounted library for a scope receives finished turns, so its own
// snapshot never overwrites them in storage.
export function attachLibrary(scope: string, saver: Saver): () => void {
  savers.set(scope, saver)
  return () => { if (savers.get(scope) === saver) savers.delete(scope) }
}

export function setViewing(sessionId: string | null) {
  viewing = sessionId
  if (sessionId && finished.some((item) => item.sessionId === sessionId)) dismissFinished(sessionId)
}

export function dismissFinished(sessionId: string) {
  finished = finished.filter((item) => item.sessionId !== sessionId)
  emit()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function useResearchRuns(): RunsSnapshot {
  return useSyncExternalStore(subscribe, () => snapshot)
}

// Test seam: forget every run between tests.
export function resetResearchRuns() {
  runs.forEach((run) => run.controller.abort())
  runs.clear()
  savers.clear()
  finished = []
  viewing = null
  emit()
}
