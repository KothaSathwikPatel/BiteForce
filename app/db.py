"""Database schema (SQLAlchemy Core) and engine factory. Works on SQLite and Postgres."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool, StaticPool

metadata = MetaData()

stalls = Table(
    "stalls",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(60), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("lat", Float, nullable=False),
    Column("lng", Float, nullable=False),
    Column("is_seed", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

devices = Table(
    "devices",
    metadata,
    Column("device_hash", String(64), primary_key=True),
    Column("first_seen", DateTime(timezone=True), nullable=False),
)

reports = Table(
    "reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("stall_id", Integer, ForeignKey("stalls.id"), nullable=False, index=True),
    Column("device_hash", String(64), nullable=False, index=True),
    Column("network_hash", String(64), nullable=False, index=True),
    Column("symptoms", String(200), nullable=False),
    Column("eaten_at", DateTime(timezone=True), nullable=False, index=True),
    Column("onset_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("is_simulated", Boolean, nullable=False, default=False),
)

alert_events = Table(
    "alert_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("stall_id", Integer, ForeignKey("stalls.id"), nullable=False, index=True),
    Column("level", String(12), nullable=False),
    Column("n_cases", Integer, nullable=False),
    Column("p_value", Float),
    Column("action", String(24), nullable=False),  # sent | held | skipped_no_email | error
    Column("ai_source", String(20)),
    Column("ai_send", Boolean),
    Column("ai_confidence", Float),
    Column("ai_reasons", Text),  # JSON list
    Column("email_id", String(80)),
    Column("detail", String(300)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # keep one shared in-memory database
        return create_engine(url, **kwargs)
    # Serverless functions: no long-lived pool, let the provider's pooler handle it.
    return create_engine(url, poolclass=NullPool, pool_pre_ping=True)
