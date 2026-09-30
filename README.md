# Reels agent

Fully automatic daily Reel posting + comment auto-reply for a personal
Instagram account, using AI-generated video.

## How it fits together

```
script_bank.py        -> today's fact-checked script (narration + image prompt per beat)
image_gen.py           -> free stills via Pollinations.ai
voice_gen.py            -> free narration via edge-tts
video_assemble.py        -> ffmpeg: Ken Burns zoom + captions + concat -> final .mp4
safety_gate.py           -> automated pre-publish check (stands in for human review)
instagram_client.py      -> publishes to Instagram, manages comments
pipeline.py                -> runs the above end to end, once a day
comment_bot.py +
run_comment_bot.py         -> replies to new comments, on its own schedule
```

## Setup

1. **Instagram account**: Settings → Account type and tools → Switch to
   professional account → Creator.
2. **Meta Developer App**: developers.facebook.com → My Apps → Create App
   (type: Business) → add the **Instagram** product, configured for
   **Instagram API with Instagram Login** (no Facebook Page required).
3. Request permissions: `instagram_business_basic`,
   `instagram_business_content_publish`, `instagram_business_manage_comments`.
4. Run the Business Login for Instagram OAuth flow once to get your
   `IG_USER_ID` and a long-lived access token. **This token expires
   (~60 days)** — you'll need a refresh step before it does, or the
   pipeline will start failing silently. Not yet implemented here.
5. Copy `.env.example` to `.env` and fill in the values.
6. `pip install -r requirements.txt`

## What's real vs. stubbed

- **Instagram publishing and comment replies**: written to the current
  documented API, but untested against a live account (no network path to
  Meta's API from where this was built) — sanity-check against
  developers.facebook.com/docs/instagram-platform before trusting it fully.
- **Script content**: there's no free real-time "what's trending on
  Instagram" API, so `script_bank.py` ships with three fact-checked scripts
  (Antikythera mechanism, Tesla's Wardenclyffe Tower, the CMB discovery),
  each already broken into narration + image-prompt beats. Ask for a refill
  in chat once you're through these — new batches get the same fact-check
  pass these did.
- **Images and narration**: `image_gen.py` (Pollinations.ai) and
  `voice_gen.py` (edge-tts) are both real, working, free, keyless APIs —
  not stubs. Pollinations' anonymous tier is rate-limited and not as
  consistent as a paid service; if a fetch fails, it retries once before
  giving up.
- **Video assembly**: `video_assemble.py`'s ffmpeg pipeline (Ken Burns
  zoom, caption burn-in, per-beat audio mux, concat) was built and verified
  against placeholder inputs — resolution, duration, and caption rendering
  all confirmed working. The real images/audio that feed it are a separate,
  untested-live network dependency (see above).
- **Public hosting for rendered clips**: `pipeline.py`'s
  `upload_to_public_host()` is an unimplemented stub — Instagram's publish
  API needs the video at a public URL, so you need somewhere to put
  rendered files (S3, Cloudflare R2, etc.) before publish.

## Running it — GitHub Actions (no server, no phone left running)

The two workflow files in `.github/workflows/` run this on GitHub's own
servers on a schedule. Nothing has to stay open on your end — not a VPS,
not your phone. Entire setup can be done from a phone browser:

1. Create a repo on github.com (Safari/Chrome, no app needed) — **public**
   is the easy default, since Actions minutes are unlimited and free on
   public repos. Private repos get a monthly free-minutes allowance before
   metered billing kicks in, which the comment-bot's 30-min polling can
   realistically bump into. Nothing secret lives in the code either way —
   API keys go in encrypted repo Secrets, never in a committed file — so
   public is fine unless you'd rather the topic queue/scripts themselves
   be private.
2. **Add file → Upload files** → select every file in this project at once
   from your Files app (multi-select works in the iOS picker) → commit.
3. For the workflow files specifically, make sure they land at
   `.github/workflows/daily-post.yml` and `.github/workflows/comment-bot.yml`
   — typing that full path in "Create new file" auto-creates the folders.
4. **Settings → Secrets and variables → Actions → New repository secret**
   — add `IG_USER_ID`, `IG_ACCESS_TOKEN`, `GEMINI_API_KEY`,
   `PUBLIC_MEDIA_BASE_URL`, `AFFILIATE_LINK` — same values as your `.env`,
   just entered one at a time in the browser. Images and narration
   (Pollinations.ai, edge-tts) need no key at all.
5. That's it — check the **Actions** tab to watch runs, or hit
   **Run workflow** there to trigger one by hand instead of waiting for the
   schedule.

Both workflows commit their own state file (`script_state.json`,
`replied_comments.json`) back to the repo after every run — necessary
because GitHub Actions throws away the runner's disk after each run, so
state wouldn't survive otherwise. As a side effect, those commits count as
repo activity, which stops GitHub's automatic 60-day disable of idle
scheduled workflows.

Edit the cron lines in the two workflow files to change timing. GitHub
only guarantees "best effort" on schedule timing — a few minutes of drift
under load is normal and fine here.

### Alternative: your own server

If you'd rather not depend on GitHub Actions, the same `pipeline.py` /
`run_comment_bot.py` run fine under plain cron on any always-on Linux box
(a small VPS):

```
0 15 * * * cd /path/to/reels-agent && python pipeline.py >> pipeline.log 2>&1
*/20 * * * * cd /path/to/reels-agent && python run_comment_bot.py >> comments.log 2>&1
```

## On "no human review"

The one safeguard kept in despite that: `safety_gate.py` runs every caption
+ narration script through Gemini before publish and blocks anything that
looks like a copyright risk, an unverified factual claim, or a policy
problem. It fails closed — if the check itself errors, the post doesn't go
out. This isn't a human, so it won't catch everything a person would, but
it's a real backstop for a zero-oversight pipeline posting daily.

Every post is also tagged `is_ai_generated=true` at publish time, which
applies Instagram's own AI-content label automatically — the platform's own
compliant way of handling AI-content disclosure, no manual captioning needed.

## Monetization — realistic paths, roughly easiest first

1. **Affiliate/commission links** in bio — no follower minimum, works from post one.
2. **Instagram Gifts** — needs 500+ followers.
3. **In-stream ads / Subscriptions** — needs an established, consistent,
   original-content account (rough threshold ~5,000+ followers, varies by
   region); payouts for mid-sized accounts are often modest.
4. **Invite-only bonus programs** — roll out slowly, not available
   everywhere, eligibility criteria set by Meta and change often.
5. **Brand sponsorships** — come once you have a real audience.

Note: Meta's Partner Monetization Policies require *original* content —
reposted/repurposed clips are explicitly excluded from monetization and
risk copyright takedowns. Since this pipeline generates original AI video,
you're on the right side of that requirement.

## Not yet built

- Token refresh automation
- The Facebook side (needs a linked Page + the Facebook-Login API variant)
- Any real analytics/revenue tracking beyond what Instagram Insights gives you
- Word-synced ("karaoke-style") captions — current captions are one static
  line per beat, not timed to individual words
