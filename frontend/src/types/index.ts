export interface Profile {
  id: string
  email: string
  display_name?: string
}

export interface Document {
  id: string
  filename: string
  title?: string
  company_name?: string
  ticker?: string
  filing_type?: string
  fiscal_year?: number
  page_count?: number
  chunk_count?: number
  source_url?: string
  created_at: string
  updated_at?: string
}

export interface Thread {
  id: string
  title: string
  created_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  created_at: string
}

export interface Citation {
  chunk_id: string
  page_number?: number
  section_title?: string
  ticker?: string
  fiscal_year?: number
  excerpt?: string
}

export interface SearchResult {
  chunk_id: string
  document_id: string
  content: string
  page_number?: number
  score: number
  source: string
}
