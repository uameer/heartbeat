"""
heartbeat_signals_x.py — X (Twitter) signal scanner for heartbeat.

Fetches recent tweets for tracked keywords and accounts, passes them
to the configured LLM, and writes a triage digest to .heartbeat/signals/.

Usage (standalone):
    python heartbeat_signals_x.py [--workspace .] [--provider anthropic]

Invoked from heartbeat.py via --signals flag.
"""

import itertools
import datetime
import logging
from pathlib import Path
from typing import Optional

from heartbeat_providers import build_client, choose_model

log = logging.getLogger("heartbeat.signals_x")

DEFAULT_KEYWORDS = [
    "agent harness",
    "KAIROS pattern",
    "proactive agent",
    "agent memory format",
    "heartbeat agent",
]

DEFAULT_ACCOUNTS = [
    "garrytan",
    "hwchase17",
    "steipete",
    "akshay_pachaar",
    "intuitiveml",
]

DIGEST_PROMPT = (
    "Analyze these tweets for relevance to heartbeat "
    "(proactive AI agent loop with local memory).\n"
    "Categorize each as:\n"
    "HIGH: thread to engage in within 2 hours\n"
    "MEDIUM: worth reading, no urgent action\n"
    "PARK: skip\n"
    "For HIGH items, suggest a one-line response angle.\n"
    "Output as markdown digest."
)


def _load_list(path: Path, defaults: list[str]) -> list[str]:
    if path.exists():
        items = [line.strip() for line in path.read_text().splitlines() if line.strip()]
        return items if items else defaults
    return defaults


def _signals_dir(workspace: Path) -> Path:
    d = workspace / ".heartbeat" / "signals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fetch_keyword_tweets(keyword: str, limit: int, cutoff: datetime.datetime) -> list[dict]:
    try:
        import snscrape.modules.twitter as sntwitter
    except ImportError:
        log.error("snscrape not installed — run: pip install snscrape")
        return []

    results = []
    try:
        scraper = sntwitter.TwitterSearchScraper(keyword)
        for tweet in itertools.islice(scraper.get_items(), limit * 3):
            if tweet.date.replace(tzinfo=None) < cutoff:
                break
            if tweet.date.replace(tzinfo=None) >= cutoff:
                results.append({
                    "source": f"keyword:{keyword}",
                    "user": tweet.user.username,
                    "date": tweet.date.isoformat(),
                    "url": tweet.url,
                    "text": tweet.content,
                })
            if len(results) >= limit:
                break
    except Exception as e:
        log.warning(f"Error scraping keyword '{keyword}': {e}")
    return results


def _fetch_account_tweets(username: str, limit: int, cutoff: datetime.datetime) -> list[dict]:
    try:
        import snscrape.modules.twitter as sntwitter
    except ImportError:
        return []

    results = []
    try:
        scraper = sntwitter.TwitterProfileScraper(username)
        for tweet in itertools.islice(scraper.get_items(), limit * 3):
            if tweet.date.replace(tzinfo=None) < cutoff:
                break
            if tweet.date.replace(tzinfo=None) >= cutoff:
                results.append({
                    "source": f"account:{username}",
                    "user": tweet.user.username,
                    "date": tweet.date.isoformat(),
                    "url": tweet.url,
                    "text": tweet.content,
                })
            if len(results) >= limit:
                break
    except Exception as e:
        log.warning(f"Error scraping account '@{username}': {e}")
    return results


def _format_tweets_for_llm(tweets: list[dict]) -> str:
    if not tweets:
        return "(no tweets found in the last 24 hours)"
    lines = []
    for t in tweets:
        lines.append(f"[{t['source']}] @{t['user']} — {t['date']}")
        lines.append(t["text"])
        lines.append(t["url"])
        lines.append("")
    return "\n".join(lines)


def _call_llm(client, provider: str, model: str, tweet_block: str) -> str:
    user_message = f"{DIGEST_PROMPT}\n\n---\n\n{tweet_block}"
    try:
        if provider in ("openai", "ollama", "gemini"):
            response = client.chat.completions.create(
                model=model,
                max_tokens=1500,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.choices[0].message.content.strip()
        else:
            response = client.messages.create(
                model=model,
                max_tokens=1500,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text.strip()
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        return f"(LLM error: {e})"


def run_signals(
    workspace: Path,
    provider: str,
    model: Optional[str] = None,
) -> Path:
    """Fetch X signals, analyse with LLM, write digest. Returns the digest path."""
    signals_dir = _signals_dir(workspace)
    keywords = _load_list(signals_dir / "keywords.txt", DEFAULT_KEYWORDS)
    accounts = _load_list(signals_dir / "accounts.txt", DEFAULT_ACCOUNTS)

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=24)

    log.info(f"[SIGNALS] Scanning {len(keywords)} keywords, {len(accounts)} accounts (last 24h)")

    tweets: list[dict] = []
    for kw in keywords:
        fetched = _fetch_keyword_tweets(kw, limit=20, cutoff=cutoff)
        log.info(f"  keyword '{kw}': {len(fetched)} tweets")
        tweets.extend(fetched)

    for acct in accounts:
        fetched = _fetch_account_tweets(acct, limit=10, cutoff=cutoff)
        log.info(f"  account @{acct}: {len(fetched)} tweets")
        tweets.extend(fetched)

    tweet_block = _format_tweets_for_llm(tweets)

    client = build_client(provider)
    resolved_model = choose_model(provider, model)
    log.info(f"[SIGNALS] Calling {provider}/{resolved_model} for digest ({len(tweets)} tweets)")

    digest_body = _call_llm(client, provider, resolved_model, tweet_block)

    now = datetime.datetime.utcnow()
    slug = now.strftime("%Y-%m-%d-%H")
    digest_path = signals_dir / f"{slug}.md"

    header = (
        f"# X Signals Digest — {now.strftime('%Y-%m-%d %H:00 UTC')}\n\n"
        f"**Keywords scanned:** {', '.join(keywords)}\n"
        f"**Accounts tracked:** {', '.join('@' + a for a in accounts)}\n"
        f"**Tweets collected:** {len(tweets)}\n\n---\n\n"
    )
    digest_path.write_text(header + digest_body + "\n")
    log.info(f"[SIGNALS] Digest written → {digest_path}")
    return digest_path


# ── CLI entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="heartbeat X signal scanner")
    parser.add_argument("--workspace", type=str, default=".", help="Project workspace directory")
    parser.add_argument(
        "--provider", type=str, default=None,
        choices=["anthropic", "openai", "ollama", "gemini"],
    )
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()

    from heartbeat_providers import PROVIDER
    provider = args.provider or os.getenv("HEARTBEAT_PROVIDER", PROVIDER)
    path = run_signals(Path(args.workspace).resolve(), provider=provider, model=args.model)
    print(f"Digest: {path}")
