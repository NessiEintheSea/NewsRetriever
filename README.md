# AI News Generation Agent

I built this because I wanted to be exhausted of scrolling news feeds with lots of same news, unrelated ads, and duplicated topic. This pulls from RSS feeds, uses Claude to score which articles actually matter, summarises them, and drops everything into Slack before I wake up.

Runs every morning at 4am JST. It Costs about $0.00002 per run. I've made some adjustments, so it might be slightly more expensive, but I assume it will be almost the same.

---

## What it does

Fetches news from RSS feeds across 5 genres, scores each article by importance using Claude Haiku, keeps the top 5 per genre, writes a 2-sentence summary for each, and posts the whole digest to Slack. Takes about 30 seconds to run.

The important bit is the filtering step — RSS feeds are sorted by recency, not importance. Without filtering you just get the 5 most recent articles which are often noise. The Claude scoring step fixes that.

---

## Stack

- Python 3.11
- Claude Haiku 4.5 (Anthropic)
- feedparser + requests for RSS
- Slack Incoming Webhooks
- GitHub Actions for scheduling

---

## Setup

**1. Clone and install**

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Set up your keys**

```bash
cp .env.example .env
```

You need two things:
- `ANTHROPIC_API_KEY` — get it at [console.anthropic.com](https://console.anthropic.com)
- `SLACK_WEBHOOK_URL` — create an app at [api.slack.com/apps](https://api.slack.com/apps), enable Incoming Webhooks, add to workspace

**3. Run it**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
PYTHONPATH=. python3 main.py
```

**4. Deploy to GitHub Actions**

- Push to GitHub
- Add `ANTHROPIC_API_KEY` and `SLACK_WEBHOOK_URL` as repository secrets (Settings → Secrets → Actions)
- It'll run automatically every day at 19:00 UTC (04:00 JST)
- You can also trigger it manually from the Actions tab

---

## Genres

Currently configured for: **Japan, World, Tech, AI, Crypto**

Each genre pulls from 2-3 RSS sources. If one feed is slow or dead it gets skipped automatically — the others pick up the slack.

Other genres available out of the box: `finance`, `science`, `health`, `sports`

To add or change genres, edit `FEEDS` in `src/config.py`.

---

## How the filtering works

For each genre, the app:
1. Fetches 30% of available articles (minimum 10) across all configured feeds
2. Sends every article's title + description to Claude with a scoring prompt
3. Claude rates each article 1-10 by importance
4. Keeps the top 5

The 30% ratio came from some back-of-envelope stats — at 30% you capture ~95% of important stories across genres with varying signal density. Crypto needs wider sampling than AI because the noise ratio is much higher.

Scoring criteria:
```
9-10  major breaking news, significant market or geopolitical impact
7-8   important development, affects a lot of people
4-6   interesting but not urgent
1-3   filler, clickbait, or too niche to care about
```

---

## Performance

Everything runs in parallel — all genres fetch simultaneously, all filter calls fire at the same time. Each RSS feed has a 10 second timeout so a dead feed never holds things up.

```
Fetch all genres     ~10s
Filter all genres    ~10s  
Summarise            ~8s
─────────────────────────
Total                ~30s
```

---

## Cost

Based on actual runs:

| | Per run | Per month |
|---|---|---|
| Filter (5 genres) | ~$0.000012 | ~$0.0004 |
| Summarise | ~$0.0000078 | ~$0.0002 |
| **Total** | **~$0.00002** | **~$0.0006** |

$50 in API credits lasts a very long time. I'm not going to do the math on how many years because it's embarrassing how cheap this is compared to a news subscription.

---

## Tuning

All the important numbers are in `src/config.py`:

```python
ANTHROPIC_MODEL      = "claude-haiku-4-5-20251001"
ARTICLES_PER_GENRE   = 5      # articles shown in Slack per genre
MIN_FETCH            = 10     # minimum articles to pull before filtering
FETCH_RATIO          = 0.30   # what fraction of the feed to sample
MAX_DESCRIPTION_CHARS = 500   # how much of each article description to send
```

To change the schedule, edit the cron in `.github/workflows/news_agent.yml`. GitHub Actions runs in UTC — Japan is UTC+9, so 19:00 UTC = 04:00 JST.

---

## Known issues

- NHK sometimes just repeats the headline as the description, which makes Claude's scoring less accurate for Japan articles
- Reuters blocks requests from GitHub Actions servers so it's been removed from the feed list
- GitHub Actions cron can run a few minutes late when their servers are busy

---

## What's next

Planning to add Slack alerts when genres fail silently and retry logic for Claude API calls. Nothing urgent — the app runs fine as-is.
