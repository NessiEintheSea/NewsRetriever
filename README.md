# News Agent

An AI-powered news digest agent that fetches top articles from RSS feeds, summarises them with Claude Haiku 4.5, and posts a formatted digest to Slack — automatically, every weekday morning.

## How it works

```
RSS Feeds → Fetcher → Summarizer (Claude Haiku, 1 API call) → Formatter → Slack
```

1. **Fetcher** pulls the top N articles per genre from curated RSS feeds
2. **Summarizer** sends all articles in a single batched Claude Haiku call
3. **Formatter** builds a Slack Block Kit payload
4. **Notifier** POSTs it to your Slack channel via Incoming Webhook

## Quick start

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/news-agent.git
cd news-agent
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure secrets

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Required environment variables:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | From [console.anthropic.com](https://console.anthropic.com) |
| `SLACK_WEBHOOK_URL` | From your Slack app's Incoming Webhooks page |

Optional:

| Variable | Default | Description |
|---|---|---|
| `GENRES` | `tech,finance,world` | Comma-separated list of genres |
| `ARTICLES_PER_GENRE` | `3` | Articles fetched per genre per run |

### 4. Run locally

```bash
# With a .env file (use python-dotenv or export manually)
export $(cat .env | xargs)
python main.py
```

### 5. Deploy to GitHub Actions

1. Push this repo to GitHub
2. Go to **Settings → Secrets and variables → Actions**
3. Add `ANTHROPIC_API_KEY` and `SLACK_WEBHOOK_URL` as repository secrets
4. The workflow runs automatically at **08:00 UTC, Monday–Friday**
5. To trigger manually: **Actions → Daily News Digest → Run workflow**

## Available genres

| Genre | Key |
|---|---|
| Technology | `tech` |
| Finance & Business | `finance` |
| World News | `world` |
| Science | `science` |
| Japan | `japan` |
| Health | `health` |
| Sports | `sports` |

Add more genres by editing `FEEDS` in `src/config.py`.

## Customising the schedule

Edit `.github/workflows/news_agent.yml`:

```yaml
- cron: "0 8 * * 1-5"   # weekdays 08:00 UTC
- cron: "0 8 * * *"     # every day
- cron: "0 8,17 * * 1-5" # twice a day on weekdays
```

## Cost

With default settings (3 genres × 3 articles, 1 run/day):

| Model | Monthly cost |
|---|---|
| Claude Haiku 4.5 | ~$0.001 |
| Claude Sonnet 4.6 | ~$0.003 |

Well within any budget. The $10/month threshold supports thousands of articles per day.

## Project structure

```
news-agent/
├── .github/workflows/news_agent.yml  # GitHub Actions cron
├── src/
│   ├── config.py      # genres, feeds, constants
│   ├── fetcher.py     # RSS parsing
│   ├── summarizer.py  # Claude Haiku integration
│   ├── formatter.py   # Slack Block Kit builder
│   └── notifier.py    # Slack webhook POST
├── main.py            # entrypoint
├── requirements.txt
└── .env.example
```
