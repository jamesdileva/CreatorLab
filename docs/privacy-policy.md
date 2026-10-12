# CreatorLab — Privacy Policy (draft for audit submission, Sprint 7.4)

> This is the repository copy staged for the Google audit submission materials.
> Publish the final version at the application's public URL before submitting.

## What we collect

- Google account identity and YouTube channel info needed for OAuth
  (channel id, channel title).
- OAuth tokens required to upload the user's own videos and read their state.

## What we do NOT collect

- We do not read other creators' private data.
- We do not store subscriber lists, watch history, or comment content.
- We do not sell, share, or analyze Google user data beyond the creator's own
  channel operations.

## Storage and security

- Refresh tokens are stored server-side outside version control and never
  committed; the database holds only a non-sensitive file reference.
- Secrets are rotated by re-running the OAuth consent flow.

## User control

- Disconnecting the YouTube account (delete the account record and its token
  file) stops all API access immediately.
- Every upload requires an explicit human publish action; nothing publishes
  autonomously.

## Contact

Add the maintainer contact before submission.
