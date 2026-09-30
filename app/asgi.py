"""ASGI entrypoint: `uvicorn app.asgi:app` locally, imported by api/index.py on Vercel."""

from .main import create_app

app = create_app()
