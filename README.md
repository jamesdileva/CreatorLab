# CreatorLab — Creator Reality Lab

Experimental AI creator ecosystem.

> Hypothesis: a simulated audience helps persistent fictional AI creators make
> better content for real human audiences, and real-world results calibrate
> the simulation.

Loop: Creator → idea → simulated audience (25 viewers) → ranking →
human approval → YouTube Short → analytics → reality-gap → calibration.

See `docs/architecture.md`, `docs/implementation-guide.md`, `docs/sprint-roadmap.md`.

## Quickstart

```powershell
# backend (port 8000)
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend
# GET http://localhost:8000/health -> {"status":"ok"}

# seed Hank + Alex.exe (SQLite proto; Postgres via DATABASE_URL)
python scripts/seed_creators.py
# GET http://localhost:8000/api/creators

# frontend (port 5173)
npm --prefix frontend install
npm --prefix frontend run dev
# open http://localhost:5173/dashboard

# tests
python -m pytest backend/tests -v
```

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

## MVP scope

- 2 fictional creators: Hank, Alex.exe (see `docs/creator-specs/`)
- Phase 12 expansion: Willow (12.1), Crash (12.2), Jessica (12.3)
- Versioned creator prompts (`creator_prompt_v1`, frozen) + `LLMProvider` abstraction
- Structured creator memory (canon/events/jokes) injected into generation
- YouTube Shorts, original episodic content
- 25-viewer synthetic audience, ranking before absolute prediction
- Human approval required for all publishes
- Reality-gap: Spearman/Kendall/top-k/directional accuracy

## Safety

No artificial engagement, no impersonation, no autonomous publishing in MVP.
Official YouTube Data API first. See `AGENTS.md`.
