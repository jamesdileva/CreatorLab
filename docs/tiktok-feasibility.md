# TikTok feasibility — Sprint 18.1

Goal (roadmap §18.1): research current API access and publishing requirements and
determine whether CreatorLab has a **legitimate publishing path** to TikTok.
End goal: **no engineering begins until platform access is confirmed.** This
document is that determination.

## Determination: GO — with a mandatory human-publish path

A legitimate, policy-compliant publishing path exists via TikTok's official
**Content Posting API**. The MVP path is **inbox draft (`MEDIA_UPLOAD`) + human
publish from the TikTok app**, which needs no audit, has no visibility
restriction, and matches our hard boundary that every publish requires explicit
human approval.

Fully automated **Direct Post** is available in principle but requires a TikTok
**audit**; until it passes, all API posts are forced private (`SELF_ONLY`) and
useless for a real-audience reality-gap experiment.

## Publishing modes (official API only)

| Mode | Endpoint family | Scope | Public? | Audit needed? |
| --- | --- | --- | --- | --- |
| Inbox draft (`MEDIA_UPLOAD`) | `/v2/post/publish/inbox/video/init/` | `video.upload` | Yes — human publishes in app | No |
| Direct Post (`DIRECT_POST`) | `/v2/post/publish/video/init/` | `video.publish` | Only after audit; `SELF_ONLY` before | Yes |

- `PULL_FROM_URL` requires the media host domain to be **verified** in the
  developer portal; `FILE_UPLOAD` uploads bytes directly.
- **Posting cap:** ~15 posts / 24h per creator account, shared across all
  clients; plus a per-client active-creator cap.
- **Unaudited Direct Post restrictions:** up to **5 creators / 24h**, and every
  post is forced to `SELF_ONLY` (`unaudited_client_can_only_post_to_private_accounts`).

## AIGC disclosure — required, not optional here

CreatorLab's creators are synthetic personas and the video is AI-generated, so
content is **AIGC**. TikTok requires labeling realistic AI-generated content.

- Direct Post: set `is_aigc: true` in `post_info` → "Creator labeled as
  AI-generated" tag.
- Inbox draft: the human toggles the AI-generated setting before publishing.
- Labeling must not be removed, and is independent of the human-approval gate.

## Hard-boundary alignment (architecture §4/§20)

- [x] Human approval before every publish — TikTok's Content Sharing guidelines
      in fact **require** explicit per-post consent and **forbid** auto-posting
      on upload or on a schedule the creator did not set per post. This matches
      our boundary exactly (no fully autonomous publishing).
- [x] Official Content Posting API only — no scraping, browser automation, or
      re-upload pipelines.
- [x] Fictional personas only — no impersonation of real people; AIGC labeled.
- [x] No artificial engagement; no mass account creation.
- [x] No brand/logo/watermark injection into posted media (guideline violation).
- [x] Consent + preview + no-default privacy dropdown + interaction toggles
      (all required by the Direct Post UX guidelines).

## Blockers to clear before ANY engineering (roadmap §18.1 gate)

- [ ] TikTok for Developers account + registered **production** app.
- [ ] Add the **Content Posting API** product; enable the intended mode.
      (`video.upload` for inbox; `video.publish` only if pursuing the audit.)
- [ ] A TikTok creator account per persona we intend to post as.
- [ ] Live, HTTPS, public **Terms of Service** and **Privacy Policy** URLs
      matching the app brand (repo drafts: `docs/privacy-policy.md`).
- [ ] Redirect URI / website / app name all reference the same brand.
- [ ] If `PULL_FROM_URL`: verify the media hosting domain in the portal.
- [ ] Record a demo video (Direct Post mode) for the audit — only if auditing.
- [ ] Confirm `client_secret` stays server-side (never in `frontend/` bundles).

Until every box for the chosen mode is checked, **no TikTok integration code is
written** (roadmap §18.1 end goal). Sprint 18.2 (cross-platform experiment) is
gated behind this.

## Recommended path

1. **18.2 MVP:** inbox draft (`MEDIA_UPLOAD`, `video.upload`) + human publishes.
   Reuses the existing episode→render→approval pipeline; adds a draft-to-inbox
   exporter and a human publish step. No audit, public results, boundary-safe.
2. **Future:** pursue the Direct Post audit for automated public posting once the
   MVP experiment justifies it.

## Sources (checked 2026-10)

- TikTok Content Posting API — Get Started / Direct Post reference.
- TikTok Content Sharing Guidelines (unaudited restrictions, UX, consent).
- TikTok AIGC policy (labeling requirement; `is_aigc`).
- Third-party Direct Post audit guide (audit prerequisites, common rejections).
