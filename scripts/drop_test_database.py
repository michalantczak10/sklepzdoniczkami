import os
import re

import psycopg2
from psycopg2 import sql


database_url = os.environ.get('DATABASE_URL')
test_database = os.environ.get('DJANGO_TEST_DATABASE_NAME')
if not database_url or not test_database:
    print('No Neon test database was configured; cleanup skipped.')
    raise SystemExit(0)

if not re.fullmatch(r'test_sklepzdoniczkami_dev_[0-9]+_[0-9]+', test_database):
    raise SystemExit('Refusing to clean up an unexpected Neon test database name.')

with psycopg2.connect(database_url, connect_timeout=15) as connection:
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', (test_database,))
        if cursor.fetchone():
            cursor.execute(
                sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(test_database))
            )
            print('Removed the isolated Neon test database.')
        else:
            print('The Neon test database was already removed.')
