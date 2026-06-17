# Quorum Frontend

React 19 + TypeScript 6 + Vite 8 SPA for the Quorum SEC Filing Analyst.

## Stack

- React 19 with TypeScript
- Vite 8 for dev server and build
- React Router v7 for routing
- Supabase Auth (browser client)
- Tailwind CSS for styling
- Lucide React for icons
- React Markdown + remark-gfm for rendering

## Setup

```bash
npm install
npm run dev        # local dev server on http://localhost:5173
npm run build      # production build to dist/
npm run lint       # lint check
```

## Dev proxy

Vite proxies `/api` requests to `http://localhost:8000` (the backend), stripping the `/api` prefix.

## Production builds

- **Vercel:** Deploy from repo root, framework=Vite, output dir=`frontend/dist`. SPA routing via `vercel.json`.
- **Docker:** Build from `Dockerfile` using `nginx.conf` (HTTPS with self-signed certs).

## Project structure

```
src/
├── App.tsx                 # Root component with routing
├── components/
│   ├── Chat.tsx            # Main chat interface + streaming + landing page
│   ├── ThreadContext.tsx    # Thread list + active thread state management
│   ├── AuthContext.tsx      # Supabase auth state management
│   ├── AuthPage.tsx        # Login + Signup pages
│   ├── Dashboard.tsx       # Landing/marketing page with Start Analysis
│   ├── Layout.tsx          # Sidebar + main content layout
│   ├── Documents.tsx       # SEC filing browser
│   └── Settings.tsx        # User settings
├── api/
│   └── quorum.ts           # Backend API client (fetch-based)
├── types/
│   └── index.ts            # TypeScript interfaces
└── lib/
    └── supabase.ts         # Supabase browser client
```
