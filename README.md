# AI News Generation Agent

Pulls news from RSS feeds, groups articles into **stories**, decides whether each
new article is genuinely *new* or just an *update* to something already reported,
ranks stories on multiple signals, controls for diversity, summarises, and
delivers a clean digest to **Discord** (or Slack) — without repeating yesterday's
news.

> **A note on the LLM:** this project summarises with **Anthropic's Claude**, not
> OpenAI/GPT. Where the original spec used `OPENAI_*` names, the equivalents here
> are `ANTHROPIC_*`.

---

## New processing flow

```
RSS fetch
  ↓  normalise (URL + text)
  ↓  exact-duplicate removal (GUID / URL / fingerprint)   ← no API cost
  ↓  embedding (local, offline)
  ↓  candidate stories by cosine → entity check → LLM identity judgement
  ↓  link to an existing story, or create a new one
  ↓  classify change: new_story / major_update / minor_update / no_meaningful_change
  ── persist articles, stories, story_events ──            [ingest job]
────────────────────────────────────────────────────────────────────────
  ↓  gather last-24h new/updated stories                   [digest job]
  ↓  rank: relevance · novelty · importance · source_quality · recency
  ↓  diversity control (MMR + per-source/category/story/update caps)
  ↓  summarise (full) or delta-summarise (updates only)
  ↓  deliver to Discord
  ── persist delivery_history ──
```

The pipeline is split into **two jobs** (see [GitHub Actions](#github-actions)):
`ingest` (frequent) and `digest` (once each morning).

---

## Stack

- Python 3.12
- Claude Haiku 4.5 (Anthropic) — model configurable via `ANTHROPIC_MODEL`
- `feedparser` + `requests` for RSS
- `pydantic` for validated structured LLM outputs
- SQLite (via stdlib `sqlite3`) for persistence
- Discord / Slack Incoming Webhooks
- GitHub Actions for scheduling

No embedding API is required by default — a dependency-free **local lexical
embedder** is used for candidate retrieval. For higher-quality clustering you can
switch to **real semantic embeddings** (OpenAI) with one env var — see
[Improving clustering & summary quality](#improving-clustering--summary-quality).

---

## Getting started

### Prerequisites

- Python 3.12+
- An Anthropic API key — [console.anthropic.com](https://console.anthropic.com)
- A Discord Incoming Webhook (see below)

### Discord webhook setup

1. In Discord: **Server Settings → Integrations → Webhooks → New Webhook**.
2. Pick the channel, click **Copy Webhook URL**.
3. Put it in `.env` as `DISCORD_WEBHOOK_URL`. Keep it secret — it is never logged.

### Installation

```bash
git clone <your-repo-url>
cd AI_NewsGeneration
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
```

Fill in at least `ANTHROPIC_API_KEY` and `DISCORD_WEBHOOK_URL`. All other
settings have sensible defaults — see [Environment variables](#environment-variables).

### Database initialisation

The schema is created automatically on first run (there is no manual migration
step). The DB file lives at the path in `DATABASE_URL` (default
`data/news.db`); its parent directory is created if missing. To start clean,
delete the file.

### Run locally

```bash
export ANTHROPIC_API_KEY=...          # or put these in .env
export DISCORD_WEBHOOK_URL=...

PYTHONPATH=. python main.py ingest    # fetch + store (no delivery)
PYTHONPATH=. python main.py digest    # rank + summarise + deliver
PYTHONPATH=. python main.py run       # both, in one process
```

---

## How story detection works

Articles about the same event are grouped into a **story**. When a new article
arrives:

1. **Exact duplicates** (same GUID, normalised URL, or content fingerprint) are
   dropped *before* any embedding or LLM call — zero API cost.
2. An **embedding** (local, deterministic) shortlists candidate stories by cosine
   similarity.
3. **Embedding similarity alone is never trusted.** A candidate is only worth an
   LLM call if it clears the similarity threshold *or* shares a proper-noun entity
   (company/product/person). This is why *"OpenAI announces model"* and
   *"Anthropic announces model"* stay separate despite similar wording.
4. The **LLM makes the final same-story-or-not judgement** (validated JSON).
5. If linked, the LLM produces a **diff** and a `change_type`:

   | `change_type`          | Meaning                                   | Delivery        |
   |------------------------|-------------------------------------------|-----------------|
   | `new_story`            | A genuinely new event                     | full summary    |
   | `major_update`         | Release, price, availability, ruling, ... | delta summary   |
   | `minor_update`         | Comment, extra region, minor note         | delta (gated)   |
   | `no_meaningful_change` | Re-post / rewording, no new facts         | **not delivered** |

`minor_update` delivery is controlled by `DELIVER_MINOR_UPDATES`.

---

## Ranking logic

Each deliverable story is scored on five signals, each normalised to 0–1:

```
score = relevance      * WEIGHT_RELEVANCE
      + novelty         * WEIGHT_NOVELTY
      + importance      * WEIGHT_IMPORTANCE
      + source_quality  * WEIGHT_SOURCE_QUALITY
      + recency         * WEIGHT_RECENCY
```

- **relevance** — overlap with your configured interest terms (from `GENRES`).
- **novelty** — new_story > major > minor.
- **importance** — the LLM's 0–1 importance judgement.
- **source_quality** — tier of the representative source (below).
- **recency** — decays over ~48h.

Weights come from `WEIGHT_*` env vars and are normalised at use-time (they need
not sum to exactly 1.0). The per-factor breakdown is logged for every candidate;
production Discord posts don't show scores.

### Source quality tiers

`primary` (official blogs/press, gov, arXiv, GitHub) → `high_quality` (major
outlets) → `secondary` (blogs/explainers) → `aggregator` (reposts). The digest
prefers a primary source as the representative article and can require at least
one primary item (`REQUIRE_PRIMARY_SOURCE`, relaxed automatically if none exist).

### Diversity

Ranking top-N alone over-represents similar stories, so an MMR-style selection
balances score against dissimilarity, under hard caps: at most
`DIGEST_MAX_ITEMS` total, `MAX_ITEMS_PER_SOURCE` per source,
`MAX_ITEMS_PER_CATEGORY` per category, one item per story, and
`MAX_UPDATE_ITEMS` updates.

---

## Discord delivery format

New and update items render as Discord **embeds** (green = new, blue = update):

```
🆕 新規  <title>
概要:        - point 1 / - point 2 / - point 3
なぜ重要か:  <short reason>
関連カテゴリ: AI / ...
情報源:      <media> (link)
```

```
🔄 更新  <story title>
前回からの変更: - new fact ...
情報源:         <media> (link)
```

Discord's limits (2000-char content, 4096-char embed description, 10 embeds and
6000 chars per message) are respected by splitting long descriptions into
continuation embeds and batching embeds across messages.

---

## Adding another delivery channel

Delivery is fully decoupled from the pipeline via a `Notifier` protocol
(`src/notifiers/base.py`):

```python
class Notifier(Protocol):
    def send_digest(self, digest: dict) -> None: ...
    def send_update(self, update: dict) -> None: ...
```

`DiscordNotifier` and `SlackNotifier` implement it. To add one (e.g. Teams,
email), implement the protocol and register it in `src/notifiers/__init__.py`.
The pipeline only ever produces a channel-agnostic `digest` dict.

### Migrating from Slack to Discord

Set `NOTIFIER=discord` and `DISCORD_WEBHOOK_URL=...`. That's it — the Slack path
remains (`NOTIFIER=slack`) for backwards compatibility.

---

## GitHub Actions

Three workflows in `.github/workflows/`:

- **`news_ingest.yml`** — scheduled every 3 hours; fetch + store only.
- **`news_digest.yml`** — scheduled each morning; rank + deliver.
- **`news_agent.yml`** — manual `workflow_dispatch` all-in-one (ingest + digest).

Add these repository **secrets** (Settings → Secrets and variables → Actions):
`ANTHROPIC_API_KEY`, `DISCORD_WEBHOOK_URL` (and `SLACK_WEBHOOK_URL` if used).
Optional repository **variables**: `NOTIFIER`, `ANTHROPIC_MODEL`,
`DELIVER_MINOR_UPDATES`.

### Cron is UTC — setting Japan time

GitHub Actions cron is **always UTC**. JST = UTC + 9, so subtract 9 hours:

| Desired (JST) | cron (UTC)       |
|---------------|------------------|
| 04:00 daily   | `0 19 * * *`     |
| 07:00 daily   | `0 22 * * *`     |
| every 3h      | `0 */3 * * *`    |

Edit the `cron:` line in the workflow file to change the time (this cannot be
done via an env var).

### SQLite persistence in Actions

The DB is persisted between runs with `actions/cache` (key `news-db-<run-id>`,
restore-key prefix `news-db-`). Both workflows share a `concurrency: news-db`
group so ingest and digest never write concurrently.

**Constraints / risks:**

- `actions/cache` is **best-effort**: entries can be evicted (7-day inactivity or
  the 10 GB repo cache limit). If the cache is lost, the DB rebuilds from empty —
  you may briefly see a story re-delivered as "new". This is acceptable for a
  news digest but is not durable storage.
- **Committing the DB file back to git is *not* used here** because it bloats
  history and invites merge conflicts on every run. If you adopt that approach
  instead, commit to a dedicated orphan branch and squash periodically.
- For durable, correct persistence, use an **external database** (see below).

---

## Using an external database (PostgreSQL)

The data-access layer (`src/db.py`) is isolated behind a `Database` class, so a
move to PostgreSQL only touches that file. `DATABASE_URL` already recognises the
`postgresql://` scheme and currently raises a clear "not implemented" error. To
add it: create a psycopg-backed `Database` subclass implementing the same
methods (the SQL uses simple `?`-style placeholders and JSON text columns that
map cleanly to `jsonb`). Point `DATABASE_URL=postgresql://...` and the caching
workflow steps become unnecessary.

---

## API cost optimisation

Calls are ordered cheapest-first so the LLM only runs when it must:

```
exact dedup (URL/GUID/hash)  →  local entity/keyword compare  →
embedding cosine shortlist   →  LLM identity (only if a candidate exists)  →
final summary (only for delivered items)
```

- Exact duplicates never reach the LLM or embedder.
- Embeddings are computed once and cached on the article row.
- New-story facts are cached on the story (`summary_json`), so the daily digest
  needs **no re-summarisation** call for new items; updates reuse the diff
  computed at ingest time.
- Candidate lookback is limited to `STORY_LOOKBACK_DAYS`.
- API call and token counts are logged at the end of each run.

---

## Improving clustering & summary quality

Two opt-in upgrades make the app materially better at grouping stories and
writing accurate summaries. Both keep Claude as the LLM and are off by default.

**1. Real embeddings (biggest quality win).** The default local embedder is
lexical; real semantic embeddings cluster "same event" far better. Anthropic has
no embedding API, so this uses OpenAI **for embeddings only**:

```bash
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small   # cheap + strong
```

Implemented behind the `Embedder` protocol (`src/embedding.py`), so no other code
changes. On any OpenAI error it falls back to the local embedder safely. **Switch
providers on a fresh DB** — local (256-dim) and OpenAI (1536-dim) vectors aren't
comparable, so a mixed DB just won't cluster old vs new items (never a false
match) until re-embedded.

**2. Full article text.** RSS descriptions are often truncated; fetching the page
body improves summaries and update-diffs:

```bash
FETCH_FULL_TEXT=true          # off by default
FULL_TEXT_MAX_CHARS=4000
```

Body text is fetched only for unique (post-dedup) articles to bound requests, and
falls back to the RSS description on any failure.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Claude API key |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Model for filter/summary/judgement |
| `EMBEDDING_PROVIDER` | `local` | `local` or `openai` (see above) |
| `OPENAI_API_KEY` | — | Required when `EMBEDDING_PROVIDER=openai` |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `FETCH_FULL_TEXT` | `false` | Fetch full article body for better summaries |
| `FULL_TEXT_MAX_CHARS` / `FULL_TEXT_TIMEOUT` | `4000` / `10` | Full-text limits |
| `NOTIFIER` | `discord` | `discord` or `slack` |
| `DISCORD_WEBHOOK_URL` | — | Required when `NOTIFIER=discord` |
| `SLACK_WEBHOOK_URL` | — | Required when `NOTIFIER=slack` |
| `DATABASE_URL` | `sqlite:///data/news.db` | DB location |
| `DELIVER_MINOR_UPDATES` | `false` | Deliver `minor_update` items |
| `STORY_LOOKBACK_DAYS` | `30` | How far back to look for candidate stories |
| `SIMILARITY_THRESHOLD` | `0.82` | Cosine bar for a strong candidate |
| `SIMILARITY_CANDIDATE_LIMIT` | `10` | Max candidate stories per article |
| `DIGEST_MAX_ITEMS` | `7` | Max items per digest |
| `MAX_ITEMS_PER_SOURCE` | `2` | Diversity cap per source |
| `MAX_ITEMS_PER_CATEGORY` | `2` | Diversity cap per category |
| `MAX_UPDATE_ITEMS` | `3` | Max update items per digest |
| `REQUIRE_PRIMARY_SOURCE` | `true` | Ensure ≥1 primary if available |
| `WEIGHT_RELEVANCE` | `0.30` | Ranking weight |
| `WEIGHT_NOVELTY` | `0.25` | Ranking weight |
| `WEIGHT_IMPORTANCE` | `0.20` | Ranking weight |
| `WEIGHT_SOURCE_QUALITY` | `0.15` | Ranking weight |
| `WEIGHT_RECENCY` | `0.10` | Ranking weight |
| `GENRES` | `japan,world,tech,ai,crypto` | Genres to fetch |
| `ARTICLES_PER_GENRE` | `5` | Articles kept per genre |
| `MIN_FETCH` / `FETCH_RATIO` | `10` / `0.30` | Fetch-volume knobs |

---

## Testing

```bash
PYTHONPATH=. python -m unittest discover -s tests
```

Tests use the stdlib `unittest` (no extra dependency). **All external calls —
Claude, RSS, Discord — are mocked**, so the suite runs offline and touches no
production data. Coverage includes URL/text normalisation, fingerprint & exact
dedup, score computation, diversity control, delivery-target selection, the four
`change_type` paths, Discord message splitting, invalid-LLM-response handling,
the DB layer, and a full ingest→digest integration test.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Missing required environment variables` | Set `ANTHROPIC_API_KEY` and the webhook for your `NOTIFIER`. |
| Nothing delivered | No fresh stories in the last 24h, or all were `no_meaningful_change`; check ingest logs and `Digest stats`. |
| A story re-delivered as "new" | The Actions cache (SQLite DB) was evicted; use an external DB for durability. |
| Discord `400` on send | Usually an embed limit; the splitter should prevent this — file an issue with the (redacted) payload size. |
| LLM output rejected repeatedly | Logged as "failed validation"; the item falls back safely (new story / no change) and is skipped, never crashing the run. |
| Reuters feed empty | Some feeds block CI IPs; other feeds in the genre cover for it. |

---

## Known issues / next steps

- Local lexical embeddings are the offline default; **OpenAI semantic embeddings
  are supported** (`EMBEDDING_PROVIDER=openai`) for much better clustering. A
  local model or Voyage can be added behind the same `Embedder` protocol.
- SQLite-in-Actions is best-effort; PostgreSQL is the durable path.
- Delivery de-duplication is time-based (per story, since last delivery); a
  per-event delivery ledger would be more precise for sub-daily digests.
