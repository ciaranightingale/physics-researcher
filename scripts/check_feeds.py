"""Fetches every source in sources.py from your machine and reports whether it works.

Each feed gets one of three results:
  ✓  loaded, and has posted recently
  ⚠  loaded, but its newest item is older than the stale threshold (or it's empty): it may have moved or stopped
  ✗  couldn't be fetched or read at all

Run with:  python scripts/check_feeds.py                 (threshold from STALE_AFTER_DAYS in sources.py)
           python scripts/check_feeds.py --stale-days 14
Exits with status 1 if anything is broken or stale, so it can run in CI or on a schedule.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from science_scout.arxiv import fetch_arxiv, newest_query_url
from science_scout.feeds import fetch_feed
from science_scout.normalise import days_since
from science_scout.server import _describe, default_http
from science_scout.sources import DEFAULT_ARXIV_CATEGORIES, FEEDS, STALE_AFTER_DAYS


def line(mark: str, name: str, detail: str) -> str:
    return f"{mark} {name:<24} {detail}"


def freshness(newest: str | None, now: datetime, stale_days: int) -> tuple[str, str]:
    """Returns (mark, description) for a feed's newest item."""
    if newest is None:
        return "\u26a0", "no dated items: check the URL is the feed, not the web page"
    age = days_since(newest, now)
    when = "today" if age == 0 else f"{age} day{'s' if age != 1 else ''} ago"
    if age > stale_days:
        return "\u26a0", f"newest item {newest[:10]} ({when}): stale, may have moved or stopped updating"
    return "\u2713", f"newest item {newest[:10]} ({when})"


async def main(stale_days: int) -> int:
    now = datetime.now(timezone.utc)
    broken = stale = 0
    async with default_http() as client:
        for source in FEEDS:
            try:
                items, undated = await fetch_feed(client, source)
            except Exception as exc:
                broken += 1
                print(line("\u2717", source.id, f"{_describe(exc)}  ({source.url})"))
                continue
            mark, detail = freshness(max((i.published for i in items), default=None), now, stale_days)
            stale += mark != "\u2713"
            extra = f", {undated} undated" if undated else ""
            print(line(mark, source.id, f"{len(items):>3} items{extra}, {detail}"))

        try:
            papers = await fetch_arxiv(client, newest_query_url(DEFAULT_ARXIV_CATEGORIES, 20))
            mark, detail = freshness(max((p.published for p in papers), default=None), now, stale_days)
            stale += mark != "\u2713"
            print(line(mark, "arxiv", f"{len(papers):>3} papers, {detail}"))
        except Exception as exc:
            broken += 1
            print(line("\u2717", "arxiv", _describe(exc)))

    total = len(FEEDS) + 1
    print(f"\n{total - broken - stale} ok, {stale} stale, {broken} broken (stale = nothing new in {stale_days} days)")
    return 1 if broken or stale else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stale-days", type=int, default=STALE_AFTER_DAYS, help=f"default: {STALE_AFTER_DAYS}")
    sys.exit(asyncio.run(main(parser.parse_args().stale_days)))
