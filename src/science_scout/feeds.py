"""Fetching and parsing RSS / RSS 1.0 (RDF) / Atom feeds into Items."""

import feedparser
import httpx

from .models import Item
from .normalise import extract_identifiers, item_key, plain_text, struct_to_iso
from .sources import FeedSource


def parse_feed(content: bytes, source: FeedSource) -> tuple[list[Item], int]:
    """Same bytes in, same items out. Returns (items, number skipped for having no readable date)."""
    parsed = feedparser.parse(content)
    if not parsed.entries and parsed.get("bozo"):
        raise ValueError(f"Not a readable feed: {parsed.get('bozo_exception')}")

    items: list[Item] = []
    skipped_no_date = 0
    for e in parsed.entries:
        title = plain_text(e.get("title", ""), 300)
        url = e.get("link") or e.get("id") or ""
        if not title or not url:
            continue
        published = struct_to_iso(e.get("published_parsed") or e.get("updated_parsed") or e.get("created_parsed"))
        if not published:
            skipped_no_date += 1
            continue
        raw_summary = e.get("summary") or (e.get("content") or [{}])[0].get("value", "")
        authors = [a.get("name", "") for a in e.get("authors", []) if a.get("name")]
        # A journal item's own URL, DOI fields and summary usually identify its paper; news items get theirs from the page later.
        id_text = " ".join(str(x) for x in (url, e.get("id", ""), e.get("prism_doi", ""), e.get("dc_identifier", ""), raw_summary))
        items.append(
            Item(
                id=item_key(url),
                title=title,
                url=url,
                published=published,
                summary=plain_text(raw_summary),
                source=source.id,
                source_name=source.name,
                tier=source.tier,
                kind=source.kind,
                authors=authors,
                categories=[t.get("term", "") for t in e.get("tags", []) if t.get("term")],
                identifiers=extract_identifiers(id_text) if source.kind != "news" else extract_identifiers(url),
            )
        )
    return items, skipped_no_date


async def fetch_feed(client: httpx.AsyncClient, source: FeedSource) -> tuple[list[Item], int]:
    res = await client.get(source.url, headers={"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    res.raise_for_status()
    return parse_feed(res.content, source)


def select_sources(all_sources: list[FeedSource], tiers: list[int] | None, source_ids: list[str] | None) -> list[FeedSource]:
    return [s for s in all_sources if (not tiers or s.tier in tiers) and (not source_ids or s.id in source_ids)]
