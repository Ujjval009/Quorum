import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './components/AuthContext'
import Layout from './components/Layout'
import { ThreadProvider } from './components/ThreadContext'
import AuthPage from './components/AuthPage'
import Dashboard from './components/Dashboard'
import Chat from './components/Chat'
import Documents from './components/Documents'
import Settings from './components/Settings'

function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent" />
    </div>
  )
}

function AppRoutes() {
  const { token, loading } = useAuth()

  if (loading) return <LoadingScreen />

  if (!token) {
    return (
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route path="/signup" element={<AuthPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/dashboard" element={<div className="h-screen"><Dashboard /></div>} />
      <Route path="/workspace" element={<ThreadProvider><Layout /></ThreadProvider>}>
        <Route index element={<Chat />} />
        <Route path="documents" element={<Documents />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
