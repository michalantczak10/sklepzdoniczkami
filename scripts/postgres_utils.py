"""Shared PostgreSQL connection helpers for local self-hosting scripts."""

import os
from urllib.parse import parse_qs, unquote, urlparse


def connection_parts(database_url):
    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": unquote(parsed.path.lstrip("/")),
        "sslmode": query.get("sslmode", ["prefer"])[0],
        "channel_binding": query.get("channel_binding", ["prefer"])[0],
    }


def postgres_environment(connection):
    environment = os.environ.copy()
    environment.update(
        {
            "PGHOST": connection["host"],
            "PGPORT": str(connection["port"]),
            "PGUSER": connection["user"],
            "PGPASSWORD": connection["password"],
            "PGDATABASE": connection["dbname"],
            "PGSSLMODE": connection["sslmode"],
            "PGCHANNELBINDING": connection["channel_binding"],
        }
    )
    return environment
