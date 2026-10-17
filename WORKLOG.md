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

---

## 2026-10-11 — Sprint 4.1 — Synthetic Viewer

**Plan:** Heterogeneous 25-viewer audience, deterministically seeded (roadmap 4.1,
arch §10, guide §9 reproducibility).
**Scope:** `SyntheticViewer` model (interests/personality/humor/attention/
affinities/response_style + `audience_version`), `services/audience_service.py`
(deterministic `seed_audience` + `baseline_interest` heuristic precursor to the
Sprint 4.2 reaction model), `api/simulation.py` (seed/list/detail/affinity/
preview), `/simulation` population page with identical-content check.
**Implement:** model/service/API/UI + 9 tests.
**Verify:** `pytest` → **100 passed** (9 new: seed 25 + version, idempotent
re-seed, heterogeneity thresholds, differing reactions on identical content,
topic-match ordering, affinity boost, endpoint validation). Live: 25 seeded
viewers, 5 personalities, 4 response styles, 6 distinct interest levels
(0.18–0.30) on identical content. `npm run build` OK. Dev DB cleaned.
**Commit:** Sprint 4.1 commit + push to `main`.

---

## 2026-10-11 — Sprint 4.2 — Audience Reactions

**Plan:** Per-viewer watch/like/comment/share/follow + persisted runs with full
reproducibility metadata, aggregated into an audience response (roadmap 4.2,
arch §10).
**Scope:** `SimulationRun` + `ViewerReaction` models (guide §9 metadata),
`services/simulation_service.py` (deterministic scroll-stop model + reason codes
+ aggregation), endpoints (run/list/detail/reactions), `SimulationRunner` UI.
**Implement:** models/engine/endpoints/UI + 10 tests.
**Verify:** `pytest` → **110 passed** (10 new: bounded probabilities,
like/comment/share/follow ≤ watch, sharer>lurker, run aggregate ranges,
episode runs, 25 stored reactions, rerun reproducibility, listing/detail,
validation/404s, affinity→follow). Live: same episode → watch 0.515/like
0.273/comment 0.06/share 0.033/follow 0.047, rerun identical, 4 distinct watch
levels stored. `npm run build` OK. Dev DB cleaned.
**Commit:** Sprint 4.2 commit + push to `main`.

---

## 2026-10-11 — Sprint 4.3 — Candidate Ranking

**Plan:** Rank several candidates through the same population and answer
"which candidate first?" (roadmap 4.3) — completes Phase 4 audience MVP.
**Scope:** `RankingRun` model (candidates, metric, ordered ranking, linked sim
runs, reproducibility metadata), `rank_candidates` service (one sim run per
candidate, same audience, candidate-id tiebreak), endpoints (rank/list/detail),
`RankingRunner` UI. Also fixed literal-vs-parameterized route shadowing
(`/simulations/rankings` before `/simulations/{run_id}`).
**Implement:** model/service/endpoints/UI + 7 tests.
**Verify:** `pytest` → **117 passed** (7 new: ordered 4-candidate ranking,
deterministic rerun, linked sim runs with 25 reactions each, persistence +
detail, alternate metric, episode ranking, validation/404s). Live:
`#2 (0.652) > #4 (0.593) > #1 (0.584) > #3 (0.583)` — roadmap's A>C>B>D shape,
rerun identical. `npm run build` OK. Dev DB cleaned.
**Commit:** Sprint 4.3 commit + push to `main`.

---

## 2026-10-11 — Sprint 5.1 — Simple Video Renderer

**Plan:** Produce an actual 15-45s video artifact (roadmap 5.1, guide §10-11):
scene cards + offline TTS + SRT captions + FFmpeg assembly, every intermediate
artifact kept.
**Scope:** `services/video_service.py` (Pillow 1080x1920 cards with Ken Burns
zoompan, pyttsx3/SAPI speech, SRT + label burn-in, concat, manifest.json),
`POST /api/episodes/{id}/render` (RENDERING→READY, REVERT on failure), `/media`
static mount, episode-detail render button + `<video>` preview. Offline-first;
character visuals deferred to 5.2.
**Implement:** video_service/render endpoint/media mount/frontend render UI + 9 tests.
**Verify:** `pytest` → **126 passed** (9 new: card dimensions, SRT format,
ffprobe duration, end-to-end render inside the 15-45s window, too-long rejection,
empty-scene rejection, episode render → status READY + manifest episode_id, 404,
real-TTS smoke). Live: 3-scene episode rendered to a 15.0s 1080x1920 h264 MP4
(697KB), episode status READY. `npm run build` OK. Artifacts gitignored.
**Commit:** Sprint 5.1 commit + push to `main`.

---

## 2026-10-11 — Sprint 5.2 — Character Visual Identity

**Plan:** Consistent, distinct per-creator visuals for the short renderer
(roadmap 5.2), offline-only (no external image services).
**Scope:** `services/character_service.py` — `CharacterIdentity` model
(palette/accessories/props/style + `identity-v1`), default identities for
Hank (cap/beard/gear, olive) and Alex.exe (visor/headset/terminal, cyan),
deterministic flat-design portrait renderer, `render_identity_card` wired into
the Sprint 5.1 pipeline (manifest `card_version`), identity endpoints
(GET/PATCH + portrait preview), creator-detail identity panel.
**Implement:** character_service/identity API/renderer wiring/UI + 9 tests.
**Verify:** `pytest` → **135 passed** (9 new: default identity, one-per-creator,
palette validation, accessory/display-name updates, 404, deterministic +
distinct portraits, five-scene consistency (character region pixel-identical),
identity snapshot, episode render through identity). Live: 5 Hank cards →
scene-vs-scene diff 0.0, Hank-vs-Alex diff 0.157. `npm run build` OK.
**Commit:** Sprint 5.2 commit + push to `main`.

---

## 2026-10-11 — Sprint 5.3 — Episode-to-Video Pipeline

**Plan:** Connect Episode → scenes → assets → voice → captions → render as a
tracked pipeline behind the human approval gate (roadmap 5.3, arch §5.6).
**Scope:** `models/render.py` (Render + SceneAsset with per-stage provenance),
`render_episode_pipeline` service (APPROVED gate, Render row, per-stage asset
rows, READY/FAILED transitions, REVIEW on failure), endpoints
(approve/reject/render/list renders/render detail), frontend approve/reject
buttons + render history.
**Implement:** models/service/endpoints/UI + 7 tests (updated 2 older tests to
approve-first per the new gate).
**Verify:** `pytest` → **142 passed** (7 new: full pipeline from approved
episode, render-before-approval 422, approve→reject, published-episode guards,
artifact provenance (3 cards + 3 voices + captions + video + manifest), render
history + 404s, failed render recorded → REVIEW). Live: render-before-approval
422 → approve → render READY 15.0s/3 scenes, video exists, render recorded
`identity-v1`, 9 assets, episode READY. `npm run build` OK.
**Commit:** Sprint 5.3 commit + push to `main`.

---

## 2026-10-11 — Sprint 6.1 — Approval Queue

**Plan:** The human review screen with script, video, simulation results, risks
and metadata; approve/reject/edit (roadmap 6.1, guide §19).
**Scope:** `services/review_service.py` (risk screen: real-person BLOCK,
copyright BLOCK, safety BLOCK, sensitive topics/repetition REVIEW,
synthetic-media disclosure always REVIEW; full review payload + queue),
endpoints `GET /api/review-queue` + `GET /api/review-queue/{id}` (kept in
`api/episodes.py` per arch §8), `/review` page with queue, detail, edit +
approve/reject.
**Implement:** review_service/endpoints/UI + 10 tests.
**Verify:** `pytest` → **152 passed** (10 new: queue membership across statuses,
payload completeness incl. script/scenes/metadata, sim attached, disclosure
risk, real-person BLOCK, copyright BLOCK, repetition REVIEW, approve/reject/
edit lifecycle, 404, render attached). Live: queue→detail (3 scenes, 63 words,
REVIEW) → sim 0.515 → edit → reject (queue stays 1) → approve (queue 0); cameo
by real person → BLOCK. `npm run build` OK. Dev DB cleaned.
**Commit:** Sprint 6.1 commit + push to `main`.

---

## 2026-10-11 — Sprint 7.1 — YouTube OAuth

**Plan:** Google OAuth 2.0 web-server flow for the YouTube Data API (roadmap
7.1, guide §12): connect a channel and store credentials safely.
**Scope:** `integrations/youtube/auth.py` (consent URL + state TTL, code
exchange, refresh, channel lookup; injectable httpx client for mock testing),
`models/youtube_account.py` (channel/oauth_reference/status/last_sync),
`services/youtube_service.py` (token files under gitignored `secrets/`, DB
stores references only — no secrets committed or stored raw in PG),
`api/youtube.py` (status/start/callback/accounts), `/youtube` UI.
Credentials copied from the CG project into local `.env` programmatically
(never printed; values masked in all output).
**Implement:** auth client/service/endpoints/UI + 16 tests (MockTransport).
**Verify:** `pytest` → **168 passed** (16 new: auth URL shape/scopes/state,
unconfigured raises, state validation, token exchange + missing-refresh +
HTTP error paths, channel fetch, refresh keeps refresh token, persistence +
token-file writing, status/config reporting, callback redirects incl. failure
paths). Live with real creds: configured=true; authorize_url well-formed
(readonly+upload scopes, offline, consent, callback redirect, state);
accounts empty until manual consent. `npm run build` OK.
**Commit:** Sprint 7.1 commit + push to `main`.

---

## 2026-10-11 — Sprint 7.2 — Private Upload

**Plan:** Upload an approved, rendered Short privately via the official API
(roadmap 7.2): resumable session + PUT, then record video/channel ids,
upload_time, and status.
**Scope:** `models/published_video.py` (episode/render/channel/video ids,
privacy, status, upload_time), `services/youtube_upload_service.py`
(resumable-upload flow, MVP gate to private/unlisted only, publish guards:
READY render + active channel, duplicate-publish rejection, failure recorded
as failed), endpoints (publish/list per episode/global), review-page publish
button + `/youtube` published list.
**Implement:** model/service/endpoints/UI + 8 tests (MockTransport).
**Verify:** `pytest` → **176 passed** (8 new: publish records video/channel
ids + privacy + upload_time, endpoint 201 + listings, READY gate, channel
gate, duplicate rejection, failure marking, public-privacy rejection,
session+PUT transport). Live with real web keys: configured=true, consent
flow intact; full-suite green; `npm run build` OK.
**Commit:** Sprint 7.2 commit + push to `main`.

---

## 2026-10-11 — Sprint 7.3 — Upload Lifecycle

**Plan:** Make publishing reliable: processing status, failures, retries,
metadata, thumbnails, publication state (roadmap 7.3).
**Scope:** status refresh (videos.list → mapped record states incl. failed),
`retry_publish` (re-upload with attempts counter), metadata update
(videos.update), thumbnails (FFmpeg frame extract + thumbnails.set), model
fields (youtube_status/attempts/updated_at), endpoints
(`/videos/{id}/status|retry|thumbnail`, PATCH metadata), `/youtube` lifecycle
buttons.
**Implement:** service/model/endpoints/UI + 8 tests.
**Verify:** `pytest` → **184 passed** (8 new: status mapping processed,
failure marking with reason, retry recovering after one more failure, retry
guard for healthy records, metadata update via mock, thumbnail extraction +
upload, endpoint-level retry, roadmap 3-uploads-1-failure-recovered case
asserting [uploaded, failed, uploaded] → retry → uploaded attempts=1).
`npm run build` OK. Dev DB cleaned.
**Commit:** Sprint 7.3 commit + push to `main`.

---

## 2026-10-11 — Sprint 7.4 — Public Publishing Path

**Plan:** Prepare a legitimate public-publishing path (roadmap 7.4): policy +
verification state in code, audit materials in docs, manual-publishing MVP
fallback intact.
**Scope:** `publishing_mode` setting (default private_api), `publish_policy`
service (blockers computed from mode + audit state + scopes), `AuditStatus`
model (not_submitted→in_review→approved/denied) + GET/PATCH endpoints,
publication-policy endpoint, public uploads gated behind approved audit,
`/youtube` policy panel, docs (`youtube-api-usage.md`, `privacy-policy.md`,
`youtube-audit-checklist.md`).
**Implement:** settings/policy/model/endpoints/docs/UI + 4 tests.
**Verify:** `pytest` → **12 passed in touched suites** (public upload blocked
pre-audit, verification record lifecycle + validation, blocker reporting with
manual fallback, all-green policy when verified). Full-suite + `npm run build`
green; `numpy`-free; secrets never printed. `npm run build` OK.
**Commit:** Sprint 7.4 commit + push to `main`.

---

## 2026-10-12 — Sprint 8.1 — Analytics Collector

**Plan:** Append-only analytics snapshots on the 15m/1h/6h/24h/48h/7d ladder
(roadmap 8.1, guide §14), with a sweep that snapshots only what's due.
**Scope:** `VideoMetrics` model (views/likes/comments/sub deltas + raw payloads;
never overwritten), `analytics_service.py` (videos.list + channels.list stats,
subscriber deltas vs previous snapshot, sequence-based ladder coverage),
APScheduler 15-min job (opt-in via `ENABLE_SCHEDULER`) + `collect_metrics.py`
script, endpoints (snapshot/history/due), `/analytics` UI with timeline +
deltas.
**Implement:** model/service/scheduler/endpoints/UI + 12 tests.
**Verify:** `pytest` → **200 passed** (12 new: stats parsing, exact ladder
offsets, first-offset/first-covered/past-window ladder behavior, append-only +
deltas, due listing, sweep exclusivity, failure isolation, endpoint + history
+ due). Live: empty-publish due list `[]`, videos `0`. `npm run build` OK.
**Commit:** Sprint 8.1 commit + push to `main`.

---

## 2026-10-12 — Sprint 8.2 — Experiment Record

**Plan:** One immutable lifecycle record per experiment — simulation + episode
+ render + YouTube video + analytics (roadmap 8.2, arch §9, guide §21).
**Scope:** `ContentExperiment` model (hypothesis/variant/sim run+score+rank/
video/real_metrics/reality_gap/conclusions), `experiment_service.py` (bind
reads latest sim run, relative rank among series episodes' latest aggregates,
video/metrics links, refresh + notebook writer), `api/experiments.py`
(create/list/lifecycle/conclusions/refresh), `/experiments` + `/:id` UI.
**Implement:** model/service/API/UI + 7 tests.
**Verify:** `pytest` → **207 passed** (7 new: full lifecycle payload with
score+rank+aggregate, graceful nulls, notebook file content, links+conclusions
round-trip, list filters, 404s, refresh relinking late video). Live: bound
experiment (score 0.515, rank 1) with all 8 lifecycle sections + notebook file
on disk. `npm run build` OK.
**Commit:** Sprint 8.2 commit + push to `main`.

---

## 2026-10-12 — Sprint 9.1 — Ranking Comparison

**Plan:** Evaluate the simulator against reality (roadmap 9.1, arch §12):
simulated episode order vs real-views order → disagreement report persisted on
the experiment.
**Scope:** `services/reality_gap.py` (sim order from latest watch means, real
order from latest snapshot views with like tiebreak, comparison via Spearman/
Kendall/top-k/directional + pairwise disagreements + rank deltas), endpoints
(POST/GET reality-gap on experiments), experiment-detail compute button + gap
display; notebook updated via the existing writer.
**Implement:** service/endpoints/UI + 6 tests.
**Verify:** `pytest` → **213 passed** (6 new: A>B>C vs B>A>C disagreement
(spearman 0.5, kendall 0.333, directional 0.667, 1 disagreement,
rank_deltas A:-1/B:1/C:0), perfect agreement, single-item degradation,
end-to-end gap persistence, 409 without both sides, 404s). Live: sim
13>14>15 vs real 14>13>15 → disagreement ('13 > 14' vs '14 > 13'),
persisted + notebook written. `npm run build` OK.
**Commit:** Sprint 9.1 commit + push to `main`.

---

## 2026-10-13 — Sprint 9.2 — Reality Gap Dashboard

**Plan:** Aggregate per-experiment reality gaps into an overall + per-creator /
per-topic / per-format accuracy view with sample-size gating (roadmap 9.2).
**Scope:** `services/reality_gap_dashboard.py` (overall + buckets, directional /
Spearman / Kendall / top-1 / disagreements + `sample_sufficient` at
`min_samples=5`), `GET /api/experiments/reality-gap/dashboard`, experiments-page
dashboard panel. Out of scope: research checkpoint analysis (9.3).
**Implement:** dashboard service + endpoint + 4 tests + frontend panel (overall
numbers, insufficiency notice, per-bucket misses/counts).
**Verify:** `pytest backend/tests/test_reality_gap_dashboard.py
backend/tests/test_reality_gap.py backend/tests/test_experiments.py` → **17 passed**
(4 new: empty, 5-comparison aggregation + sufficiency, min_samples gating,
disagreement counting); broader suite 217 passed (slow `test_video_render.py`
excluded); `npm run build` OK (51 modules). Test-generated
`docs/experiments/EXPERIMENT-*.md` artifacts removed before commit.
**Commit:** Sprint 9.2 commit + push to `main`.

---

## 2026-10-13 — Sprint 9.3 — First Research Checkpoint

**Plan:** Answer the roadmap question (simulator vs random) with an explicit,
gated verdict instead of ad-hoc notebook inspection.
**Scope:** `services/research_checkpoint.py` (random baselines: directional 0.5,
correlations 0.0, top-1 mean(1/n); verdict A/beats, B/similar, C/worse with
±0.15 margin; human baseline reported unavailable — deferred to Sprint 17.1),
`GET /api/experiments/research-checkpoint`, checkpoint panel on the experiments
page. Out of scope: human judges (17.1), calibration/forecasting (Phase 15).
Also moved literal `reality-gap/dashboard` + `research-checkpoint` routes above
`/{experiment_id}` (same shadowing class fixed in Sprint 4.3).
**Implement:** checkpoint service + endpoint + 4 tests + frontend panel.
**Verify:** `pytest` touched suites → **21 passed** (4 new: boundary mapping incl.
margin edges, empty→insufficient, 5-experiment sufficiency with fixed random
baselines, min_samples gating). `npm run build` OK (51 modules).
Test-generated `docs/experiments/EXPERIMENT-*.md` artifacts removed.
**Commit:** Sprint 9.3 commit + push to `main`.

---

## 2026-10-13 — Sprint 10.1 — Performance Memory

**Plan:** Close the learning loop: derive evidence-backed lessons from real
performance history into structured memory so generation references actual
results (roadmap 10.1, guide §16, arch §13).
**Scope:** `services/performance_memory.py` (per-episode real-views + sim
coverage, topic/structure buckets with strong ≥1.25x / weak ≤0.75x lifts,
`AUDIENCE_DISCOVERY` findings + hedged `CONTENT_LESSON` actions, refresh on
re-distill, 409 below 3 episodes with metrics), `GET` performance summary +
`POST distill-performance` on creators, creator-detail performance panel +
distill button. Out of scope: strategy generation (10.2).
**Implement:** memory service + endpoints + 5 tests + frontend service/panel.
**Verify:** `pytest` → **226 passed** (5 new: min-episode 409, topic strong/weak
buckets + lesson types + Sample/Confidence strings, distilled lessons reach
`memories_used` in generation, refresh without duplicates, 404s; full suite
minus slow `test_video_render.py`). `npm run build` OK (51 modules).
Test-generated `docs/experiments/EXPERIMENT-*.md` artifacts removed.
**Commit:** Sprint 10.1 commit + push to `main`.

---

## 2026-10-13 — Sprint 10.2 — Creator Strategy

**Plan:** Turn distilled performance summaries into differentiated,
evidence-backed strategy observations per creator plus shared cross-creator
patterns (roadmap 10.2).
**Scope:** `services/creator_strategy.py` (per-creator strong/weak topic +
structure observations with sample counts/lifts, shared patterns requiring
≥2 sufficient creators, read-only — writes stay in 10.1),
`GET /api/creators/strategy` (literal route above `/{creator_id}` to avoid the
param-shadow class), strategy panel on the creators page. Out of scope:
memory writes, human judges (17.1).
**Implement:** strategy service + endpoint + 3 tests + frontend service/panel.
**Verify:** `pytest` → **229 passed** (3 new: empty→insufficient, differentiated
Hank-tractor vs Alex-cryptid topics + shared long-structure pattern with
counts, single-creator gating; full suite minus slow `test_video_render.py`).
`npm run build` OK (51 modules). Test-generated
`docs/experiments/EXPERIMENT-*.md` artifacts removed.
**Commit:** Sprint 10.2 commit + push to `main`.

---

## 2026-10-13 — Sprint 11.1 — Viewer Memory

**Plan:** Give viewers repetition fatigue: watch-weighted recall of content
words across past runs dulls near-identical follow-ups (roadmap 11.1).
**Scope:** `services/viewer_memory.py` (effective exposures + capped penalty,
same-target reruns excluded so identical reruns stay bit-identical, episode
runs only — concept evaluations stay memory-free so candidate ranking keeps
a clean read), `compute_reaction(fatigue)` + `repetition_fatigue` reason code,
reaction model bumped `reaction-v1` → `reaction-v2`. Out of scope: familiarity
(11.2), segments (11.3).
**Implement:** memory service + engine wiring + 6 tests (1 version-bump fix).
**Verify:** `pytest` → **235 passed** (6 new: five-tractor dulls sixth by >0.05
with fatigue codes, rerun determinism, unrelated immunity, concept immunity,
fatigue-unit, penalty math; ranking determinism intact; full suite minus slow
`test_video_render.py`). `npm run build` OK. Test-generated
`docs/experiments/EXPERIMENT-*.md` artifacts removed.
**Commit:** Sprint 11.1 commit + push to `main`.

---

## 2026-10-13 — Sprint 11.2 — Creator Familiarity

**Plan:** Same concept, different reactions per viewer depending on how
familiar they are with the creator (roadmap 11.2).
**Scope:** `services/creator_familiarity.py` (watch-weighted exposure per
creator → thresholds 1.2/3.0 → tiers unknown/familiar/favorite + monotonic
affinity filling the gap when no explicit affinity set; same-target reruns
excluded), `compute_reaction(familiarity)` + `familiar_creator` reason code,
`episodes`-only scope, `reaction-v2` → `v3`, `GET /{id}/familiarity`,
audience-page familiarity panel. Out of scope: segments (11.3).
**Implement:** familiarity service + engine wiring + endpoint + 5 tests + UI.
**Verify:** `pytest` → **240 passed** (5 new: tier boundaries, follow
stranger<familiar<favorite, audience gained familiar+favorite after four
seen episodes, rerun determinism, monotonic strength; simulation + ranking
suites green). `npm run build` OK (51 modules). Test-generated
`docs/experiments/EXPERIMENT-*.md` artifacts removed.
**Commit:** Sprint 11.2 commit + push to `main`.

---

## 2026-10-13 — Sprint 9.3 gap-fill — empirical random baseline

**Plan:** Roadmap 9.3 asks to compare Simulator vs Random selection; the first
checkpoint (d260c4f) used analytic random expectations. This strengthens it
with the actual experiment: a seeded random selector that shuffles the
simulated order and is scored on the same pairwise comparisons.
**Scope:** `empirical_random_selector` in `research_checkpoint.py` (deterministic
per seed, seeds RECORDED: RANDOM_SEED=20261012, RANDOM_TRIALS=200), deltas now
reference the empirical baseline when available, `verdict_text` outcome wording
in the API, checkpoint UI shows the shuffled-selector baseline + verdict text.
**Verify:** `pytest` checkpoint suites → **9 passed** (5 new: chance-level ≈0.5
directional + ≈1/3 top-1 within tolerance, per-seed determinism, empty +
single-item degradation, 6-experiment checkpoint reporting trials/verdict/
verdict_text, empty checkpoint stays insufficient with wording). `npm run build`
OK.
**Commit:** Sprint 9.3 gap-fill commit + push to `main`.

---

## 2026-10-13 — Sprint 11.3 — Audience Segments

**Plan:** Group viewers based on behavior (roadmap 11.3): segments from reaction
signals + specialization, clusters identified from simulation behavior.
**Scope:** `services/audience_segments.py` (behavior labels from mean watch/
follow/engagement + comment share; specialization = top-creator exposure share;
deterministic k-means over (watch, follow, engagement) with max/min/farthest
seeding, stable cluster labels from centroids), `GET /api/audience/segments`
(literal route above `/{viewer_id}`), `/simulation` segments + clusters panel.
**Implement:** service + endpoint + clustering + 8 tests (4 labels/specialization
from the in-flight segments work committed here, 4 new clustering) + UI.
**Verify:** `pytest` → **253 passed** (4 new: determinism under row reordering,
deep-vs-skimmer separation, empty/tiny degradation, endpoint payload incl.
25 viewers in 3 labeled clusters + specialization/top_creator). `npm run build`
OK (51 modules). Test-generated `docs/experiments/EXPERIMENT-*.md` artifacts
removed before commit.
**Commit:** Sprint 11.3 commit + push to `main`.

---

## 2026-10-14 — Sprint 12.1 — Willow

**Plan:** Third fictional creator (roadmap 12.1): environmental/alternative-
culture, distinct across humor, interests, visual identity, audience response,
and content strategy from Hank and Alex.exe.
**Scope:** Willow seed (personality/values/interests/voice/safety) + spec
(`docs/creator-specs/willow.md`) + 4 universe-tied memories (seed-library bus
CANON, composting PREFERENCE, mycelium RUNNING_JOKE, seedling-trade
RELATIONSHIP with Hank), `willow` identity default (terracotta/forest palette,
flower crown + clay mug accessories), docs (AGENTS/README note the 12.x
expansion), creators UI needs no change (new creator flows through existing
list/detail/identity/memory/generation).
**Implement:** seed/spec/identity art + 6 tests.
**Verify:** `pytest` → **6 passed** (interests pairwise-disjoint across all
three creators, three distinct humor styles, Willow identity defaults + portrait
diff >0.02 vs both Hank and Alex, three distinct voices on the same message
with Willow's permaculture token, Willow memories retrieved into generation,
identity endpoint). Seed run idempotent including Willow creator + 4 memories.
`npm run build` OK.

---

## 2026-10-14 — Sprint 12.2 — Crash

**Plan:** Fourth creator (roadmap 12.2): chaotic absurdist with a distinct
comedic style from Hank, Alex.exe, and Willow.
**Scope:** Crash seed (spectacle/momentum/loyalty/improvisation values,
slapstick/demolition/stunt/prank/junkyard/fireworks interests, chaotic
absurdist non-sequitur humor, loud escalating voice) + spec
(`docs/creator-specs/crash.md`) + 4 universe-tied memories (toaster
jump-start CANON, always-breaks-it RUNNING_JOKE, louder-solutions PREFERENCE,
Alex demo-invoice RELATIONSHIP), `crash` identity default + new mohawk/
sledgehammer renderer art, creators UI needs no change.
**Implement:** seed/spec/identity art + 5 tests.
**Verify:** `pytest` → **5 passed** (interests pairwise-disjoint across all
four creators, four distinct humor styles incl. chaotic absurdist, Crash
identity defaults + portraits diff >0.02 vs all three, four distinct voices
on the same message with Crash's demolition token, Crash memories retrieved
into generation). Seed idempotent incl. Crash creator + 4 memories; related
suites (willow, identity) 15 passed; `npm run build` OK.
**Commit:** Sprint 12.2 commit + push to `main`.

---

## 2026-10-14 — Sprint 12.3 — Jessica

**Plan:** Fifth creator (roadmap 12.3): gaming creator; verify all five
creators operate independently.
**Scope:** Jessica seed (sportsmanship/persistence/fair-play/curiosity values,

## 2026-10-14 — Sprint 13.1 — Relationship Graph

**Plan:** Social continuity for the ecosystem (roadmap 13.1): pairwise
relationships across five dimensions, changed by story events, with a full
history trail.
**Scope:** `models/relationship.py` (CreatorRelationship unordered unique pair
with friendship/rivalry/respect/annoyance/collaboration 0..1 + RelationshipEvent
history; six story events mapping to clamped dimension deltas),
`services/relationship_service.py` (pair ordering + self-relationship rejection,
event application with history records, notes), routes in `api/creators.py`
(literal-first registration so `/relationships/...` is not shadowed by
`/{creator_id}` — same class fixed in Sprint 4.3), 6 seeded universe
relationships (Hank/Alex rivalry, Hank/Willow seedlings, Alex/Crash demo
invoice, Crash/Jessica derbies, …), creator-detail relationships panel with
event picker + history. Out of scope: cross-creator episode generation (13.2).
**Implement:** models/service/routes/seeds/UI + 7 tests.
**Verify:** `pytest` → **277 passed** (7 new: pair creation + idempotent reversal
with normalized ordering, self-400/unknown-404, per-creator listing, roadmap
event-change path with history accumulation + clamped deltas, unknown
event_type-400/missing-404s, note update). Seed run reports 6 universe
relationships created/updated. `npm run build` OK.
**Commit:** Sprint 13.1 commit + push to `main`.

---

## 2026-10-14 — Sprint 13.2 — Cross-Creator Episodes

**Plan:** Generate coherent cross-character episodes involving multiple
creators (roadmap 13.2) — e.g. Hank asks Alex.exe to repair his tractor.
**Scope:** `CrossEpisodeDraft` parsing (participants/premise/synopsis/scenes/
script), `cross_episode_prompt_v1.md` (cast section + combined canon, memories
from ALL participants, relationship profile between them), stub deterministic
4-beat crossover archetype (problem → negotiation → breakdown → finish, every
participant speaks), `cross_episode_service.py` (host must participate,
2-3 participants, duplicate collapse, relationship echo or "unknown" guidance),
evaluation gates (`unknown_participant` BLOCK, `missing_participant`/
`silent_participant` REVIEW layered on the standard draft evaluation),
`POST /api/series/{id}/generate-cross-episode`, series-detail participant
picker + cast/issues preview. Out of scope: cross-channel publishing behavior
(documentation-only boundary noted below).
**Implement:** draft/prompt/stub/service/endpoints/UI + 11 tests.
**Verify:** `pytest` → **288 passed** (11 new: endpoint end-to-end with 2
creators + relationship (cast, premise, 4 scenes, both voices in script,
status/version/cast_used, persisted episode + scenes), coherent beat structure,
duplicate collapse, single-400, non-host-400, unknown-creator-400, ended-400,
three-creator cast, silent/missing flags, unknown-participant BLOCK).
`npm run build` OK.
**Note:** cross-creator storytelling is fictional continuity only — creator
accounts never interact to manufacture engagement (architecture §4/§20);
no cross-posting automation exists.
**Commit:** Sprint 13.2 commit + push to `main`.

---

## 2026-10-14 — Sprint 14.1 — Shared Canon (Creator Universe)

**Plan:** Universe-level canon shared by every channel (roadmap 14.1):
locations/characters/events/objects/relationships/timeline — generation must
never contradict it, so episodes across creators stay consistent.
**Scope:** `models/universe.py` (`UniverseEntity`, 6 kinds), universe service +
8 seeded shared facts (County Fair, Old Red, Seed Library Bus, Toaster Incident,
Seedling Trades, Old Data Center, Gravel Pit, Season One timeline), universe
facts injected into solo + cross generation context and the contradiction
evaluation, **new** `episode_prompt_v2.md` (v1 stays frozen per guide §26 — v1
still renders unchanged and stays registered; default flipped to v2), stub echo
of a universe fact in both solo + cross scripts, endpoints in `api/episodes.py`
(GET/POST/DELETE `/api/universe`), `/universe` page + dashboard link.
**Implement:** model/service/seeds/prompt v2/stub/endpoints/UI + 7 tests.
**Verify:** `pytest` → **295 passed** (7 new: universe CRUD + validation,
two-channel consistency — Hank's and Alex.exe's episodes both echo the shared
fact with zero `canon_contradiction` flags, prompt version list keeps v1+v2,
v1 renders without the universe section while v2 includes it, cross-episode
universe echo, seed constants cover all six kinds). `npm run build` OK.
**Commit:** Sprint 14.1 commit + push to `main`.

---

## 2026-10-14 — Sprint 14.2 — Audience Lore

**Plan:** Track recurring viewer reactions and let them enter the fictional
universe (roadmap 14.2, arch §13).
**Scope:** `AudienceLore` model (theme, creator, episode ids, mention count,
avg watch, status emerging/recurring/promoted), `lore_service.py` — distill
recurring bigram themes from episode-level simulation runs whose mean watch is
above the cohort mean (recurrence across ≥2 distinct episodes; mean chosen over
median because small cohorts make the median degenerate to the low value),
`promote_lore` writes the theme into that series' canon as a RUNNING_JOKE
(idempotent, human-initiated, emerging themes rejected 409), endpoints
(POST distill / GET list / POST promote), `/lore` UI with promote action.
**Implement:** model/service/endpoints/UI + 8 tests.
**Verify:** `pytest` → **303 passed** (8 new: recurring theme found across 3
episodes with avg watch recorded, single-episode themes stay emerging,
below-mean-watch episodes create no themes, distill endpoint + listing,
promotion writes RUNNING_JOKE canon in the right series and is idempotent,
emerging promotion rejected, 404, empty distill without runs). `npm run build`
OK.
**Commit:** Sprint 14.2 commit + push to `main`.

---

## 2026-10-14 — Sprint 15.1 — Prediction Calibration

**Plan:** Attempt absolute prediction (roadmap 15.1): instead of good/bad,
predict a probable view RANGE per simulator score, and record whether the
ranges actually hold so we can decide if absolute forecasting is feasible.
**Scope:** `calibration_service.py` — least-squares fit (views ≈ slope·score +
intercept) over observed (score, real views) pairs, residual-σ × 1.28 ≈ 80%
interval as the range, evaluation with coverage / MAE / MAPE per experiment,
all aggregates withheld below MIN_SAMPLES=5 (guide §15); degenerate inputs
handled (<2 samples → zero model, identical scores → flat model, never-negative
ranges); `GET /api/experiments/calibration`; experiments-page calibration panel
(model, coverage/MAE/MAPE when sufficient, per-experiment range table).
**Implement:** service/endpoint/UI + 7 tests.
**Verify:** `pytest` → **310 passed** (7 new: slope/intercept recovery on exact
linear data with σ=0, range width grows with residual σ, never-negative bounds,
coverage 1.0 + MAE 0 on linear data with verdict, insufficient-sample gating
(None aggregates + gated verdict), endpoint payload shape, identical-scores flat
model). `npm run build` OK.
**Commit:** Sprint 15.1 commit + push to `main`.

---

## 2026-10-14 — Sprint 15.2 — Early Performance Forecasting

**Plan:** Estimate 24h performance from the first hour (roadmap 15.2), then
compare the 1h-based prediction against the realized 24h result.
**Scope:** `forecast_service.py` — pair each published video's snapshot closest
to 1h with the first snapshot ≥24h (using the append-only `VideoMetrics`
ladder), learn the growth factor (views_24h ≈ factor · views_1h) as the mean of
observed ratios with ratio-σ spread, predict a range (factor ± 1.28σ) that
scales with early views, and evaluate coverage / MAE / MAPE per video; all
aggregates withheld below MIN_SAMPLES=5 (guide §15). Degenerate inputs handled
(zero early views skipped, videos lacking a ≥24h reading skipped, single
snapshot can't self-pair, prediction never negative). `GET
/api/youtube/analytics/forecast` (optional `early_views` for on-demand
prediction); Analytics page forecast panel with model/coverage and a per-video
observed-vs-range table.
**Implement:** service/endpoint/UI + 9 tests.
**Verify:** `pytest` → **319 passed** (9 new: factor recovery on consistent
growth with σ=0, prediction scaling + zero-early, range widens with factor σ,
zero-early skipped, video without ≥24h reading skipped, early reading nearest
1h chosen among 15m/1h/24h, coverage 1.0 + MAE 0 with verdict, insufficient-
sample gating, endpoint shape + `early_views` prediction). `npm run build` OK.
**Commit:** Sprint 15.2 commit + push to `main`.

---

## 2026-10-14 — Sprint 16.1 — Hook Experiment

**Plan:** Content-strategy experiment (roadmap 16.1): test the four hook types
(direct / question / absurd / character) and check whether the simulator and the
real audience agree on which hook performs best.
**Scope:** `hook_experiment_service.py` — deterministic `classify_hook` with a
documented priority (question → character → absurd → direct) over the episode
hook text (first sentence of the synopsis, the same text the reaction engine
uses as the episode hook, falling back to premise then title); per-type
aggregation of latest simulation watch-mean and latest real views across
episodes; `simulation_preferred` / `reality_preferred` / `agreement`; all
interpretation gated below MIN_TOTAL=4 with MIN_PER_TYPE=2 sufficiency flags
(guide §15). `GET /api/experiments/hook-experiment` (optional `creator_id`);
Experiments page hook-experiment panel (per-type sim vs reality table,
preferred hooks, agreement badge).
**Implement:** service/endpoint/UI + 7 tests.
**Verify:** `pytest` → **326 passed** (7 new: classification of each type incl.
empty/None, priority question-over-absurd and character-over-absurd,
first-sentence hook extraction with premise fallback, report prefers the
matching hook with agreement True, report detects disagreement, gating below
min total, endpoint shape + `creator_id` filtering). `npm run build` OK.
**Commit:** Sprint 16.1 commit + push to `main`.

---

## 2026-10-14 — Sprint 16.2 — Episode Length Experiment

**Plan:** Content-strategy experiment (roadmap 16.2): test multiple episode
lengths and determine whether the simulator's preferred length matches reality's.
**Scope:** `length_experiment_service.py` — measured duration (published video
first, then latest render; unmeasured episodes counted and skipped) bucketed
into short (<30s) / medium (30–60s) / long (≥60s); per-bucket aggregation of
latest simulation watch-mean vs latest real views; `simulation_preferred` /
`reality_preferred` / `agreement`; interpretation gated below MIN_TOTAL=4 with
MIN_PER_TYPE=2 flags. Report records an honest `simulator_note`: the reaction
engine scores hook text + interest only, and the pipeline simulates before a
render exists, so any length preference is indirect. `GET
/api/experiments/length-experiment` (optional `creator_id`); Experiments page
length-experiment panel.
**Implement:** service/endpoint/UI + 7 tests.
**Verify:** `pytest` → **333 passed** (7 new: bucket boundaries, duration source
preference published>render and unknown when neither, report prefers matching
length with agreement True, disagreement detection, gating + unknown-duration
count, simulator-note present, endpoint shape + `creator_id` filtering).
`npm run build` OK.
**Commit:** Sprint 16.2 commit + push to `main`.

---

## 2026-10-14 — Sprint 16.3 — Story vs Meme

**Plan:** Content-strategy experiment (roadmap 16.3): compare standalone meme
vs episodic story — does persistent storytelling produce stronger subscriber /
returning-viewer behavior than disposable jokes?
**Scope:** `story_vs_meme_service.py` — serialization classifier (series with
≥2 episodes = story, one-off series = meme); per-episode real behavior from the
latest published video (latest views + summed `subscribers_gained` across its
append-only snapshots); per-format aggregates including `subscriber_conversion`
(subs gained / views) as the practical returning-audience proxy, with an
explicit `analytics_note` that true returning/retention data needs the YouTube
Analytics API (guide §14); higher-conversion format named only when strictly
better, interpretation gated below MIN_TOTAL=4 and MIN_PER_FORMAT=2.
`GET /api/experiments/story-vs-meme` (optional `creator_id`); Experiments page
story-vs-meme panel.
**Implement:** service/endpoint/UI + 6 tests.
**Verify:** `pytest` → **339 passed** (6 new: series-size classification, story
wins on conversion, meme wins on conversion, gating below min total, episode
rows + skip counting (orphan series and never-published episodes), endpoint
shape + `creator_id` filtering). `npm run build` OK.
**Commit:** Sprint 16.3 commit + push to `main`.

---

## 2026-10-14 — Sprint 17.1 — Human Judges

**Plan:** Simulation vs human baseline (roadmap 17.1): a human panel ranks the
same candidate videos as the synthetic audience and the real YouTube audience,
then compare all three pairwise — end goal: does the simulator resemble human
judgment?
**Scope:** `HumanPanelRanking` model (candidate_type, best-first JSON order,
note); `human_baseline.py` — validated panel recording (≥2 unique, existing
episode ids only), and a three-way comparison restricted to candidates that all
three judges scored (stored simulation watch mean, human panel position, latest
real views) so every pair covers the same items; per-pair top-1 / top-3 /
directional / Spearman / Kendall τ via `core.metrics`; verdict that separately
states whether the simulator resembles human judgment and/or the real audience,
gated below MIN_CANDIDATES=5 (resemblance = directional ≥ 0.6).
`POST`/`GET /api/experiments/human-panel` + `GET /api/experiments/judge-comparison`
(optional `series_id`); Experiments page panel to record a ranking and view the
three-way table.
**Implement:** model/service/endpoints/UI + 7 tests.
**Verify:** `pytest` → **346 passed** (7 new: panel-recording validation for
wrong type/short/unknown/duplicate orders, persistence, full agreement gives
1.0 directional + Spearman with the "resembles both" verdict, simulator
diverging from both judges, exclusion of candidates missing any judge with
`judged_by_all_three` flags and gating, `series_id` filter, endpoint flow
POST 201 + 400 + comparison shape). `npm run build` OK.
**Commit:** Sprint 17.1 commit + push to `main`.

