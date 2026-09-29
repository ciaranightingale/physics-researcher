"""The deployable web app: host checking, the path secret, and a real HTTP round trip."""

import pytest
from starlette.testclient import TestClient

from science_scout.app import create_app

HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


@pytest.fixture
def app_env(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH_SECRET", "s3cret")
    monkeypatch.setenv("ALLOWED_HOSTS", "scout.test")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "scout.db"))


def test_serves_tools_on_the_secret_path(app_env):
    with TestClient(create_app(), base_url="http://scout.test") as c:
        r = c.post("/mcp/s3cret", json=TOOLS_LIST, headers=HEADERS)
        assert r.status_code == 200
        assert "get_stories" in {t["name"] for t in r.json()["result"]["tools"]}
        assert c.post("/mcp", json=TOOLS_LIST, headers=HEADERS).status_code == 404
        assert c.post("/mcp/wrong", json=TOOLS_LIST, headers=HEADERS).status_code == 404


def test_rejects_unknown_hosts(app_env):
    with TestClient(create_app(), base_url="http://evil.test") as c:
        assert c.post("/mcp/s3cret", json=TOOLS_LIST, headers=HEADERS).status_code in (403, 421)
