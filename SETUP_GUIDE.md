# AI News Daily Digest — Setup Guide

## What This Does

A Python script that automatically fetches AI news from **7 free sources** every morning and emails you a beautifully formatted digest. No paid subscriptions needed.

### Free Sources Used

| Source | What It Covers | API Key Needed? |
|---|---|---|
| Google News RSS | Breaking AI news | No |
| NewsAPI.org | Aggregated AI articles | Yes (free tier) |
| ArXiv | Latest AI research papers | No |
| HuggingFace Papers | Trending ML papers | No |
| TechCrunch AI | AI startups & business | No |
| MIT Technology Review | AI research & policy | No |
| The Verge AI | General AI news | No |

---

## Step 1: Install Python

You need Python 3.10+. Check with:

```bash
python3 --version
```

No external packages are required — the script uses only Python standard library.

---

## Step 2: Get a Free NewsAPI Key (Optional but Recommended)

1. Go to [https://newsapi.org/register](https://newsapi.org/register)
2. Sign up for a free account (100 requests/day)
3. Copy your API key

---

## Step 3: Create a Gmail App Password

Gmail requires an "App Password" for scripts to send email. Here's how:

1. Go to [https://myaccount.google.com/security](https://myaccount.google.com/security)
2. Make sure **2-Step Verification** is turned ON
3. Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. Select **"Other (Custom name)"** and type `AI News Agent`
5. Click **Generate**
6. Copy the 16-character password (e.g., `abcd efgh ijkl mnop`)

---

## Step 4: Configure the Script

Open `ai_news_agent.py` and update the CONFIG section near the top:

```python
CONFIG = {
    "email": "jyothi.venkat23@gmail.com",
    "app_password": "your-16-char-app-password",
    "newsapi_key": "your-newsapi-key-here",  # or leave as-is to skip
    "max_articles_per_source": 5,
    "max_total_articles": 25,
}
```

**Or use environment variables** (more secure):

```bash
export AI_NEWS_EMAIL="jyothi.venkat23@gmail.com"
export AI_NEWS_APP_PASSWORD="abcd efgh ijkl mnop"
export AI_NEWS_API_KEY="your-newsapi-key"
```

---

## Step 5: Test It

```bash
python3 ai_news_agent.py
```

You should see log output and receive an email within seconds.

---

## Step 6: Schedule It to Run Twice Daily (8 AM & 7 PM)

### macOS (using cron)

1. Open **Terminal**
2. Run:

```bash
crontab -e
```

3. Add these two lines (adjust the path to where you saved the script):

```
0 8 * * * cd "/path/to/News Agent" && /usr/bin/python3 ai_news_agent.py >> ai_news.log 2>&1
0 19 * * * cd "/path/to/News Agent" && /usr/bin/python3 ai_news_agent.py >> ai_news.log 2>&1
```

**With environment variables:**

```
0 8 * * * AI_NEWS_EMAIL="missastroglow23@gmail.com" AI_NEWS_APP_PASSWORD="your-app-password" AI_NEWS_API_KEY="your-key" cd "/path/to/News Agent" && /usr/bin/python3 ai_news_agent.py >> ai_news.log 2>&1
0 19 * * * AI_NEWS_EMAIL="missastroglow23@gmail.com" AI_NEWS_APP_PASSWORD="your-app-password" AI_NEWS_API_KEY="your-key" cd "/path/to/News Agent" && /usr/bin/python3 ai_news_agent.py >> ai_news.log 2>&1
```

4. Save and exit (press `Esc`, then type `:wq` and press `Enter`)

**Tip:** To find the exact path to your folder, open Terminal and drag the News Agent folder into it — it will paste the full path.

**Note:** Your Mac must be awake at the scheduled times for cron to run. If your Mac is asleep, the job will be skipped. To verify your cron jobs are saved, run `crontab -l` in Terminal.

### Linux (using cron)

Same as macOS above — use `crontab -e` to add the two schedule lines.

### Windows (using Task Scheduler)

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task**
3. Name it `AI News Digest - Morning`
4. Set trigger to **Daily** at **8:00 AM**
5. Action: **Start a Program**
   - Program: `python3` (or full path like `C:\Python312\python.exe`)
   - Arguments: `C:\path\to\ai_news_agent.py`
6. Click **Finish**
7. Repeat steps 2–6 to create a second task named `AI News Digest - Evening` with trigger at **7:00 PM**

### Alternative: Use a Free Cloud Scheduler

If you want it to run even when your computer is off:

**GitHub Actions (free, 2000 min/month):**

Create `.github/workflows/ai-news.yml`:

```yaml
name: AI News Digest
on:
  schedule:
    - cron: '0 13 * * *'  # 8 AM EST = 1 PM UTC
    - cron: '0 0 * * *'   # 7 PM EST = 12 AM UTC
  workflow_dispatch:  # manual trigger

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
```

Then add your secrets in GitHub repo → Settings → Secrets → Actions.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `SMTPAuthenticationError` | Check your App Password is correct and 2FA is enabled |
| `No articles found` | Check internet connection; some RSS feeds may be temporarily down |
| Script runs but no email | Check your spam/junk folder |
| `ModuleNotFoundError` | Make sure you're using Python 3.10+ |

---

## Customization

**Add more RSS sources** — edit the `fetchers` list in `main()` and add new functions following the existing pattern.

**Change categories** — modify the `category` parameter when creating Articles.

**Adjust article count** — change `max_articles_per_source` and `max_total_articles` in CONFIG.
