# Quorum Frontend

React 19 + TypeScript 6 + Vite 8 SPA for the Quorum SEC Filing Analyst.

## Stack

- React 19 with TypeScript
- Vite 8 for dev server and build
- Supabase Auth (browser client)
- Nginx for production serving (see `nginx.conf` for local HTTPS, `nginx.conf.railway` for Railway)

## Setup

```bash
npm install
npm run dev        # local dev server on http://localhost:5173
npm run build      # production build to dist/
```

## Dev proxy

Vite proxies `/api` requests to `http://localhost:8000` (the backend), stripping the `/api` prefix.

## Production builds

- **Local Docker:** `../docker-compose.yml` builds from `Dockerfile` using `nginx.conf` (HTTPS with self-signed certs)
- **Railway:** Build from `Dockerfile.railway` using `nginx.conf.railway` (plain HTTP, TLS handled at Railway edge)

## Project structure

```
src/
├── App.tsx                 # Root component with routing
├── components/
│   ├── Chat.tsx            # Main chat interface + streaming
│   ├── AuthContext.tsx     # Supabase auth state management
│   ├── Login.tsx           # Login page
│   ├── Signup.tsx          # Signup page
│   └── Documents.tsx       # SEC filing browser
├── api/
│   └── quorum.ts           # Backend API client (fetch-based)
└── lib/
    └── supabase.ts         # Supabase browser client
```
