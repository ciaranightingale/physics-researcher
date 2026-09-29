"""The web app you deploy. Configured by environment variables:

  PATH_SECRET    Optional but recommended. The server then only answers on /mcp/<PATH_SECRET>.
  ALLOWED_HOSTS  Comma-separated Host headers to accept, e.g. "your-app.fly.dev". Default: localhost only.
  DB_PATH        Where the SQLite database lives. Put it on a persistent volume. Default: data/scout.db

Run locally:  uvicorn science_scout.app:create_app --factory --port 8000
"""

import os

from mcp.server.transport_security import TransportSecuritySettings

from .server import Deps, create_server
from .store import Store


def create_app():
    secret = os.environ.get("PATH_SECRET", "").strip()
    hosts = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost:*,127.0.0.1:*").split(",") if h.strip()]
    server = create_server(Deps(store=Store(os.environ.get("DB_PATH", "data/scout.db"))))
    return server.streamable_http_app(
        streamable_http_path=f"/mcp/{secret}" if secret else "/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=[]),
        host="0.0.0.0",
    )

