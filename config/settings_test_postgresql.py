import os

import dj_database_url

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': dj_database_url.parse(
        os.environ['DJANGO_TEST_DATABASE_URL'],
        conn_max_age=0,
    )
}
