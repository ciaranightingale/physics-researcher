"""Finding which paper a news article is about, by reading the links on its page.

Science news articles almost always link to the paper (doi.org, nature.com/articles, arxiv.org...).
Two articles that link to the same paper are the same story. Results are cached forever per URL,
so each article page is fetched at most once and later runs are fast and repeatable.
"""

import asyncio
import html
import re

import httpx

from .normalise import extract_identifiers, item_key

_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)

MAX_IDENTIFIERS_PER_PAGE = 5
"""A page linking more papers than this is probably a reference list or round-up; grouping on it would
wrongly merge unrelated stories, so such pages contribute no identifiers."""


def identifiers_from_html(page_html: str, page_url: str) -> tuple[list[str], str]:
    """Returns (identifiers, status) where status is "ok" or "too_many_links". Pure."""
    own = set(extract_identifiers(page_url))
    found: list[str] = []
    for href in _HREF.findall(page_html):
        for ident in extract_identifiers(html.unescape(href)):
            if ident not in own and ident not in found:
                found.append(ident)
    if len(found) > MAX_IDENTIFIERS_PER_PAGE:
        return [], "too_many_links"
    return found, "ok"


async def resolve_pages(client: httpx.AsyncClient, urls: list[str], concurrency: int = 6) -> dict[str, tuple[list[str], str] | Exception]:
    """Fetches each page (bounded concurrency) and extracts identifiers. Keyed by item_key(url)."""
    sem = asyncio.Semaphore(concurrency)
    results: dict[str, tuple[list[str], str] | Exception] = {}

    async def one(url: str) -> None:
        async with sem:
            try:
                res = await client.get(url, headers={"Accept": "text/html"})
                res.raise_for_status()
                results[item_key(url)] = identifiers_from_html(res.text, str(res.url))
            except Exception as exc:  # reported, never silently dropped
                results[item_key(url)] = exc

    await asyncio.gather(*(one(u) for u in urls))
    return results
