#!/usr/bin/env python3
"""AI Newsletter Bot using OpenClaw WhatsApp channel.

Features:
- Fetches AI-related items from RSS feeds and optional NewsAPI.
- Ranks by recency and popularity.
- Sends a formatted newsletter to WhatsApp via OpenClaw gateway on a schedule.

Notes:
- This uses the OpenClaw HTTP API to send messages (no Telegram dependencies).
- Run it on the same host as the OpenClaw Gateway (or set OPENCLAW_BASE_URL).
"""

from __future__ import annotations

import asyncio
import dataclasses
import html
import math
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import aiohttp
import feedparser
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bs4 import BeautifulSoup


# -----------------------------
# Configuration (env overrides)
# -----------------------------
# OpenClaw delivery
OPENCLAW_BASE_URL = os.getenv("OPENCLAW_BASE_URL", "http://127.0.0.1:18789").rstrip("/")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "").strip()

# Messaging channel + target
# - channel: whatsapp|feishu|...
# - target: for WhatsApp use E.164 phone (e.g. +1587...), for Feishu omit to reply in current chat
CHANNEL = os.getenv("OPENCLAW_CHANNEL", "whatsapp").strip().lower()
TARGET = os.getenv("OPENCLAW_TARGET", os.getenv("WHATSAPP_TARGET", "+15876677928")).strip()
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()
RUN_EVERY_HOURS = int(os.getenv("RUN_EVERY_HOURS", "6"))
RUN_ON_START = os.getenv("RUN_ON_START", "1").strip() != "0"
# When invoked by run.sh (cron/reminder), we want to run once and exit.
RUN_ONCE_AND_EXIT = os.getenv("RUN_ONCE_AND_EXIT", "0").strip() != "0"

# Only include news since last trigger. Default: last 6 hours.
WINDOW_HOURS = float(os.getenv("WINDOW_HOURS", "6"))

# Enable/disable bilingual output.
INCLUDE_ZH = os.getenv("INCLUDE_ZH", "1").strip() != "0"
INCLUDE_EN = os.getenv("INCLUDE_EN", "1").strip() != "0"

# Scoring weights
RECENCY_WEIGHT = float(os.getenv("RECENCY_WEIGHT", "0.75"))
POPULARITY_WEIGHT = float(os.getenv("POPULARITY_WEIGHT", "0.25"))
RECENCY_HALF_LIFE_HOURS = float(os.getenv("RECENCY_HALF_LIFE_HOURS", "48"))

# Category quotas
CATEGORY_QUOTAS = {
    "Product": 3,
    "Policy": 2,
    "Business": 5,
}

TOTAL_ITEMS = int(os.getenv("TOTAL_ITEMS", str(sum(CATEGORY_QUOTAS.values()))))

# RSS sources (edit as needed)
RSS_SOURCES = [
    # Official / labs
    {"name": "Google AI Blog", "url": "https://ai.googleblog.com/atom.xml", "category": "Product"},
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss/", "category": "Product"},
    {"name": "OpenAI - Releases", "url": "https://openai.com/releases/rss/", "category": "Product"},
    {"name": "Anthropic News", "url": "https://www.anthropic.com/news/rss.xml", "category": "Product"},
    {"name": "DeepMind Blog", "url": "https://deepmind.google/blog/rss.xml", "category": "Product"},
    {"name": "Google AI Blog", "url": "https://ai.googleblog.com/atom.xml", "category": "Product"},
    {"name": "Microsoft Research Blog", "url": "https://www.microsoft.com/en-us/research/feed/", "category": "Product"},
    {"name": "Microsoft Blog", "url": "https://blogs.microsoft.com/feed/", "category": "Business"},
    {"name": "Meta Newsroom", "url": "https://about.fb.com/news/feed/", "category": "Business"},
    {"name": "NVIDIA Developer Blog", "url": "https://developer.nvidia.com/blog/feed/", "category": "Product"},

    # (Removed) Community aggregators (HN/Reddit) — too noisy for "latest reliable AI news".

    # Policy
    {"name": "White House Statements", "url": "https://www.whitehouse.gov/briefing-room/statements-releases/feed/", "category": "Policy"},

    # Media (AI-focused or high-signal tech)
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/tag/artificial-intelligence/feed/", "category": "Business"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/artificial-intelligence/rss/index.xml", "category": "Business"},
    {"name": "MIT Technology Review - AI", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed/", "category": "Business"},
    {"name": "Wired - AI", "url": "https://www.wired.com/tag/artificial-intelligence/rss", "category": "Business"},
    {"name": "Ars Technica - AI", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "category": "Business"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/", "category": "Business"},
    {"name": "AI News (aggregated)", "url": "https://www.artificialintelligence-news.com/feed/", "category": "Business"},
    {"name": "The Decoder (AI)", "url": "https://the-decoder.com/feed/", "category": "Business"},

    # Chinese sources (RSS)
    {"name": "量子位", "url": "https://www.qbitai.com/feed", "category": "Business"},
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "category": "Business"},
    {"name": "36氪-人工智能", "url": "https://36kr.com/tags/%E4%BA%BA%E5%B7%A5%E6%99%BA%E8%83%BD/feed", "category": "Business"},
]

# NewsAPI queries (optional; requires NEWSAPI_KEY)
NEWSAPI_QUERIES = [
    {"query": "AI model release OR foundation model", "category": "Product"},
    {"query": "AI regulation OR AI policy OR AI Act", "category": "Policy"},
    {"query": "AI startup OR AI funding OR AI acquisition", "category": "Business"},
]


# -----------------------------
# Data model
# -----------------------------
@dataclasses.dataclass
class NewsItem:
    title: str
    url: str
    published: datetime
    source: str
    category: str
    summary: str
    recency: float
    popularity: float

    @property
    def score(self) -> float:
        return RECENCY_WEIGHT * self.recency + POPULARITY_WEIGHT * self.popularity


# -----------------------------
# Utilities
# -----------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return _now_utc()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return _now_utc()


def recency_score(published: datetime) -> float:
    age_hours = max(0.0, (_now_utc() - published).total_seconds() / 3600.0)
    # Exponential decay; 1.0 when fresh, ~0.5 at half-life.
    return math.exp(-age_hours / max(1.0, RECENCY_HALF_LIFE_HOURS))


def normalize(values: List[float]) -> List[float]:
    if not values:
        return []
    v_min = min(values)
    v_max = max(values)
    if abs(v_max - v_min) < 1e-9:
        return [0.5 for _ in values]
    return [(v - v_min) / (v_max - v_min) for v in values]


def clean_text(text: str) -> str:
    raw = text or ""
    # Strip HTML tags if present (common in RSS summaries).
    if "<" in raw and ">" in raw:
        raw = BeautifulSoup(raw, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", raw).strip()


# -----------------------------
# Fetchers
# -----------------------------

def fetch_rss_source(source: Dict[str, str]) -> List[NewsItem]:
    # feedparser.parse can hang if a feed stalls; set a socket timeout.
    import socket
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(20)
    try:
        feed = feedparser.parse(source["url"])
    finally:
        socket.setdefaulttimeout(old_timeout)

    items: List[NewsItem] = []

    for entry in feed.entries:
        title = clean_text(entry.get("title", "Untitled"))
        url = entry.get("link", "")
        if not url:
            continue

        published_raw = entry.get("published") or entry.get("updated") or entry.get("pubDate")
        published = parse_datetime(published_raw)

        summary = clean_text(entry.get("summary", ""))
        rec = recency_score(published)

        # Optional popularity hints (HN provides 'comments' sometimes; others may provide 'score')
        popularity = 0.0
        for key in ("score", "points", "comments"):
            if key in entry:
                try:
                    popularity = float(entry.get(key, 0))
                except Exception:
                    popularity = 0.0
                break

        items.append(
            NewsItem(
                title=title,
                url=url,
                published=published,
                source=source["name"],
                category=source["category"],
                summary=summary,
                recency=rec,
                popularity=popularity,
            )
        )

    # Normalize popularity within this feed so we can compare fairly later
    pops = normalize([i.popularity for i in items])
    for item, pop in zip(items, pops):
        item.popularity = pop

    return items


def fetch_all_rss() -> List[NewsItem]:
    all_items: List[NewsItem] = []
    for source in RSS_SOURCES:
        try:
            all_items.extend(fetch_rss_source(source))
        except Exception:
            # Skip broken feeds; keep the bot running
            continue
    return all_items


async def fetch_newsapi_items(session: aiohttp.ClientSession, query: str, category: str, language: str = "en") -> List[NewsItem]:
    if not NEWSAPI_KEY:
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": language,
        "sortBy": "popularity",
        "pageSize": 50,
        "apiKey": NEWSAPI_KEY,
    }

    items: List[NewsItem] = []

    async with session.get(url, params=params, timeout=30) as resp:
        if resp.status != 200:
            return []
        payload = await resp.json()

    for art in payload.get("articles", []):
        title = clean_text(art.get("title") or "Untitled")
        url = art.get("url") or ""
        if not url:
            continue
        published = parse_datetime(art.get("publishedAt"))
        summary = clean_text(art.get("description") or "")
        rec = recency_score(published)

        # NewsAPI already sorts by popularity; use a light constant
        items.append(
            NewsItem(
                title=title,
                url=url,
                published=published,
                source=art.get("source", {}).get("name", "NewsAPI"),
                category=category,
                summary=summary,
                recency=rec,
                popularity=0.6,
            )
        )

    return items


async def fetch_all_newsapi() -> List[NewsItem]:
    if not NEWSAPI_KEY:
        return []
    async with aiohttp.ClientSession() as session:
        tasks = []
        if INCLUDE_EN:
            tasks.extend([fetch_newsapi_items(session, q["query"], q["category"], language="en") for q in NEWSAPI_QUERIES])
        if INCLUDE_ZH:
            tasks.extend([fetch_newsapi_items(session, q["query"], q["category"], language="zh") for q in NEWSAPI_QUERIES])
        results = await asyncio.gather(*tasks, return_exceptions=True)

    items: List[NewsItem] = []
    for res in results:
        if isinstance(res, Exception):
            continue
        items.extend(res)
    return items


def _window_start_utc() -> datetime:
    return _now_utc() - timedelta(hours=WINDOW_HOURS)


async def fetch_all_items() -> List[NewsItem]:
    rss_items = await asyncio.to_thread(fetch_all_rss)
    newsapi_items = await fetch_all_newsapi()
    items = rss_items + newsapi_items

    # De-duplicate by URL
    seen: set[str] = set()
    deduped: List[NewsItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        deduped.append(item)

    # Only keep items in the time window (between last trigger and now).
    window_start = _window_start_utc()
    deduped = [i for i in deduped if i.published >= window_start]

    return deduped


# -----------------------------
# Ranking + formatting
# -----------------------------

PREFERRED_SOURCES = {
    # Official / labs
    "OpenAI Blog",
    "Anthropic News",
    "Google AI Blog",
    "DeepMind Blog",
    "Microsoft Blog",
    "Meta Newsroom",
    "NVIDIA Developer Blog",
}


def source_boost(source: str, url: str) -> float:
    s = (source or "").lower()
    u = (url or "").lower()
    # Strong preference for official sources
    if any(k in s for k in ("openai", "anthropic", "deepmind", "google ai", "nvidia", "microsoft", "meta")):
        return 1.25
    # Medium preference for high-signal media
    if any(k in s for k in ("mit technology review", "wired", "financial times", "the decoder", "the information", "reuters")):
        return 1.10
    # If URL looks like a newsroom / press-release page
    if any(k in u for k in ("/news", "/newsroom", "/press", "/press-release", "/research")):
        return 1.05
    return 1.0


def _looks_like_noise(url: str, source: str) -> bool:
    u = (url or "").lower()
    s = (source or "").lower()
    # Filter out obvious non-news / community posts.
    noisy_domains = [
        "github.com",
        "reddit.com",
        "news.ycombinator.com",
        "hnrss.org",
        "medium.com",
        "substack.com",
    ]
    if any(d in u for d in noisy_domains):
        return True
    if any(k in s for k in ("hacker news", "reddit", "github")):
        return True
    return False


def select_top_items(items: List[NewsItem]) -> List[NewsItem]:
    # Normalize recency + popularity across all items
    recs = normalize([i.recency for i in items])
    pops = normalize([i.popularity for i in items])
    for item, rec, pop in zip(items, recs, pops):
        item.recency = rec
        item.popularity = pop

    # Hard filter: remove noisy/community links.
    items = [i for i in items if not _looks_like_noise(i.url, i.source)]

    grouped: Dict[str, List[NewsItem]] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)

    # Apply source boost into popularity channel (bounded), so it affects ranking.
    for it in items:
        it.popularity = min(1.0, max(0.0, it.popularity * source_boost(it.source, it.url)))

    selected: List[NewsItem] = []
    remaining: List[NewsItem] = []

    for category, quota in CATEGORY_QUOTAS.items():
        candidates = sorted(grouped.get(category, []), key=lambda x: x.score, reverse=True)
        take = candidates[:quota]
        selected.extend(take)
        remaining.extend(candidates[quota:])

    # If any category is short, backfill from remaining by score
    total_needed = TOTAL_ITEMS
    if len(selected) < total_needed:
        remaining_sorted = sorted(remaining, key=lambda x: x.score, reverse=True)
        selected.extend(remaining_sorted[: total_needed - len(selected)])

    # Final sort: category order then score
    category_order = list(CATEGORY_QUOTAS.keys())
    selected.sort(
        key=lambda x: (
            category_order.index(x.category) if x.category in category_order else 999,
            -x.score,
        )
    )

    return selected[:total_needed]


TZ_DISPLAY = os.getenv("TZ_DISPLAY", "Asia/Shanghai")


def _fmt_time_minute(dt: datetime) -> str:
    # Prefer local display time (default: Beijing time).
    # We avoid zoneinfo dependency issues by using a fixed offset for Asia/Shanghai.
    if TZ_DISPLAY in ("Asia/Shanghai", "CST", "UTC+8", "GMT+8"):
        tz = timezone(timedelta(hours=8))
        suffix = "(Beijing)"
    else:
        tz = timezone.utc
        suffix = "(UTC)"
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") + f" {suffix}"


def _bold(text: str) -> str:
    # Emphasis across channels:
    # - WhatsApp supports *bold*
    # - Feishu supports **bold** (Markdown-like)
    if not text:
        return ""
    if CHANNEL == "feishu":
        return f"**{text}**"
    return f"*{text}*"


def extract_keywords(item: NewsItem) -> List[str]:
    # Lightweight heuristics. Prefer a few high-signal tokens.
    text = f"{item.title} {item.summary}".lower()
    candidates = [
        "openai",
        "anthropic",
        "google",
        "deepmind",
        "meta",
        "microsoft",
        "nvidia",
        "llm",
        "agent",
        "agents",
        "diffusion",
        "benchmark",
        "alignment",
        "safety",
        "policy",
        "regulation",
        "ai act",
        "funding",
        "acquisition",
        "chip",
        "robot",
    ]
    found: List[str] = []
    for c in candidates:
        if c in text:
            found.append(c.upper() if len(c) <= 6 else c.title())
        if len(found) >= 4:
            break
    return found


def detect_domain(item: NewsItem) -> str:
    cat = (item.category or "").lower()
    if cat == "policy":
        return "Policy"
    if cat == "product":
        return "Product"
    return "Business"


def short_abstract_en(text: str, max_words: int = 100) -> str:
    words = clean_text(text).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip() + "…"


def short_abstract_zh(text: str, max_chars: int = 50) -> str:
    s = clean_text(text)
    if len(s) <= max_chars:
        return s
    return s[:max_chars].rstrip() + "…"


def format_item_pretty(item: NewsItem, idx: int) -> str:
    kws = extract_keywords(item)
    domain = detect_domain(item)
    when = _fmt_time_minute(item.published)
    title = item.title.strip()
    source = item.source.strip()
    summary = item.summary.strip() or title

    # Bilingual abstracts from available summary (best-effort; not MT).
    en_abs = short_abstract_en(summary, 100) if INCLUDE_EN else ""
    zh_abs = short_abstract_zh(summary, 50) if INCLUDE_ZH else ""

    kw_str = "、".join([_bold(k) for k in kws]) if kws else ""

    # A slightly nicer, emoji-led layout for Feishu; still readable in WhatsApp.
    parts = [
        f"{_bold(f'{idx:02d}.')}  🧭 {_bold(domain)} · ⏱️ {_bold(when)}",
        f"📰 {_bold(title)}\n🏷️ {source}",
    ]
    if kw_str:
        parts.append(f"✨ {_bold('关键词')}: {kw_str}")
    if INCLUDE_ABSTRACT:
        if INCLUDE_ZH and zh_abs:
            parts.append(f"📌 {_bold('要点')}: {zh_abs}")
        if INCLUDE_EN and en_abs:
            parts.append(f"🗒️ {_bold('Notes')}: {en_abs}")
    parts.append(f"🔗 {_bold('链接')}: {item.url}")

    return "\n".join(parts)


MAX_WA_MSG_CHARS = int(os.getenv("MAX_WA_MSG_CHARS", "3500"))
INCLUDE_ABSTRACT = os.getenv("INCLUDE_ABSTRACT", "1").strip() != "0"


def build_one_message(items: List[NewsItem]) -> str:
    window_start = _window_start_utc()
    header = "\n".join(
        [
            f"{_bold('AI NEWSLETTER')}  ·  {_bold(_fmt_time_minute(_now_utc()))}",
            f"窗口: {_fmt_time_minute(window_start)} → {_fmt_time_minute(_now_utc())}",
            "—" * 28,
        ]
    )

    def render(with_abstract: bool, itms: List[NewsItem]) -> str:
        lines: List[str] = []
        for idx, item in enumerate(itms, 1):
            # INCLUDE_ABSTRACT is a module-level flag; emulate it without recursion.
            if not with_abstract:
                # Temporarily blank summaries by setting a sentinel env var is messy;
                # simplest: rely on INCLUDE_ABSTRACT check inside format_item_pretty.
                pass
            lines.append(format_item_pretty(item, idx) if with_abstract else _strip_abstract(format_item_pretty(item, idx)))
            lines.append("—" * 28)
        body = "\n".join(lines).rstrip()
        return f"{header}\n{body}".strip()

    def _strip_abstract(block: str) -> str:
        # Remove lines starting with abstract markers.
        out = []
        for ln in block.splitlines():
            if ln.startswith("📌 ") or ln.startswith("🗒️ "):
                continue
            out.append(ln)
        return "\n".join(out)

    max_chars = MAX_WA_MSG_CHARS

    msg = render(INCLUDE_ABSTRACT, items)

    # If too long, try dropping abstracts first.
    if len(msg) > max_chars and INCLUDE_ABSTRACT:
        msg = render(False, items)

    # If still too long, truncate tail items.
    while len(msg) > max_chars and len(items) > 1:
        items = items[:-1]
        msg = render(False, items)

    return msg


def chunk_messages(lines: List[str], header: str) -> List[str]:
    # WhatsApp practical limit is lower than Telegram HTML; keep chunks conservative.
    MAX_CHARS = 3500
    messages: List[str] = []
    current = header
    for line in lines:
        if len(current) + len(line) + 2 > MAX_CHARS:
            messages.append(current)
            current = header
        current += "\n\n" + line
    if current.strip():
        messages.append(current)
    return messages


def build_messages(items: List[NewsItem]) -> List[str]:
    timestamp = _now_utc().strftime("%Y-%m-%d %H:%M UTC")
    header = f"AI Newsletter — {timestamp}"

    lines: List[str] = []
    by_category: Dict[str, List[NewsItem]] = {}
    for item in items:
        by_category.setdefault(item.category, []).append(item)

    for category in CATEGORY_QUOTAS.keys():
        entries = by_category.get(category, [])
        if not entries:
            continue
        lines.append(f"[{category}]")
        for i, item in enumerate(entries, 1):
            lines.append(f"{i}. {format_item(item)}")

    return chunk_messages(lines, header)


# -----------------------------
# OpenClaw send + scheduler
# -----------------------------

async def openclaw_send_text(session: aiohttp.ClientSession, text: str) -> None:
    # Note: the gateway HTTP endpoint for sending is not guaranteed stable across versions.
    # We use the OpenClaw CLI (which talks to the gateway correctly) for reliability.
    if not OPENCLAW_TOKEN:
        raise SystemExit("Set OPENCLAW_TOKEN (gateway auth token) in the environment.")

    import subprocess

    ACCOUNT_ID = os.getenv("OPENCLAW_ACCOUNT_ID", "")
    cmd = [
        "openclaw",
        "message",
        "send",
        "--channel",
        CHANNEL,
    ]
    
    if ACCOUNT_ID:
        cmd += ["--account", ACCOUNT_ID]

    # Feishu: omit --target to reply to the current conversation if bot runs within that context.
    # But our bot runs as a standalone process, so we should provide a target when possible.
    # If OPENCLAW_TARGET is empty, we send without --target and rely on default routing (may fail).
    if TARGET:
        cmd += ["--target", TARGET]

    cmd += [
        "--message",
        text,
        "--json",
    ]

    env = os.environ.copy()
    env["OPENCLAW_TOKEN"] = OPENCLAW_TOKEN
    env["OPENCLAW_CHANNEL"] = CHANNEL
    env["OPENCLAW_TARGET"] = TARGET
    env["OPENCLAW_ACCOUNT_ID"] = os.getenv("OPENCLAW_ACCOUNT_ID", "")

    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"openclaw message send failed: {proc.stderr.strip() or proc.stdout.strip()}")


async def run_once() -> None:
    items = await fetch_all_items()
    if not items:
        # Still send a heartbeat message so scheduled runs are visible even when nothing new is found.
        msg = "【AI newsletter】本期无新条目（抓取窗口内无更新或源暂不可用）。\n\n我会按计划继续定时检查。"
    else:
        selected = select_top_items(items)
        msg = build_one_message(selected)

    async with aiohttp.ClientSession() as session:
        await openclaw_send_text(session, msg)
        print(f"sent 1 message ({len(msg)} chars)", flush=True)


async def main() -> None:
    if RUN_ONCE_AND_EXIT:
        await run_once()
        return

    scheduler = AsyncIOScheduler(timezone="UTC")
    job_kwargs = {
        "trigger": "interval",
        "hours": RUN_EVERY_HOURS,
    }
    if RUN_ON_START:
        job_kwargs["next_run_time"] = _now_utc()

    # Use the scheduler's event loop integration (we are already inside asyncio.run(main())).
    # Passing a coroutine function lets APScheduler await it safely.
    scheduler.add_job(run_once, **job_kwargs)
    scheduler.start()

    # Keep process alive
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
