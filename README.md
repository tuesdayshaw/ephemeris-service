# ephemeris-service

A small, reusable calculation-only astrology microservice built with FastAPI and Swiss Ephemeris (`pyswisseph`).

## Project Scope

This service intentionally includes only:

- Ephemeris calculations (tropical ecliptic coordinates)
- Daily snapshot caching (SQLite)
- Simple API key gate for `/v1/*` routes

This repository intentionally excludes app/business logic, user accounts, UI, and interpretation text.

## Endpoints

- `GET /` (no auth)
- `GET /health` (no auth)
- `GET /v1/positions`
- `GET /v1/snapshot/daily`
- `GET /v1/moon/aspects`
- `GET /v1/moon/phase`
- `GET /v1/aspects`
- `GET /v1/retrogrades`
- `GET /v1/daily/windows`

All `/v1/*` routes require `X-API-Key` when `API_KEY` is set. If `API_KEY` is empty/unset, auth is disabled for local dev.

## Quickstart (Local)

1. Install Python 3.11+.
2. Copy `.env.example` to `.env` and set values.
3. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. Start the API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables

- `EPHE_PATH`: directory containing Swiss Ephemeris data files (`.se1`, etc.)
- `CACHE_DIR`: directory for snapshot SQLite cache
- `API_KEY`: API key for `/v1/*` routes; empty disables auth (dev only)
- `TZ`: default timezone for endpoints that accept `tz` (default `America/Chicago`)
- `ALLOWED_ORIGINS`: comma-separated CORS allowlist; empty disables CORS middleware
- `ALLOWED_HOSTS`: comma-separated trusted host allowlist; empty disables trusted host checks
- `DISABLE_DOCS`: `true` to disable `/docs`, `/redoc`, and `/openapi.json`

Example:

```bash
EPHE_PATH=/var/ephe
CACHE_DIR=/var/cache
API_KEY=devkey
TZ=America/Chicago
ALLOWED_ORIGINS=http://localhost:3000
ALLOWED_HOSTS=localhost,127.0.0.1
DISABLE_DOCS=false
```

## Production settings (Render)

- CORS allowlist format:
  - `ALLOWED_ORIGINS` is a comma-separated list of exact origins, for example:
    - `https://app.example.com,http://localhost:3000`
  - Leave empty to disable CORS middleware.
- Trusted hosts allowlist format:
  - `ALLOWED_HOSTS` is a comma-separated list of allowed hostnames, for example:
    - `ephemeris-service.onrender.com`
  - Leave empty to disable TrustedHost middleware.
- Docs disabling:
  - Set `DISABLE_DOCS=true` to disable `/docs`, `/redoc`, and `/openapi.json` in production.

Render example values:

```bash
ALLOWED_ORIGINS=https://<your-moon-minutes-domain>,http://localhost:3000
ALLOWED_HOSTS=ephemeris-service.onrender.com
DISABLE_DOCS=true
```

## Ephemeris Data Files

Ephemeris data files are not baked into the image; mount them via volume at runtime.

- Official source: `https://www.astro.com/ftp/swisseph/ephe/`
- Typical required files for planets/moon in common year ranges include files such as:
  - `sepl_18.se1`, `sepl_24.se1`
  - `semo_18.se1`, `semo_24.se1`

Download the files you need for your supported date range and point `EPHE_PATH` to that folder.

### Modern block (example)

For modern dates, these two files are sufficient for planets + Moon in a common range:

```bash
mkdir -p "$EPHE_PATH"
curl -fL -o "$EPHE_PATH/sepl_18.se1" https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/sepl_18.se1
curl -fL -o "$EPHE_PATH/semo_18.se1" https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/semo_18.se1
```

## API Examples

### Root

```bash
curl http://localhost:8000/
```

### Health

```bash
curl http://localhost:8000/health
```

### Positions

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8000/v1/positions?dt=2025-06-15T12:00:00Z"
```

Filtered bodies:

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8000/v1/positions?dt=2025-06-15T12:00:00Z&bodies=sun,moon,mars"
```

### Daily Snapshot

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8000/v1/snapshot/daily?date=2025-06-15&tz=America/Chicago"
```

### Moon Aspects

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8000/v1/moon/aspects?date=2025-06-15&tz=America/Chicago&orb=6.0"
```

### Moon Phase

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8000/v1/moon/phase?dt=2025-06-15T12:00:00Z"
```

### Aspects

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8000/v1/aspects?dt=2025-06-15T12:00:00Z&bodies=sun,moon,mars&aspects=conjunction,sextile,square,trine,opposition&orb=6"
```

### Retrogrades

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8000/v1/retrogrades?dt=2025-06-15T12:00:00Z&retrograde_only=true"
```

### Daily Windows

```bash
curl -H "X-API-Key: your-key" \
  "http://localhost:8000/v1/daily/windows?date=2025-06-15&tz=America/Chicago&orb=6"
```

## Testing (Integration/Smoke)

Tests are integration-style and use real Swiss Ephemeris files.

1. Ensure ephemeris files are present locally.
2. Export `EPHE_PATH` to that directory.
3. Run:

```bash
pytest -q
```

Included tests:

- `/health` smoke test
- `/v1/positions` known-date sanity checks
- `/v1/snapshot/daily` cache-miss then cache-hit verification
- `/v1/moon/phase` ranges/sanity checks
- `/v1/aspects` structure/ranges checks
- `/v1/retrogrades` structure checks
- `/v1/daily/windows` structure checks

## Docker

Build and run:

```bash
docker compose up --build
```

`docker-compose.yml` mounts:

- `./ephe -> /ephe` (read-only)
- `./cache -> /cache`

Set `.env` values accordingly.

## Deployment Notes

### Render (low-cost)

- Create a Web Service from this repo.
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Add env vars: `EPHE_PATH`, `API_KEY`, `CACHE_DIR`, `TZ`
- Mount a persistent disk (e.g. mount at `/var`) and set `EPHE_PATH=/var/ephe`, `CACHE_DIR=/var/cache`.
- Download required `.se1` files into `$EPHE_PATH` at runtime (or bake them into a private image if licensing allows).

### Google Cloud Run

- Build container with the provided `Dockerfile`.
- Deploy to Cloud Run and set env vars.
- Provide ephemeris files through a mounted volume strategy (for example, Cloud Storage FUSE or pre-provisioned volume) and point `EPHE_PATH` there.
- Keep `CACHE_DIR` on writable storage.

## Architecture Notes

- `app/ephemeris.py` isolates all `swisseph` calls behind `EphemerisEngine`.
- `app/cache.py` provides SQLite cache access.
- `app/main.py` handles HTTP routes/orchestration only.

This separation keeps switching ephemeris backends or licensing paths straightforward.

## License & Compliance Notes

This project is licensed under **AGPL-3.0-or-later**.

Practical notes:

- This service includes AGPL-covered server-side code and uses Swiss Ephemeris through `pyswisseph`.
- Downstream applications that call this service over HTTP are typically separate programs communicating via network API boundaries.
- If you modify and deploy this service, publish corresponding source as required by AGPL.
- Review Swiss Ephemeris licensing terms for your distribution/deployment model.

This section is informational and not legal advice.
