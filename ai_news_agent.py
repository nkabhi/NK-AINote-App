"""
AI / ML / GenAI News Monitor - Agent
--------------------------------------
Fetches the latest AI, machine learning, deep learning, GenAI, new AI tools
and new AI/LLM model news from 15 dedicated AI sources, groups results by
source website, and builds ONE beautiful HTML/CSS digest page - sent to you
as a file on Telegram once a day.

Runs on a schedule (see .github/workflows/monitor.yml) so it behaves like a
24x7 "employee" without costing anything or needing your PC on.

This is a separate agent/repo/Telegram bot from the Cybersecurity News
Monitor - point it at its OWN bot token + chat id (see README).
"""

import os
import re
import json
import time
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

# ---------- CONFIG ----------
# All 15 sources are dedicated AI/ML publications or official AI lab blogs -
# every article on them is already "AI news" by definition, so (like the
# cyber agent) no keyword filter is applied by default. One exception is
# flagged below (MIT Technology Review, whose public feed is site-wide,
# not AI-only) - see OPTIONAL_KEYWORD_FILTER_SOURCES.
FEEDS = {
    # Breaking AI news / tech journalism
    "TechCrunch (AI)": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "VentureBeat (AI)": "https://venturebeat.com/category/ai/feed/",
    "The Verge (AI)": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "Ars Technica (AI)": "https://arstechnica.com/ai/feed/",
    "Wired (AI)": "https://www.wired.com/feed/category/artificial-intelligence/rss",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",

    # Official AI lab / company blogs (most accurate for new model releases)
    "OpenAI News": "https://openai.com/news/rss.xml",
    "Google DeepMind Blog": "https://deepmind.google/blog/rss.xml",
    "Hugging Face Blog": "https://huggingface.co/blog/feed.xml",
    "NVIDIA Blog": "https://blogs.nvidia.com/feed/",
    "Google Research Blog": "https://research.google/blog/rss/",

    # Research / curated AI-only analysis
    "Marktechpost": "https://www.marktechpost.com/feed/",
    "AI News (artificialintelligence-news.com)": "https://www.artificialintelligence-news.com/feed/",
    "MIT News (AI)": "https://news.mit.edu/rss/topic/artificial-intelligence2",
    "Unite.AI": "https://www.unite.ai/feed/",
}

# Homepage link shown next to each source's section header in the digest.
SOURCE_HOMEPAGE = {
    "TechCrunch (AI)": "https://techcrunch.com/category/artificial-intelligence/",
    "VentureBeat (AI)": "https://venturebeat.com/category/ai/",
    "The Verge (AI)": "https://www.theverge.com/ai-artificial-intelligence",
    "Ars Technica (AI)": "https://arstechnica.com/ai/",
    "Wired (AI)": "https://www.wired.com/tag/artificial-intelligence/",
    "MIT Technology Review": "https://www.technologyreview.com/topic/artificial-intelligence/",
    "OpenAI News": "https://openai.com/news/",
    "Google DeepMind Blog": "https://deepmind.google/blog/",
    "Hugging Face Blog": "https://huggingface.co/blog",
    "NVIDIA Blog": "https://blogs.nvidia.com/",
    "Google Research Blog": "https://research.google/blog/",
    "Marktechpost": "https://www.marktechpost.com/",
    "AI News (artificialintelligence-news.com)": "https://www.artificialintelligence-news.com/",
    "MIT News (AI)": "https://news.mit.edu/topic/artificial-intelligence2",
    "Unite.AI": "https://www.unite.ai/",
}

# MIT Technology Review's public RSS is site-wide (biotech, climate, space,
# etc. too), not AI-only, unlike the other 14 sources. Only for sources
# listed here, we require at least one of these words in the title/summary.
# Leave this list empty ([]) to disable filtering entirely for everyone.
OPTIONAL_KEYWORD_FILTER_SOURCES = {
    "MIT Technology Review": [
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "llm", "large language model", "generative ai", "genai", "chatgpt",
        "gpt-", "gemini", "claude", "openai", "deepmind", "neural network",
        "chatbot", "algorithm", "model",
    ],
}

MAX_PER_SOURCE = 6            # latest unseen stories to include, per website
LOOKBACK_HOURS = 30           # wider-than-24h window so borderline-recent stories aren't missed
SEEN_FILE = "seen_articles.json"    # prevents the same story ever being sent twice, across days

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")       # optional - AI one-liners per story
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")   # THIS agent's OWN bot token
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")       # THIS agent's OWN chat id


# ---------- STEP 1: FETCH ----------
def normalize_title(title):
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_duplicate(title, seen_titles, threshold=0.72):
    norm = normalize_title(title)
    for existing in seen_titles:
        if SequenceMatcher(None, norm, existing).ratio() >= threshold:
            return True
    return False


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen_set):
    trimmed = list(seen_set)[-2500:]
    with open(SEEN_FILE, "w") as f:
        json.dump(trimmed, f)


def fetch_recent_articles():
    """
    Returns an ORDERED dict: {source_name: [item, item, ...]}
    - Only sources with at least 1 new (never-before-sent) story are included.
    - Each source's list is newest-first, capped at MAX_PER_SOURCE.
    - Stories already sent on a previous day are permanently excluded.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    seen_ids = load_seen()
    grouped = {}

    for source, url in FEEDS.items():
        feed = None
        last_error = None
        for attempt in range(2):
            try:
                # A browser User-Agent avoids silent bot-blocking (403s) on
                # some sites (this bit us on the cyber agent with CISA).
                resp = requests.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"},
                    timeout=20,
                )
                resp.raise_for_status()
                feed = feedparser.parse(resp.content)
                break
            except Exception as e:
                last_error = e
                if attempt == 0:
                    time.sleep(3)

        if feed is None:
            print(f"[FEED FAIL] {source}: exception after retry - {last_error}")
            continue

        total_entries = len(feed.entries)
        if total_entries == 0:
            status = getattr(feed, "status", "unknown")
            print(f"[FEED EMPTY] {source}: 0 entries returned (http status: {status}, url: {url})")
            continue

        required_keywords = OPTIONAL_KEYWORD_FILTER_SOURCES.get(source)

        source_candidates = []
        for entry in feed.entries:
            uid = entry.get("id", entry.get("link"))
            if uid in seen_ids:
                continue

            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
            else:
                pub_dt = datetime.now(timezone.utc)

            title = entry.get("title", "").strip()
            summary = re.sub("<[^<]+?>", "", entry.get("summary", ""))
            text_blob = (title + " " + summary).lower()

            if required_keywords and not any(k in text_blob for k in required_keywords):
                continue

            source_candidates.append({
                "id": uid,
                "source": source,
                "title": title,
                "link": entry.get("link"),
                "summary": summary[:1500],
                "published": pub_dt,
            })

        source_candidates.sort(key=lambda x: x["published"], reverse=True)
        deduped = []
        seen_titles_norm = []
        for item in source_candidates:
            if is_duplicate(item["title"], seen_titles_norm):
                continue
            seen_titles_norm.append(normalize_title(item["title"]))
            deduped.append(item)
            if len(deduped) >= MAX_PER_SOURCE:
                break

        print(f"[FEED OK] {source}: {total_entries} entries fetched, {len(deduped)} new stories selected")

        if deduped:
            grouped[source] = deduped

    total = sum(len(v) for v in grouped.values())
    print(f"\n[SUMMARY] {total} total new stories across {len(grouped)} sources with activity\n")
    for src, items in grouped.items():
        capped_note = " (hit MAX_PER_SOURCE cap - more may exist)" if len(items) >= MAX_PER_SOURCE else ""
        print(f"  {src}: {len(items)} stories{capped_note}")

    return grouped, seen_ids


# ---------- STEP 2: SUMMARIZE (optional, free Gemini tier) ----------
def summarize_source(source, items):
    """
    One-liner-plus-context summaries for a single source's stories.
    Returns None if Gemini isn't configured or the call fails (caller
    falls back to raw headlines for this source instead).
    """
    if not GEMINI_API_KEY:
        return None

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    )

    story_lines = "\n\n".join(
        f"STORY {idx}\nTitle: {item['title']}\n"
        f"Published: {item['published'].strftime('%d %b %Y, %H:%M UTC')}\n"
        f"Details: {item['summary']}"
        for idx, item in enumerate(items, start=1)
    )

    prompt = (
        "You are summarizing AI/ML/GenAI news from a single source for a "
        "quick daily briefing. Below are "
        f"{len(items)} raw news items. For EACH one, write:\n\n"
        "N. [Headline in your own words, one line, no markdown]\n"
        "   Date: <copy the exact 'Published' value given below for this "
        "story - do not compute, guess, or reformat it, just copy it "
        "verbatim>\n"
        "   Summary: <2-3 plain-language sentences covering what happened - "
        "e.g. what model/tool/feature was released or what research was "
        "announced, who/which company was involved, and why it matters>\n\n"
        "STRICT RULES:\n"
        "- Base every fact ONLY on the details given below for that story. "
        "Never invent or guess facts not present in the source text.\n"
        "- Do not include any URLs or links.\n"
        "- Plain text only, no markdown bold/asterisks/headers.\n"
        "- Number stories 1 through "
        f"{len(items)}, matching STORY numbers below, in the same order.\n\n"
        f"{story_lines}"
    )

    for attempt in range(3):
        try:
            resp = requests.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 2048},
                },
                timeout=45,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return text
        except Exception as e:
            wait = (attempt + 1) * 5
            print(f"  Gemini call failed for {source} (attempt {attempt + 1}/3): {e}")
            if attempt < 2:
                time.sleep(wait)
            else:
                print(f"  Falling back to raw headlines for {source}.")
                return None


def format_raw_source(items):
    """Fallback (no Gemini) - numbered headlines + dates for one source."""
    lines = []
    for idx, item in enumerate(items, start=1):
        date_str = item["published"].strftime("%d %b %Y, %H:%M UTC")
        lines.append(f"{idx}. [{date_str}] {item['title']}")
    return "\n".join(lines)


# ---------- STEP 3: BUILD THE HTML/CSS DIGEST PAGE ----------
def build_html_digest(source_blocks):
    """
    source_blocks: list of dicts, each {source, homepage, count, body}
    Builds one self-contained, styled HTML page covering the whole day's
    AI news, grouped by website - this is the only thing sent to Telegram.
    """
    now_str = datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M UTC')

    sections_html = ""
    for block in source_blocks:
        # Turn "N. Headline\n   Date: ...\n   Summary: ..." plain text into
        # a clean numbered card list instead of one big <br>-joined blob.
        story_cards = ""
        raw_stories = re.split(r"\n(?=\d+\.\s)", block["body"].strip())
        for raw in raw_stories:
            raw = raw.strip()
            if not raw:
                continue
            m = re.match(r"^(\d+)\.\s*(.+?)(?:\n\s*Date:\s*(.+?))?(?:\n\s*Summary:\s*(.+))?$", raw, re.DOTALL)
            if m:
                num, headline, date, summary = m.groups()
                headline = (headline or "").strip()
                date = (date or "").strip()
                summary = (summary or "").strip()
                story_cards += f"""
                <div class="story">
                    <div class="story-num">{num}</div>
                    <div class="story-body">
                        <div class="story-headline">{headline}</div>
                        {f'<div class="story-date">{date}</div>' if date else ''}
                        {f'<div class="story-summary">{summary}</div>' if summary else ''}
                    </div>
                </div>"""
            else:
                story_cards += f'<div class="story"><div class="story-body">{raw}</div></div>'

        sections_html += f"""
        <div class="source-section">
            <h2><a href="{block['homepage']}" target="_blank">{block['source']}</a>
                <span class="count">{block['count']} stories</span></h2>
            <div class="stories">{story_cards}</div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI News Digest - {now_str}</title>
<style>
  :root {{
    --accent: #6d28d9;
    --accent-light: #ede9fe;
    --bg: #f7f7fb;
    --card-bg: #ffffff;
    --border: #e6e6f0;
    --text: #1c1c28;
    --muted: #6b6b7b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    max-width: 860px; margin: 0 auto; padding: 28px 20px 60px;
    line-height: 1.55; color: var(--text); background: var(--bg);
  }}
  .masthead {{
    display: flex; align-items: center; justify-content: space-between;
    border-bottom: 3px solid var(--accent); padding-bottom: 14px; margin-bottom: 8px;
  }}
  h1 {{ font-size: 24px; margin: 0; }}
  .generated {{ color: var(--muted); font-size: 13px; margin-bottom: 28px; }}
  .source-section {{
    background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px;
    padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  h2 {{
    font-size: 17px; margin: 0 0 14px 0; display: flex; align-items: baseline; gap: 10px;
    border-bottom: 1px solid var(--border); padding-bottom: 10px;
  }}
  h2 a {{ color: var(--accent); text-decoration: none; }}
  h2 a:hover {{ text-decoration: underline; }}
  .count {{
    color: var(--accent); background: var(--accent-light); font-weight: 600;
    font-size: 12px; padding: 2px 10px; border-radius: 999px;
  }}
  .story {{ display: flex; gap: 12px; padding: 12px 0; }}
  .story + .story {{ border-top: 1px dashed var(--border); }}
  .story-num {{
    flex-shrink: 0; width: 24px; height: 24px; border-radius: 50%;
    background: var(--accent); color: #fff; font-size: 12px; font-weight: 700;
    display: flex; align-items: center; justify-content: center; margin-top: 2px;
  }}
  .story-headline {{ font-weight: 600; font-size: 14.5px; margin-bottom: 3px; }}
  .story-date {{ color: var(--muted); font-size: 12px; margin-bottom: 5px; }}
  .story-summary {{ font-size: 13.5px; color: #333; }}
  @media (max-width: 480px) {{
    h1 {{ font-size: 20px; }}
    .source-section {{ padding: 16px 16px; }}
  }}
</style>
</head>
<body>
  <div class="masthead">
    <h1>🤖 AI &amp; GenAI News Digest</h1>
  </div>
  <div class="generated">Generated {now_str}</div>
  {sections_html}
</body>
</html>"""
    return html


# ---------- STEP 4: DELIVER (Telegram only, HTML file only) ----------
def send_telegram_document(filepath, caption=""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured - cannot send HTML file. Set TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(filepath, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                files={"document": (os.path.basename(filepath), f, "text/html")},
                timeout=30,
            )
        if resp.status_code != 200:
            print(f"Telegram file send failed ({resp.status_code}): {resp.text[:200]}")
        else:
            print("HTML digest file sent to Telegram successfully.")
    except Exception as e:
        print(f"Telegram file send error: {e}")


# ---------- MAIN ----------
def main():
    grouped, seen = fetch_recent_articles()

    if not grouped:
        print("No new AI stories found on any source in this window.")
        return

    total = sum(len(v) for v in grouped.values())
    print(f"Found {total} new stories across {len(grouped)} sources. Building HTML digest...")

    source_blocks_for_html = []

    for source, items in grouped.items():
        homepage = SOURCE_HOMEPAGE.get(source, "")

        body = summarize_source(source, items)
        if body is None:
            body = format_raw_source(items)

        source_blocks_for_html.append({
            "source": source,
            "homepage": homepage,
            "count": len(items),
            "body": body,
        })

        # Mark as permanently seen right after building its block, so a
        # failure later doesn't cause a resend of sources already processed.
        seen.update(item["id"] for item in items)
        save_seen(seen)

    html_content = build_html_digest(source_blocks_for_html)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html_path = f"ai_news_digest_{date_str}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    caption = f"🤖 AI News Digest — {total} stories across {len(grouped)} sources — {date_str}"
    send_telegram_document(html_path, caption=caption)


if __name__ == "__main__":
    main()
