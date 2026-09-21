import os


# The Playwright sync driver runs its dispatcher loop in the pytest thread.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
