import { useState, useEffect, useCallback, useRef } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { useThreads } from './ThreadContext'
import { LayoutDashboard, FileText, Settings, LogOut, Menu, X, Moon, Sun, Plus, MessageSquare, Trash2, Sparkles } from 'lucide-react'

function formatDate(d: string) {
  const date = new Date(d)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const days = Math.floor(diff / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, path: '/dashboard' },
  { id: 'documents', label: 'Documents', icon: FileText, path: '/workspace/documents' },
  { id: 'settings', label: 'Settings', icon: Settings, path: '/workspace/settings' },
]

export default function Layout() {
  const { profile, logout } = useAuth()
  const { threads, threadId, loadingThreads, createThread, deleteThread, setThreadId } = useThreads()
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('sidebarWidth')
      if (stored) return Math.max(200, Math.min(500, parseInt(stored, 10)))
      return 280
    }
    return 280
  })
  const [dark, setDark] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('theme')
      if (stored) return stored === 'dark'
      return true
    }
    return true
  })

  const isChatActive = location.pathname === '/workspace'

  function isActive(item: typeof NAV_ITEMS[0]) {
    if (item.path === '/workspace') return isChatActive
    return location.pathname.startsWith(item.path)
  }

  useEffect(() => {
    const root = document.documentElement
    if (dark) {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const handleNewChat = useCallback(async () => {
    const t = await createThread()
    if (t) navigate('/workspace')
  }, [createThread, navigate])

  const handleSelectThread = useCallback((id: string) => {
    setThreadId(id)
    navigate('/workspace')
  }, [setThreadId, navigate])

  const handleDeleteThread = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    deleteThread(id)
  }, [deleteThread])

  const resizingRef = useRef(false)

  const handleMouseDown = useCallback(() => {
    resizingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    function handleMouseMove(e: MouseEvent) {
      if (!resizingRef.current) return
      const newWidth = Math.max(200, Math.min(500, e.clientX))
      setSidebarWidth(newWidth)
    }
    function handleMouseUp() {
      if (resizingRef.current) {
        resizingRef.current = false
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
        setSidebarWidth(w => {
          localStorage.setItem('sidebarWidth', String(w))
          return w
        })
      }
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [])

  const SidebarContent = ({ closeable, isMobile }: { closeable?: boolean; isMobile?: boolean }) => (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2.5">
          <img src="/logo.png" alt="Quorum" className="w-8 h-8 object-contain shrink-0" />
          <div>
            <h1 className="text-base font-bold text-blue-600 dark:text-blue-400">Quorum</h1>
            <p className="text-[10px] text-gray-500 dark:text-gray-400 -mt-0.5">SEC Filing Research Assistant</p>
          </div>
        </div>
      </div>

      {isMobile && (
        <div className="p-3">
          <button
            onClick={() => { handleNewChat(); closeable && setSidebarOpen(false) }}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium rounded-lg border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600 transition-all active:scale-[0.98]"
          >
            <Plus size={15} /> New chat
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-2 space-y-0.5 min-h-0">
        {loadingThreads ? (
          <div className="space-y-2 p-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-9 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse" />
            ))}
          </div>
        ) : threads.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
            <MessageSquare size={22} className="text-gray-200 dark:text-gray-700 mb-2" />
            <p className="text-xs text-gray-400 dark:text-gray-500">No conversations yet</p>
            <p className="text-[11px] text-gray-300 dark:text-gray-600 mt-0.5">Start a new chat to begin</p>
          </div>
        ) : (
          threads.map(t => (
            <div
              key={t.id}
              className={`group flex items-center rounded-lg cursor-pointer transition-all ${
                threadId === t.id
                  ? 'bg-gray-100 dark:bg-gray-800'
                  : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
              }`}
            >
              <button
                onClick={() => { handleSelectThread(t.id); closeable && setSidebarOpen(false) }}
                className="flex-1 flex items-center gap-2 px-3 py-2 min-w-0 text-left"
              >
                <MessageSquare size={13} className={`shrink-0 ${threadId === t.id ? 'text-gray-600 dark:text-gray-300' : 'text-gray-300 dark:text-gray-600'}`} />
                <div className="min-w-0">
                  <span className={`text-xs truncate block ${threadId === t.id ? 'font-medium text-gray-900 dark:text-gray-100' : 'text-gray-600 dark:text-gray-400'}`}>
                    {t.title}
                  </span>
                  <span className="text-[10px] text-gray-400 dark:text-gray-500">{formatDate(t.created_at)}</span>
                </div>
              </button>
              <button
                onClick={(e) => handleDeleteThread(e, t.id)}
                className="p-1 mr-1 text-gray-300 dark:text-gray-600 hover:text-red-500 dark:hover:text-red-400 shrink-0 transition-colors"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))
        )}
      </div>

      <div className="p-2 border-t border-gray-200 dark:border-gray-700 space-y-0.5">
        {NAV_ITEMS.map(item => {
          const Icon = item.icon
          return (
            <button
              key={item.id}
              onClick={() => { navigate(item.path); closeable && setSidebarOpen(false) }}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive(item)
                  ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <Icon size={18} />
              {item.label}
            </button>
          )
        })}
        <button
          onClick={() => setDark(!dark)}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        >
          {dark ? <Sun size={18} /> : <Moon size={18} />}
          <span>{dark ? 'Light mode' : 'Dark mode'}</span>
        </button>
        <div className="flex items-center justify-between px-3 py-2">
          <div className="text-xs text-gray-500 dark:text-gray-500 truncate">{profile?.email}</div>
          <button onClick={logout} className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800" title="Logout">
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950">
      {/* Desktop sidebar */}
      <aside
        className="hidden md:flex bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex-col shrink-0 relative"
        style={{ width: sidebarWidth }}
      >
        <div className="p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2.5">
            <img src="/logo.png" alt="Quorum" className="w-8 h-8 object-contain shrink-0" />
            <div>
              <h1 className="text-base font-bold text-blue-600 dark:text-blue-400">Quorum</h1>
              <p className="text-[10px] text-gray-500 dark:text-gray-400 -mt-0.5">SEC Filing Research</p>
            </div>
          </div>
        </div>

        {/* New Chat button */}
        <div className="p-3">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-sm font-medium rounded-xl bg-blue-600 text-white hover:bg-blue-700 transition-all active:scale-[0.98] shadow-sm"
          >
            <Plus size={16} /> New chat
          </button>
        </div>

        {threads.length > 0 && (
          <div className="px-4 pt-3 pb-1">
            <span className="text-[11px] font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider">Conversations</span>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-2 space-y-0.5 min-h-0">
          {loadingThreads ? (
            <div className="space-y-2 p-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-9 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : threads.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
              <Sparkles size={24} className="text-gray-200 dark:text-gray-700 mb-2" />
              <p className="text-xs text-gray-400 dark:text-gray-500">No conversations yet</p>
              <p className="text-[11px] text-gray-300 dark:text-gray-600 mt-0.5">Ask a question to get started</p>
            </div>
          ) : (
            threads.map(t => (
              <div
                key={t.id}
                className={`group flex items-center rounded-lg cursor-pointer transition-all ${
                  threadId === t.id
                    ? 'bg-gray-100 dark:bg-gray-800'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                }`}
              >
                <button
                  onClick={() => handleSelectThread(t.id)}
                  className="flex-1 flex items-center gap-2 px-3 py-2 min-w-0 text-left"
                >
                  <MessageSquare size={13} className={`shrink-0 ${threadId === t.id ? 'text-gray-600 dark:text-gray-300' : 'text-gray-300 dark:text-gray-600'}`} />
                  <div className="min-w-0">
                    <span className={`text-xs truncate block ${threadId === t.id ? 'font-medium text-gray-900 dark:text-gray-100' : 'text-gray-600 dark:text-gray-400'}`}>
                      {t.title}
                    </span>
                    <span className="text-[10px] text-gray-400 dark:text-gray-500">{formatDate(t.created_at)}</span>
                  </div>
                </button>
                <button
                  onClick={(e) => handleDeleteThread(e, t.id)}
                  className="p-1 mr-1 text-gray-300 dark:text-gray-600 hover:text-red-500 dark:hover:text-red-400 shrink-0 transition-colors"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="p-2 border-t border-gray-200 dark:border-gray-700 space-y-0.5">
          {NAV_ITEMS.map(item => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                onClick={() => navigate(item.path)}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive(item)
                    ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                <Icon size={18} />
                {item.label}
              </button>
            )
          })}
          <button
            onClick={() => setDark(!dark)}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
            <span>{dark ? 'Light mode' : 'Dark mode'}</span>
          </button>
          <div className="flex items-center justify-between px-3 py-2">
            <div className="text-xs text-gray-500 dark:text-gray-500 truncate">{profile?.email}</div>
            <button onClick={logout} className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800" title="Logout">
              <LogOut size={16} />
            </button>
          </div>
        </div>

        <div
          onMouseDown={handleMouseDown}
          className="absolute right-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-blue-500/30 dark:hover:bg-blue-400/30 active:bg-blue-500/50 dark:active:bg-blue-400/50 transition-colors group"
        >
          <div className="absolute inset-y-0 right-0 w-0.5 bg-transparent group-hover:bg-blue-400/40 dark:group-hover:bg-blue-300/40 transition-colors" />
        </div>
      </aside>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setSidebarOpen(false)} />
          <aside className="relative w-[280px] h-full bg-white dark:bg-gray-900 shadow-lg">
            <SidebarContent closeable isMobile />
          </aside>
        </div>
      )}

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="md:hidden flex items-center justify-between px-4 py-3 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
          <button onClick={() => setSidebarOpen(true)} className="p-1.5 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <h1 className="text-sm font-semibold text-blue-600 dark:text-blue-400">Quorum</h1>
          <button
            onClick={() => setDark(!dark)}
            className="p-1.5 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
            title={dark ? 'Light mode' : 'Dark mode'}
          >
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </header>
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
