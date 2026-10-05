import argparse
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

import psycopg2
from dotenv import dotenv_values


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RENDER_SERVICE_ID = "srv-dao3huoae00c73akpv40"
PRODUCTION_DATABASE_NAME = "sklepzdoniczkami_prod"
LOCAL_DATABASE_NAME = "sklepzdoniczkami_dev"
LOCAL_PORT = 5435


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


def run_postgres_tool(command, environment, log_file):
    result = subprocess.run(command, env=environment, capture_output=True, text=True)
    if result.returncode:
        log_file.write_text(
            f"Command failed with exit code {result.returncode}.\n"
            f"{result.stderr}",
            encoding="utf-8",
        )
        raise RuntimeError(
            f"PostgreSQL utility failed; details are in the private log {log_file}."
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Copy a production snapshot into the isolated local development database. "
            "This does not modify Render or Neon."
        )
    )
    parser.add_argument(
        "--confirm-empty-local-target",
        action="store_true",
        help="Confirm that the existing local target may be replaced.",
    )
    arguments = parser.parse_args()
    if not arguments.confirm_empty_local_target:
        parser.error("Pass --confirm-empty-local-target to authorize replacing the local target.")

    render_api_key = dotenv_values(REPOSITORY_ROOT / ".env").get("RENDER_API_KEY")
    if not render_api_key:
        raise RuntimeError("RENDER_API_KEY is missing from the local .env file.")

    request = Request(
        f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars",
        headers={"Authorization": f"Bearer {render_api_key}"},
    )
    with urlopen(request, timeout=30) as response:
        render_environment = json.load(response)
    render_variables = {
        item["envVar"]["key"]: item["envVar"]["value"] for item in render_environment
    }
    source_url = render_variables.get("DATABASE_URL_PRODUCTION")
    if not source_url:
        raise RuntimeError("The production database URL was not found on Render.")

    source = connection_parts(source_url)
    if (
        source["dbname"] != PRODUCTION_DATABASE_NAME
        or not source["host"]
        or not source["host"].endswith(".neon.tech")
    ):
        raise RuntimeError("The configured source is not the expected Neon production database.")

    local_root = Path(os.environ["LOCALAPPDATA"]) / "Sklepzdoniczkami"
    local_values = dotenv_values(local_root / ".env.selfhost")
    target_url = local_values.get("DATABASE_URL_DEVELOPMENT")
    if not target_url:
        raise RuntimeError("The private local development database configuration is missing.")

    target = connection_parts(target_url)
    if (
        target["dbname"] != LOCAL_DATABASE_NAME
        or target["host"] not in {"127.0.0.1", "localhost", "::1"}
        or target["port"] != LOCAL_PORT
    ):
        raise RuntimeError("Refusing to restore: the target is not the isolated local database.")

    target_connection = psycopg2.connect(**target, connect_timeout=5)
    try:
        with target_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM auth_user")
            users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sklepzdoniczkami_order")
            orders = cursor.fetchone()[0]
    finally:
        target_connection.close()

    if users or orders:
        raise RuntimeError(
            "Refusing to replace the local target because it already contains users or orders."
        )

    postgres_bin = Path(r"C:\Program Files\PostgreSQL\18\bin")
    pg_dump = postgres_bin / "pg_dump.exe"
    pg_restore = postgres_bin / "pg_restore.exe"
    if not pg_dump.is_file() or not pg_restore.is_file():
        raise RuntimeError("PostgreSQL 18 pg_dump and pg_restore are required.")

    migration_directory = local_root / "migration"
    migration_directory.mkdir(parents=True, exist_ok=True)
    dump_file = migration_directory / "production-initial.dump"
    log_file = migration_directory / "migration.log"
    if dump_file.exists():
        raise RuntimeError(
            f"A snapshot already exists at {dump_file}; refusing to overwrite it."
        )

    try:
        run_postgres_tool(
            [
                str(pg_dump),
                "--format=custom",
                "--no-owner",
                "--no-acl",
                f"--file={dump_file}",
            ],
            postgres_environment(source),
            log_file,
        )
        run_postgres_tool(
            [
                str(pg_restore),
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                f"--dbname={target['dbname']}",
                str(dump_file),
            ],
            postgres_environment(target),
            log_file,
        )
    except RuntimeError:
        if dump_file.exists() and dump_file.stat().st_size == 0:
            dump_file.unlink()
        raise

    verify_connection = psycopg2.connect(**target, connect_timeout=5)
    try:
        with verify_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM auth_user")
            users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sklepzdoniczkami_product")
            products = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sklepzdoniczkami_order")
            orders = cursor.fetchone()[0]
    finally:
        verify_connection.close()

    print(f"Production snapshot restored to the isolated local database.")
    print(f"Local counts — users: {users}; products: {products}; orders: {orders}.")
    print(f"Private snapshot retained at {dump_file}.")


if __name__ == "__main__":
    main()
