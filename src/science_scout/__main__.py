"""Run the server as a local stdio MCP server: `python -m science_scout`.

This is the local counterpart to `app.py`. Nothing is served over the network: the client (Claude
Code, Claude Desktop) starts this process and talks to it over stdin/stdout.

  DB_PATH  Where the SQLite database lives. Defaults to a fixed per-user path rather than
           anything relative, because the client chooses the working directory and a relative
           path would silently give you a different videos log per directory - which looks like
           "nothing is covered yet" rather than an error.
"""

import os
import sys
from pathlib import Path

from .server import Deps, create_server
from .store import Store


def default_db_path() -> Path:
    """A stable per-user location, honouring XDG_DATA_HOME where it is set."""
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "science-scout" / "scout.db"


def main() -> None:
    db = Path(os.environ["DB_PATH"]) if os.environ.get("DB_PATH") else default_db_path()
    # stdout is the MCP transport, so anything human-readable has to go to stderr.
    print(f"science-scout: video log at {db}", file=sys.stderr)
    create_server(Deps(store=Store(db))).run()


if __name__ == "__main__":
    main()
