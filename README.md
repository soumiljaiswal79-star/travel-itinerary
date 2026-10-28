# Wayfarer

Wayfarer is a personalized trip planner built to match the supplied architecture: a React/Vite web app talks to a FastAPI REST API; only that API talks to Supabase, Groq, and Unsplash. Supabase service-role credentials and provider API keys stay on the backend.

## Project layout

- `frontend/` — React 18, TypeScript, and Vite application for sign-in, trip planning, itinerary editing, and collaboration.
- `backend/` — FastAPI REST API, Pydantic validation, Supabase persistence/authentication, Groq itinerary generation, and an authenticated Unsplash image proxy.
- `supabase/schema.sql` — profiles, trips, itinerary days, collaborators, database functions, and row-level security policies.
- `.env.example` — complete local and deployment variable reference.

The browser stores only the signed-in user's access/refresh tokens. Auth requests go through FastAPI; the backend verifies access tokens with Supabase and applies owner/member checks before using its service-role database connection. The service-role key is never sent to the browser. Image bytes are fetched and proxied by the backend, so the browser does not call Unsplash directly. The default Groq model is `qwen/qwen3.8-27b`; set `GROQ_MODEL` to an active model on your Groq account if that changes.

## Requirements

- Python 3.12 recommended for local use and Render.
- Node.js 20 or newer.
- A Supabase project, Groq API key, and (optionally) Unsplash access key.

## Configure Supabase

1. Create a Supabase project.
2. In the Supabase SQL Editor, run [`supabase/schema.sql`](./supabase/schema.sql).
3. In **Authentication → Providers → Email**, configure email/password sign-in and your desired email-confirmation behavior.
4. Copy the project URL, anon key, and service-role key from **Project Settings → API**. `SUPABASE_URL` should be the project root URL, such as `https://your-project.supabase.co`, not a `/rest/v1/` endpoint. The backend strips a pasted `/rest/v1` or `/auth/v1` suffix automatically. The service-role key is backend-only and must never be prefixed with `VITE_`.
5. Add your local and deployed frontend origins to the FastAPI `ALLOWED_ORIGINS` variable.

The SQL creates the profile trigger and enables RLS on every application table. Run it before using trip storage; without it, Supabase Auth may work while trip requests fail because `public.trips` does not exist. Owner, editor, and viewer access is represented in `shared_trip_members`; database policies prevent a viewer from changing trip data. The backend additionally checks membership before each trip operation.

## Run locally

From the project root, copy the example to the backend environment file:

```powershell
Copy-Item .env.example backend\.env
```

Edit `backend\.env` and set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `GROQ_API_KEY`. `UNSPLASH_ACCESS_KEY` is optional; without it, the app displays a local fallback instead of an image. The example allows both `localhost:5173` and `127.0.0.1:5173` for local development.

### Start FastAPI

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

The API is at `http://localhost:8000`; interactive API documentation is at `http://localhost:8000/docs`.

### Start Vite

In another terminal:

```powershell
cd frontend
'VITE_API_URL=http://localhost:8000/api' | Set-Content .env
npm install
npm run dev
```

The Vite development server proxies `/api` requests to `http://127.0.0.1:8000`, so local development does not depend on browser CORS settings. Open the Vite URL (normally `http://localhost:5173`). Create an account and confirm the email if confirmation is enabled in Supabase.

## API overview

All application endpoints are under `/api`; protected endpoints require `Authorization: Bearer <Supabase access token>`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/signup`, `/api/auth/login`, `/api/auth/refresh` | Create/sign in/refresh a user session |
| GET | `/api/auth/me` | Verify the current session |
| POST | `/api/trips/generate` | Generate and save a validated itinerary |
| GET | `/api/trips`, `/api/trips/{id}` | List accessible trips or read one |
| PATCH / DELETE | `/api/trips/{id}` | Update trip details or delete an owned trip |
| POST | `/api/trips/{id}/regenerate` | Replan a trip with new guidance |
| PUT | `/api/trips/{id}/days/{day}` | Save day-level edits |
| POST | `/api/trips/{id}/days/{day}/regenerate` | Regenerate one day |
| GET / POST | `/api/trips/{id}/members` | List or invite trip collaborators by email |
| DELETE | `/api/trips/{id}/members/{user_id}` | Remove a collaborator (owner only) |
| GET | `/api/images?q=...` | Search and proxy one Unsplash image |
| GET | `/health` | Render health check |

Generation requests are validated before provider calls. Groq is asked for JSON-only output, the result is validated against Pydantic models, and one repair call is attempted for malformed output. Rate limits return HTTP 429 with a retry-friendly message; provider failures return a clear HTTP 502. Image lookup failures are non-fatal. Route ordering uses a nearest-neighbor distance heuristic for stops with coordinates between dining stops, preserving the model's scheduled time slots; no external mapping/routing provider is implied by the supplied architecture.

## Deploy

### Render (backend)

1. Create a Render **Web Service** using this repository and set its root directory to `backend` (the included `backend/render.yaml` is also available as a Blueprint).
2. Build command: `pip install -r requirements.txt`.
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
4. Add `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GROQ_API_KEY`, and `ALLOWED_ORIGINS` as Render environment variables. `ALLOWED_ORIGINS` must contain the exact Vercel production URL (comma-separate additional preview origins if needed). Add `UNSPLASH_ACCESS_KEY` for images; it is optional.
5. Render uses `/health` as its health check. Keep all provider keys and the Supabase service-role key in Render's secret environment settings.

### Vercel (frontend)

1. Import the repository into Vercel and set the project root directory to `frontend`.
2. Vercel detects Vite; use `npm run build` and `dist` if prompted.
3. Set `VITE_API_URL` to the Render API origin plus `/api`, for example `https://wayfarer-api.onrender.com/api`.
4. Redeploy after setting the variable. Configure the Render `ALLOWED_ORIGINS` value to the exact Vercel URL.
5. Do not add any Supabase, Groq, or Unsplash secret to Vercel. The Vite variable is only the public FastAPI base URL.

## Tests and checks

Backend unit tests cover date validation, strict itinerary constraints, and route ordering:

```powershell
cd backend
python -m pytest
```

Frontend TypeScript checking and production bundling:

```powershell
cd frontend
npm run build
```

Live provider/database flows need project credentials and deployed Supabase schema. After configuration, verify these product paths in the browser:

1. Create a solo weekend itinerary with food/sightseeing interests and a budget; confirm dates, dining, transport, and estimated costs are shown.
2. Create a relaxed couple trip, edit a stop, regenerate a single day with guidance, and confirm the saved day and total update.
3. Create a group trip, invite a second registered account, and verify both accounts can see it while viewer/editor permissions are respected.

## Small implementation choices

- Itineraries are saved when generated; regeneration updates the existing saved plan.
- Trips are limited to 14 days so a structured itinerary can fit within economical model output limits.
- Trip costs are estimates for the whole group, not per-person quotes.
- Sharing is by email for accounts that have already registered; owners choose editor or viewer access.
- When Unsplash is not configured or has no result, a local styled image placeholder keeps the itinerary usable.
- The app does not book travel, verify real-time availability, or claim live transit durations.
