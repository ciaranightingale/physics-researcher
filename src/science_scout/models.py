"""The shapes every tool returns. Pydantic models become the tools' structured output schemas."""

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["journal", "press-office", "news", "preprint"]
Format = Literal["short", "long"]
Platform = Literal["youtube", "tiktok", "other"]


class Item(BaseModel):
    """One story or paper, in the same shape whichever source it came from."""

    id: str = Field(description="Canonical key: `arxiv:<id>` or `url:<canonical url>`.")
    title: str
    url: str
    published: str = Field(description="ISO 8601, UTC.")
    summary: str
    source: str
    source_name: str
    tier: int = Field(description="0 = preprint, 1 = primary source, 2 = journalism.")
    kind: Kind
    authors: list[str] = []
    categories: list[str] = []
    identifiers: list[str] = Field(default=[], description="DOIs and arXiv IDs of the paper(s) this item is about or links to.")


class PostedVideo(BaseModel):
    video_id: int
    video_title: str
    format: Format
    platform: Platform
    video_url: str
    posted_on: str
    story_title: str
    note: str | None = None


class CoveredFlag(BaseModel):
    """Present when you've already posted a video on this story. Informational only: nothing is hidden."""

    covered_as: Literal["short", "long", "both"]
    videos: list[PostedVideo]


class MatchEvidence(BaseModel):
    reason: Literal["same_link", "same_paper", "similar_headline"]
    detail: str
    items: list[str]


class StoryGroup(BaseModel):
    group_id: str = Field(description="Pass this to log_posted_video once a video on this story is published.")
    headline: str
    latest_published: str
    source_count: int
    sources: list[Item]
    identifiers: list[str]
    preprints: list[Item] = Field(default=[], description="arXiv preprints linked from this story. Not peer-reviewed.")
    match_evidence: list[MatchEvidence]
    already_covered: CoveredFlag | None = None


class SourceError(BaseModel):
    source: str
    error: str


class StaleSource(BaseModel):
    source: str
    newest_item: str | None = Field(description="Publication date of the feed's newest item, or null if the feed was empty.")
    days_since_newest: int | None


class StoriesResult(BaseModel):
    generated_at: str
    window_days: int
    sources_checked: list[str]
    items_per_source: dict[str, int]
    errors: list[SourceError]
    stale_sources: list[StaleSource] = Field(
        description="Feeds that loaded fine but have posted nothing recently. They may have moved or stopped updating."
    )
    skipped_no_date: int
    article_pages: dict[str, int] = Field(description="Link lookups: cached, fetched, failed, too_many_links, pending.")
    total_groups: int
    returned: int
    groups: list[StoryGroup]


class FlaggedPaper(Item):
    already_covered: CoveredFlag | None = None


class ArxivResult(BaseModel):
    generated_at: str
    window_days: int
    categories: list[str]
    query_url: str
    total_fetched: int
    possibly_truncated: bool
    total_matching: int
    items: list[FlaggedPaper]


class LogResult(BaseModel):
    video: PostedVideo
    was_already_logged: bool
    linked_keys: list[str] = Field(description="Story links and paper identifiers this video is now attached to.")


class VideoList(BaseModel):
    total: int
    videos: list[PostedVideo]


class DeleteResult(BaseModel):
    deleted: bool
    video_id: int
