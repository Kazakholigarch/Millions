"""Production WSGI entrypoint, e.g. `gunicorn wsgi:app`. `run.py` is for
local development (Flask's own dev server); this is what a real host
(Render, Railway, a VPS behind nginx, ...) should point at."""
from app import create_app

app = create_app()
