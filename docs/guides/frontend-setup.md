# Frontend setup

A Vite + React SPA that connects to the FastAPI backend. No server-side rendering needed.

## Init

```bash
cd frontend
npm install
```

## Dev

```bash
npm run dev    # http://localhost:5173, proxies /api to localhost:8000
```

## Build

```bash
npm run build  # outputs to dist/
```

## TypeScript

```bash
npx tsc --noEmit
```

## Production deployment (Vercel)

1. Connect repo to Vercel
2. Set framework to Vite
3. Root directory: `frontend/`
4. Build command: `npm run build`
5. Output directory: `dist`
6. Add env var `VITE_API_URL=https://your-backend.onrender.com`
7. `vercel.json` contains the SPA rewrites rule (all routes → index.html)

## Project structure

```
src/
├── App.tsx                 # Root component with routing
├── components/
│   ├── Chat.tsx            # Main chat interface + streaming + landing page
│   ├── ThreadContext.tsx    # Thread list + active thread state management
│   ├── AuthContext.tsx      # Supabase auth state
│   ├── AuthPage.tsx        # Login + Signup
│   ├── Dashboard.tsx       # Marketing/landing page
│   ├── Layout.tsx          # Sidebar + content layout
│   ├── Documents.tsx       # SEC filing browser
│   └── Settings.tsx        # User settings
├── api/quorum.ts           # Backend API client
├── types/index.ts          # TypeScript interfaces
└── lib/supabase.ts         # Supabase browser client
```
