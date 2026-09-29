"""The arXiv API: one HTTP request that returns the newest papers (or specific papers) as an Atom feed.

arXiv asks for at most one request every 3 seconds; each tool call makes at most one.
"""

import re
from urllib.parse import urlencode

import feedparser
import httpx

from .models import Item
from .normalise import plain_text, struct_to_iso

ARXIV_API = "https://export.arxiv.org/api/query"


def newest_query_url(categories: list[str], max_results: int) -> str:
    return f"{ARXIV_API}?" + urlencode(
        {
            "search_query": " OR ".join(f"cat:{c}" for c in categories),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "start": 0,
            "max_results": max_results,
        }
    )


def id_list_url(arxiv_ids: list[str]) -> str:
    return f"{ARXIV_API}?" + urlencode({"id_list": ",".join(arxiv_ids), "max_results": len(arxiv_ids)})


def parse_arxiv(content: bytes) -> list[Item]:
    parsed = feedparser.parse(content)
    items: list[Item] = []
    for e in parsed.entries:
        abs_url = e.get("id", "")
        if "/api/errors" in abs_url:
            raise ValueError(f"arXiv API error: {plain_text(e.get('summary', ''))}")
        arxiv_id = re.sub(r"v\d+$", "", abs_url.rsplit("/abs/", 1)[-1]) if "/abs/" in abs_url else ""
        published = struct_to_iso(e.get("published_parsed"))
        if not arxiv_id or not published:
            continue
        primary = (e.get("arxiv_primary_category") or {}).get("term")
        cats = [t.get("term") for t in e.get("tags", []) if t.get("term")]
        if primary:
            cats = [primary, *[c for c in cats if c != primary]]
        items.append(
            Item(
                id=f"arxiv:{arxiv_id.lower()}",
                title=plain_text(e.get("title", ""), 300),
                url=e.get("link") or abs_url,
                published=published,
                summary=plain_text(e.get("summary", ""), 500),
                source="arxiv",
                source_name="arXiv",
                tier=0,
                kind="preprint",
                authors=[a.get("name", "") for a in e.get("authors", []) if a.get("name")],
                categories=cats,
                identifiers=[f"arxiv:{arxiv_id.lower()}"],
            )
        )
    return items


async def fetch_arxiv(client: httpx.AsyncClient, url: str) -> list[Item]:
    res = await client.get(url, timeout=20)
    res.raise_for_status()
    return parse_arxiv(res.content)
