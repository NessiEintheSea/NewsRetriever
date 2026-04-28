# AI News Generation Agent

An AI-powered daily news digest agent that intelligently fetches, filters, and summarises the most important articles from RSS feeds — then delivers them to Slack every morning automatically.

Built with Python, Claude Haiku 4.5, and GitHub Actions.

---

## How it works

```
RSS Feeds
    ↓
Fetcher       — ratio-based sampling (30% of feed, min 10 articles)
    ↓
Filter        — Claude scores each article by importance (title + description)
    ↓
Summarizer    — Claude writes 2-sentence summary for top 5 per genre
    ↓
Formatter     — builds Slack Block Kit payload
    ↓
Slack
```

### Pipeline detail

1. **Fetcher** — for each genre, counts total available articles across all configured RSS feeds, then fetches `max(10, total × 30%)`. This ratio-based strategy ensures statistically robust coverage regardless of how busy the news cycle is — quiet days get full coverage, busy days get proportional sampling.

2. **Filter** — sends all fetched articles (title + description) to Claude Haiku in one API call per genre. Claude scores each article 1–10 by importance and returns the top 5. This separates recency (what RSS gives you) from importance (what you actually want to read).

3. **Summarizer** — sends all top articles across all genres in a single batched API call. Claude writes exactly 2 sentences per article: one core fact, one context or implication.

4. **Formatter** — builds a structured Slack Block Kit message with genre headers, article titles as links, and summaries.

5. **Notifier** — HTTP POSTs the payload to your Slack channel via Incoming Webhook.

---

## Quick start

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### 2. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure secrets

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Required environment variables:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `SLACK_WEBHOOK_URL` | [api.slack.com/apps](https://api.slack.com/apps) → Incoming Webhooks |

Optional overrides:

| Variable | Default | Description |
|---|---|---|
| `GENRES` | `japan,world,tech,ai,crypto` | Comma-separated genres to run |
| `ARTICLES_PER_GENRE` | `5` | Final articles per genre sent to Slack |
| `MIN_FETCH` | `10` | Minimum articles to fetch per genre |
| `FETCH_RATIO` | `0.30` | Ratio of available articles to sample |

### 5. Run locally

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
PYTHONPATH=. python3 main.py
```

### 6. Deploy to GitHub Actions

1. Push this repo to GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Add `ANTHROPIC_API_KEY` and `SLACK_WEBHOOK_URL` as repository secrets
4. The workflow runs automatically at **19:00 UTC (04:00 JST), Monday–Friday**
5. To trigger manually: **Actions → Daily News Digest → Run workflow**

---

## Configured genres

| Genre | Key | Primary sources |
|---|---|---|
| Japan | `japan` | NHK, Japan Today, BBC Asia |
| World News | `world` | BBC World, NYT World, Reuters |
| Technology | `tech` | Ars Technica, NYT Tech, BBC Tech |
| Artificial Intelligence | `ai` | AI Weekly, AI News, BBC Tech |
| Crypto | `crypto` | CoinTelegraph, CoinDesk, Decrypt |

Additional available genres: `finance`, `science`, `health`, `sports`

To add a genre, edit `FEEDS` in `src/config.py` and add the key to `GENRES`.

---

## Intelligent filtering

The app uses a two-stage Claude pipeline to select the most important articles:

**Stage 1 — importance scoring (filter)**
Claude receives each article's title and description, then scores it 1–10:
```
10  = Major breaking news, significant global/market impact
7–9 = Important development, affects many people or industries
4–6 = Interesting but moderate significance
1–3 = Minor, niche, or low-impact story
```

**Stage 2 — summarisation**
Only the top 5 scoring articles per genre proceed to summarisation,
ensuring the digest contains the most significant stories rather
than just the most recent.

---

## Customising the schedule

Edit `.github/workflows/news_agent.yml`:

```yaml
- cron: "0 19 * * 0-4"   # 04:00 JST weekdays (current)
- cron: "0 22 * * 0-4"   # 07:00 JST weekdays
- cron: "0 0 * * 1-5"    # 09:00 JST weekdays
- cron: "0 19 * * *"     # 04:00 JST every day
```

Note: GitHub Actions cron runs in UTC. Japan (JST) is UTC+9.

---

## Cost

With current settings (5 genres × 5 articles, 1 run/day, Claude Haiku 4.5):

| | Per run | Per month |
|---|---|---|
| Filter calls (5 genres) | ~$0.00015 | ~$0.005 |
| Summarise call (1 batch) | ~$0.00010 | ~$0.003 |
| **Total** | **~$0.00025** | **~$0.008** |

Your $50 API credit covers approximately 500 years of daily runs at this rate.

---

## Project structure

```
AI_NewsGeneration/
├── .github/
│   └── workflows/
│       └── news_agent.yml   # GitHub Actions cron + manual dispatch
├── src/
│   ├── config.py            # genres, feeds, constants, prompts
│   ├── fetcher.py           # RSS parsing + ratio-based sampling
│   ├── filter.py            # Claude importance scoring + selection
│   ├── summarizer.py        # Claude Haiku summarisation
│   ├── formatter.py         # Slack Block Kit payload builder
│   └── notifier.py          # Slack webhook POST
├── main.py                  # pipeline entrypoint
├── requirements.txt
├── .env.example
└── README.md
```

---

## Model

Currently using `claude-haiku-4-5-20251001`. To switch models, edit `ANTHROPIC_MODEL` in `src/config.py`.

| Model | Speed | Quality | Cost |
|---|---|---|---|
| `claude-haiku-4-5-20251001` | Fastest | Good | $1/$5 per 1M |
| `claude-sonnet-4-6` | Fast | Better | $3/$15 per 1M |
| `claude-opus-4-6` | Slower | Best | $5/$25 per 1M |# updated
