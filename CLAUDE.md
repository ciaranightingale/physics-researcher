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
- `server.py`: the five MCP tools. `__main__.py`: the local stdio entry point, which is how it is actually used. `app.py`: the optional web app for remote use (env: `PATH_SECRET`, `ALLOWED_HOSTS`, `DB_PATH`).
- `feeds.py`, `arxiv.py`: fetching and parsing. `links.py`: reads article pages for DOIs/arXiv IDs. `grouping.py`: merges coverage of the same story. `store.py`: SQLite (videos log, link cache, group snapshots). `normalise.py`: pure helpers.
- `tests/`: pytest against fixture files; no network. `scripts/check_feeds.py`: checks the real feeds.

## Commands

```sh
python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pytest
python scripts/check_feeds.py
python -m science_scout                 # local stdio server, as Claude Code runs it
uvicorn science_scout.app:create_app --factory --port 8000   # only for remote use
```

## Status

- Working end to end against the live feeds as of 2026-09-29: all 7 feeds plus arXiv fetch, `get_stories` returns grouped stories with DOIs and linked preprints. 30 tests pass.
- CERN's old `api/news/news/feed.rss` was dead (404) and is now the site-wide `home.cern/feed/`.
- **Cross-source grouping does not fire, and that looks correct.** Checked over 7/14/30-day windows against the live feeds: zero merges between two different outlets, by either headline or DOI. These sources cover the same result months apart in feed order (APS wrote up the real-valued-quantum-theory paper 83 days before Physics World did), so nothing is there to merge inside a 30-day window. The headline path's real job on these feeds is de-duplicating one outlet against itself, which it does.
- `MIN_SHARED_WORDS` stays at 4. Lowering it collapses recurring programme titles - six separate "BBC Inside Science" episodes share exactly 3 words at overlap 1.00. `tests/test_grouping.py` pins both directions. `MIN_OVERLAP` is only pinned upward: at 0.5 no test breaks, because the 4-word requirement already rejects the generic pairs.
- `get_stories` silently ignores unknown arguments (`window_days` instead of `days` returns 7-day data with no error). Worth a look before the scout skill depends on it.
- `USER_AGENT` in `sources.py` still has the placeholder `you@example.com`.
- **Runs as a local stdio server** (`python -m science_scout`, wired up in `.mcp.json`). Verified over a real MCP client: all five tools listed, and the videos log survives a restart.
- Hosting is deliberately not done. It is only needed to reach the server from another device, and this is a single-user tool. `app.py` and the `Dockerfile` still work if that changes.
- The videos log defaults to `~/.local/share/science-scout/scout.db`, an absolute path on purpose: the client picks the working directory, and a relative default would silently give a different log per directory.

## Careful

- Don't change a source's `id` once videos are logged; don't change how `item_key` or identifiers are computed without a migration, or the covered log stops matching.
- Any behaviour change needs a test; keep tests offline (add fixtures rather than hitting the network).
- The MCP SDK is v2; many online examples are v1 and use different imports (`FastMCP` etc.).
