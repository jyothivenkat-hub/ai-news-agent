# AI News Daily Digest Agent

> Zero-dependency Python agent that fetches AI news from 10 free sources and emails you a beautifully formatted HTML digest.

Pulls from official AI lab blogs, research feeds, and top tech publications -- then delivers a curated, ranked digest straight to your inbox. No paid APIs, no pip installs, just Python standard library and one free API key.

---

## Architecture

```
                        +--------------------------------------+
                        |       AI News Daily Digest Agent      |
                        +--------------------------------------+
                                         |
             +---------------------------+---------------------------+
             |                           |                           |
    +--------v--------+       +---------v---------+       +---------v---------+
    |  Source Fetchers  |       |  Processing Engine |       |   Email Delivery   |
    |  (10 sources)     |       |  (rank & dedupe)   |       |   (SMTP / Gmail)   |
    +------------------+       +-------------------+       +-------------------+
             |                           |                           |
    +--------v--------+       +---------v---------+       +---------v---------+
    | ThreadPoolExec   |       |  Article Ranking   |       |  HTML Templating   |
    | (6 workers)       |       |  + Deduplication   |       |  + TL;DR Summary   |
    +------------------+       +-------------------+       +-------------------+

    +------------------+
    | News Sources      |       Concurrent Fetch
    +------------------+       (ThreadPoolExecutor)
    | Anthropic Blog   |  ──>  +------------------+
    | OpenAI Blog RSS  |  ──>  |                  |
    | DeepMind Blog    |  ──>  |  Fetch, Parse,   |
    | Google News RSS  |  ──>  |  Deduplicate,    |
    | NewsAPI.org      |  ──>  |  Rank, Format,   |
    | ArXiv API        |  ──>  |  Email           |
    | HuggingFace RSS  |  ──>  |                  |
    | TechCrunch RSS   |  ──>  +------------------+
    | MIT Tech Review  |  ──>
    | The Verge AI     |  ──>
    +------------------+
```

### Data Flow

```
 1. FETCH             2. PROCESS           3. FORMAT            4. DELIVER
 +-----------+       +--------------+     +----------------+   +-------------+
 | 10 sources | -->   | Deduplicate  | --> | HTML digest    | -->| Gmail SMTP  |
 | fetched in |       | by title     |     | with TL;DR,   |   | to one or   |
 | parallel   |       | hash, rank   |     | top stories,   |   | multiple    |
 | (6 threads)|       | by priority  |     | reading times  |   | recipients  |
 +-----------+       +--------------+     +----------------+   +-------------+
```

---

## What It Does

### Fetches from 10 Free Sources
The agent pulls from official AI lab blogs, research archives, news aggregators, and top tech publications -- all in parallel using `concurrent.futures.ThreadPoolExecutor` for speed.

### Deduplicates and Ranks
Articles are deduplicated by title similarity (via hash matching), then ranked with official AI lab sources (Anthropic, OpenAI, DeepMind) boosted to the top.

### Sends a Premium HTML Digest
Delivers a single email with:
- **TL;DR summary** -- top 3 stories at a glance
- **Categorized articles** -- grouped by source type (Official Blogs, Research, News, Tech Media)
- **Reading time estimates** -- so you know what you're clicking into
- **Responsive design** -- looks great on desktop and mobile

---

## News Sources

| Source | Category | What It Covers | API Key? |
|--------|----------|---------------|----------|
| Anthropic News | Official Blog | Claude releases, safety research | No |
| OpenAI Blog RSS | Official Blog | GPT updates, research papers | No |
| Google DeepMind RSS | Official Blog | Gemini, AlphaFold, research | No |
| Google News RSS | Aggregator | Breaking AI headlines | No |
| NewsAPI.org | Aggregator | Cross-publication AI articles | Yes (free) |
| ArXiv API | Research | Latest AI/ML papers | No |
| HuggingFace Papers | Research | Trending ML papers | No |
| TechCrunch AI RSS | Tech Media | AI startups and business | No |
| MIT Technology Review | Tech Media | AI research and policy | No |
| The Verge AI RSS | Tech Media | Consumer AI news | No |

Only **one** source (NewsAPI) requires an API key, and it's free (100 requests/day). The agent works without it -- you just get 9 sources instead of 10.

---

## Download & Install

### Prerequisites
- Python 3.10 or later
- A Gmail account with 2-Step Verification enabled

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/jyothivenkat-hub/ai-news-agent.git

# 2. Navigate to the project
cd ai-news-agent

# 3. Set environment variables
export AI_NEWS_EMAIL="your-email@gmail.com"
export AI_NEWS_APP_PASSWORD="your-16-char-app-password"
export AI_NEWS_API_KEY="your-newsapi-key"           # optional
export AI_NEWS_RECIPIENTS="email1@gmail.com,email2@gmail.com"

# 4. Run
python3 ai_news_agent.py
```

No `pip install` needed. Zero external dependencies.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AI_NEWS_EMAIL` | Yes | Your Gmail address (sender) |
| `AI_NEWS_APP_PASSWORD` | Yes | Gmail App Password ([generate here](https://myaccount.google.com/apppasswords)) |
| `AI_NEWS_API_KEY` | No | Free NewsAPI key ([register here](https://newsapi.org/register)) |
| `AI_NEWS_RECIPIENTS` | No | Comma-separated recipient emails (defaults to sender) |

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for step-by-step setup including Gmail App Password creation.

---

## Scheduling

### macOS / Linux (cron)

```bash
crontab -e
```

Add lines for your preferred schedule (e.g., 8 AM and 7 PM):

```
0 8 * * * cd "/path/to/ai-news-agent" && /usr/bin/python3 ai_news_agent.py >> ai_news.log 2>&1
0 19 * * * cd "/path/to/ai-news-agent" && /usr/bin/python3 ai_news_agent.py >> ai_news.log 2>&1
```

### Windows (Task Scheduler)

Create a Basic Task with trigger **Daily** and action **Start a Program** pointing to `python3 ai_news_agent.py`.

### GitHub Actions (runs even when your computer is off)

Create `.github/workflows/ai-news.yml`:

```yaml
name: AI News Digest
on:
  schedule:
    - cron: '0 13 * * *'   # 8 AM EST
    - cron: '0 0 * * *'    # 7 PM EST
  workflow_dispatch:

jobs:
  send-digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python ai_news_agent.py
        env:
          AI_NEWS_EMAIL: ${{ secrets.AI_NEWS_EMAIL }}
          AI_NEWS_APP_PASSWORD: ${{ secrets.AI_NEWS_APP_PASSWORD }}
          AI_NEWS_API_KEY: ${{ secrets.AI_NEWS_API_KEY }}
          AI_NEWS_RECIPIENTS: ${{ secrets.AI_NEWS_RECIPIENTS }}
```

Add your secrets in the repo under Settings > Secrets > Actions.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| HTTP | `urllib.request` (standard library) |
| XML Parsing | `xml.etree.ElementTree` (standard library) |
| Email | `smtplib` + `email.mime` (standard library) |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` |
| Templating | Inline HTML string builder |
| External APIs | NewsAPI.org (free tier, optional) |

**Zero pip dependencies.** Everything runs on the Python standard library.

---

## Project Structure

```
News Agent/
  ai_news_agent.py           -- Main script: 10 fetchers, ranking engine,
                                 HTML builder, email delivery
  SETUP_GUIDE.md             -- Step-by-step setup (Gmail, NewsAPI, scheduling)
  index.html                 -- Sample digest output (rendered HTML)
  sample_ai_digest.html      -- Example email digest v1
  sample_ai_digest_v2.html   -- Example email digest v2
  .gitignore                 -- Ignores .env, __pycache__, .DS_Store
```

---

## License

MIT
