# Reddit feasibility — Sprint 19.1

Goal (roadmap §19.1): determine whether the current Reddit API and Responsible
Builder requirements permit the intended experiment (§19.2 — a fictional creator
holding conversations in communities). End goal: **do not build a Reddit
automation layer until the intended use is clearly permitted.**

## Determination: NOT PERMITTED YET — do not build

The intended experiment — a creator account engaging communities in open
"human conversation" — is **not clearly permitted** as specified. Reddit now
requires **explicit approval for *any* API access**, requires non-human accounts
to be **labeled as apps** (no masking automation), and prohibits automated
posting/comments that constitute spam. Per the §19.1 end goal, **no Reddit
automation layer is built.**

A *narrow, disclosed-bot* research path may become permissible **after** Reddit
approval **and** explicit community/moderator consent — but it would look very
different from an open conversational creator (see "Only permitted narrow path").

## What Reddit currently requires

- **Approval before access.** Since the Nov 2025 change and the Responsible
  Builder Policy (updated Oct 2026), you must request access and get explicit
  approval for new OAuth tokens. Unapproved/unidentified traffic is throttled or
  blocked.
- **Transparency / no masking.** You must not misrepresent or mask how/why you
  access Reddit; no registering multiple accounts or apps for the same use case.
  Non-human accounts must carry an **App label** (register the app + developer
  profile). You must not circumvent Reddit's labeling.
- **Single-purpose app accounts.** App accounts are for app functions only — no
  mixed human/bot use.
- **No spam.** No automated spam via posts, comments, or DMs; no posting
  substantially identical content across subreddits.
- **No feature manipulation.** No vote/karma manipulation; no circumventing
  blocks/bans.
- **No AI training on Reddit data.** Using Reddit data to train any LLM/AI model
  requires explicit permission.
- **Privacy.** No inferring sensitive user characteristics; delete user content
  when it is deleted (≈48h recommended); no retaining deleted/identifying data.
- **Rate limits.** Free access: **100 QPM** per OAuth client id; chat ≈2,000
  msgs/day/recipient and 3,000/day total; bot chat-room joins ≈300/day.
- **Devvit preferred.** Reddit directs app developers to build on its Developer
  Platform (Devvit); other use cases need a ticket/approval.
- **Commercial use** requires written approval + a contract.

## Conflict analysis vs. CreatorLab hard boundaries (architecture §4/§20)

| Intended behavior | Reddit | CreatorLab boundary | Verdict |
| --- | --- | --- | --- |
| Fictional creator posts/comments as if human | App label required; no masking | no platform-evasion; no deceptive automation | **Conflict** |
| Automated conversational posting into communities | spam rules; mod/community consent | no artificial/unapproved engagement | **Conflict unless disclosed + consented** |
| Open-ended "human conversation" loop | app accounts single-purpose | — | Risk of spam finding |
| Reading public threads to build a sim | no AI training without permission | no scraping pipelines | **Conflict** |

The core blocker is structural, not just technical: Reddit mandates that
automation be **visible and approved**, whereas the experiment's premise is a
creator that converses like a participant. Making it compliant removes most of
what the experiment intends to measure.

## Only permitted narrow path (research, if pursued)

If Phase 19 is revisited, the only defensible shape is:

1. Get **written Reddit approval** for the specific use case (likely via the
   devvit/ticket path), with a registered app + **App label**.
2. Operate a **single, clearly disclosed non-human account**; never mask it.
3. Obtain **explicit moderator + community consent** before posting in any
   subreddit; post only there.
4. **No vote/karma interaction, no DM automation, no cross-posting spam.**
5. **Do not train** any model on Reddit data; store only what the approved use
   case needs and honor deletion (≈48h).
6. Treat the environment as **read-mostly / observation** unless a community
   explicitly invites participation.

## Blockers before ANY engineering (§19.1 gate)

- [ ] Written Reddit **API access approval** for this exact use case.
- [ ] Registered app + developer profile → **App label**.
- [ ] Named subreddit(s) whose **moderators consent** to the experiment.
- [ ] Use case confirmed **non-commercial** (or a commercial contract in place).
- [ ] Confirmation that no Reddit data will be used for model training.
- [ ] Privacy/deletion handling documented.

Until every box is checked, **no Reddit integration code is written** (roadmap
§19.1 end goal). Sprint 19.2 (conversational creator experiment) is gated behind
this.

## Recommended path

**Defer Phase 19.** The compliant version does not measure what §19.2 wants to
measure. Prefer building the **Phase 20 emulator laboratory** (our own controlled
social environment) for conversational experiments, where consent, labeling, and
scope are ours to define legitimately.

## Sources (checked 2026-10)

- Reddit Responsible Builder Policy (updated 2026-10-05).
- Reddit Data API Terms (revised 2026-07-20) + Developer Terms.
- Reddit Data API Wiki (rules, User-Agent, rate limits, deletion).
- Reddit app labeling docs ("Apps on Reddit"); Devvit guidelines (LLM use).
