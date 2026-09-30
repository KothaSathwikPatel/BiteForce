"""BiteTrace entry point.

Run locally with::

    uvicorn main:app --reload

The application itself lives in the ``app/`` package (outbreak engine, anti-abuse
weighting, AI review, e-mail escalation, REST routes). This module only exposes the
ASGI application under the conventional ``main:app`` name.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.asgi import app as _application

app: FastAPI = _application

__all__ = ["app"]