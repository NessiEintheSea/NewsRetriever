# AI News Generation Agent

An AI-powered daily news digest agent that intelligently fetches, filters, and summarises the most important articles from RSS feeds — then delivers them to Slack every morning automatically.

Built with Python, Claude Haiku 4.5, and GitHub Actions.

---

## How it works

```
RSS Feeds
    ↓
Fetcher       — parallel fetch with 10s timeout, ratio-based sampling (30%, min 10)
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

1. **Fetcher** — fetches all feeds for all genres simultaneously using parallel threads. Each feed has a 10 second timeout to prevent hanging. Collects all available articles in a single pass, then applies `max(MIN_FETCH=10, total × FETCH_RATIO=30%)` to determine how many to keep. This ratio-based strategy ensures statistically robust coverage — quiet days get full coverage, busy days get proportional sampling.

2. **Filter** — all genres are filtered simultaneously using parallel threads. Each genre sends its articles (title + description) to Claude Haiku for importance scoring (1–10). Top 5 per genre are selected. This separates recency (what RSS gives you) from importance (what you actually want to read).

3. **Summarizer** — sends all top articles across all genres in a single batched API call. Claude writes exactly 2 sentences per article: one core fact, one context or implication.

4. **Formatter** — builds a structured Slack Block Kit message with genre headers, article titles as clickable links, and 2-sentence summaries.

5. **Notifier** — HTTP POSTs the payload to your Slack channel via Incoming Webhook.

---

## Performance

With parallel fetching and filtering:

| Stage | Time |
|---|---|
| Fetch (all genres + feeds simultaneously) | ~10s |
| Filter (all genres simultaneously) | ~10s |
| Summarise (single batched call) | ~8s |
| **Total runtime** | **~30 seconds** |

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
4. The workflow runs automatically every day at **19:00 UTC (04:00 JST)**
5. To trigger manually: **Actions → Daily News Digest → Run workflow**

---

## Configured genres

| Genre | Key | Primary sources |
|---|---|---|
| Japan | `japan` | NHK, BBC Asia |
| World News | `world` | BBC World, NYT World |
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

## Resilience

- **Feed timeout** — each RSS feed has a 10s timeout. Slow or dead feeds are skipped automatically, next feed in list is tried.
- **Filter fallback** — if Claude filter call fails, falls back to first N articles by recency.
- **Summariser fallback** — if summarise call fails, falls back to raw RSS description.
- **GitHub Actions alerts** — enable email notifications in GitHub Settings → Notifications → Actions to get alerted on total failures.

---

## Customising the schedule

Edit `.github/workflows/news_agent.yml`:

```yaml
- cron: "0 19 * * *"     # 04:00 JST every day (current)
- cron: "0 19 * * 0-4"   # 04:00 JST weekdays only
- cron: "0 22 * * *"     # 07:00 JST every day
- cron: "0 0 * * *"      # 09:00 JST every day
```

Note: GitHub Actions cron runs in UTC. Japan (JST) is UTC+9.

---

## Cost

Based on actual token usage from real runs (5 genres, normal news day):

| Call | Input tokens | Output tokens | Cost |
|---|---|---|---|
| Filter japan | ~1,300 | ~150 | ~$0.0000020 |
| Filter world | ~1,500 | ~390 | ~$0.0000035 |
| Filter tech | ~1,060 | ~290 | ~$0.0000025 |
| Filter ai | ~800 | ~150 | ~$0.0000015 |
| Filter crypto | ~1,200 | ~300 | ~$0.0000025 |
| Summariser | ~1,800 | ~1,200 | ~$0.0000078 |
| **Total per run** | **~7,660** | **~2,480** | **~$0.00002** |
| **Per month** (30 runs) | ~230,000 | ~74,400 | **~$0.0006** |
| **Per year** (365 runs) | ~2,796,000 | ~905,200 | **~$0.007** |

Your $50 API credit covers approximately **7,000 years** of daily runs at this rate.

---

## Project structure

```
AI_NewsGeneration/
├── .github/
│   └── workflows/
│       └── news_agent.yml   # GitHub Actions cron + manual dispatch
├── src/
│   ├── config.py            # genres, feeds, constants, prompts
│   ├── fetcher.py           # parallel RSS fetching + ratio-based sampling
│   ├── filter.py            # parallel Claude importance scoring + selection
│   ├── summarizer.py        # Claude Haiku summarisation (single batch call)
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
| `claude-opus-4-6` | Slower | Best | $5/$25 per 1M |

---

## Known limitations

- RSS descriptions vary in quality by publisher — NHK sometimes repeats the title as the description, which reduces filter scoring accuracy for Japan articles.
- Some feed providers (e.g. Reuters) block requests from GitHub Actions servers. These have been removed from the feed config and replaced with alternatives.
- GitHub Actions cron schedule may run a few minutes late during high-demand periods.