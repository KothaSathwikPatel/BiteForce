"""Vercel serverless entrypoint. Static files in /public are served by the CDN;
only /api/* requests reach this ASGI app (see vercel.json)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.asgi import app  # noqa: E402,F401
