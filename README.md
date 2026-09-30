# Reels agent

Fully automatic daily Reel posting + comment auto-reply for a personal
Instagram account, using AI-generated video.

## How it fits together

```
script_bank.py          -> today's fact-checked script (narration + image prompt per beat)
image_gen.py            -> free stills via Pollinations.ai
voice_gen.py            -> free narration via edge-tts
video_assemble.py       -> ffmpeg: Ken Burns zoom + captions + concat -> final .mp4
safety_gate.py          -> automated pre-publish check (Gemini)
media_host.py           -> upload final .mp4 to R2/S3/B2 -> public HTTPS URL
instagram_client.py     -> publishes to Instagram, manages comments
pipeline.py             -> runs the above end to end, once a day
token_refresh.py        -> refreshes the 60-day Instagram token (weekly)
comment_bot.py +
run_comment_bot.py      -> replies to new comments, on its own schedule
```

## What's implemented

| Piece | Status |
|-------|--------|
| Script bank (15 topics) | Ready |
| Image gen (Pollinations) | Ready |
| Voice gen (edge-tts) | Ready |
| Video assemble (ffmpeg) | Ready |
| Safety gate (Gemini) | Ready |
| Public upload (R2/S3/B2) | Ready |
| Instagram publish + comments | Ready (untested live) |
| Token refresh | Ready |
| GitHub Actions schedules | Ready |
| Optional Discord/Slack alerts | Ready |

## Go-live checklist

### 1. Instagram + Meta app
1. Switch the Instagram account to **Professional → Creator**.
2. At [developers.facebook.com](https://developers.facebook.com) create an app (type: Business).
3. Add the **Instagram** product configured for **Instagram API with Instagram Login**.
4. Request permissions: `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_comments`.
5. Complete Business Login for Instagram once → get `IG_USER_ID` and a **long-lived** access token.

### 2. Public video hosting (Cloudflare R2 recommended)
Instagram needs a public HTTPS URL for the video.

**Cloudflare R2 (free egress):**
1. Create an R2 bucket (e.g. `ambson-reels`).
2. Enable **public access** on the bucket (R2 → bucket → Settings → Public access) **or** attach a custom domain.
3. Create an R2 API token with Object Read & Write.
4. Note:
   - Account ID
   - Access Key ID
   - Secret Access Key
   - Public base URL (e.g. `https://pub-xxxxx.r2.dev` or your custom domain)
   - Endpoint: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`

### 3. Gemini API key
Get a key from [Google AI Studio](https://aistudio.google.com/apikey) (free tier is enough for one safety check + comment replies per day).

### 4. GitHub repo secrets
**Settings → Secrets and variables → Actions → New repository secret** — add all of these:

| Secret | Required |
|--------|----------|
| `IG_USER_ID` | Yes |
| `IG_ACCESS_TOKEN` | Yes |
| `GEMINI_API_KEY` | Yes |
| `PUBLIC_MEDIA_BUCKET` | Yes |
| `PUBLIC_MEDIA_ACCESS_KEY` | Yes |
| `PUBLIC_MEDIA_SECRET_KEY` | Yes |
| `PUBLIC_MEDIA_BASE_URL` | Yes |
| `PUBLIC_MEDIA_ENDPOINT` | Yes (R2/B2) |
| `PUBLIC_MEDIA_REGION` | Optional (`auto` for R2) |
| `PUBLIC_MEDIA_PREFIX` | Optional (`reels/`) |
| `AFFILIATE_LINK` | Optional |
| `NOTIFY_WEBHOOK_URL` | Optional (Discord/Slack) |
| `GH_PAT` | Optional — classic PAT with `repo` so token refresh can update `IG_ACCESS_TOKEN` automatically |

### 5. First test run
1. Open **Actions → Daily reel post → Run workflow**.
2. Watch the logs. On success you get a published Reel + optional webhook notification.
3. If publish fails, check: public URL is reachable in a browser, Instagram token scopes, and container status in the logs.

### 6. Keep the token alive
The workflow **Refresh Instagram token** runs every Monday.  
- With `GH_PAT` set: it writes the new token back into `IG_ACCESS_TOKEN` automatically.  
- Without it: open the workflow log, copy the printed token, and paste it into Secrets.

## Local run (optional)

```bash
cp env.example .env   # fill in values
pip install -r requirements.txt
# ffmpeg must be installed on the machine
python pipeline.py
python run_comment_bot.py
python token_refresh.py
```

## Scheduling

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `daily-post.yml` | 09:30 UTC daily | Generate + publish one Reel |
| `comment-bot.yml` | every 30 min | Reply to new comments |
| `token-refresh.yml` | Monday 08:00 UTC | Refresh Instagram token |

Edit the cron lines to change timing. GitHub schedule delivery is best-effort (a few minutes of drift is normal).

Both the daily post and comment bot commit their state files (`script_state.json`, `replied_comments.json`) back to the repo so state survives between runs and scheduled workflows stay active.

## Monetization (realistic order)

1. **Affiliate / link-in-bio** — works from day one (`AFFILIATE_LINK` in caption CTA).
2. **Instagram Gifts** — ~500+ followers.
3. **In-stream ads / Subscriptions** — usually needs consistent original content and a real audience (often ~5k+).
4. **Brand deals** — after you have niche engagement.

Meta’s Partner Monetization policies require original content. This pipeline generates original AI video and tags posts with `is_ai_generated=true`.

Growth still depends on hooks, niche consistency, and watch time — automation alone does not guarantee revenue.

## Safety

`safety_gate.py` runs every caption + narration through Gemini before publish and **fails closed** (if the check errors, the post does not go out). Posts are tagged AI-generated at publish time.

## Not yet built / known limits

- Word-synced (“karaoke”) captions — current captions are one static line per beat
- Live analytics dashboard (use Instagram Insights)
- Automatic script generation beyond the 15-topic bank (ask for a refill when you cycle through)
- Facebook Page–linked API path (this project uses Instagram Login only)
