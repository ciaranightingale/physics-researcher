from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from mcp import Client

from science_scout.server import Deps, create_server
from science_scout.sources import FeedSource
from science_scout.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

FEEDS = [
    FeedSource("news-a", "News A", "https://feeds.test/news-a", 2, "news"),
    FeedSource("news-b", "News B", "https://feeds.test/news-b", 2, "news"),
    FeedSource("journal", "Journal", "https://feeds.test/journal", 1, "journal"),
    FeedSource("broken", "Broken", "https://feeds.test/broken", 1, "press-office"),
    FeedSource("quiet", "Quiet", "https://feeds.test/quiet", 2, "news"),
]

ROUTES = {
    "feeds.test/news-a": "news_a.xml",
    "feeds.test/news-b": "news_b.xml",
    "feeds.test/journal": "journal.xml",
    "feeds.test/quiet": "quiet.xml",
    "news-a.test/2026/09/twisted-graphene/": "page_graphene_a.html",
    "news-b.test/graphene-phase": "page_graphene_b.html",
    "news-a.test/2026/09/bh-merger/": "page_bh_a.html",
    "news-a.test/2026/09/roundup/": "page_roundup.html",
}


class FakeWeb:
    """Serves fixtures instead of the internet, and records every request."""

    def __init__(self):
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.requests.append(str(url))
        if url.host == "export.arxiv.org":
            body = (FIXTURES / "arxiv_newest.xml").read_text()
            if "id_list" in url.params:
                # Return only the requested papers, as the real API does.
                wanted = set(url.params["id_list"].split(","))
                entries = body.split("<entry>")
                body = entries[0] + "".join("<entry>" + e for e in entries[1:] if any(w in e for w in wanted))
                if not body.rstrip().endswith("</feed>"):
                    body += "</feed>"
            return httpx.Response(200, text=body)
        key = f"{url.host.removeprefix('www.')}{url.path}"
        if key in ROUTES:
            return httpx.Response(200, text=(FIXTURES / ROUTES[key]).read_text())
        if url.host == "feeds.test":
            return httpx.Response(500)
        return httpx.Response(404)

    def page_requests(self) -> list[str]:
        return [r for r in self.requests if "feeds.test" not in r and "arxiv.org" not in r]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb()


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


@pytest.fixture
async def client(web: FakeWeb, store: Store):
    deps = Deps(
        store=store,
        http=lambda: httpx.AsyncClient(transport=httpx.MockTransport(web.handler), follow_redirects=True),
        now=lambda: NOW,
        feeds=FEEDS,
    )
    async with Client(create_server(deps)) as c:
        yield c
