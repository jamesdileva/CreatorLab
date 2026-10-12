# YouTube Data API — how CreatorLab uses it (Sprint 7.4 audit materials)

Creator Reality Lab uses only the official YouTube Data API
(architecture §5.8, §17). No scraping, no account automation, no emulators.

## OAuth scopes requested

| Scope | Used for |
| --- | --- |
| `youtube.readonly` | channel identity, video processing state |
| `youtube.upload` | private/unlisted Short uploads with explicit human approval |

`youtube.upload` is the minimum for uploads; no broader access is requested.

## Endpoints called

| Call | Purpose |
| --- | --- |
| `POST /upload/youtube/v3/videos?uploadType=resumable` | open an upload session |
| `PUT <session>` | upload one MP4 |
| `GET /youtube/v3/videos?part=status` | processing/publication state |
| `PUT /youtube/v3/videos?part=snippet` | metadata corrections (title/description) |
| `POST /upload/youtube/v3/thumbnails/set` | custom thumbnail per video |
| `GET /youtube/v3/channels?mine=true` | channel identity after OAuth |

## Quotas and behavior

- One resumable upload per published episode; uploads happen only when a human
  approves and presses publish — no background spam.
- Failed uploads are retried by a human decision, never in a tight loop.
- Analytics collection (Sprint 8.1) will use the YouTube Analytics API with the
  same least-privilege approach.

## Data handling

- OAuth refresh tokens live in git-ignored `secrets/` files; the database
  stores only a reference (guide §12).
- No subscriber/comment/channel data beyond the authorized channel and our own
  videos is stored.
