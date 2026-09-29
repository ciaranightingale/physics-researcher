"""The MCP server: five tools over the fetching, grouping and video-log code."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from .arxiv import fetch_arxiv, id_list_url, newest_query_url
from .feeds import fetch_feed, select_sources
from .grouping import group_items
from .links import resolve_pages
from .models import (
    ArxivResult, CoveredFlag, DeleteResult, FlaggedPaper, Format, Item, LogResult, Platform,
    PostedVideo, SourceError, StaleSource, StoriesResult, StoryGroup, VideoList,
)
from .normalise import days_since, is_identifier, iso_now, item_key, within_days
from .sources import DEFAULT_ARXIV_CATEGORIES, FEEDS, STALE_AFTER_DAYS, USER_AGENT, FeedSource
from .store import Store

_PLATFORM_HOSTS = {"youtube": ("youtube.com", "youtu.be"), "tiktok": ("tiktok.com",)}


def default_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=10, follow_redirects=True)


@dataclass
class Deps:
    store: Store
    http: Callable[[], httpx.AsyncClient] = default_http
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    feeds: list[FeedSource] = field(default_factory=lambda: list(FEEDS))
    stale_after_days: int = STALE_AFTER_DAYS


def covered_flag(videos: list[PostedVideo]) -> CoveredFlag | None:
    if not videos:
        return None
    formats = {v.format for v in videos}
    return CoveredFlag(covered_as="both" if len(formats) == 2 else formats.pop(), videos=videos)


def create_server(deps: Deps) -> MCPServer:
    mcp = MCPServer(
        "science-scout",
        version="0.2.0",
        instructions=(
            "Fetches science news deterministically and groups coverage of the same story. "
            "Stories already made into videos are flagged, never hidden. "
            "Only log a video once the user confirms it is published and gives its link."
        ),
    )
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=True)

    @mcp.tool(annotations=read_only)
    async def get_stories(
        days: Annotated[int, Field(ge=1, le=30, description="Only include items published in the last N days.")] = 7,
        tiers: Annotated[list[int] | None, Field(description="Restrict to these source tiers (1 = primary, 2 = journalism). Omit for all.")] = None,
        sources: Annotated[list[str] | None, Field(description="Restrict to these source ids. Omit for all.")] = None,
        max_page_lookups: Annotated[int, Field(ge=0, le=100, description="Max new article pages to read for paper links this call.")] = 40,
        limit: Annotated[int, Field(ge=1, le=200, description="Max story groups returned, newest first.")] = 40,
    ) -> StoriesResult:
        """Fetch every configured science feed and return STORY GROUPS: all coverage of the same story from
        different outlets, plus the paper itself, merged into one entry.

        Items are grouped when they link to the same paper (DOI or arXiv ID), or, more weakly, when their headlines
        share most of their words; `match_evidence` says which, and "similar_headline" groups deserve a sanity check.
        Stories already made into videos are still returned, with `already_covered` showing the format(s) and video titles.
        If `errors` is non-empty, those sources failed and the list is incomplete: tell the user.
        If `stale_sources` is non-empty, those feeds loaded but haven't posted recently: mention it, as they may be broken.
        """
        now = deps.now()
        selected = select_sources(deps.feeds, tiers, sources)
        async with deps.http() as client:
            results = await asyncio.gather(*(fetch_feed(client, s) for s in selected), return_exceptions=True)

            errors: list[SourceError] = []
            stale: list[StaleSource] = []
            per_source: dict[str, int] = {}
            skipped = 0
            by_id: dict[str, Item] = {}
            for src, res in zip(selected, results):
                if isinstance(res, BaseException):
                    errors.append(SourceError(source=src.id, error=_describe(res)))
                    continue
                items, no_date = res
                skipped += no_date
                newest = max((i.published for i in items), default=None)
                if newest is None or days_since(newest, now) > deps.stale_after_days:
                    stale.append(StaleSource(source=src.id, newest_item=newest, days_since_newest=newest and days_since(newest, now)))
                recent = [i for i in items if within_days(i.published, days, now)]
                per_source[src.id] = len(recent)
                for i in recent:
                    by_id.setdefault(i.id, i)

            # Which paper is each article about? Read its links (cached per URL, so each page is fetched once ever).
            needing = sorted((i for i in by_id.values() if not i.identifiers), key=lambda i: (i.published, i.id), reverse=True)
            cached = deps.store.cached_links([i.id for i in needing])
            to_fetch = [i for i in needing if i.id not in cached]
            fetched = await resolve_pages(client, [i.url for i in to_fetch[:max_page_lookups]])
            pages = {"cached": len(cached), "fetched": 0, "failed": 0, "too_many_links": 0, "pending": max(0, len(to_fetch) - max_page_lookups)}
            for key, outcome in fetched.items():
                if isinstance(outcome, Exception):
                    pages["failed"] += 1  # not cached, so it's retried next call
                    continue
                deps.store.cache_links(key, outcome[0], outcome[1], iso_now(now))
                cached[key] = outcome
                pages["fetched"] += 1
            for key, (_, status) in cached.items():
                if status == "too_many_links":
                    pages["too_many_links"] += 1
            for i in needing:
                if i.id in cached:
                    by_id[i.id] = i.model_copy(update={"identifiers": cached[i.id][0]})

            raw_groups = group_items(list(by_id.values()))

            # Attach arXiv metadata for any preprints the stories link to (one request).
            linked_arxiv = sorted({ident.removeprefix("arxiv:") for g in raw_groups for ident in g.identifiers if ident.startswith("arxiv:")})[:50]
            preprints: dict[str, Item] = {}
            if linked_arxiv:
                try:
                    preprints = {p.id: p for p in await fetch_arxiv(client, id_list_url(linked_arxiv))}
                except Exception as exc:
                    errors.append(SourceError(source="arxiv", error=_describe(exc)))

        groups = [
            StoryGroup(
                group_id=g.group_id,
                headline=g.headline,
                latest_published=g.latest_published,
                source_count=len(g.items),
                sources=g.items,
                identifiers=g.identifiers,
                preprints=[preprints[i] for i in g.identifiers if i in preprints],
                match_evidence=g.evidence,
                already_covered=covered_flag(deps.store.videos_for_keys(g.keys)),
            )
            for g in raw_groups[:limit]
        ]
        deps.store.save_snapshots([(g.group_id, g.headline, g.keys) for g in raw_groups[:limit]], iso_now(now))

        return StoriesResult(
            generated_at=iso_now(now),
            window_days=days,
            sources_checked=[s.id for s in selected],
            items_per_source=per_source,
            errors=errors,
            stale_sources=stale,
            skipped_no_date=skipped,
            article_pages=pages,
            total_groups=len(raw_groups),
            returned=len(groups),
            groups=groups,
        )

    @mcp.tool(annotations=read_only)
    async def get_arxiv_papers(
        categories: Annotated[list[str] | None, Field(description=f"arXiv categories. Default: {', '.join(DEFAULT_ARXIV_CATEGORIES)}.")] = None,
        days: Annotated[int, Field(ge=1, le=14, description="Only include papers first submitted in the last N days.")] = 3,
        max_results: Annotated[int, Field(ge=10, le=200, description="How many papers to request from arXiv.")] = 100,
    ) -> ArxivResult:
        """Fetch the newest arXiv preprints in the given categories (one arXiv request, newest first), to find
        research before journalists cover it. Preprints are NOT peer-reviewed; always say so.
        Papers already made into videos are flagged with `already_covered`, not hidden.
        If `possibly_truncated` is true, more papers exist in the window than were fetched.
        """
        now = deps.now()
        cats = categories or DEFAULT_ARXIV_CATEGORIES
        url = newest_query_url(cats, max_results)
        async with deps.http() as client:
            try:
                fetched = await fetch_arxiv(client, url)
            except Exception as exc:
                raise ToolError(f"arXiv request failed: {_describe(exc)} ({url})") from exc
        recent = sorted((p for p in fetched if within_days(p.published, days, now)), key=lambda p: (p.published, p.id), reverse=True)
        items = [FlaggedPaper(**p.model_dump(), already_covered=covered_flag(deps.store.videos_for_keys([p.id]))) for p in recent]
        return ArxivResult(
            generated_at=iso_now(now),
            window_days=days,
            categories=cats,
            query_url=url,
            total_fetched=len(fetched),
            possibly_truncated=len(fetched) == max_results and bool(fetched) and within_days(fetched[-1].published, days, now),
            total_matching=len(items),
            items=items,
        )

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=True, open_world_hint=False))
    async def log_posted_video(
        format: Annotated[Format, Field(description="'short' (TikTok, Shorts, Reels) or 'long' (a full YouTube video).")],
        platform: Annotated[Platform, Field(description="Where it's published.")],
        video_title: Annotated[str, Field(min_length=1, description="The published video's title.")],
        video_url: Annotated[str, Field(description="Link to the published video.")],
        group_id: Annotated[str | None, Field(description="The story's group_id from get_stories.")] = None,
        story_urls: Annotated[list[str] | None, Field(description="Story or paper URLs, if there's no group_id (e.g. a story the user found themselves).")] = None,
        identifiers: Annotated[list[str] | None, Field(description="Extra paper identifiers, like 'doi:10.1038/...' or 'arxiv:2609.01234'.")] = None,
        story_title: Annotated[str | None, Field(description="Defaults to the group's headline.")] = None,
        note: Annotated[str | None, Field(max_length=500)] = None,
    ) -> LogResult:
        """Record a PUBLISHED video about a story. Call this only after the user confirms the video is live and
        gives you its link: never for planned, drafted or scheduled videos.

        Log each video separately: a short and a long video on the same story are two calls, and the story will
        then show as covered 'both'. Logged stories keep appearing in results, flagged with the video titles.
        """
        keys: set[str] = set()
        headline = None
        if group_id:
            snap = deps.store.snapshot(group_id)
            if snap is None:
                raise ToolError(f"Unknown group_id {group_id!r}. Run get_stories again, or pass story_urls instead.")
            headline, snap_keys = snap
            keys.update(snap_keys)
        for url in story_urls or []:
            if urlsplit(url).scheme not in ("http", "https"):
                raise ToolError(f"Not a web link: {url!r}")
            keys.add(item_key(url))
        for ident in identifiers or []:
            if not is_identifier(ident):
                raise ToolError(f"Identifiers look like 'doi:10.xxxx/...' or 'arxiv:2609.01234', got {ident!r}")
            keys.add(ident)
        if not keys:
            raise ToolError("Say which story this video covers: pass group_id (from get_stories) or story_urls.")

        _check_video_url(video_url, platform)
        title = story_title or headline
        if not title:
            raise ToolError("story_title is required when there's no group_id.")

        video, existed = deps.store.add_video(
            story_title=title, video_title=video_title, format=format, platform=platform, video_url=video_url,
            posted_on=iso_now(deps.now()), note=note, keys=sorted(keys),
        )
        return LogResult(video=video, was_already_logged=existed, linked_keys=deps.store.video_keys(video.video_id))

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
    async def list_posted_videos(
        days: Annotated[int | None, Field(ge=1, description="Only videos logged in the last N days. Omit for all.")] = None,
        format: Annotated[Format | None, Field(description="Only 'short' or only 'long'.")] = None,
    ) -> VideoList:
        """List your published videos, newest first."""
        since = iso_now(deps.now() - timedelta(days=days)) if days else None
        videos = deps.store.list_videos(since, format)
        return VideoList(total=len(videos), videos=videos)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
    async def delete_posted_video(
        video_id: Annotated[int, Field(description="video_id from list_posted_videos.")],
    ) -> DeleteResult:
        """Remove a video from the log, e.g. one logged by mistake. Only call when the user asks."""
        return DeleteResult(deleted=deps.store.delete_video(video_id), video_id=video_id)

    return mcp


def _check_video_url(url: str, platform: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ToolError(f"video_url must be a link to the published video, got {url!r}")
    hosts = _PLATFORM_HOSTS.get(platform)
    host = parts.hostname.lower()
    if hosts and not any(host == h or host.endswith("." + h) for h in hosts):
        raise ToolError(f"That doesn't look like a {platform} link: {url}")


def _describe(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code} {exc.response.reason_phrase}".strip()
    if isinstance(exc, httpx.TimeoutException):
        return "timed out"
    return f"{type(exc).__name__}: {exc}"
