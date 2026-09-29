# science-scout-mcp

A remote MCP server (Python, official MCP SDK v2) that fetches science news for a physics YouTube/TikTok channel. Claude connects to it as a custom connector, and a separate "scout" skill turns its output into a shortlist of video ideas.

## Design rules (keep these)

- **Deterministic.** Same feeds in, same output out: fixed source order, stable sorting with tie-breakers, no randomness.
- **Never hide, always report.** Failed sources go in `errors`, feeds that load but have gone quiet go in `stale_sources`, undated items are counted, unread article pages are reported as `pending`. Nothing is silently dropped.
- **Covered stories are flagged, not filtered.** `already_covered` shows format(s) and video titles; the user may cover a story again.
- **Only published videos are logged**, one call per video, with a link that matches the platform.
- The server does rule-based work; judgement (ranking, angles, short vs long, topic filtering) belongs in the scout skill.

## Layout

- `src/science_scout/sources.py`: the source list, arXiv categories, stale threshold, User-Agent. Most day-to-day edits happen here.
- `server.py`: the five MCP tools. `app.py`: the deployable web app (env: `PATH_SECRET`, `ALLOWED_HOSTS`, `DB_PATH`).
- `feeds.py`, `arxiv.py`: fetching and parsing. `links.py`: reads article pages for DOIs/arXiv IDs. `grouping.py`: merges coverage of the same story. `store.py`: SQLite (videos log, link cache, group snapshots). `normalise.py`: pure helpers.
- `tests/`: pytest against fixture files; no network. `scripts/check_feeds.py`: checks the real feeds.

## Commands

```sh
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pytest
python scripts/check_feeds.py
uvicorn science_scout.app:create_app --factory --port 8000
```

## Status

- Working end to end against the live feeds as of 2026-09-29: all 7 feeds plus arXiv fetch, `get_stories` returns grouped stories with DOIs and linked preprints, 18 tests pass.
- CERN's old `api/news/news/feed.rss` was dead (404) and is now the site-wide `home.cern/feed/`.
- **Cross-source grouping is largely unproven in the wild.** A live run produced 57 groups but only one with more than a single item, and that one merged two BBC videos with each other — no two *different* outlets were ever merged. Either the sources genuinely don't overlap much in a 7-day window, or `headline_overlap` is too strict. Worth a look before trusting the dedup.
- `USER_AGENT` in `sources.py` still has the placeholder `you@example.com`.
- Not deployed yet. Needs a Docker host with HTTPS and a persistent volume for the SQLite file; host not chosen.

## Careful

- Don't change a source's `id` once videos are logged; don't change how `item_key` or identifiers are computed without a migration, or the covered log stops matching.
- Any behaviour change needs a test; keep tests offline (add fixtures rather than hitting the network).
- The MCP SDK is v2; many online examples are v1 and use different imports (`FastMCP` etc.).
