# Payout Engine

A minimal but strictly production-realistic payout engine mechanism simulating a bank gateway. Focused entirely on concurrency safety, mathematical idempotency bounding, and PostgreSQL ledger data integrity.

## Stack

- **Backend:** Django + DRF
- **Database:** PostgreSQL (row-level locking via `SELECT FOR UPDATE`)
- **Background jobs:** Huey + Redis
- **Frontend:** React + Vite + Tailwind CSS

## Local Setup

### 1. Environment variables

Copy both env files and fill in your values:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Backend `.env` variables:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for local |
| `ALLOWED_HOSTS` | `*` for local |
| `DATABASE_URL` | Postgres connection string |
| `REDIS_URL` | Redis connection string |

Frontend `.env` variables:

| Variable | Description |
|---|---|
| `VITE_API_BASE_URL` | Backend API base URL, e.g. `http://localhost:8000/api/v1` |

### 2. Start infrastructure (Postgres + Redis)

```bash
docker compose up -d
```

Or point `DATABASE_URL` and `REDIS_URL` at Supabase/Upstash if you prefer managed services.

### 3. Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd backend
python manage.py migrate
python seed.py          # Seeds 3 merchants with credit history
python manage.py runserver
```

### 4. Background worker (required)

The worker handles bank simulation, retries, and timeouts. Run this in a separate terminal:

```bash
# In a new terminal:
source .venv/bin/activate
cd backend
python manage.py run_huey
```

Without this running, payouts will stay in `pending` forever.

### 5. Frontend

```bash
cd frontend
pnpm install
pnpm run dev
```

Open `http://localhost:5173`. Use the merchant dropdown (top right) to switch between seeded merchants.

## Tests

```bash
cd backend
source .venv/bin/activate
python manage.py test payouts.tests
```

Covers:
- **Concurrency:** Two simultaneous 60-rupee requests against a 100-rupee balance — exactly one succeeds
- **Idempotency:** Same `Idempotency-Key` submitted twice — identical response, single payout created

## Architecture notes

See `EXPLAINER.md` for the specific decisions around locking primitives, the ledger model, idempotency in-flight handling, and the state machine constraints.

## Cloud Deployment (Render / Fly.io / Railway)

A production-ready `Dockerfile` and `start.sh` are included in the `backend/` directory.

To bypass the free-tier limitation of 1 container per project, the `start.sh` boots the `run_huey` worker securely into the background process space before successfully spinning up and tying the public port to `gunicorn`. This lets both the API and the background workers reliably operate simultaneously under a single container(because most of provider offer only 1 container per project in free tier).