# Test settings: use SQLite in-memory without a remote database.
# This imports normal settings then overrides DATABASES for tests.
from .settings import *  # noqa: F401,F403

# Use fast in-memory SQLite for test runs to avoid CREATE DATABASE requirements on remote Postgres
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Ensure migrations run in tests as usual
MIGRATION_MODULES = getattr(globals(), 'MIGRATION_MODULES', None) or {}
