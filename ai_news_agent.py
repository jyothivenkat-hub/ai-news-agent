#!/usr/bin/env python3
"""
AI News Daily Digest Agent v2.0
================================
Fetches AI news from 10 free sources including official blogs from
Anthropic, OpenAI, and Google DeepMind, then sends a premium-quality
HTML email digest to your Gmail every morning.

Free resources used:
- Anthropic News (web scraper, free)
- OpenAI Blog RSS (free)
- Google DeepMind Blog RSS (free)
- Google Research Blog RSS (free)
- NewsAPI.org (free tier: 100 requests/day)
- Google News RSS feeds (free)
- ArXiv API (free)
- HuggingFace Daily Papers RSS (free)
- TechCrunch AI RSS (free)
- MIT Technology Review RSS (free)
- The Verge AI RSS (free)

Setup:
1. Get a free NewsAPI key at https://newsapi.org/register
2. Create a Gmail App Password (see SETUP_GUIDE.md)
3. Fill in the config below
4. Run: python3 ai_news_agent.py
"""

import os
import ssl
import json
import re
import smtplib
import logging
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote_plus
from html import unescape
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# CONFIGURATION
# ============================================================
CONFIG = {
    # Your Gmail address (sender)
    "email": os.environ.get("AI_NEWS_EMAIL", "your-email@gmail.com"),

    # All recipients (add or remove emails here)
    "recipients": os.environ.get("AI_NEWS_RECIPIENTS", "your-email@gmail.com").split(","),

    # Gmail App Password (NOT your regular password)
    # Generate one at: https://myaccount.google.com/apppasswords
    # Spaces are stripped automatically (Gmail formats them as "xxxx xxxx xxxx xxxx")
    "app_password": os.environ.get("AI_NEWS_APP_PASSWORD", "").replace(" ", ""),

    # Free NewsAPI key from https://newsapi.org/register
    "newsapi_key": os.environ.get("AI_NEWS_API_KEY", ""),

    # Max articles per source
    "max_articles_per_source": 5,

    # Max total articles in the digest
    "max_total_articles": 30,

    # Number of top/highlighted stories
    "top_stories_count": 3,
}

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ai_news_agent")

# ============================================================
# News Article Model
# ============================================================
class Article:
    # Priority sources get boosted in ranking
    PRIORITY_SOURCES = {"Anthropic", "OpenAI", "Google DeepMind", "Google Research"}

    def __init__(self, title: str, url: str, source: str,
                 summary: str = "", published: str = "", category: str = "General AI",
                 is_official: bool = False):
        self.title = self._clean(title)
        self.url = url
        self.source = source
        self.summary = self._clean(summary)[:400]
        self.published = published
        self.category = category
        self.is_official = is_official or source in self.PRIORITY_SOURCES

    @staticmethod
    def _clean(text: str) -> str:
        if not text:
            return ""
        text = unescape(text)
        text = re.sub(r"<[^>]+>", "", text)  # strip HTML tags
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @property
    def reading_time(self) -> str:
        """Estimate reading time from summary length."""
        words = len(self.summary.split()) if self.summary else 0
        if words < 30:
            return "1 min"
        elif words < 80:
            return "2 min"
        else:
            return "3+ min"

    def __repr__(self):
        return f"Article({self.title[:50]}... | {self.source})"


# ============================================================
# Fetcher Utilities
# ============================================================
def fetch_url(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch URL content with error handling."""
    try:
        ctx = ssl.create_default_context()
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError, TimeoutError) as e:
        log.warning(f"Failed to fetch {url}: {e}")
        return None


def parse_rss(xml_text: str, source_name: str, category: str,
              max_items: int = 5, is_official: bool = False) -> list[Article]:
    """Parse an RSS/Atom feed into Article objects."""
    articles = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom",
              "content": "http://purl.org/rss/1.0/modules/content/",
              "dc": "http://purl.org/dc/elements/1.1/",
              "media": "http://search.yahoo.com/mrss/"}

        # Try RSS format first
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//atom:entry", ns)

        for item in items[:max_items]:
            title = (
                _get_text(item, "title") or
                _get_text(item, "atom:title", ns)
            )
            link = (
                _get_text(item, "link") or
                _get_attr(item, "atom:link", "href", ns) or
                _get_attr(item, "atom:link[@rel='alternate']", "href", ns)
            )
            desc = (
                _get_text(item, "description") or
                _get_text(item, "atom:summary", ns) or
                _get_text(item, "content:encoded", ns) or
                ""
            )
            pub = (
                _get_text(item, "pubDate") or
                _get_text(item, "atom:published", ns) or
                _get_text(item, "atom:updated", ns) or
                _get_text(item, "dc:date", ns) or
                ""
            )
            if title and link:
                articles.append(Article(title, link, source_name, desc, pub,
                                        category, is_official))
    except ET.ParseError as e:
        log.warning(f"XML parse error for {source_name}: {e}")
    return articles


def _get_text(elem, tag, ns=None):
    child = elem.find(tag, ns) if ns else elem.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _get_attr(elem, tag, attr, ns=None):
    child = elem.find(tag, ns) if ns else elem.find(tag)
    return child.get(attr) if child is not None else None


# ============================================================
# OFFICIAL AI COMPANY BLOGS (Priority Sources)
# ============================================================

def fetch_anthropic_news() -> list[Article]:
    """Fetch Anthropic/Claude news from their website (free, scraping)."""
    log.info("Fetching Anthropic News...")
    articles = []

    # Try the community-maintained RSS feed first
    rss_url = "https://raw.githubusercontent.com/conoro/anthropic-engineering-rss-feed/main/anthropic_engineering_rss.xml"
    xml = fetch_url(rss_url)
    if xml:
        articles.extend(parse_rss(xml, "Anthropic", "Official Announcements",
                                   max_items=CONFIG["max_articles_per_source"],
                                   is_official=True))

    # Also scrape the main news page for announcements
    html = fetch_url("https://www.anthropic.com/news")
    if html:
        # Extract article links and titles from the news page
        pattern = r'<a[^>]*href="(/news/[^"]+)"[^>]*>.*?</a>'
        title_pattern = r'<h[23][^>]*>(.*?)</h[23]>'

        # Simple extraction of news items
        links = re.findall(r'href="(/news/[^"]+)"', html)
        titles = re.findall(r'<h[23][^>]*class="[^"]*"[^>]*>(.*?)</h[23]>', html, re.DOTALL)

        seen_links = set()
        for link in links[:CONFIG["max_articles_per_source"]]:
            if link not in seen_links and link != "/news":
                seen_links.add(link)
                full_url = f"https://www.anthropic.com{link}"
                # Extract a rough title from the link slug
                slug_title = link.replace("/news/", "").replace("-", " ").title()
                articles.append(Article(
                    title=slug_title,
                    url=full_url,
                    source="Anthropic",
                    summary="Latest from Anthropic — makers of Claude AI.",
                    category="Official Announcements",
                    is_official=True,
                ))

    return articles


def fetch_openai_blog() -> list[Article]:
    """Fetch OpenAI blog/news via their official RSS feed (free)."""
    log.info("Fetching OpenAI Blog...")
    # Official OpenAI RSS feed
    url = "https://openai.com/news/rss.xml"
    xml = fetch_url(url)
    if not xml:
        # Fallback to old URL
        xml = fetch_url("https://openai.com/blog/rss.xml")
    if not xml:
        return []
    return parse_rss(xml, "OpenAI", "Official Announcements",
                     max_items=CONFIG["max_articles_per_source"],
                     is_official=True)


def fetch_google_deepmind() -> list[Article]:
    """Fetch Google DeepMind blog (free RSS)."""
    log.info("Fetching Google DeepMind Blog...")
    articles = []

    # Try the DeepMind blog RSS
    urls = [
        "https://deepmind.google/blog/feed/basic/",
        "https://deepmind.com/blog/feed/basic/",
    ]
    for url in urls:
        xml = fetch_url(url)
        if xml:
            articles.extend(parse_rss(xml, "Google DeepMind", "Official Announcements",
                                       max_items=CONFIG["max_articles_per_source"],
                                       is_official=True))
            break

    # Also try Google Research blog (covers Gemini, etc.)
    xml = fetch_url("https://blog.research.google/feeds/posts/default")
    if xml:
        articles.extend(parse_rss(xml, "Google Research", "Official Announcements",
                                   max_items=3, is_official=True))

    return articles


# ============================================================
# OTHER NEWS SOURCES
# ============================================================

def fetch_google_news_ai() -> list[Article]:
    """Fetch AI news from Google News RSS (free, no key needed)."""
    log.info("Fetching Google News AI...")
    queries = [
        "artificial+intelligence",
        "large+language+model",
        "generative+AI",
        "Claude+Anthropic+OR+ChatGPT+OpenAI+OR+Gemini+Google",
    ]
    articles = []
    for q in queries:
        url = f"https://news.google.com/rss/search?q={q}+when:1d&hl=en-US&gl=US&ceid=US:en"
        xml = fetch_url(url)
        if xml:
            articles.extend(parse_rss(xml, "Google News", "General AI",
                                       max_items=CONFIG["max_articles_per_source"]))
    return articles


def fetch_newsapi() -> list[Article]:
    """Fetch AI news from NewsAPI.org (free tier: 100 req/day)."""
    key = CONFIG["newsapi_key"]
    if key == "YOUR_NEWSAPI_KEY_HERE":
        log.info("Skipping NewsAPI (no key configured)")
        return []

    log.info("Fetching NewsAPI...")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Two targeted queries for better coverage
    queries = [
        "artificial+intelligence+OR+LLM+OR+generative+AI",
        "Anthropic+Claude+OR+OpenAI+ChatGPT+OR+Google+Gemini+OR+DeepMind",
    ]
    articles = []
    for q in queries:
        url = (
            f"https://newsapi.org/v2/everything?"
            f"q={q}&from={yesterday}&sortBy=relevancy&pageSize=5"
            f"&language=en&apiKey={key}"
        )
        data = fetch_url(url)
        if not data:
            continue
        try:
            resp = json.loads(data)
            for item in resp.get("articles", [])[:CONFIG["max_articles_per_source"]]:
                articles.append(Article(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source=f"NewsAPI / {item.get('source', {}).get('name', 'Unknown')}",
                    summary=item.get("description", ""),
                    published=item.get("publishedAt", ""),
                    category="LLMs & GenAI",
                ))
        except json.JSONDecodeError:
            log.warning("Failed to parse NewsAPI response")
    return articles


def fetch_arxiv_ai() -> list[Article]:
    """Fetch latest AI papers from ArXiv (free, unlimited)."""
    log.info("Fetching ArXiv AI papers...")
    url = (
        "https://export.arxiv.org/api/query?"
        "search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG"
        "&sortBy=submittedDate&sortOrder=descending&max_results=8"
    )
    xml = fetch_url(url, timeout=20)
    if not xml:
        return []

    articles = []
    try:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(xml)
        for entry in root.findall("atom:entry", ns)[:CONFIG["max_articles_per_source"]]:
            title = _get_text(entry, "atom:title", ns) or ""
            link_el = entry.find("atom:link[@rel='alternate']", ns)
            link = link_el.get("href") if link_el is not None else ""
            summary = _get_text(entry, "atom:summary", ns) or ""
            published = _get_text(entry, "atom:published", ns) or ""
            if title and link:
                articles.append(Article(title, link, "ArXiv", summary, published,
                                        "AI Research"))
    except ET.ParseError as e:
        log.warning(f"ArXiv XML parse error: {e}")
    return articles


def fetch_huggingface_papers() -> list[Article]:
    """Fetch HuggingFace Daily Papers (free)."""
    log.info("Fetching HuggingFace Daily Papers...")
    url = "https://huggingface.co/papers/rss"
    xml = fetch_url(url)
    if not xml:
        return []
    return parse_rss(xml, "HuggingFace Papers", "AI Research",
                     max_items=CONFIG["max_articles_per_source"])


def fetch_techcrunch_ai() -> list[Article]:
    """Fetch TechCrunch AI category RSS (free)."""
    log.info("Fetching TechCrunch AI...")
    url = "https://techcrunch.com/category/artificial-intelligence/feed/"
    xml = fetch_url(url)
    if not xml:
        return []
    return parse_rss(xml, "TechCrunch", "AI Business & Startups",
                     max_items=CONFIG["max_articles_per_source"])


def fetch_mit_tech_review() -> list[Article]:
    """Fetch MIT Technology Review RSS (free)."""
    log.info("Fetching MIT Technology Review AI...")
    url = "https://www.technologyreview.com/feed/"
    xml = fetch_url(url)
    if not xml:
        return []
    return parse_rss(xml, "MIT Tech Review", "AI Research & Policy",
                     max_items=CONFIG["max_articles_per_source"])


def fetch_the_verge_ai() -> list[Article]:
    """Fetch The Verge AI RSS (free)."""
    log.info("Fetching The Verge AI...")
    url = "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
    xml = fetch_url(url)
    if not xml:
        return []
    return parse_rss(xml, "The Verge", "General AI",
                     max_items=CONFIG["max_articles_per_source"])


# ============================================================
# Deduplication & Ranking
# ============================================================
def deduplicate(articles: list[Article]) -> list[Article]:
    """Remove near-duplicate articles by normalized title."""
    seen = set()
    unique = []
    for a in articles:
        key = re.sub(r"[^a-z0-9]", "", a.title.lower())[:60]
        if key not in seen and len(key) > 10:
            seen.add(key)
            unique.append(a)
    return unique


def rank_articles(articles: list[Article]) -> list[Article]:
    """Rank articles: official sources first, then by category diversity."""
    official = [a for a in articles if a.is_official]
    others = [a for a in articles if not a.is_official]
    return official + others


# ============================================================
# TLDR / Trending Summary Builder
# ============================================================
def build_tldr_summary(articles: list[Article], top_stories: list[Article]) -> str:
    """Build a TLDR trending summary section from the articles."""

    # --- Detect trending keywords/themes ---
    TRENDING_KEYWORDS = {
        "GPT": "GPT Models", "Claude": "Claude AI", "Gemini": "Gemini",
        "LLM": "Large Language Models", "AGI": "AGI", "Llama": "Llama",
        "open source": "Open Source AI", "open-source": "Open Source AI",
        "safety": "AI Safety", "regulation": "AI Regulation",
        "multimodal": "Multimodal AI", "vision": "AI Vision",
        "robotics": "AI Robotics", "autonomous": "Autonomous AI",
        "agent": "AI Agents", "agentic": "AI Agents",
        "reasoning": "AI Reasoning", "training": "Model Training",
        "fine-tun": "Fine-Tuning", "benchmark": "Benchmarks",
        "startup": "AI Startups", "funding": "AI Funding",
        "healthcare": "AI in Healthcare", "medical": "AI in Healthcare",
        "image": "Image Generation", "diffusion": "Image Generation",
        "video": "AI Video", "Sora": "AI Video",
        "chip": "AI Hardware", "GPU": "AI Hardware", "NVIDIA": "AI Hardware",
        "copyright": "AI & Copyright", "lawsuit": "AI Legal",
        "Anthropic": "Anthropic", "OpenAI": "OpenAI",
        "Google": "Google AI", "DeepMind": "DeepMind",
        "Meta": "Meta AI", "Microsoft": "Microsoft AI",
        "Apple": "Apple AI",
    }

    theme_counts = {}
    theme_articles = {}
    for a in articles:
        text = f"{a.title} {a.summary}".lower()
        matched_themes = set()
        for keyword, theme in TRENDING_KEYWORDS.items():
            if keyword.lower() in text and theme not in matched_themes:
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
                theme_articles.setdefault(theme, []).append(a)
                matched_themes.add(theme)

    # Sort by frequency, pick top 5 trending themes
    trending = sorted(theme_counts.items(), key=lambda x: -x[1])[:5]

    # --- Build TLDR bullets from top stories ---
    tldr_bullets = ""
    for a in top_stories[:4]:
        short_summary = a.summary[:120].rstrip()
        if len(a.summary) > 120:
            short_summary = short_summary.rsplit(" ", 1)[0] + "..."
        tldr_bullets += f"""
            <tr>
                <td style="padding:6px 10px 6px 0;vertical-align:top;color:#6366F1;font-size:16px;">&#x25B8;</td>
                <td style="padding:6px 0;">
                    <a href="{a.url}" style="color:#1E293B;text-decoration:none;font-size:14px;font-weight:600;line-height:1.4;">{a.title}</a>
                    <div style="color:#64748B;font-size:12px;margin-top:2px;">{short_summary}</div>
                </td>
            </tr>"""

    # --- Build trending tags ---
    tag_colors = ["#6366F1", "#EC4899", "#F59E0B", "#10B981", "#3B82F6"]
    trending_tags = ""
    for i, (theme, count) in enumerate(trending):
        color = tag_colors[i % len(tag_colors)]
        trending_tags += f'<span style="display:inline-block;background:{color}15;color:{color};border:1px solid {color}30;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;margin:3px 4px;">&#x1F525; {theme} ({count})</span>'

    # --- Category breakdown mini-stats ---
    cat_counts = {}
    for a in articles:
        cat_counts[a.category] = cat_counts.get(a.category, 0) + 1

    # --- Compose TLDR section ---
    tldr_html = f"""
    <!-- TLDR Summary -->
    <div style="background:linear-gradient(135deg,#EEF2FF 0%,#F0FDFA 50%,#FFF7ED 100%);padding:24px;border-bottom:1px solid #E5E7EB;">
        <div style="margin-bottom:16px;">
            <span style="background:#0F172A;color:#FFFFFF;padding:4px 12px;border-radius:4px;font-size:11px;font-weight:800;letter-spacing:1.5px;">&#x26A1; TLDR</span>
        </div>
        <p style="color:#334155;font-size:15px;font-weight:600;line-height:1.6;margin:0 0 14px 0;">
            Today's digest covers {len(articles)} stories from {len(set(a.source.split(' / ')[0] for a in articles))} sources.
            {"The big players making news today: " + ", ".join(t for t, _ in trending[:3]) + "." if trending else ""}
        </p>
        <table style="width:100%;border-collapse:collapse;">
            {tldr_bullets}
        </table>
    </div>

    <!-- Trending Now -->
    <div style="padding:18px 24px;background:#FAFAFE;border-bottom:1px solid #E5E7EB;">
        <p style="color:#0F172A;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;margin:0 0 10px 0;">
            &#x1F4C8; TRENDING NOW
        </p>
        <div style="line-height:2.2;">
            {trending_tags}
        </div>
    </div>"""

    return tldr_html


# ============================================================
# Email Builder — Premium Quality
# ============================================================
def build_email_html(articles: list[Article]) -> str:
    """Build a premium-quality HTML email from the articles."""
    today = datetime.now().strftime("%A, %B %d, %Y")
    time_now = datetime.now().strftime("%I:%M %p")

    # Rank articles
    articles = rank_articles(articles)

    # Top stories (first N official/priority articles)
    top_stories = [a for a in articles if a.is_official][:CONFIG["top_stories_count"]]
    if len(top_stories) < CONFIG["top_stories_count"]:
        top_stories += [a for a in articles if a not in top_stories][
            :CONFIG["top_stories_count"] - len(top_stories)]

    # Build TLDR summary
    tldr_html = build_tldr_summary(articles, top_stories)

    # Group remaining by category
    categories = {}
    for a in articles:
        if a not in top_stories:
            categories.setdefault(a.category, []).append(a)

    # Category config: name -> (color, emoji)
    cat_config = {
        "Official Announcements": ("#6366F1", "&#x1F3E2;"),
        "General AI": ("#3B82F6", "&#x1F4F0;"),
        "LLMs & GenAI": ("#8B5CF6", "&#x1F9E0;"),
        "AI Business & Startups": ("#10B981", "&#x1F4B0;"),
        "AI Research": ("#F59E0B", "&#x1F52C;"),
        "AI Research & Policy": ("#EF4444", "&#x1F3DB;"),
    }

    # Source logos/icons mapping
    source_icons = {
        "Anthropic": "&#x1F7E0;",
        "OpenAI": "&#x1F7E2;",
        "Google DeepMind": "&#x1F535;",
        "Google Research": "&#x1F535;",
        "ArXiv": "&#x1F4D1;",
        "HuggingFace Papers": "&#x1F917;",
        "TechCrunch": "&#x1F4F1;",
        "MIT Tech Review": "&#x1F393;",
        "The Verge": "&#x25B6;",
        "Google News": "&#x1F310;",
    }

    # --- Build Top Stories Section ---
    top_html = ""
    for i, a in enumerate(top_stories):
        icon = source_icons.get(a.source, "&#x2B50;")
        border_color = "#6366F1" if a.is_official else "#3B82F6"
        top_html += f"""
        <div style="background:#FAFAFE;border-left:4px solid {border_color};padding:16px 18px;margin-bottom:12px;border-radius:0 8px 8px 0;">
            <div style="font-size:11px;color:#6366F1;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px;">
                {icon} {a.source}
            </div>
            <a href="{a.url}" style="color:#111827;text-decoration:none;font-size:17px;font-weight:700;line-height:1.4;display:block;">
                {a.title}
            </a>
            <p style="color:#6B7280;font-size:13px;line-height:1.6;margin:8px 0 0 0;">{a.summary}</p>
            <div style="margin-top:8px;">
                <span style="color:#9CA3AF;font-size:11px;">{a.reading_time} read</span>
            </div>
        </div>"""

    # --- Build Category Sections ---
    sections_html = ""

    # Order categories: Official first, then the rest
    ordered_cats = []
    if "Official Announcements" in categories:
        ordered_cats.append("Official Announcements")
    for cat in ["LLMs & GenAI", "AI Business & Startups", "AI Research",
                "AI Research & Policy", "General AI"]:
        if cat in categories:
            ordered_cats.append(cat)

    for cat in ordered_cats:
        arts = categories[cat]
        color, emoji = cat_config.get(cat, ("#6B7280", "&#x1F4CC;"))
        items = ""
        for a in arts:
            icon = source_icons.get(a.source.split(" / ")[0], "&#x1F4CC;")
            official_badge = ""
            if a.is_official:
                official_badge = '<span style="background:#EEF2FF;color:#4F46E5;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;margin-left:6px;">OFFICIAL</span>'

            summary_html = ""
            if a.summary:
                summary_html = f'<p style="color:#6B7280;font-size:13px;line-height:1.5;margin:6px 0 0 0;">{a.summary[:200]}{"..." if len(a.summary) > 200 else ""}</p>'

            items += f"""
            <div style="padding:14px 0;border-bottom:1px solid #F3F4F6;">
                <a href="{a.url}" style="color:#1F2937;text-decoration:none;font-size:15px;font-weight:600;line-height:1.4;">
                    {a.title}
                </a>
                <div style="margin-top:6px;display:flex;align-items:center;gap:8px;">
                    <span style="background:{color}12;color:{color};padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;">
                        {icon} {a.source}
                    </span>
                    {official_badge}
                    <span style="color:#D1D5DB;font-size:11px;">&#x2022;</span>
                    <span style="color:#9CA3AF;font-size:11px;">{a.reading_time} read</span>
                </div>
                {summary_html}
            </div>"""

        sections_html += f"""
        <div style="margin-bottom:28px;">
            <h2 style="color:{color};font-size:14px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:0 0 12px 0;padding-bottom:8px;border-bottom:2px solid {color};">
                {emoji} {cat}
            </h2>
            {items}
        </div>"""

    # --- Source Stats ---
    source_counts = {}
    for a in articles:
        base_source = a.source.split(" / ")[0]
        source_counts[base_source] = source_counts.get(base_source, 0) + 1

    stats_html = ""
    for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        icon = source_icons.get(src, "&#x1F4CC;")
        stats_html += f'<span style="display:inline-block;background:#F3F4F6;padding:3px 10px;border-radius:12px;font-size:11px;color:#6B7280;margin:3px 4px;">{icon} {src}: {count}</span>'

    # --- Full Email ---
    total_sources = len(source_counts)
    official_count = sum(1 for a in articles if a.is_official)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F0F1F5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',sans-serif;">
<div style="max-width:640px;margin:0 auto;background:#FFFFFF;box-shadow:0 1px 3px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#0F172A 0%,#1E293B 40%,#312E81 100%);padding:36px 28px;text-align:center;">
        <div style="font-size:36px;margin-bottom:8px;">&#x1F916;</div>
        <h1 style="color:#FFFFFF;font-size:28px;font-weight:800;margin:0 0 6px 0;letter-spacing:-0.5px;">AI Daily Digest</h1>
        <p style="color:#94A3B8;font-size:14px;margin:0;">{today} &#x2022; {time_now}</p>
        <div style="margin-top:14px;display:inline-block;">
            <span style="background:rgba(255,255,255,0.12);color:#E2E8F0;padding:4px 14px;border-radius:20px;font-size:12px;font-weight:500;">
                {len(articles)} stories &#x2022; {total_sources} sources &#x2022; {official_count} official posts
            </span>
        </div>
    </div>

    {tldr_html}

    <!-- Top Stories -->
    <div style="padding:24px 24px 8px 24px;">
        <h2 style="color:#0F172A;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;margin:0 0 16px 0;">
            &#x2B50; TOP STORIES
        </h2>
        {top_html}
    </div>

    <!-- Divider -->
    <div style="padding:0 24px;">
        <hr style="border:none;border-top:1px solid #E5E7EB;margin:16px 0;">
    </div>

    <!-- All Stories by Category -->
    <div style="padding:8px 24px 24px 24px;">
        {sections_html}
    </div>

    <!-- Source Breakdown -->
    <div style="background:#F8FAFC;padding:20px 24px;border-top:1px solid #E5E7EB;">
        <p style="color:#64748B;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin:0 0 10px 0;">
            Sources Used Today
        </p>
        <div style="line-height:2;">
            {stats_html}
        </div>
    </div>

    <!-- Footer -->
    <div style="background:#0F172A;padding:24px;text-align:center;">
        <p style="color:#64748B;font-size:11px;margin:0 0 4px 0;">
            AI Daily Digest v2.0 &#x2022; Your personal AI news agent
        </p>
        <p style="color:#475569;font-size:10px;margin:0;">
            Featuring official blogs from Anthropic, OpenAI &amp; Google DeepMind<br>
            Powered by free APIs &#x2022; No subscriptions required
        </p>
    </div>

</div>
</body>
</html>"""


# ============================================================
# Email Sender
# ============================================================
def send_email(html_body: str, article_count: int):
    """Send the digest email via Gmail SMTP."""
    today = datetime.now().strftime("%b %d, %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"AI Daily Digest — {today} ({article_count} stories)"
    msg["From"] = f"AI News Agent <{CONFIG['email']}>"
    recipients = CONFIG.get("recipients", [CONFIG["email"]])
    msg["To"] = ", ".join(recipients)

    # Plain text fallback
    plain = f"Your AI Daily Digest for {today} — {article_count} stories. View in an HTML-enabled email client for the best experience."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    log.info(f"Sending email to {', '.join(recipients)}...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(CONFIG["email"], CONFIG["app_password"])
            server.sendmail(CONFIG["email"], recipients, msg.as_string())
        log.info("Email sent successfully!")
    except Exception as e:
        log.error(f"Failed to send email: {e}")
        # Save as fallback HTML file
        fallback = os.path.expanduser(f"~/ai_digest_{datetime.now().strftime('%Y%m%d')}.html")
        with open(fallback, "w") as f:
            f.write(html_body)
        log.info(f"Saved HTML fallback to {fallback}")
        raise


# ============================================================
# Main Agent
# ============================================================
def main():
    log.info("=" * 55)
    log.info("  AI News Daily Digest Agent v2.0 — Starting")
    log.info("=" * 55)

    # All fetchers — official sources listed first
    fetchers = [
        # Priority: Official AI company blogs
        fetch_anthropic_news,
        fetch_openai_blog,
        fetch_google_deepmind,
        # News aggregators
        fetch_google_news_ai,
        fetch_newsapi,
        # Research
        fetch_arxiv_ai,
        fetch_huggingface_papers,
        # Tech media
        fetch_techcrunch_ai,
        fetch_mit_tech_review,
        fetch_the_verge_ai,
    ]

    # Fetch all sources in parallel for speed
    all_articles = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(f): f.__name__ for f in fetchers}
        for future in as_completed(futures):
            name = futures[future]
            try:
                articles = future.result()
                log.info(f"  -> {name}: {len(articles)} articles")
                all_articles.extend(articles)
            except Exception as e:
                log.warning(f"  -> {name} failed: {e}")

    # Deduplicate and limit
    all_articles = deduplicate(all_articles)
    all_articles = all_articles[:CONFIG["max_total_articles"]]

    official = sum(1 for a in all_articles if a.is_official)
    log.info(f"Total: {len(all_articles)} unique articles ({official} from official sources)")

    if not all_articles:
        log.warning("No articles found! Check your internet connection.")
        return

    # Build and send email
    html = build_email_html(all_articles)
    send_email(html, len(all_articles))

    log.info("Done! Check your inbox.")


if __name__ == "__main__":
    main()
