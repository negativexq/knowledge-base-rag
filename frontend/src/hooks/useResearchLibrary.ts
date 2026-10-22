import { useEffect, useState, type SetStateAction } from "react"

import { readOrganization, writeOrganization, RESEARCH_EVENT } from "@/lib/organization"
import { attachLibrary, appendTurn, isRunning } from "@/lib/researchRuns"
import { newResearchSession, readResearchSessions, samePin, type EvidencePin, type ResearchSession, type ResearchNote, type ResearchTurn } from "@/lib/research"

interface Library { sessions: ResearchSession[]; activeId: string; launch?: { sessionId: string; projectId: string } }

function load(scope: string): Library {
  const sessions = readResearchSessions(scope)
  try {
    const launch = JSON.parse(sessionStorage.getItem(`${scope}:launch`) ?? "null")
    if (launch?.sessionId && sessions.some((session) => session.id === launch.sessionId)) return { sessions, activeId: launch.sessionId }
    if (launch?.sessionId === null) {
      const draft = newResearchSession()
      const project = readOrganization(scope).projects.find((project) => project.id === launch.projectId)
      return { sessions: [...sessions, draft], activeId: draft.id, launch: project ? { sessionId: draft.id, projectId: project.id } : undefined }
    }
    const activeId = sessionStorage.getItem(`${scope}:active`)
    if (activeId && sessions.some((session) => session.id === activeId)) return { sessions, activeId }
  } catch { /* An unavailable browser store doesn't prevent research. */ }
  const draft = newResearchSession()
  return { sessions: [...sessions, draft], activeId: draft.id }
}

export function useResearchLibrary(scope: string) {
  const [library, setLibrary] = useState(() => load(scope))
  const [removed, setRemoved] = useState<ResearchSession | null>(null)
  const [storageError, setStorageError] = useState(false)
  const activeSession = library.sessions.find((session) => session.id === library.activeId)!
  const active = { ...activeSession, pinned: activeSession.pinned ?? false, notes: activeSession.notes ?? [] }

  useEffect(() => {
    try { sessionStorage.removeItem(`${scope}:launch`) } catch { /* Launch requests are scoped and optional. */ }
    if (library.launch) {
      const launch = library.launch
      writeOrganization(scope, (value) => value.projects.some((project) => project.id === launch.projectId) ? { ...value, assignments: { ...value.assignments, [launch.sessionId]: launch.projectId } } : value)
    }
  }, [scope, library.launch])

  // Research finished in the background lands in this library, including a
  // draft session that was left before its first answer arrived.
  useEffect(() => attachLibrary(scope, (sessionId, turn) => setLibrary((value) => ({
    ...value,
    sessions: value.sessions.some((session) => session.id === sessionId)
      ? value.sessions.map((session) => session.id === sessionId ? appendTurn(session, turn) : session)
      : [...value.sessions, appendTurn({ ...newResearchSession(), id: sessionId }, turn)],
  }))), [scope])

  useEffect(() => {
    let cancelled = false
    // Persist completed snapshots; never restore a half-finished SSE turn.
    void Promise.resolve().then(() => {
      const snapshots = library.sessions.map((session) => ({ ...session, notes: session.notes ?? [], turns: session.turns.filter((turn) => !turn.streaming) }))
        .filter((session) => session.turns.length > 0 || (session.notes ?? []).length > 0)
      try {
        localStorage.setItem(scope, JSON.stringify(snapshots))
        window.dispatchEvent(new Event(RESEARCH_EVENT))
        if (snapshots.some((session) => session.id === library.activeId)) sessionStorage.setItem(`${scope}:active`, library.activeId)
        else sessionStorage.removeItem(`${scope}:active`)
        return false
      } catch { return true }
    }).then((failed) => { if (!cancelled) setStorageError(failed) })
    return () => { cancelled = true }
  }, [library, scope])

  function updateSession(id: string, update: (session: ResearchSession) => ResearchSession) {
    setLibrary((value) => ({ ...value, sessions: value.sessions.map((session) => session.id === id ? update(session) : session) }))
  }

  function setTurns(next: SetStateAction<ResearchTurn[]>) {
    updateSession(library.activeId, (session) => {
      const turns = typeof next === "function" ? next(session.turns) : next
      if (turns === session.turns) return session
      return { ...session, turns, title: session.customTitle ? session.title : (turns[0]?.question.slice(0, 100) || session.title), updatedAt: new Date().toISOString() }
    })
  }

  function newSession() {
    const draft = newResearchSession()
    setLibrary((value) => ({ sessions: [...value.sessions.filter((session) => session.turns.length > 0 || (session.notes ?? []).length > 0 || isRunning(session.id)), draft], activeId: draft.id }))
    return draft.id
  }

  function openSession(id: string) {
    setLibrary((value) => value.sessions.some((session) => session.id === id)
      ? { sessions: value.sessions.filter((session) => session.turns.length > 0 || (session.notes ?? []).length > 0 || isRunning(session.id) || session.id === id), activeId: id }
      : value)
  }

  function rename(id: string, title: string) {
    if (title.trim()) updateSession(id, (session) => ({ ...session, title: title.trim().slice(0, 100), customTitle: true }))
  }

  function star(id: string) { updateSession(id, (session) => ({ ...session, starred: !session.starred })) }

  function pinSession(id: string) { updateSession(id, (session) => ({ ...session, pinned: !session.pinned })) }

  function restoreSession(session: ResearchSession) {
    setLibrary((value) => ({ ...value, sessions: value.sessions.some((item) => item.id === session.id) ? value.sessions : [...value.sessions, session] }))
  }

  function remove(id: string) {
    setRemoved(library.sessions.find((session) => session.id === id) ?? null)
    setLibrary((value) => {
      const sessions = value.sessions.filter((session) => session.id !== id)
      if (value.activeId !== id) return { ...value, sessions }
      const draft = newResearchSession()
      return { sessions: [...sessions, draft], activeId: draft.id }
    })
  }

  function undoRemove() {
    if (!removed) return
    setLibrary((value) => ({ ...value, sessions: value.sessions.some((session) => session.id === removed.id) ? value.sessions : [...value.sessions, removed] }))
    setRemoved(null)
  }

  function saveNote(note: ResearchNote) {
    if (!note.text.trim()) return
    updateSession(library.activeId, (session) => ({ ...session, updatedAt: new Date().toISOString(), notes: (session.notes ?? []).some((item) => item.id === note.id)
      ? (session.notes ?? []).map((item) => item.id === note.id ? { ...note, text: note.text.trim().slice(0, 20000) } : item)
      : [...(session.notes ?? []), { ...note, text: note.text.trim().slice(0, 20000) }] }))
  }

  function removeNote(id: string) {
    updateSession(library.activeId, (session) => ({ ...session, notes: (session.notes ?? []).filter((note) => note.id !== id), updatedAt: new Date().toISOString() }))
  }

  function togglePin(pin: EvidencePin) {
    updateSession(library.activeId, (session) => ({ ...session, pins: session.pins.some((item) => samePin(item, pin))
      ? session.pins.filter((item) => !samePin(item, pin)) : [...session.pins, pin] }))
  }

  return { active, sessions: library.sessions.filter((session) => session.turns.some((turn) => !turn.streaming) || (session.notes ?? []).length > 0).map((session) => ({ ...session, pinned: session.pinned ?? false, notes: session.notes ?? [] })), setTurns, newSession, openSession, rename, star, pinSession, remove, restoreSession, togglePin, saveNote, removeNote, storageError, removed, undoRemove }
}
