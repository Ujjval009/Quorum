# Frontend setup

This project uses a Vite + React SPA because the frontend is an internal tool that mainly needs fast iteration, authenticated app flows, and a clean connection to the FastAPI backend. We do not need the extra server-rendering, SEO, or full-stack routing features that Next.js is optimized for.

## Init (from empty `frontend/`)

```bash

cdfrontend

pnpmcreatevite.--templatereact-ts

pnpminstall

pnpmaddreact-router-dom@supabase/supabase-js

pnpmadd-Dtailwindcss@tailwindcss/vite

pnpmdlxshadcn@latestinit

```

## Run

```bash

cdfrontend

pnpminstall

pnpmdev

```

## Check

```bash

pnpmtsc--noEmit

pnpmlint

```
