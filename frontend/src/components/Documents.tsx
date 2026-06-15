import { useEffect, useState, useMemo } from 'react'
import { useAuth } from './AuthContext'
import * as api from '../api/quorum'
import type { Document } from '../types'
import { FileText, Database, Search, ExternalLink, X, Building2, Calendar, Layers, Filter } from 'lucide-react'

const TICKERS = ['', 'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL']
const FILING_TYPES = ['', '10-K', '10-Q']
const YEARS = ['', '2021', '2022', '2023', '2024', '2025']

export default function Documents() {
  const { token } = useAuth()
  const [docs, setDocs] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ticker, setTicker] = useState('')
  const [filingType, setFilingType] = useState('')
  const [year, setYear] = useState('')
  const [sort, setSort] = useState('fiscal_year')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  useEffect(() => {
    if (token) load()
  }, [token, ticker, sort])

  async function load() {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.listDocuments(token, ticker || undefined, sort)
      setDocs(data.documents)
    } catch {
      setError('Unable to load filings. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  async function openDetail(doc: Document) {
    setSelectedDoc(doc)
    if (doc.chunk_count !== undefined) return
    setDetailLoading(true)
    try {
      const detail = await api.getDocument(token!, doc.id)
      setSelectedDoc(detail)
    } catch {} finally {
      setDetailLoading(false)
    }
  }

  const filteredDocs = useMemo(() => {
    let result = docs
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter(d =>
        d.company_name?.toLowerCase().includes(q) ||
        d.ticker?.toLowerCase().includes(q) ||
        d.filing_type?.toLowerCase().includes(q) ||
        String(d.fiscal_year || '').includes(q)
      )
    }
    if (filingType) {
      result = result.filter(d => d.filing_type === filingType)
    }
    if (year) {
      result = result.filter(d => String(d.fiscal_year) === year)
    }
    return result
  }, [docs, searchQuery, filingType, year])

  const activeFilters = [ticker, filingType, year].filter(Boolean).length

  return (
    <div className="h-full flex overflow-hidden">
      <div className="flex-1 flex flex-col min-w-0 p-4 md:p-6 overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">SEC Filing Browser</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">Browse and analyze indexed 10-K and 10-Q filings</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-3 py-1.5 rounded-lg">
            <Database size={14} />
            {filteredDocs.length} of {docs.length} filing{docs.length !== 1 ? 's' : ''}
          </div>
        </div>

        {/* Search + Filters */}
        <div className="flex flex-col sm:flex-row gap-3 mb-4">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search by company, ticker, year..."
              className="w-full pl-9 pr-3 py-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500"
            />
          </div>
          <div className="flex gap-2">
            <select
              value={filingType}
              onChange={e => setFilingType(e.target.value)}
              className="px-3 py-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl text-sm text-gray-600 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {FILING_TYPES.map(ft => (
                <option key={ft} value={ft}>{ft || 'All types'}</option>
              ))}
            </select>
            <select
              value={year}
              onChange={e => setYear(e.target.value)}
              className="px-3 py-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl text-sm text-gray-600 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {YEARS.map(y => (
                <option key={y} value={y}>{y || 'All years'}</option>
              ))}
            </select>
            <select
              value={sort}
              onChange={e => setSort(e.target.value)}
              className="px-3 py-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl text-sm text-gray-600 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="fiscal_year">Newest first</option>
              <option value="company">By company</option>
            </select>
          </div>
        </div>

        {/* Active filters bar */}
        <div className="flex items-center gap-3 mb-4">
          <Filter size={14} className="text-gray-400 dark:text-gray-500" />
          <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
            {TICKERS.map(t => (
              <button
                key={t}
                onClick={() => setTicker(t)}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                  ticker === t
                    ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                }`}
              >
                {t || 'All'}
              </button>
            ))}
          </div>
          {activeFilters > 0 && (
            <button
              onClick={() => { setTicker(''); setFilingType(''); setYear(''); setSearchQuery('') }}
              className="text-xs text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Content */}
        {loading ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="h-24 bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
                <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-1/3 animate-pulse mb-2" />
                <div className="h-3 bg-gray-50 dark:bg-gray-800 rounded w-1/2 animate-pulse mb-3" />
                <div className="h-3 bg-gray-50 dark:bg-gray-800 rounded w-1/4 animate-pulse" />
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-12 h-12 bg-red-50 dark:bg-red-900/20 rounded-xl flex items-center justify-center mb-3">
              <FileText size={22} className="text-red-400" />
            </div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Unable to load filings</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">{error}</p>
            <button onClick={load} className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 transition-colors">
              Try again
            </button>
          </div>
        ) : filteredDocs.length === 0 ? (
          <div className="text-center py-16 text-gray-400 dark:text-gray-500">
            <Search size={40} className="mx-auto mb-3 opacity-40" />
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">No filings found</p>
            <p className="text-xs mt-1 text-gray-400 dark:text-gray-500">
              {searchQuery || activeFilters > 0 ? 'Try adjusting your filters' : 'Run the ingestion script to load filings'}
            </p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {filteredDocs.map(doc => (
              <button
                key={doc.id}
                onClick={() => openDetail(doc)}
                className="text-left bg-white dark:bg-gray-900 p-4 rounded-xl border border-gray-200 dark:border-gray-700 hover:border-blue-200 dark:hover:border-blue-800 hover:shadow-sm dark:hover:shadow-gray-900/50 transition-all group"
              >
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-blue-50 dark:bg-blue-900/30 rounded-xl flex items-center justify-center shrink-0 group-hover:bg-blue-100 dark:group-hover:bg-blue-900/50 transition-colors">
                    <FileText size={18} className="text-blue-500 dark:text-blue-400" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {doc.ticker && (
                        <span className="text-xs font-semibold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-1.5 py-0.5 rounded">{doc.ticker}</span>
                      )}
                      {doc.filing_type && (
                        <span className="text-xs text-gray-400 dark:text-gray-500">{doc.filing_type}</span>
                      )}
                      {doc.fiscal_year && (
                        <span className="text-xs text-gray-400 dark:text-gray-500">FY{doc.fiscal_year}</span>
                      )}
                    </div>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate mt-1">{doc.company_name || doc.title || doc.filename}</p>
                    <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-400 dark:text-gray-500">
                      <span className="flex items-center gap-1"><Calendar size={11} /> FY{doc.fiscal_year}</span>
                      <span className="flex items-center gap-1"><Layers size={11} /> {doc.chunk_count ?? '?'} chunks</span>
                      {doc.page_count && (
                        <span className="flex items-center gap-1"><FileText size={11} /> {doc.page_count} pages</span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Detail Drawer */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/20 dark:bg-black/50" onClick={() => setSelectedDoc(null)} />
          <div className="relative w-full max-w-md bg-white dark:bg-gray-900 shadow-2xl h-full overflow-y-auto animate-slide-in">
            <div className="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-blue-500" />
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Filing Details</h3>
              </div>
              <button onClick={() => setSelectedDoc(null)} className="p-1.5 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
                <X size={16} />
              </button>
            </div>

            {detailLoading ? (
              <div className="p-5 space-y-4">
                <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-2/3 animate-pulse" />
                <div className="h-3 bg-gray-50 dark:bg-gray-800 rounded w-1/2 animate-pulse" />
                <div className="h-20 bg-gray-50 dark:bg-gray-800 rounded-xl animate-pulse" />
              </div>
            ) : (
              <div className="p-5 space-y-5">
                {/* Company header */}
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 bg-blue-50 dark:bg-blue-900/30 rounded-2xl flex items-center justify-center">
                    <Building2 size={22} className="text-blue-500 dark:text-blue-400" />
                  </div>
                  <div>
                    <h4 className="text-base font-semibold text-gray-900 dark:text-gray-100">{selectedDoc.company_name || selectedDoc.ticker}</h4>
                    <p className="text-sm text-gray-500 dark:text-gray-400">{selectedDoc.filing_type} · FY{selectedDoc.fiscal_year}</p>
                  </div>
                </div>

                {/* Metadata grid */}
                <div className="grid grid-cols-2 gap-3">
                  <MetadataItem label="Company" value={selectedDoc.company_name || '-'} />
                  <MetadataItem label="Ticker" value={selectedDoc.ticker || '-'} />
                  <MetadataItem label="Filing Type" value={selectedDoc.filing_type || '-'} />
                  <MetadataItem label="Fiscal Year" value={selectedDoc.fiscal_year ? `FY${selectedDoc.fiscal_year}` : '-'} />
                  <MetadataItem label="Pages" value={String(selectedDoc.page_count ?? '?')} />
                  <MetadataItem label="Indexed Chunks" value={detailLoading ? '...' : String(selectedDoc.chunk_count ?? '?')} />
                </div>

                {/* Description */}
                <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4 border border-gray-100 dark:border-gray-700">
                  <p className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">Description</p>
                  <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                    {selectedDoc.title || selectedDoc.filename}
                  </p>
                </div>

                {/* SEC link */}
                {selectedDoc.source_url ? (
                  <a
                    href={selectedDoc.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-2 w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-xl hover:bg-blue-700 transition-colors"
                  >
                    <ExternalLink size={14} />
                    View on SEC.gov
                  </a>
                ) : (
                  <a
                    href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=&type=10-K`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-2 w-full py-2.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-sm font-medium rounded-xl hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
                  >
                    <ExternalLink size={14} />
                    Search on SEC.gov
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function MetadataItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 border border-gray-100 dark:border-gray-700">
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">{label}</p>
      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{value}</p>
    </div>
  )
}
