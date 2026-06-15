import { useEffect, useState, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useAuth } from './AuthContext'
import { useThreads } from './ThreadContext'
import * as api from '../api/quorum'
import type { Message, Citation } from '../types'
import { Trash2, Send, Loader2, FileText, ChevronRight, X, ExternalLink } from 'lucide-react'
import type { Components } from 'react-markdown'

const CIK_MAP: Record<string, string> = {
  AAPL: '320193',
  MSFT: '789019',
  NVDA: '1045810',
  AMZN: '1018724',
  GOOGL: '1652044',
}

function secUrl(ticker?: string, fiscalYear?: number): string {
  const cik = ticker ? CIK_MAP[ticker.toUpperCase()] : ''
  if (!cik) {
    const search = ticker ? `&company=${ticker}` : ''
    return `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany${search}&type=10-K`
  }
  const yearSuffix = fiscalYear ? `&dateb=${fiscalYear}1231` : ''
  return `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${cik}&type=10-K${yearSuffix}`
}

interface ExampleQuery {
  label: string
  query: string
}

const EXAMPLE_QUERIES: ExampleQuery[] = [
  { label: 'Revenue Analysis', query: "How has Apple's revenue mix changed over the last three fiscal years?" },
  { label: 'Cloud Business', query: 'Compare AWS, Azure, and Google Cloud revenue growth' },
  { label: 'Risk Factors', query: 'What changed in NVIDIA risk factor disclosures?' },
  { label: 'AI Strategy', query: "How has Microsoft's AI strategy evolved?" },
]

const ROTATING_QUESTIONS = [
  "What is Apple's revenue by segment in FY2024?",
  'Compare Microsoft and Amazon cloud revenue growth',
  "What are NVIDIA's key risk factors?",
  'How does Google Cloud perform compared to AWS?',
  "What was Amazon's operating margin trend over 5 years?",
  "Analyze Microsoft's AI-related investments",
  "How has Apple's Services revenue grown?",
  'Compare R&D spending across Apple, Microsoft, and Google',
]

const FEATURES = [
  'Multi-Year Financial Analysis',
  'Deterministic Calculations',
  'SEC Filing Citations',
  'Company Comparisons',
  'Risk Disclosure Tracking',
]

const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <h1 className="text-xl font-bold mt-5 mb-2 text-gray-900 dark:text-gray-100">{children}</h1>,
  h2: ({ children }) => <h2 className="text-lg font-semibold mt-5 mb-2 text-gray-900 dark:text-gray-100">{children}</h2>,
  h3: ({ children }) => <h3 className="text-base font-semibold mt-4 mb-1.5 text-gray-900 dark:text-gray-100">{children}</h3>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  code: ({ children }) => <code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm font-mono text-pink-600 dark:text-pink-400">{children}</code>,
  table: ({ children }) => (
    <div className="overflow-x-auto my-2 rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-50 dark:bg-gray-800">{children}</thead>,
  th: ({ children }) => <th className="px-3 py-2 font-semibold text-gray-900 dark:text-gray-100 border-b-2 border-gray-200 dark:border-gray-700 text-left">{children}</th>,
  td: ({ children }) => <td className="px-3 py-2 text-gray-700 dark:text-gray-300 border-b border-gray-100 dark:border-gray-700">{children}</td>,
  ul: ({ children }) => <ul className="space-y-0.5 my-2">{children}</ul>,
  li: ({ children }) => <li className="ml-4 pl-1 text-gray-700 dark:text-gray-300">{children}</li>,
  p: ({ children }) => <p className="mb-3 text-gray-700 dark:text-gray-300 leading-relaxed">{children}</p>,
}

function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={MARKDOWN_COMPONENTS}
    >
      {content}
    </ReactMarkdown>
  )
}

interface CitationCardProps {
  citation: Citation
  index: number
  onClick: (citation: Citation) => void
}

function CitationCard({ citation, index, onClick }: CitationCardProps) {
  const label = [
    citation.ticker && `[${index + 1}] ${citation.ticker}${citation.fiscal_year ? ` FY${citation.fiscal_year}` : ''}`,
    citation.page_number && `p.${citation.page_number}`,
  ].filter(Boolean).join(' · ')

  return (
    <button
      onClick={() => onClick(citation)}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300 rounded-full text-xs font-medium hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors border border-gray-200 dark:border-gray-700"
    >
      <FileText size={11} />
      <span>{label || `[${index + 1}]`}</span>
    </button>
  )
}

export default function Chat() {
  const { token } = useAuth()
  const { threads, threadId, loadThreads, setThreadId } = useThreads()
  const [messages, setMessages] = useState<Message[]>([])
  const [currentStream, setCurrentStream] = useState<string>('')
  const [typingState, setTypingState] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [asking, setAsking] = useState(false)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [sourceDrawer, setSourceDrawer] = useState<{ citation: Citation; messageId: string } | null>(null)
  const streamTidRef = useRef<string | null>(null)

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, currentStream, scrollToBottom])

  const loadMessages = useCallback(async (id: string) => {
    if (!token) return
    setLoadingMessages(true)
    setCurrentStream('')
    try {
      const data = await api.getThread(token, id)
      setMessages(data.messages)
    } catch {} finally { setLoadingMessages(false) }
  }, [token])

  useEffect(() => {
    if (threadId) loadMessages(threadId)
    else { setMessages([]); setCurrentStream('') }
  }, [threadId, loadMessages])

  async function ask() {
    if (!query.trim() || !token || asking) return
    const q = query.trim()
    setQuery('')

    let tid = threadId
    if (!tid) {
      try {
        const t = await api.createThread(token, q.length > 80 ? q.slice(0, 80) + '…' : q)
        loadThreads()
        tid = t.id
        setThreadId(t.id)
      } catch { return }
    }

    const userMsg: Message = {
      id: 'temp-user-' + Date.now(),
      role: 'user',
      content: q,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])
    setAsking(true)
    setCurrentStream('')
    setTypingState('Searching SEC filings...')
    streamTidRef.current = tid

    try {
      const res = await fetch(`${api.BASE}/chat/threads/${tid}/ask/stream`, {
        method: 'POST',
        headers: api.headers(token!),
        body: JSON.stringify({ query: q, top_k: 10 }),
      })

      if (!res.ok) {
        setTypingState(null)
        setAsking(false)
        streamTidRef.current = null
        return
      }

      setTypingState('Generating analysis...')

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullText = ''
      let done = false

      while (!done) {
        const { value, done: doneReading } = await reader.read()
        done = doneReading
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })

        const lines = buffer.split('\n')
        buffer = ''

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i]
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'token') {
                fullText += data.content
                setCurrentStream(fullText)
                setTypingState(null)
              } else if (data.type === 'done') {
                if (streamTidRef.current !== tid) return
                const assistantMsg: Message = {
                  id: data.message_id,
                  role: 'assistant',
                  content: fullText,
                  citations: data.citations,
                  created_at: new Date().toISOString(),
                }
                setMessages(prev => [...prev, assistantMsg])
                setCurrentStream('')
                setAsking(false)
                setTypingState(null)
                loadThreads()
              } else if (data.type === 'error') {
                setAsking(false)
                setTypingState(null)
              }
            } catch {}
          }
        }
      }

      setAsking(false)
      setTypingState(null)
    } catch {
      setAsking(false)
      setTypingState(null)
    } finally {
      streamTidRef.current = null
    }
  }

  function openSourceDrawer(citation: Citation, messageId: string) {
    setSourceDrawer({ citation, messageId })
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        {threadId && (
          <div className="md:hidden flex items-center gap-2 px-4 py-2.5 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800">
            <button onClick={() => setThreadId(null)} className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
              <ChevronRight size={18} className="rotate-180" />
            </button>
            <span className="text-sm font-medium truncate flex-1 text-gray-900 dark:text-gray-100">{threads.find(t => t.id === threadId)?.title}</span>
            <button
              onClick={() => {}}
              className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 transition-colors"
              title="Delete chat"
            >
              <Trash2 size={14} />
            </button>
          </div>
        )}

        {/* Desktop header */}
        {threadId && (
          <div className="hidden md:flex items-center gap-2 px-4 py-2 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{threads.find(t => t.id === threadId)?.title}</span>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {loadingMessages ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <div className="flex gap-1">
                <div className="w-1.5 h-1.5 bg-gray-300 dark:bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 bg-gray-300 dark:bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 bg-gray-300 dark:bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <p className="text-sm text-gray-400 dark:text-gray-500">Loading conversation...</p>
            </div>
          ) : !threadId || (messages.length === 0 && !asking) ? (
            <LandingPage inputRef={inputRef} onQuerySelect={setQuery} />
          ) : (
            <div className="max-w-3xl mx-auto px-4 py-6 space-y-1">
              {messages.map(m => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  onCitationClick={(c) => openSourceDrawer(c, m.id)}
                />
              ))}

              {currentStream && (
                <div className="flex justify-start px-4 py-3 animate-fade-in">
                  <div className="max-w-[85%] bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-2xl rounded-bl-md px-4 py-3">
                    <div className="flex items-center gap-2 mb-2">
                      <img src="/logo.png" alt="Quorum" className="w-5 h-5 object-contain shrink-0" />
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Quorum</span>
                    </div>
                    <Markdown content={currentStream} />
                    <span className="inline-block w-1.5 h-4 bg-gray-400 dark:bg-gray-500 animate-pulse ml-0.5 align-text-bottom" />
                  </div>
                </div>
              )}

              {typingState && !currentStream && (
                <div className="flex justify-start px-4 py-3 animate-fade-in">
                  <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-2xl rounded-bl-md px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div className="flex gap-1">
                        <div className="w-1.5 h-1.5 bg-gray-300 dark:bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-1.5 h-1.5 bg-gray-300 dark:bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-1.5 h-1.5 bg-gray-300 dark:bg-gray-600 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                      <span className="text-sm text-gray-400 dark:text-gray-500">{typingState}</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        <div className="border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 px-4 py-3">
          <div className="max-w-2xl mx-auto">
            <div className="flex items-center gap-2 border border-gray-200 dark:border-gray-700 rounded-xl px-3 py-1.5 focus-within:border-gray-300 dark:focus-within:border-gray-600 focus-within:shadow-sm transition-all bg-white dark:bg-gray-900">
              <input
                ref={inputRef}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && ask()}
                placeholder="Ask a question..."
                disabled={asking}
                className="flex-1 bg-transparent py-1.5 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none disabled:opacity-50"
              />
              <button
                onClick={ask}
                disabled={!query.trim() || asking}
                className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
              >
                {asking ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
              </button>
            </div>
            <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-1.5 text-center">
              Quorum analyzes SEC 10-K filings. Verify important facts against original filings.
            </p>
          </div>
        </div>
      </div>

      {/* Source Drawer */}
      {sourceDrawer && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/20 dark:bg-black/50" onClick={() => setSourceDrawer(null)} />
          <div className="relative w-full max-w-lg bg-white dark:bg-gray-900 shadow-2xl h-full overflow-y-auto animate-slide-in">
            <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-gray-400 dark:text-gray-500" />
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Source Details</h3>
              </div>
              <button onClick={() => setSourceDrawer(null)} className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
                <X size={16} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700">
                <p className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">Excerpt</p>
                <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{sourceDrawer.citation.excerpt}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {sourceDrawer.citation.ticker && (
                  <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 border border-gray-100 dark:border-gray-700">
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">Company</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {sourceDrawer.citation.ticker}
                      {sourceDrawer.citation.fiscal_year ? ` · FY${sourceDrawer.citation.fiscal_year}` : ''}
                    </p>
                  </div>
                )}
                <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 border border-gray-100 dark:border-gray-700">
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">Page</p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{sourceDrawer.citation.page_number || 'N/A'}</p>
                </div>
              </div>
              {sourceDrawer.citation.section_title && (
                <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 border border-gray-100 dark:border-gray-700">
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">Section</p>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{sourceDrawer.citation.section_title}</p>
                </div>
              )}
              <a
                href={secUrl(sourceDrawer.citation.ticker, sourceDrawer.citation.fiscal_year)}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 w-full py-2.5 bg-gray-900 dark:bg-gray-700 text-white text-sm font-medium rounded-xl hover:bg-gray-800 dark:hover:bg-gray-600 transition-colors"
              >
                <ExternalLink size={14} />
                View on SEC.gov
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function LandingPage({ inputRef, onQuerySelect }: { inputRef: React.RefObject<HTMLInputElement | null>; onQuerySelect: (q: string) => void }) {
  const [rotatingIndex, setRotatingIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setRotatingIndex(prev => (prev + 1) % ROTATING_QUESTIONS.length)
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  function handleQuery(query: string) {
    onQuerySelect(query)
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  return (
    <div className="h-full flex flex-col items-center justify-center px-6 overflow-y-auto">
      <div className="max-w-2xl w-full mx-auto -mt-8 space-y-8 animate-fade-in-up">
        {/* Hero */}
        <div className="text-center space-y-4">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-50 dark:bg-blue-900/30 rounded-2xl mb-2 animate-scale-in">
            <img src="/logo.png" alt="Quorum" className="w-10 h-10 object-contain" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 tracking-tight">Welcome to Quorum</h1>
          <p className="text-base text-gray-500 dark:text-gray-400 max-w-md mx-auto leading-relaxed">
            AI-powered SEC Filing Intelligence
          </p>
          <p className="text-sm text-gray-400 dark:text-gray-500 max-w-lg mx-auto leading-relaxed">
            Analyze 10-K filings, compare companies, uncover financial trends, and explore risk disclosures using evidence-backed AI research.
          </p>
        </div>

        {/* Quick-action cards */}
        <div className="grid grid-cols-2 gap-3">
          {EXAMPLE_QUERIES.map((q, i) => (
            <button
              key={i}
              onClick={() => handleQuery(q.query)}
              className="group relative flex items-center gap-3 px-4 py-4 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl text-left transition-all hover:border-blue-300 dark:hover:border-blue-700 hover:shadow-md dark:hover:shadow-blue-900/20 hover:-translate-y-0.5 active:scale-[0.98] animate-fade-in-up"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <span className="text-lg shrink-0">{['📈', '☁️', '⚠️', '🤖'][i]}</span>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-gray-900 dark:text-gray-100">{q.label}</p>
                <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-0.5 leading-snug line-clamp-2">{q.query}</p>
              </div>
            </button>
          ))}
        </div>

        {/* Rotating questions */}
        <div className="text-center space-y-3">
          <p className="text-[11px] font-medium text-gray-400 dark:text-gray-500 uppercase tracking-widest">Try asking</p>
          <div className="flex flex-wrap justify-center gap-2">
            {ROTATING_QUESTIONS.slice(0, 6).map((q, i) => (
              <button
                key={i}
                onClick={() => handleQuery(q)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-medium border transition-all animate-fade-in-up ${
                  i === rotatingIndex
                    ? 'bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-700 text-blue-600 dark:text-blue-400 shadow-sm animate-glow-pulse'
                    : 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:border-blue-200 dark:hover:border-blue-700 hover:text-blue-600 dark:hover:text-blue-400'
                }`}
                style={{ animationDelay: `${i * 60}ms` }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Features */}
        <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 pb-4">
          {FEATURES.map((f, i) => (
            <div key={i} className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 animate-fade-in-up" style={{ animationDelay: `${300 + i * 80}ms` }}>
              <svg className="w-3.5 h-3.5 text-blue-500 dark:text-blue-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              {f}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ message, onCitationClick }: { message: Message; onCitationClick: (c: Citation) => void }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} px-4 py-2 animate-fade-in`}>
      <div className={`max-w-[85%] ${message.role === 'user' ? 'order-1' : 'order-2'}`}>
        {message.role === 'assistant' && (
          <div className="flex items-center gap-1.5 mb-1 px-1">
            <img src="/logo.png" alt="Quorum" className="w-4 h-4 object-contain shrink-0" />
            <span className="text-xs font-medium text-gray-400 dark:text-gray-500">Quorum</span>
          </div>
        )}
        <div
          className={`px-4 py-3 text-sm leading-relaxed ${
            message.role === 'user'
              ? 'bg-blue-600 text-white rounded-2xl rounded-br-md'
              : 'bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-2xl rounded-bl-md shadow-sm'
          }`}
        >
          {message.role === 'user' ? (
            <p>{message.content}</p>
          ) : (
            <Markdown content={message.content} />
          )}
        </div>
        {message.role === 'assistant' && message.citations && message.citations.length > 0 && (
          <div className="mt-2 px-1">
            <div className="flex flex-wrap gap-1.5">
              {(!expanded ? message.citations.slice(0, 3) : message.citations).map((c, i) => (
                <CitationCard key={i} citation={c} index={i} onClick={onCitationClick} />
              ))}
              {message.citations.length > 3 && (
                <button
                  onClick={() => setExpanded(!expanded)}
                  className="text-xs text-gray-400 dark:text-gray-500 hover:text-blue-500 dark:hover:text-blue-400 px-2 py-1"
                >
                  {expanded ? 'Show less' : `+${message.citations.length - 3} more`}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
