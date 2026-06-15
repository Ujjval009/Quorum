import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './components/AuthContext'
import Layout from './components/Layout'
import { ThreadProvider } from './components/ThreadContext'
import Login from './components/Login'
import Signup from './components/Signup'
import Chat from './components/Chat'
import Documents from './components/Documents'
import Settings from './components/Settings'

function ProtectedApp() {
  const { token, loading } = useAuth()
  const [tab, setTab] = useState('chat')

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (!token) return <Navigate to="/login" replace />

  return (
    <ThreadProvider>
      <Layout currentTab={tab} onTabChange={setTab}>
        {tab === 'chat' && <Chat />}
        {tab === 'documents' && <Documents />}
        {tab === 'settings' && <Settings />}
      </Layout>
    </ThreadProvider>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/*" element={<ProtectedApp />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
