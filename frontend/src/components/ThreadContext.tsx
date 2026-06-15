import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { useAuth } from './AuthContext'
import * as api from '../api/quorum'
import type { Thread } from '../types'

interface ThreadContextValue {
  threads: Thread[]
  threadId: string | null
  loadingThreads: boolean
  setThreadId: (id: string | null) => void
  loadThreads: () => Promise<void>
  createThread: () => Promise<Thread | undefined>
  deleteThread: (id: string) => void
}

const ThreadContext = createContext<ThreadContextValue | null>(null)

export function ThreadProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth()
  const [threads, setThreads] = useState<Thread[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)
  const [loadingThreads, setLoadingThreads] = useState(true)

  useEffect(() => { if (token) loadThreads() }, [token])

  async function loadThreads() {
    if (!token) return
    try {
      const data = await api.listThreads(token)
      setThreads(data.threads)
    } catch {} finally { setLoadingThreads(false) }
  }

  async function createThread(): Promise<Thread | undefined> {
    if (!token) return
    try {
      const t = await api.createThread(token, 'New chat')
      setThreads(prev => [t, ...prev])
      setThreadId(t.id)
      return t
    } catch {}
  }

  function deleteThread(id: string) {
    setThreads(prev => prev.filter(t => t.id !== id))
    if (threadId === id) setThreadId(null)
    api.deleteThread(token!, id).catch(() => {})
  }

  return (
    <ThreadContext.Provider value={{ threads, threadId, loadingThreads, setThreadId, loadThreads, createThread, deleteThread }}>
      {children}
    </ThreadContext.Provider>
  )
}

export function useThreads() {
  const ctx = useContext(ThreadContext)
  if (!ctx) throw new Error('useThreads must be used within ThreadProvider')
  return ctx
}
