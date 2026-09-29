"""Drives the real server through a real MCP client, in-process, with fixture feeds instead of the network."""

import pytest

pytestmark = pytest.mark.anyio

GRAPHENE_DOI = "doi:10.1038/s41567-026-00001-x"


async def call(client, name: str, **args) -> dict:
    res = await client.call_tool(name, args)
    assert not res.is_error, res.content
    return res.structured_content


async def call_error(client, name: str, **args) -> str:
    res = await client.call_tool(name, args)
    assert res.is_error
    return res.content[0].text


def by_headline(result: dict) -> dict[str, dict]:
    return {g["headline"]: g for g in result["groups"]}


async def test_lists_five_tools(client):
    tools = {t.name for t in (await client.list_tools()).tools}
    assert tools == {"get_stories", "get_arxiv_papers", "log_posted_video", "list_posted_videos", "delete_posted_video"}


async def test_groups_same_story_across_outlets_and_the_paper(client):
    r = await call(client, "get_stories", days=7)
    groups = by_headline(r)
    assert list(groups) == [
        "Twisted graphene reveals a new quantum phase",
        "Record-breaking black hole merger spotted by gravitational wave detectors",
        "Our physics reading list for September",
    ]

    graphene = groups["Twisted graphene reveals a new quantum phase"]
    assert graphene["source_count"] == 3
    assert [s["source"] for s in graphene["sources"]] == ["journal", "news-a", "news-b"]
    assert graphene["identifiers"] == [GRAPHENE_DOI]
    assert graphene["match_evidence"][0]["reason"] == "same_paper"
    assert graphene["already_covered"] is None

    merger = groups["Record-breaking black hole merger spotted by gravitational wave detectors"]
    assert merger["source_count"] == 2
    assert {e["reason"] for e in merger["match_evidence"]} == {"similar_headline"}
    assert [p["id"] for p in merger["preprints"]] == ["arxiv:2609.04567"]
    assert merger["preprints"][0]["kind"] == "preprint"

    roundup = groups["Our physics reading list for September"]
    assert roundup["identifiers"] == []  # linked 8 papers: treated as a round-up, not grouped on


async def test_reports_failures_and_gaps(client):
    r = await call(client, "get_stories", days=7)
    assert r["errors"] == [{"source": "broken", "error": "HTTP 500 Internal Server Error"}]
    assert r["skipped_no_date"] == 1
    assert r["items_per_source"] == {"news-a": 4, "news-b": 2, "journal": 1, "quiet": 0}  # in-window items per feed, before de-duplication
    assert r["article_pages"] == {"cached": 0, "fetched": 4, "failed": 1, "too_many_links": 1, "pending": 0}


async def test_flags_feeds_that_load_but_have_gone_quiet(client):
    r = await call(client, "get_stories", days=7)
    assert r["stale_sources"] == [{"source": "quiet", "newest_item": "2026-08-17T09:00:00Z", "days_since_newest": 24}]
    assert "quiet" not in {e["source"] for e in r["errors"]}  # stale is not the same as broken


async def test_article_pages_are_fetched_once_and_results_repeat_exactly(client, web):
    first = await call(client, "get_stories", days=7)
    pages_after_first = len(web.page_requests())
    second = await call(client, "get_stories", days=7)
    retried = web.page_requests()[pages_after_first:]
    assert retried == ["https://news-b.test/heaviest-merger"]  # only the page that failed is retried
    assert second["article_pages"]["cached"] == 4
    assert first["groups"] == second["groups"]


async def test_page_lookup_cap_reports_pending(client):
    r = await call(client, "get_stories", days=7, max_page_lookups=2)
    assert r["article_pages"]["pending"] == 3


async def test_covered_stories_are_flagged_not_hidden(client):
    r = await call(client, "get_stories", days=7)
    graphene = by_headline(r)["Twisted graphene reveals a new quantum phase"]

    short = await call(client, "log_posted_video", group_id=graphene["group_id"], format="short", platform="tiktok",
                       video_title="The quantum phase hiding in twisted graphene", video_url="https://www.tiktok.com/@channel/video/111")
    assert short["video"]["story_title"] == "Twisted graphene reveals a new quantum phase"
    assert GRAPHENE_DOI in short["linked_keys"]

    flagged = by_headline(await call(client, "get_stories", days=7))["Twisted graphene reveals a new quantum phase"]
    assert flagged["already_covered"]["covered_as"] == "short"
    assert flagged["already_covered"]["videos"][0]["video_title"] == "The quantum phase hiding in twisted graphene"

    # A long video logged against just one outlet's URL still flags the whole group.
    await call(client, "log_posted_video", story_urls=["https://news-b.test/graphene-phase"], story_title="Graphene phase",
               format="long", platform="youtube", video_title="Twisted graphene, explained", video_url="https://youtu.be/abc123")
    flagged = by_headline(await call(client, "get_stories", days=7))["Twisted graphene reveals a new quantum phase"]
    assert flagged["already_covered"]["covered_as"] == "both"
    assert [v["format"] for v in flagged["already_covered"]["videos"]] == ["short", "long"]


async def test_logging_rules(client):
    r = await call(client, "get_stories", days=7)
    gid = r["groups"][0]["group_id"]
    base = dict(format="short", platform="tiktok", video_title="t", video_url="https://www.tiktok.com/@channel/video/1")

    assert "doesn't look like a youtube link" in await call_error(client, "log_posted_video", **{**base, "platform": "youtube"}, group_id=gid)
    assert "pass group_id" in await call_error(client, "log_posted_video", **base)
    assert "Unknown group_id" in await call_error(client, "log_posted_video", **base, group_id="g_nope")
    assert "Identifiers look like" in await call_error(client, "log_posted_video", **base, group_id=gid, identifiers=["10.1038/x"])

    first = await call(client, "log_posted_video", **base, group_id=gid)
    again = await call(client, "log_posted_video", **base, group_id=gid)
    assert (first["was_already_logged"], again["was_already_logged"]) == (False, True)
    assert again["video"]["video_id"] == first["video"]["video_id"]


async def test_arxiv_papers_flag_covered_preprints(client):
    r = await call(client, "get_stories", days=7)
    merger = by_headline(r)["Record-breaking black hole merger spotted by gravitational wave detectors"]
    await call(client, "log_posted_video", group_id=merger["group_id"], format="long", platform="youtube",
               video_title="The biggest black hole crash ever heard", video_url="https://www.youtube.com/watch?v=xyz")

    papers = await call(client, "get_arxiv_papers", days=3, categories=["astro-ph.HE", "quant-ph"])
    assert [p["id"] for p in papers["items"]] == ["arxiv:2609.04567", "arxiv:2609.03210"]
    assert papers["items"][0]["already_covered"]["covered_as"] == "long"
    assert papers["items"][1]["already_covered"] is None
    assert papers["possibly_truncated"] is False
    assert papers["items"][0]["categories"] == ["astro-ph.HE", "gr-qc"]


async def test_list_and_delete(client):
    r = await call(client, "get_stories", days=7)
    gid = r["groups"][0]["group_id"]
    s = await call(client, "log_posted_video", group_id=gid, format="short", platform="tiktok", video_title="s", video_url="https://tiktok.com/@c/video/1")
    await call(client, "log_posted_video", group_id=gid, format="long", platform="youtube", video_title="l", video_url="https://youtube.com/watch?v=1")

    assert (await call(client, "list_posted_videos"))["total"] == 2
    assert [v["video_title"] for v in (await call(client, "list_posted_videos", format="short"))["videos"]] == ["s"]

    assert (await call(client, "delete_posted_video", video_id=s["video"]["video_id"]))["deleted"] is True
    flagged = (await call(client, "get_stories", days=7))["groups"][0]["already_covered"]
    assert flagged["covered_as"] == "long"


async def test_bad_arguments_rejected(client):
    res = await client.call_tool("get_stories", {"days": 365})
    assert res.is_error
