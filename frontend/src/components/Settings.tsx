import { useState, useEffect } from 'react'
import { useAuth } from './AuthContext'
import * as api from '../api/quorum'
import { Sun, Moon, CheckCircle, XCircle, Server, Info } from 'lucide-react'

export default function Settings() {
  const { profile } = useAuth()
  const [dark, setDark] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('theme')
      if (stored) return stored === 'dark'
      return true
    }
    return true
  })
  const [backendStatus, setBackendStatus] = useState<'checking' | 'ok' | 'error'>('checking')

  useEffect(() => {
    const root = document.documentElement
    if (dark) {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    api.healthCheck().then(() => setBackendStatus('ok')).catch(() => setBackendStatus('error'))
  }, [])

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <div className="max-w-xl mx-auto space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Settings</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">Manage your preferences and account</p>
        </div>

        {/* Appearance */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center gap-3 mb-4">
            {dark ? <Moon size={18} className="text-amber-500" /> : <Sun size={18} className="text-amber-500" />}
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Appearance</h3>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Dark mode</p>
              <p className="text-xs text-gray-400 dark:text-gray-500">Toggle dark theme across the app</p>
            </div>
            <button
              onClick={() => setDark(!dark)}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                dark ? 'bg-blue-600' : 'bg-gray-200 dark:bg-gray-700'
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-sm transition-transform ${
                  dark ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>

        {/* API Status */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center gap-3 mb-4">
            <Server size={18} className="text-gray-500 dark:text-gray-400" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">API & Services</h3>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-1">
              <span className="text-sm text-gray-700 dark:text-gray-300">Backend</span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400 dark:text-gray-500">localhost:8000</span>
                {backendStatus === 'checking' ? (
                  <div className="w-2 h-2 bg-gray-300 dark:bg-gray-600 rounded-full animate-pulse" />
                ) : backendStatus === 'ok' ? (
                  <CheckCircle size="14px" className="text-green-500" />
                ) : (
                  <XCircle size="14px" className="text-red-500" />
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Account */}
        <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center gap-3 mb-4">
            <Info size={18} className="text-gray-500 dark:text-gray-400" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Account</h3>
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
            <p><span className="text-gray-400 dark:text-gray-500">Email:</span> {profile?.email ?? '—'}</p>
            <p><span className="text-gray-400 dark:text-gray-500">ID:</span> {profile?.id ?? '—'}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
