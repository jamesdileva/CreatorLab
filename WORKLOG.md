# WORKLOG.md — CreatorLab sprint log (append-only, newest at bottom)

Format per sprint:
`## YYYY-MM-DD — Sprint X.Y — Title` + Plan / Scope / Implement / Verify / Commit.

---

## 2026-10-11 — Sprint 0.1 — Repository and Documentation Foundation

**Plan:** Establish clean empty foundation before app logic (roadmap Phase 0).
**Scope:** git init, backend skeleton (FastAPI + GET /health), frontend skeleton
(React+Vite + /dashboard), docs/ normalized copies, creator-specs stubs,
`.env.example`, `docker-compose.yml`, `README.md`, `AGENTS.md`, `WORKLOG.md`.
**Implement:** Created repo structure per architecture §8; backend `app.main`
with `/health`; pytest `test_health.py`; Vite+React frontend with `/dashboard`
route; docs copies; env/compose/README/gitignore.
**Verify:** `python -m pytest backend/tests -v` passes; `/health` returns
`{"status":"ok"}`; `npm run build` succeeds; structure matches architecture §8.
**Commit:** Initial commit + `gh repo create CreatorLab --public` + push.

---

## 2026-10-11 — Sprint 1.1 — Creator Model

**Plan:** Persistent creator identities in DB (roadmap Phase 1, guide Phase 2, arch §9).
**Scope:** Creator model (all §9 fields) + DB wiring + CRUD API
(list/create/get/update/soft-deactivate) + Hank/Alex.exe seeds + creator UI
(list/create/deactivate, detail/edit). Out of scope: prompts (1.2), memory (1.3),
Alembic (later; `create_all` for proto).
**Implement:** `backend/app/models/creator.py`, `core/database.py` (SQLite default,
Postgres via `DATABASE_URL`), `api/creators.py` (409 dup, 400 bad slug, DELETE→soft
deactivate), `scripts/seed_creators.py` (idempotent), `tests/test_creators.py`
(7 tests), frontend `types/creator`, `services/creators`, `pages/Creators`,
`pages/CreatorDetail`, routes, dashboard nav. Also: `*.db` gitignore,
Pydantic `ConfigDict` cleanup.
**Verify:** `python -m pytest backend/tests -v` → 8 passed; seed run twice
(created→updated); live `GET /api/creators` returns Hank + Alex.exe with full
fields; `npm run build` succeeds (37 modules). Dev `creatorlab.db` removed after check.
**Commit:** Sprint 1.1 commit + push to `jamesdileva/CreatorLab` `main`.

---

## 2026-10-11 — Sprint 1.2 — Creator Prompt System

**Plan:** Versioned prompts + `LLMProvider` abstraction + creator-voice generation
(roadmap 1.2, guide §25/§26, arch §7).
**Scope:** `ai/providers/` (ABC + StubProvider deterministic/offline + OpenAICompatibleProvider
+mocked tests + factory), `ai/prompts/creator_prompt_v1.md` + registry (v1 frozen,
new version = new file), `services/creator_service.py`, `POST /api/creators/{id}/generate`,
`GET /api/creators/prompts/versions`, frontend "Test voice" box.
Out of scope: real API keys, memory/canon injection (1.3), structured_output/evaluation (later).
**Implement:** `providers/{base,stub,openai_compatible,__init__}`, `prompts/__init__`
(render + registry), `creator_service.py`, endpoint in `api/creators.py`, config
(`llm_provider`, `creator_prompt_version`, `openai_*`), `frontend` voice UI + service + types.
**Verify:** `pytest` → **29 passed** (6 prompt, 9 provider incl. httpx.MockTransport,
6 generate endpoint, prior suites intact); live `POST /api/creators/{1,2}/generate` →
Hank voice (plain-spoken, farming/trucks, dry deadpan) meaningfully different from
Alex.exe voice (buzzword-dense, AI/startups), each stamped `creator_prompt_v1` +
model; `npm run build` OK. Dev DB cleaned after check.
**Commit:** Sprint 1.2 commit + push to `main`.

---

## 2026-10-11 — Sprint 1.3 — Creator Memory

**Plan:** Structured creator memory before any RAG (guide Phase 3); generation
retrieves stored facts (roadmap 1.3).
**Scope:** `CreatorMemory` model (arch §9 fields + 7 memory types), memory CRUD
(`POST/GET/DELETE /api/creators/{id}/memories`, type filter, importance sort,
400 on bad type/range, 404 on cross-creator), memory injection into generation
(appended to frozen `creator_prompt_v1` as canon context; templates untouched),
stub replays recalled facts, seeded Hank/Alex.exe memories, frontend memory panel.
Out of scope: embeddings/RAG (explicitly deferred per guide §5).
**Implement:** `models/creator_memory.py`, memory endpoints + `memories_used` in
generate response, `services/creator_service.py` (`retrieve_memories`,
`build_system_prompt`), `providers/base` + `stub` memory recall, seed
`SEED_MEMORIES`, frontend memory panel (list/add/delete, importance input).
**Verify:** `pytest` → **41 passed** (14 new memory tests incl. roadmap two-pass
check: generate (no memory) → store CANON fact → generate again → fact appears
in text + `memories_used`); seed idempotent (8 memories created → updated); live
generation used all 4 Hank memories sorted by importance; `npm run build` OK.
Dev DB cleaned after check.
**Commit:** Sprint 1.3 commit + push to `main`.

---

## 2026-10-11 — Sprint 2.1 — Series Model

**Plan:** Give creators an actual fictional universe (roadmap 2.1, guide Phase 4).
**Scope:** Models `Series`, `Episode` (auto numbering, unique per series, 8 statuses),
`Scene`, `StoryThread` (OPEN/RESOLVED/ABANDONED + introduced/resolved episode),
`Canon` (universe facts, 7 categories); full CRUD in `api/episodes.py` (arch §8
file list respected); delete-episode → ARCHIVED, delete-series → ENDED (history
preserved); frontend `/series`, `/series/:id` (episodes/threads/canon),
`/episodes/:id` (scenes + status).
Out of scope: episode generator (2.2).
**Implement:** 5 model files + `api/episodes.py` (~600 lines) + `tests/test_story_universe.py`
(11 tests) + 3 pages + `services/story.ts` + `types/story.ts` + routes/nav.
**Verify:** `pytest` → **52 passed** (11 new: three-episode history retrieval
returns ordered [1,2,3] with premises; auto-numbering; duplicate 409; status
lifecycle + invalid 400; archive keeps record viewable; scenes unique+ordered;
thread open→resolve linking episode; cross-series link 400; canon CRUD + 400s;
404s). Live check: created series + 3 episodes + scenes + resolved thread + canon
via REST. `npm run build` OK (43 modules). Dev DB cleaned.
**Commit:** Sprint 2.1 commit + push to `main`.

---

## 2026-10-11 — Sprint 2.2 — Episode Generator

**Plan:** Canon-aware episode generator (roadmap 2.2, guide Phase 5): retrieve
canon + memory + episode history + open threads, draft, evaluate, persist.
**Scope:** `ai/prompts/episode_prompt_v1.md` + registry (+`render_episode_prompt`),
`ai/structured_output.py` (EpisodeDraft + strict JSON parse), `ai/evaluation.py`
(PASS/REVIEW/BLOCK: safety blocklist, canon-contradiction via negation-vs-canon
with echo exclusion, repetition, canon-not-referenced), `services/episode_service.py`,
`POST /api/series/{id}/generate-episode` (persists Episode+Scenes on PASS/REVIEW,
422 on BLOCK), stub deterministic 5-archetype JSON drafts, frontend generate panel.
**Implement:** 4 backend files + endpoint + 13 tests + frontend service/panel.
**Verify:** `pytest` → **65 passed** (13 new: 5-episode roadmap check — distinct
premises, zero contradictions/repetition/safety issues; parse/validation tests;
safety BLOCK; contradiction/repetition/canon-not-referenced REVIEW flags; persistence
+ numbering; prompt/model recorded). Live: 5 generations → Ep1-5 all PASS, history
ordered, distinct premises. `npm run build` OK. Dev DB cleaned.
**Commit:** Sprint 2.2 commit + push to `main`.

---

## 2026-10-11 — Sprint 2.3 — Running Jokes and Story Threads

**Plan:** Episodes resolve introduced threads naturally (roadmap 2.3).
**Scope:** `EpisodeDraft.resolves_thread` (exact-title contract), evaluation flag
`thread_not_found` for hallucinated resolutions (REVIEW, never mutates state),
service resolution logic (open-thread match → RESOLVED + resolved_episode_id,
`resolved_threads` in response), stub callback archetype (variant %6 ==5),
thread prompt instruction, frontend thread badges + resolved notice.
**Implement:** evaluation/base/stub/structured_output/service/endpoint/frontend.
**Verify:** `pytest` → **70 passed** (5 new: roadmap path — introduce in Ep1,
OPEN through Ep2-3, RESOLVED in Ep4 linked to Ep4; no-thread case resolves nothing;
hallucinated title flagged; real resolution accepted; multiple threads resolve only
the claimed one). Live: Ep1 thread → open through Ep3 → Ep4 RESOLVED
resolved_episode_id=4, history 1-4. `npm run build` OK. Dev DB cleaned.
**Note on prompts:** `episode_prompt_v1` was extended this sprint (adds the
resolves_thread instruction) BEFORE any experiment record referenced it, so no
experiment's reproducibility is affected — noted per guide §26.
**Commit:** Sprint 2.3 commit + push to `main`.

---

## 2026-10-11 — Sprint 3.1 — Candidate Generator

**Plan:** Generate 5-10 substantially different episode concepts per request
(roadmap 3.1, guide §5) as the candidate pool for Phase 4 simulation.
**Scope:** `models/concept.py` (ConceptSet + Concept), `structured_output.py`
ConceptItem + `parse_concepts` (3-10 bounds), `ai/evaluation.py::evaluate_concepts`
(safety BLOCK, duplicate_concepts BLOCK, topic_not_covered REVIEW),
`concepts_prompt_v1.md` + registry, stub 10 deterministic archetypes with count
selection, `services/concept_service.py`, `POST /api/series/{id}/generate-concepts`
+ list sets/concepts, frontend concepts panel.
**Implement:** model/parse/eval/prompt/stub/service/endpoints/UI + 12 tests.
**Verify:** `pytest` → **82 passed** (12 new: 5 concepts distinct on same topic,
10 distinct, deterministic same-topic reruns, persisted set+children, duplicate
BLOCK, banned BLOCK, wrong-count ParseError, topic REVIEW, count bounds 400,
empty topic 400, unknown series/prompt 404/400). Live: count=5 and count=10 both
PASS with 5/10 distinct premises, tags/angles varied; sets retrievable.
`npm run build` OK. Dev DB cleaned.
**Commit:** Sprint 3.1 commit + push to `main`.

---

## 2026-10-11 — Sprint 3.2 — Concept Evaluation

**Plan:** Score candidate concepts on the six roadmap dimensions and compare
rankings against human judgment (roadmap 3.2, arch §12).
**Scope:** `core/metrics.py` (Spearman, Kendall-τ, top-k, directional accuracy —
shared with Phase 9 later), `models/concept_score.py` (ConceptScore + HumanRanking),
`services/scoring_service.py` (deterministic heuristic-v1 baseline: hook, character
fit, novelty, story potential, audience relevance, episode continuity → weighted
composite + rank; idempotent upserts; human ranking validation; comparison report),
4 endpoints (score/lists/human-ranking/comparison), `ConceptRanking.tsx` UI.
**Implement:** metrics/models/service/endpoints/UI + 9 tests.
**Verify:** `pytest` → **91 passed** (9 new: known-vector metric correctness incl.
reversed/inverted rankings; six-dimension output + rank ordering + composite
weights; persistence idempotence; human-ranking validation; reversed vs identical
comparison values; pre-data 409; 404s). Live: 5 concepts scored+ranks,
identical comparison (1.0/1.0) then reversed (-1.0/-1.0, directional 0.0).
`npm run build` OK. Dev DB cleaned.
**Commit:** Sprint 3.2 commit + push to `main`.
