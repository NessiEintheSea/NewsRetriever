# AI News Generation Agent

Built out of frustration with scrolling through news feeds full of duplicated topics, unrelated ads, and noise. This agent pulls from RSS feeds, uses Claude to score which articles actually matter, summarises them, and drops a clean digest into Slack before you wake up.

Runs every morning at 4am JST. Costs about $0.00002 per run.

---

## What it does

Fetches news from RSS feeds across 5 genres, scores each article by importance using Claude Haiku, keeps the top 5 per genre, writes a 2-sentence summary for each, and posts the whole digest to Slack. Takes about 30 seconds to run.

The key part is the filtering step — RSS feeds are sorted by recency, not importance. Without filtering you just get the 5 most recent articles which are often noise. The Claude scoring step fixes that.

---

## Stack

- Python 3.11
- Claude Haiku 4.5 (Anthropic)
- feedparser + requests for RSS
- Slack Incoming Webhooks
- GitHub Actions for scheduling

---

## Getting started

### Prerequisites

- Python 3.11+
- An Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com)
- A Slack workspace with Incoming Webhooks enabled — set one up at [api.slack.com/apps](https://api.slack.com/apps)

### Installation

```bash
git clone https://github.com/NessiEintheSea/NewsRetriever.git
cd NewsRetriever
python3 -m venv .venv
source .venv/bin/activate      # Mac/Linux
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```
ANTHROPIC_API_KEY=your_key_here
SLACK_WEBHOOK_URL=your_webhook_url_here
```

Optional settings you can adjust:

| Variable | Default | Description |
|---|---|---|
| `GENRES` | `japan,world,tech,ai,crypto` | Comma-separated genres to run |
| `ARTICLES_PER_GENRE` | `5` | Articles shown in Slack per genre |
| `MIN_FETCH` | `10` | Minimum articles to fetch before filtering |
| `FETCH_RATIO` | `0.30` | Fraction of feed to sample |

### Run locally

```bash
export ANTHROPIC_API_KEY=your_key_here
export SLACK_WEBHOOK_URL=your_webhook_url_here
PYTHONPATH=. python3 main.py
```

You should see a digest appear in your Slack channel within 30 seconds.

### Schedule with GitHub Actions

To run automatically every morning:

1. Push this repo to your GitHub account
2. Go to **Settings → Secrets and variables → Actions**
3. Add `ANTHROPIC_API_KEY` and `SLACK_WEBHOOK_URL` as repository secrets
4. The workflow will run every day at 19:00 UTC (04:00 JST) automatically
5. You can also trigger a manual run anytime from the **Actions** tab

---

## Genres

Comes pre-configured for: **Japan, World, Tech, AI, Crypto**

Each genre pulls from 2-3 RSS sources. If one feed is slow or unresponsive it gets skipped automatically and the others pick up the slack.

Additional genres available out of the box: `finance`, `science`, `health`, `sports`

To add or change genres, edit `FEEDS` in `src/config.py` and update the `GENRES` variable.

---

## How the filtering works

For each genre, the agent:
1. Fetches 30% of available articles (minimum 10) across all configured feeds
2. Sends every article's title + description to Claude with a scoring prompt
3. Claude rates each article 1-10 by importance
4. Keeps the top 5

The 30% ratio comes from some back-of-envelope stats — at 30% you capture ~95% of important stories across genres with varying signal density. Crypto needs wider sampling than AI because the noise ratio is much higher.

Scoring criteria:
```
9-10  major breaking news, significant market or geopolitical impact
7-8   important development, affects a lot of people
4-6   interesting but not urgent
1-3   filler, clickbait, or too niche to care about
```

---

## Performance

Everything runs in parallel — all genres fetch simultaneously, all filter calls fire at the same time. Each RSS feed has a 10 second timeout so a slow or dead feed never holds things up.

```
Fetch all genres     ~10s
Filter all genres    ~10s
Summarise            ~8s
─────────────────────────
Total                ~30s
```

---

## Cost

Based on actual runs with 5 genres and 5 articles per genre:

| | Per run | Per month |
|---|---|---|
| Filter (5 genres) | ~$0.000012 | ~$0.0004 |
| Summarise | ~$0.0000078 | ~$0.0002 |
| **Total** | **~$0.00002** | **~$0.0006** |

Significantly cheaper than a news subscription. $50 in API credits will last a very long time.

---

## Tuning

All the key numbers live in `src/config.py`:

```python
ANTHROPIC_MODEL       = "claude-haiku-4-5-20251001"
ARTICLES_PER_GENRE    = 5      # articles shown in Slack per genre
MIN_FETCH             = 10     # minimum articles to pull before filtering
FETCH_RATIO           = 0.30   # fraction of the feed to sample
MAX_DESCRIPTION_CHARS = 500    # description length sent to Claude
```

To change the schedule, edit the cron expression in `.github/workflows/news_agent.yml`. Note that GitHub Actions runs in UTC — if you're in Japan, UTC+9 means 19:00 UTC = 04:00 JST.

---

## Known issues

- NHK sometimes repeats the headline as the description, which reduces Claude's scoring accuracy for Japan articles
- Reuters blocks requests from GitHub Actions servers and has been removed from the feed list
- GitHub Actions cron can run a few minutes late during high-demand periods

---

## What's next

- Slack alerts when a genre fails silently
- Retry logic for Claude API calls
- Support for custom scoring criteria per genre