import { useState, type FormEvent } from 'react'
import { useAuth } from './AuthContext'
import { Navigate, useSearchParams } from 'react-router-dom'
import {
  Eye, EyeOff, Sparkles, Building2, BarChart3, ShieldCheck, ArrowRight,
} from 'lucide-react'

const FEATURES = [
  { icon: BarChart3, title: 'Multi-Year Financial Analysis', desc: 'Revenue breakdowns, margins, and growth rates extracted directly from SEC 10-K filings.' },
  { icon: Building2, title: 'Company Comparisons', desc: 'Side-by-side financial metrics across competitors with deterministic calculations.' },
  { icon: ShieldCheck, title: 'Citation-Backed Answers', desc: 'Every data point links to its source filing section. No hallucinations.' },
  { icon: Sparkles, title: 'AI-Powered Insights', desc: 'Natural language queries over structured financial data with instant answers.' },
]

export default function AuthPage() {
  const { token, login, signup } = useAuth()
  const [searchParams] = useSearchParams()
  const pathMode = window.location.pathname.includes('signup') ? 'signup' : 'signin'
  const defaultMode = searchParams.get('tab') === 'signup' ? 'signup' : pathMode
  const [mode, setMode] = useState<'signin' | 'signup'>(defaultMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  if (token) return <Navigate to="/" replace />

  function switchMode(m: 'signin' | 'signup') {
    setMode(m)
    setError('')
    setEmail('')
    setPassword('')
    setConfirmPassword('')
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    if (!email.trim()) { setError('Email is required'); return }
    if (!password) { setError('Password is required'); return }
    if (mode === 'signup') {
      if (password.length < 6) { setError('Password must be at least 6 characters'); return }
      if (password !== confirmPassword) { setError('Passwords do not match'); return }
    }

    setBusy(true)
    try {
      if (mode === 'signin') {
        await login(email, password)
      } else {
        await signup(email, password)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : ''
      if (mode === 'signin') {
        setError(msg || 'Invalid email or password')
      } else {
        setError(msg || 'Signup failed. Please try a different email.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex bg-gray-950">
      {/* ── Left: Brand Showcase ── */}
      <div className="hidden lg:flex lg:w-[45%] relative overflow-hidden bg-gradient-to-br from-blue-950 via-gray-950 to-indigo-950">
        {/* Decorative grid pattern */}
        <div className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: `linear-gradient(#60a5fa 1px, transparent 1px), linear-gradient(90deg, #60a5fa 1px, transparent 1px)`,
            backgroundSize: '60px 60px',
          }}
        />
        {/* Glowing orbs */}
        <div className="absolute -top-40 -left-40 w-80 h-80 bg-blue-500/20 rounded-full blur-[120px]" />
        <div className="absolute -bottom-40 -right-40 w-80 h-80 bg-indigo-500/20 rounded-full blur-[120px]" />

        <div className="relative flex flex-col justify-center px-16 py-20 w-full">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-600/25">
              <img src="/logo.png" alt="Quorum" className="w-8 h-8 object-contain" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">Quorum</h1>
              <p className="text-sm text-blue-300/80 -mt-0.5">SEC Filing Intelligence</p>
            </div>
          </div>

          {/* Tagline */}
          <h2 className="text-3xl font-bold text-white leading-tight mb-3">
            AI-Powered<br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-400">
              SEC Filing Analysis
            </span>
          </h2>
          <p className="text-gray-400 text-sm leading-relaxed mb-12 max-w-md">
            Analyze 10-K filings, compare companies, uncover financial trends, and explore risk disclosures with evidence-backed AI research.
          </p>

          {/* Feature list */}
          <div className="space-y-6">
            {FEATURES.map((f, i) => {
              const Icon = f.icon
              return (
                <div key={i} className="flex items-start gap-4 group">
                  <div className="w-10 h-10 rounded-lg bg-blue-600/10 border border-blue-500/20 flex items-center justify-center shrink-0 group-hover:bg-blue-600/20 transition-colors">
                    <Icon size={18} className="text-blue-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-200">{f.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{f.desc}</p>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Bottom branding */}
          <p className="mt-auto pt-16 text-xs text-gray-600">
            Powered by Groq LLM · Deterministic financial extraction
          </p>
        </div>
      </div>

      {/* ── Right: Auth Form ── */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-gray-950 lg:bg-gray-950/50">
        <div className="w-full max-w-sm">
          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-10">
            <div className="inline-flex items-center justify-center w-14 h-14 bg-blue-600 rounded-2xl mb-4 shadow-lg shadow-blue-600/25">
              <img src="/logo.png" alt="Quorum" className="w-9 h-9 object-contain" />
            </div>
            <h1 className="text-xl font-bold text-white">Quorum</h1>
            <p className="text-sm text-gray-500 mt-0.5">SEC Filing Intelligence</p>
          </div>

          {/* Tab switcher */}
          <div className="flex items-center gap-1 p-1 bg-gray-900 rounded-xl mb-8 border border-gray-800">
            <button
              onClick={() => switchMode('signin')}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all ${
                mode === 'signin'
                  ? 'bg-blue-600 text-white shadow-sm shadow-blue-600/20'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => switchMode('signup')}
              className={`flex-1 py-2.5 text-sm font-medium rounded-lg transition-all ${
                mode === 'signup'
                  ? 'bg-blue-600 text-white shadow-sm shadow-blue-600/20'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              Sign Up
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="text-sm text-red-400 bg-red-950/50 border border-red-900/50 px-4 py-3 rounded-xl animate-fade-in">
                {error}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Email</label>
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full px-4 py-2.5 bg-gray-900 border border-gray-800 rounded-xl text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder={mode === 'signup' ? 'Min. 6 characters' : 'Enter your password'}
                  className="w-full px-4 py-2.5 pr-11 bg-gray-900 border border-gray-800 rounded-xl text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {mode === 'signup' && (
              <div className="animate-fade-in">
                <label className="block text-sm font-medium text-gray-300 mb-1.5">Confirm Password</label>
                <div className="relative">
                  <input
                    type={showConfirm ? 'text' : 'password'}
                    autoComplete="new-password"
                    required
                    value={confirmPassword}
                    onChange={e => setConfirmPassword(e.target.value)}
                    placeholder="Re-enter your password"
                    className="w-full px-4 py-2.5 pr-11 bg-gray-900 border border-gray-800 rounded-xl text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirm(!showConfirm)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
                  >
                    {showConfirm ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed transition-all active:scale-[0.99] shadow-lg shadow-blue-600/20"
            >
              {busy ? (
                <span className="flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {mode === 'signin' ? 'Signing in...' : 'Creating account...'}
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  {mode === 'signin' ? 'Sign In' : 'Create Account'}
                  <ArrowRight size={15} />
                </span>
              )}
            </button>

            <p className="text-center text-sm text-gray-500">
              {mode === 'signin' ? (
                <>
                  Don&apos;t have an account?{' '}
                  <button type="button" onClick={() => switchMode('signup')} className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
                    Sign up
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{' '}
                  <button type="button" onClick={() => switchMode('signin')} className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
                    Sign in
                  </button>
                </>
              )}
            </p>
          </form>

          <p className="text-center text-xs text-gray-700 mt-8">
            Secure access to SEC filing intelligence
          </p>
        </div>
      </div>
    </div>
  )
}
