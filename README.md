# NK's AI / GenAI News Monitor  


Monitors global AI, machine learning, deep learning, GenAI, new AI tools,
and new AI/LLM model news 24x7 and sends you ONE beautiful HTML digest page
on Telegram, once a day. Runs entirely on free infrastructure.

This is a separate "employee" from the Cybersecurity News Monitor - it uses
its own repo and its own Telegram bot, so the two digests never mix.

## How it works
1. GitHub Actions wakes the agent up once a day (8:30 AM IST by default).
2. It pulls the latest articles from 15 AI-dedicated sources - breaking AI
   news outlets (TechCrunch, VentureBeat, The Verge, Ars Technica, Wired,
   MIT Technology Review), official AI lab blogs (OpenAI, Google DeepMind,
   Hugging Face, NVIDIA, Google Research), and curated AI-only publications
   (Marktechpost, AI News, MIT News AI, Unite.AI).
3. Since every one of these sources is already AI-focused, there's no
   keyword filter by default (same logic as the cyber agent) - the only
   exception is MIT Technology Review, whose public feed covers all of MIT
   Tech Review's topics, so a light AI-keyword filter is applied just to
   that one source (see `OPTIONAL_KEYWORD_FILTER_SOURCES` in the script).
4. It removes duplicate stories (near-identical titles across runs).
5. It groups everything by website, and (optionally) uses Google Gemini's
   free tier to write a headline + 2-3 sentence summary for each story.
6. It builds ONE styled HTML page - clean cards per source, numbered
   stories, headline + date + summary, no clutter - and sends that file to
   your Telegram as a document attachment. No per-website chat spam.
7. It remembers what it already sent you across runs (`seen_articles.json`),
   so nothing repeats even if a story is still trending the next day.

## Setup (about 15 minutes, all free)

### 1. Create a NEW Telegram bot for this agent
Use a separate bot from your cybersecurity one so the two digests don't mix.
1. Open Telegram, message **@BotFather**, send `/newbot`, follow the prompts
   (e.g. name it "AI News Bot").
2. It gives you a **bot token** - save it.
3. Message your new bot anything (e.g. "hi") so it can message you back.
4. Get your **chat ID**: visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   in a browser right after step 3, and find `"chat":{"id": ...}` in the
   response.

### 2. Get a free Gemini API key (for AI summarization - optional)
1. Go to https://aistudio.google.com/apikey
2. Create a free API key (no card required).
3. If you skip this, the agent still works - it just sends raw headlines
   with dates instead of AI-written 2-3 sentence summaries.

### 3. Put this code on GitHub
1. Create a **new** GitHub repo (separate from your cyber one; private is
   fine, and free).
2. Upload all files in this folder to the repo, including the `.github`
   folder (GitHub sometimes hides dot-folders in drag-and-drop uploads -
   if that happens, use "Add file → Create new file" and type the full
   path `.github/workflows/monitor.yml` in the filename box instead).

### 4. Add your secrets to the repo
In your repo: **Settings → Secrets and variables → Actions → New repository
secret**. Add these:
- `TELEGRAM_BOT_TOKEN` (the NEW bot's token from step 1)
- `TELEGRAM_CHAT_ID` (from step 1)
- `GEMINI_API_KEY` (optional, from step 2)

### 5. Turn it on
- Go to the **Actions** tab in your repo → enable workflows if prompted.
- It will now run automatically every day, forever, for free.
- You can also click **Run workflow** manually anytime to test it right now
  instead of waiting for the scheduled time.

## What you'll receive
A single Telegram message with one HTML file attached, e.g.
`ai_news_digest_2026-07-14.html`. Tap it, your phone opens it in the
browser, and you get a nicely designed single page: one card per website,
each story numbered with a headline, date, and short summary - no links
cluttering the story list (only the website name at the top of each card
links out, if you want to read the full article).

## No cap, no repeats
- **`MAX_PER_SOURCE` is `None`** - every new, never-sent-before story from
  every source is included, however many that is on a given day. A quiet
  site (MIT News, DeepMind) might only have 1; a busy one (TechCrunch,
  VentureBeat) might have 15+. Both are sent in full.
- **`LOOKBACK_HOURS` is 48** - wide enough that a slow-posting site isn't
  missed just because it didn't publish in the last day. This is safe
  because of the next point:
- **`seen_articles.json` is permanent memory** - once a story's unique ID
  has been included in a digest, it is never included again, no matter how
  long it stays in that site's RSS feed or how wide the lookback window is.
  "Send it once, never again" is enforced per-story, forever - not by
  narrowing the time window.

## Customizing your "employee"
- **Frequency**: edit the `cron` line in `.github/workflows/monitor.yml`.
  If you go more frequent than daily, you can also raise `LOOKBACK_HOURS`
  further with no duplicate risk - see above.
- **Story detail**: summaries are written to be detailed (5-7+ sentences,
  covering what was released, who's behind it, technical specifics, and
  why it matters) whenever `GEMINI_API_KEY` is set. Without a Gemini key,
  you still get the source's own raw excerpt for each story (headline +
  date + summary), just not AI-rewritten.
- **Sources**: add/remove RSS feeds in the `FEEDS` dict (and add a matching
  entry in `SOURCE_HOMEPAGE`). If a feed silently returns 0 items, check the
  Actions log - it prints `[FEED OK]`, `[FEED EMPTY]`, or `[FEED FAIL]` for
  every source so broken URLs are easy to spot and fix.
- **Dedup sensitivity**: `is_duplicate()`'s `threshold` (0.72 by default)
  controls how similar two headlines need to be to count as the same story.
- **Styling**: all CSS lives inline in `build_html_digest()` in
  `ai_news_agent.py` - change colors, fonts, spacing directly there.

## Cost
₹0 / $0 - GitHub Actions free tier + RSS feeds (free) + Gemini free tier +
Telegram Bot API (free). The only limits are rate limits, not bills.
