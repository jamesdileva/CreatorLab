# YouTube audit submission — materials checklist (Sprint 7.4)

Goal: a legitimate path to public automated publishing (roadmap §7.4). Until
the audit is approved, MVP publishing stays private + human-approved.

## Official-API conformance

- [x] Only the official YouTube Data API is used — no scraping, browser
      automation, or emulator tooling (`docs/youtube-api-usage.md`).
- [x] Least-privilege scopes: `youtube.readonly` + `youtube.upload`.
- [x] Human approval required before every publish (Sprint 5.3/6.1 gates,
      `publish_episode` guard).
- [x] No artificial engagement anywhere (architecture §4/§20; nothing in the
      codebase manufactures likes/views/comments/subscribers).

## Submission materials

- [x] API usage documentation: `docs/youtube-api-usage.md`.
- [x] Privacy policy draft: `docs/privacy-policy.md` (publish at public URL).
- [ ] OAuth consent screen: branding, authorized domains, test users.
- [ ] Brand verification + domain verification (Search Console).
- [ ] Privacy policy hosted at the public application URL.
- [ ] Homepage/terms link at the public application URL.

## Ready-state tracked in the app

- `GET /api/youtube/publication-policy` reports blockers: publishing mode,
  audit status, connected channel + scopes.
- `GET/PATCH /api/youtube/verification` tracks the audit state machine
  (not_submitted → in_review → approved/denied).

## MVP fallback (until approved)

Manual publishing: human downloads the private render from `/media` and
uploads it to YouTube by hand. Implemented by keeping `publishing_mode`
`private_api` and all public automation gated behind policy checks
(rejected with the blockers list).
