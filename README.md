# AI News Daily Digest Agent

A Python script that automatically fetches AI news from **10 free sources** and emails you a beautifully formatted HTML digest — twice daily.

## Sources

- Anthropic News
- OpenAI Blog RSS
- Google DeepMind Blog RSS
- Google Research Blog RSS
- NewsAPI.org (free tier)
- Google News RSS
- ArXiv API
- HuggingFace Daily Papers RSS
- TechCrunch AI RSS
- MIT Technology Review RSS
- The Verge AI RSS

## Quick Start

1. Get a free [NewsAPI key](https://newsapi.org/register) (optional but recommended)
2. Create a [Gmail App Password](https://myaccount.google.com/apppasswords)
3. Set your environment variables:

```bash
export AI_NEWS_EMAIL="your-email@gmail.com"
export AI_NEWS_APP_PASSWORD="your-16-char-app-password"
export AI_NEWS_API_KEY="your-newsapi-key"
export AI_NEWS_RECIPIENTS="email1@gmail.com,email2@gmail.com"
```

4. Run:

```bash
python3 ai_news_agent.py
```

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for full setup instructions including scheduling (cron, Task Scheduler, GitHub Actions).

## Requirements

- Python 3.10+
- No external packages needed (uses only Python standard library)

## License

MIT
