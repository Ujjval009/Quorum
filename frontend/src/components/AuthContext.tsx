import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { supabase } from '../lib/supabase'
import * as api from '../api/quorum'

interface AuthState {
  token: string | null
  profile: { id: string; email: string } | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(sessionStorage.getItem('token'))
  const [profile, setProfile] = useState<{ id: string; email: string } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (token) {
      api.getProfile(token)
        .then(setProfile)
        .catch(() => { sessionStorage.removeItem('token'); setToken(null) })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [token])

  async function login(email: string, password: string) {
    const data = await api.login(email, password)
    sessionStorage.setItem('token', data.access_token)
    setToken(data.access_token)
  }

  async function signup(email: string, password: string) {
    const data = await api.signup(email, password)
    sessionStorage.setItem('token', data.access_token)
    setToken(data.access_token)
    setProfile(data.user)
  }

  function logout() {
    sessionStorage.removeItem('token')
    setToken(null)
    setProfile(null)
    supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider value={{ token, profile, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be inside AuthProvider')
  return ctx
}
