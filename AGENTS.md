# AGENTS.md — CreatorLab contributor guide

This file governs all AI/human contributors. Follow it exactly.

## Project

Creator Reality Lab — experimental AI creator ecosystem.
Hypothesis: a simulated audience helps persistent fictional AI creators make better
content for real humans, and real-world results calibrate the simulation.
Reality is ground truth. Relative ranking before absolute prediction.

MVP: 2 creators (Hank, Alex.exe) → episodic Shorts → 25-viewer synthetic audience →
human approval → YouTube → analytics → reality-gap comparison.

## Stack

- Backend: Python 3.12+ + FastAPI + SQLAlchemy + Alembic + pytest
- Frontend: React + Vite + TypeScript
- DB: PostgreSQL (SQLite allowed only for local proto)
- Media: FFmpeg, local `media/` dir first (S3 later)
- Scheduler: APScheduler for MVP
- AI: provider abstraction (`LLMProvider`), prompt versioning, never hard-code one model

## Commands

```powershell
# backend
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend   # serves GET /health
python -m pytest backend/tests -v

# frontend
npm --prefix frontend install
npm --prefix frontend run dev      # /dashboard
npm --prefix frontend run build
```

Ports: backend `8000`, frontend `5173`. No secrets in repo — use `.env` (see `.env.example`).

## Repo structure (must match `docs/architecture.md` §8)

```text
docs/ backend/app/{api,core,models,services,simulation,ai,integrations}
frontend/src/{components,pages,hooks,services,types}
media/{creators,episodes,generated,approved,published}  scripts/
```

## Hard boundaries (from architecture §4 + §20)

NEVER build: autonomous comment warfare, artificial likes/subs/shares/comments,
mass account creation, fully autonomous publishing, impersonation of real people,
fake-news personalities, scraping/re-upload pipelines, platform-evasion tooling.
All YouTube publishes require explicit human approval in MVP.
Use official YouTube Data API first; emulators/browser automation are future-only.
Controversy/outrage is never the optimization target.

## Conventions

- Every sprint follows: `plan + scope → implement → verify (tests) → commit + push`.
- Update `WORKLOG.md` every sprint (append-only, newest at bottom).
- Simulation runs must store: `simulation_run_id, model, model_version,
  prompt_version, audience_version, seed, timestamp` for reproducibility.
- Prompts live in `backend/app/ai/prompts/`, versioned (`*_v1`, `*_v2`); never
  silently edit a production prompt.
- Experiments get immutable records under `docs/experiments/EXPERIMENT-XXXX.md`.
- Keep every content-pipeline artifact (script, scenes, assets, captions, render).
- Cost tiers: cheap (concepts/sim/metadata) → moderate (script/voice/images) →
  expensive (video/large sims). Start sims small (25 viewers).
- Tests: unit (CRUD, memory, scoring, aggregation, reality-gap) + integration
  (creator→episode→sim→approval→video). YouTube tests use private/unlisted only.
