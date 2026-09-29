"""Your source list. This is the single place to add, remove or re-tier sources.

Tier 1 = primary sources (journals, press offices).
Tier 2 = trusted science journalism.

These URLs were written from memory and have NOT been tested.
Run `python scripts/check_feeds.py` and fix any that fail before deploying.
"""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["journal", "press-office", "news", "preprint"]


@dataclass(frozen=True)
class FeedSource:
    id: str
    """Stable slug used in results and for filtering. Don't change it once in use."""
    name: str
    url: str
    tier: Literal[1, 2]
    kind: Kind


FEEDS: list[FeedSource] = [
    # Tier 1: primary
    FeedSource("nature-physics", "Nature Physics", "https://www.nature.com/nphys.rss", 1, "journal"),
    FeedSource("aps-physics", "APS Physics Magazine", "https://feeds.aps.org/rss/recent/physics.xml", 1, "journal"),
    FeedSource("cern", "CERN news", "https://home.cern/api/news/news/feed.rss", 1, "press-office"),
    # Tier 2: journalism
    FeedSource("physics-world", "Physics World", "https://physicsworld.com/feed/", 2, "news"),
    FeedSource("quanta", "Quanta Magazine", "https://www.quantamagazine.org/feed/", 2, "news"),
    FeedSource("new-scientist-physics", "New Scientist (physics)", "https://www.newscientist.com/subject/physics/feed/", 2, "news"),
    # Covers science AND environment (climate, nature), so expect non-physics stories; the scout skill filters by topic.
    FeedSource("bbc-science", "BBC News (science and environment)", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", 2, "news"),
]

# arXiv categories searched when the caller doesn't specify any. See https://arxiv.org/category_taxonomy
DEFAULT_ARXIV_CATEGORIES = ["quant-ph", "astro-ph.CO", "astro-ph.HE", "cond-mat.mes-hall", "physics.optics"]

# A feed whose newest item is older than this is reported as stale: it may have moved or stopped updating.
# Quieter sources (e.g. a press office that posts weekly) may need a higher number.
STALE_AFTER_DAYS = 7

# Sent with every request so publishers can see who is fetching. Put your contact email in.
USER_AGENT = "science-scout-mcp/0.2 (personal research tool; contact: you@example.com)"
