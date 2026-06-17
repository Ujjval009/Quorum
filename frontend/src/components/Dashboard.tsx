import { useRef, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles, BarChart3, ShieldCheck, Search,
  TrendingUp, GitCompare, AlertTriangle, BrainCircuit, FileCheck,
  ArrowRight, MessageSquare, Sun, Moon,
} from 'lucide-react'

const FEATURES = [
  {
    icon: Search,
    title: 'SEC Filing Analysis',
    desc: 'Upload and analyze any 10-K filing. Extract revenue, margins, EPS, and key financial metrics with deterministic precision.',
    gradient: 'from-blue-500 to-cyan-500',
  },
  {
    icon: TrendingUp,
    title: 'Revenue Intelligence',
    desc: 'Multi-year revenue breakdowns by segment, product category, and geography. See growth rates and CAGR calculated in Python.',
    gradient: 'from-emerald-500 to-teal-500',
  },
  {
    icon: GitCompare,
    title: 'Company Comparisons',
    desc: 'Side-by-side financial metrics across competitors. Compare AWS vs Azure vs Google Cloud revenue in a single query.',
    gradient: 'from-violet-500 to-purple-500',
  },
  {
    icon: AlertTriangle,
    title: 'Risk Factor Tracking',
    desc: 'Track changes in risk language year-over-year. See what risks were added, removed, or modified across filings.',
    gradient: 'from-amber-500 to-orange-500',
  },
  {
    icon: BrainCircuit,
    title: 'AI-Powered Insights',
    desc: 'Natural language queries over structured financial data. Ask in plain English, get answers with source citations.',
    gradient: 'from-pink-500 to-rose-500',
  },
  {
    icon: FileCheck,
    title: 'Citation-Backed Answers',
    desc: 'Every data point links to its source filing section, page number, and fiscal year. No hallucinations — verifiable results.',
    gradient: 'from-indigo-500 to-blue-500',
  },
]

const SUGGESTED_QUERIES = [
  "What is Apple's revenue by segment in FY2024?",
  'Compare Microsoft and Amazon cloud revenue growth',
  "What are NVIDIA's key risk factors?",
  'How does Google Cloud perform compared to AWS?',
  "What was Amazon's operating margin trend over 5 years?",
  "Analyze Microsoft's AI-related investments",
]

const APPROACH_STEPS = [
  {
    icon: Search,
    title: 'Ingest SEC Filings',
    desc: 'Raw 10-K HTML filings are parsed, chunked, and embedded into a vector database with pgvector.',
  },
  {
    icon: BarChart3,
    title: 'Retrieve & Extract',
    desc: 'Hybrid search (vector + full-text) finds relevant tables. Financial facts extracted deterministically in Python — never by the LLM.',
  },
  {
    icon: ShieldCheck,
    title: 'Compute & Verify',
    desc: 'Growth rates, CAGR, and revenue shares are computed algorithmically. Coverage validation ensures every claim has evidence.',
  },
  {
    icon: Sparkles,
    title: 'Generate & Cite',
    desc: 'Structured tables are rendered first, then the LLM writes the narrative. Every citation includes ticker, year, section, and excerpt.',
  },
]

function AnimatedSection({ children, className = '', delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); observer.disconnect() } },
      { threshold: 0.1 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ease-out ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const featuresRef = useRef<HTMLDivElement>(null)
  const [dark, setDark] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('theme')
      if (stored) return stored === 'dark'
      return true
    }
    return true
  })

  useEffect(() => {
    const root = document.documentElement
    if (dark) {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  function scrollToFeatures() {
    featuresRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  function handleQueryClick(query: string) {
    navigate('/workspace', { state: { prefillQuery: query } })
  }

  return (
    <div className="h-full overflow-y-auto bg-gray-50 dark:bg-gray-950">
      {/* ── Hero Section ── */}
      <section className="relative overflow-hidden border-b border-gray-200 dark:border-gray-800/60">
        {/* Decorative background */}
        <div className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `radial-gradient(circle at 25% 50%, #60a5fa 0%, transparent 50%), radial-gradient(circle at 75% 50%, #818cf8 0%, transparent 50%)`,
          }}
        />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-500/5 rounded-full blur-[120px]" />
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-blue-500/20 to-transparent hidden dark:block" />

        <div className="relative max-w-4xl mx-auto px-6 pt-20 pb-24 text-center">
          {/* Theme toggle */}
          <button
            onClick={() => setDark(!dark)}
            className="absolute top-6 right-6 p-2 rounded-xl bg-white/80 dark:bg-gray-800/80 border border-gray-300 dark:border-gray-700/50 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-all"
            title={dark ? 'Light mode' : 'Dark mode'}
          >
            {dark ? <Sun size={16} /> : <Moon size={16} />}
          </button>

          {/* Pill badge */}
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-medium mb-6 animate-fade-in">
            <Sparkles size={12} />
            AI-Powered SEC Filing Intelligence
          </div>

          {/* Headline */}
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 dark:text-white leading-tight mb-4 animate-fade-in-up">
            Transform SEC Filings into{' '}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-purple-500 dark:from-blue-400 dark:via-indigo-400 dark:to-purple-400">
              Actionable Financial Intelligence
            </span>
          </h1>

          {/* Subtitle */}
          <p className="text-lg text-gray-500 dark:text-gray-400 max-w-2xl mx-auto mb-10 animate-fade-in-up leading-relaxed" style={{ animationDelay: '100ms' }}>
            Analyze 10-K filings, compare company financials, track risk factor changes, and uncover revenue trends — all with deterministic calculations and citation-backed answers.
          </p>

          {/* CTAs */}
          <div className="flex items-center justify-center gap-4 animate-fade-in-up" style={{ animationDelay: '200ms' }}>
            <button
              onClick={() => navigate('/workspace')}
              className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-all active:scale-[0.98] shadow-lg shadow-blue-600/20"
            >
              <MessageSquare size={16} />
              Start Analysis
              <ArrowRight size={15} />
            </button>
            <button
              onClick={scrollToFeatures}
              className="inline-flex items-center gap-2 px-6 py-3 bg-gray-100 dark:bg-gray-800/80 text-gray-600 dark:text-gray-300 text-sm font-medium rounded-xl border border-gray-300 dark:border-gray-700/50 hover:bg-gray-200 dark:hover:bg-gray-800 hover:border-gray-400 dark:hover:border-gray-600 transition-all active:scale-[0.98]"
            >
              Explore Features
            </button>
          </div>
        </div>
      </section>

      {/* ── Stats Bar ── */}
      <section className="border-b border-gray-200 dark:border-gray-800/60">
        <div className="max-w-4xl mx-auto px-6 py-8">
          <div className="grid grid-cols-3 gap-8">
            {[
              { label: 'Filings Analyzed', value: '240+' },
              { label: 'Companies Tracked', value: '5' },
              { label: 'Data Points Extracted', value: '12,000+' },
            ].map((stat, i) => (
              <div key={i} className="text-center animate-fade-in-up" style={{ animationDelay: `${i * 80}ms` }}>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{stat.value}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Feature Cards ── */}
      <section ref={featuresRef} className="border-b border-gray-200 dark:border-gray-800/60">
        <div className="max-w-5xl mx-auto px-6 py-20">
          <AnimatedSection>
            <div className="text-center mb-14">
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-3">Platform Capabilities</h2>
              <p className="text-gray-500 dark:text-gray-400 text-sm max-w-xl mx-auto">
                Everything you need to analyze SEC filings, from revenue breakdowns to risk factor tracking.
              </p>
            </div>
          </AnimatedSection>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {FEATURES.map((f, i) => {
              const Icon = f.icon
              return (
                <AnimatedSection key={i} delay={i * 80}>
                  <div className="group relative p-5 rounded-xl bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-800/60 hover:border-gray-300 dark:hover:border-gray-700/60 transition-all duration-300 hover:-translate-y-0.5 shadow-sm dark:shadow-none">
                    {/* Gradient accent line */}
                    <div className={`absolute top-0 left-4 right-4 h-px bg-gradient-to-r ${f.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />

                    <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${f.gradient} bg-opacity-10 flex items-center justify-center mb-3`}>
                      <Icon size={18} className="text-white" />
                    </div>
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-1.5">{f.title}</h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{f.desc}</p>
                  </div>
                </AnimatedSection>
              )
            })}
          </div>
        </div>
      </section>

      {/* ── Suggested Queries ── */}
      <section className="border-b border-gray-200 dark:border-gray-800/60">
        <div className="max-w-4xl mx-auto px-6 py-20">
          <AnimatedSection>
            <div className="text-center mb-12">
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-3">Try These Queries</h2>
              <p className="text-gray-500 dark:text-gray-400 text-sm max-w-xl mx-auto">
                Click any question to jump to the chat — or explore the platform at your own pace.
              </p>
            </div>
          </AnimatedSection>

          <div className="grid sm:grid-cols-2 gap-3">
            {SUGGESTED_QUERIES.map((q, i) => (
              <AnimatedSection key={i} delay={i * 60}>
                <button
                  onClick={() => handleQueryClick(q)}
                  className="w-full text-left p-4 rounded-xl bg-white dark:bg-gray-900/40 border border-gray-200 dark:border-gray-800/50 hover:border-blue-500/30 hover:bg-gray-100 dark:hover:bg-gray-900/80 transition-all duration-200 group shadow-sm dark:shadow-none"
                >
                  <div className="flex items-start gap-3">
                    <div className="w-7 h-7 rounded-lg bg-blue-600/10 border border-blue-500/20 flex items-center justify-center shrink-0 mt-0.5 group-hover:bg-blue-600/20 transition-colors">
                      <MessageSquare size={13} className="text-blue-600 dark:text-blue-400" />
                    </div>
                    <p className="text-sm text-gray-500 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-gray-200 transition-colors leading-relaxed">
                      {q}
                    </p>
                  </div>
                </button>
              </AnimatedSection>
            ))}
          </div>
        </div>
      </section>

      {/* ── How It Works ── */}
      <section className="border-b border-gray-200 dark:border-gray-800/60">
        <div className="max-w-4xl mx-auto px-6 py-20">
          <AnimatedSection>
            <div className="text-center mb-14">
              <h2 className="text-2xl md:text-3xl font-bold text-gray-900 dark:text-white mb-3">Why Quorum Is Different</h2>
              <p className="text-gray-500 dark:text-gray-400 text-sm max-w-xl mx-auto">
                Most AI finance tools use LLMs for everything. We take a different approach.
              </p>
            </div>
          </AnimatedSection>

          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-10">
            {APPROACH_STEPS.map((step, i) => {
              const Icon = step.icon
              return (
                <AnimatedSection key={i} delay={i * 100}>
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 rounded-lg bg-blue-600/10 border border-blue-500/20 flex items-center justify-center shrink-0">
                      <Icon size={18} className="text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-medium text-blue-600 dark:text-blue-400">0{i + 1}</span>
                        <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{step.title}</h3>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{step.desc}</p>
                    </div>
                  </div>
                </AnimatedSection>
              )
            })}
          </div>

          <AnimatedSection delay={400}>
            <div className="mt-12 p-5 rounded-xl bg-white dark:bg-gray-900/40 border border-gray-200 dark:border-gray-800/50 shadow-sm dark:shadow-none">
              <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                <span className="text-blue-600 dark:text-blue-400 font-semibold">Key difference:</span> Financial metrics are computed in Python, never by the LLM.
                Growth rates, CAGR, margins, and revenue shares are deterministic extraction — the LLM only writes the narrative around pre-computed tables.
                This means you get <span className="text-gray-700 dark:text-gray-300">reproducible, verifiable financial analysis</span> with every query.
              </p>
            </div>
          </AnimatedSection>
        </div>
      </section>

      {/* ── CTA Footer ── */}
      <section className="max-w-4xl mx-auto px-6 py-16 text-center">
        <AnimatedSection>
          <div className="inline-flex items-center justify-center w-14 h-14 bg-blue-600/10 rounded-2xl mb-4 border border-blue-500/20">
            <img src="/logo.png" alt="Quorum" className="w-9 h-9 object-contain" />
          </div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">Ready to explore?</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-md mx-auto">
            Ask your first question and see the difference deterministic financial intelligence makes.
          </p>
          <button
            onClick={() => navigate('/workspace')}
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white text-sm font-semibold rounded-xl hover:bg-blue-700 transition-all active:scale-[0.98] shadow-lg shadow-blue-600/20"
          >
            <MessageSquare size={16} />
            Start Your First Analysis
            <ArrowRight size={15} />
          </button>
        </AnimatedSection>

        <p className="text-xs text-gray-400 dark:text-gray-600 mt-10">
          Powered by Groq Llama 3.3 70B · pgvector hybrid search · Deterministic financial extraction
        </p>
      </section>
    </div>
  )
}
