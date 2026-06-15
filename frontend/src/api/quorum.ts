import type { Document, Thread, Message, SearchResult } from '../types'

export const BASE = import.meta.env.VITE_API_URL || '/api'

export function headers(token?: string): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

async function handle(res: Response) {
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export async function login(email: string, password: string): Promise<{ access_token: string }> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ email, password }),
  })
  return handle(res)
}

export async function signup(email: string, password: string): Promise<{ access_token: string; user: { id: string; email: string } }> {
  const res = await fetch(`${BASE}/auth/signup`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ email, password }),
  })
  return handle(res)
}

export async function getProfile(token: string): Promise<{ id: string; email: string }> {
  const res = await fetch(`${BASE}/auth/me`, { headers: headers(token) })
  return handle(res)
}

export async function listDocuments(token: string, ticker?: string, sort?: string): Promise<{ documents: Document[] }> {
  const params = new URLSearchParams()
  if (ticker) params.set('ticker', ticker)
  if (sort) params.set('sort', sort)
  const qs = params.toString()
  const res = await fetch(`${BASE}/documents${qs ? `?${qs}` : ''}`, { headers: headers(token) })
  return handle(res)
}

export async function getDocument(token: string, id: string): Promise<Document> {
  const res = await fetch(`${BASE}/documents/${id}`, { headers: headers(token) })
  return handle(res)
}

export async function searchChunks(token: string, query: string, topK = 10): Promise<{ results: SearchResult[] }> {
  const res = await fetch(`${BASE}/chat/search`, {
    method: 'POST',
    headers: headers(token),
    body: JSON.stringify({ query, top_k: topK }),
  })
  return handle(res)
}

export async function createThread(token: string, title: string): Promise<Thread> {
  const res = await fetch(`${BASE}/chat/threads`, {
    method: 'POST',
    headers: headers(token),
    body: JSON.stringify({ title }),
  })
  return handle(res)
}

export async function listThreads(token: string): Promise<{ threads: Thread[] }> {
  const res = await fetch(`${BASE}/chat/threads`, { headers: headers(token) })
  return handle(res)
}

export async function getThread(token: string, id: string): Promise<{ id: string; title: string; messages: Message[] }> {
  const res = await fetch(`${BASE}/chat/threads/${id}`, { headers: headers(token) })
  return handle(res)
}

export async function deleteThread(token: string, id: string): Promise<void> {
  await fetch(`${BASE}/chat/threads/${id}`, {
    method: 'DELETE',
    headers: headers(token),
  })
}

export async function healthCheck(): Promise<{ status: string }> {
  const res = await fetch(`${BASE}/health`)
  return handle(res)
}

export async function askQuestion(token: string, threadId: string, query: string, topK = 10): Promise<{ answer: string; citations: { chunk_id: string; page_number?: number; excerpt?: string }[]; message_id: string }> {
  const res = await fetch(`${BASE}/chat/threads/${threadId}/ask`, {
    method: 'POST',
    headers: headers(token),
    body: JSON.stringify({ query, top_k: topK }),
  })
  return handle(res)
}
