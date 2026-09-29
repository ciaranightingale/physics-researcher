# science-scout-mcp

A remote MCP server that gives Claude deterministic access to science news. Every configured source is fetched on every call, filtered to a date window, and returned in a fixed order. Coverage of the same story from different outlets is grouped into one entry, and stories you've already made videos about are flagged (never hidden).

## Tools

| Tool | What it does |
|---|---|
| `get_stories` | Fetches every feed in `sources.py` and returns **story groups**: all coverage of one story, plus the paper, in a single entry. Reports failed sources, **stale** sources (loaded fine but nothing new in 7 days), undated items and unread article pages instead of silently skipping them. |
| `get_arxiv_papers` | One arXiv API query for the newest preprints in your categories, to find research before journalists do. |
| `log_posted_video` | Records a **published** video (format, platform, title, link) against a story. Call it once per video: a short and a long on the same story show as covered "both". |
| `list_posted_videos` | Your published videos, newest first, optionally only shorts or only long-form. |
| `delete_posted_video` | Removes a video logged by mistake. |

## How grouping works

1. **Same paper (strong).** Science articles almost always link to the paper they're about. The server reads each article page once, pulls out DOIs and arXiv IDs from the links, and caches the result forever. Articles that link to the same paper are the same story. Journal items carry their own DOI.
2. **Similar headline (weaker).** When there's no shared link, headlines that share at least 4 content words, and most of the shorter headline's words, are grouped. `match_evidence` shows which words matched, so check these.

Pages linking more than 5 papers (reading lists, round-ups) are ignored for grouping so they can't glue unrelated stories together. Each group's `headline` comes from journalism if there is some (more readable than paper titles), and any linked arXiv preprint is attached with its abstract.

## How "already covered" works

Each logged video is attached to every key of its story: each outlet's link plus the paper's DOI/arXiv ID. A story is flagged if any of its keys match, so a new outlet covering a paper you've already done is flagged too. The flag shows `covered_as` ("short", "long" or "both") and each video's title and link. Nothing is ever excluded, so you can always cover a story again.

## Setup

Needs Python 3.11+.

```sh
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # 18 tests against fixture feeds, no network
python scripts/check_feeds.py   # fetches your real sources: ✓ working, ⚠ stale or empty, ✗ broken
```

Fix any source marked ✗ or ⚠ in `src/science_scout/sources.py`. The stale threshold is `STALE_AFTER_DAYS` in the same file (default 7); try `--stale-days 14` if a slow source keeps tripping it. Also put your email in `USER_AGENT`.

## Run locally

```sh
uvicorn science_scout.app:create_app --factory --port 8000
npx @modelcontextprotocol/inspector   # choose "Streamable HTTP", URL http://127.0.0.1:8000/mcp
```

## Deploy

Claude connects to custom connectors from Anthropic's cloud, so the server needs a public HTTPS URL. Use any host that runs a Docker container, gives you HTTPS, and offers a **persistent volume** for the SQLite file (Fly.io and Railway both do; check their current pricing). The `Dockerfile` is ready to go.

Environment variables:

| Variable | Value |
|---|---|
| `PATH_SECRET` | A long random string. The server then only answers on `/mcp/<PATH_SECRET>`. |
| `ALLOWED_HOSTS` | Your app's hostname, e.g. `science-scout.fly.dev`. |
| `DB_PATH` | Defaults to `/data/scout.db` in the container. Mount the volume at `/data`. |

## Connect to Claude

In Claude, go to Customize > Connectors, click **+**, choose **Add custom connector**, and paste `https://<your host>/mcp/<PATH_SECRET>`.

## Notes

- The path secret is a lightweight guard for a personal tool, not real auth. Add OAuth if you ever share it.
- `get_stories` reads at most 40 new article pages per call (`max_page_lookups`). Anything beyond that is reported as `pending` and picked up next call; because results are cached, runs after the first are fast.
- Grouping thresholds live at the top of `grouping.py`; tests pin the current behaviour.
