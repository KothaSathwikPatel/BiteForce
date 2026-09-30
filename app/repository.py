"""All SQL lives here. The service layer never touches the database directly."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from .db import alert_events, devices, metadata, reports, stalls
from .domain import Case
from .timeutil import ensure_utc


@dataclass(frozen=True)
class StallRow:
    id: int
    name: str
    kind: str
    lat: float
    lng: float
    is_seed: bool


@dataclass(frozen=True)
class EventRow:
    id: int
    stall_id: int
    level: str
    n_cases: int
    p_value: float | None
    action: str
    ai_source: str | None
    ai_send: bool | None
    ai_confidence: float | None
    ai_reasons: list[str]
    email_id: str | None
    detail: str | None
    created_at: datetime


def _stall(row) -> StallRow:
    return StallRow(row.id, row.name, row.kind, row.lat, row.lng, bool(row.is_seed))


def _event(row) -> EventRow:
    return EventRow(
        id=row.id,
        stall_id=row.stall_id,
        level=row.level,
        n_cases=row.n_cases,
        p_value=row.p_value,
        action=row.action,
        ai_source=row.ai_source,
        ai_send=row.ai_send,
        ai_confidence=row.ai_confidence,
        ai_reasons=json.loads(row.ai_reasons) if row.ai_reasons else [],
        email_id=row.email_id,
        detail=row.detail,
        created_at=ensure_utc(row.created_at),
    )


class Repository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def init_schema(self) -> None:
        metadata.create_all(self.engine)

    # ---- stalls ---------------------------------------------------------
    def list_stalls(self) -> list[StallRow]:
        with self.engine.connect() as conn:
            return [_stall(r) for r in conn.execute(select(stalls).order_by(stalls.c.id))]

    def get_stall(self, stall_id: int) -> StallRow | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(stalls).where(stalls.c.id == stall_id)).first()
        return _stall(row) if row else None

    def count_stalls(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(stalls)).scalar_one()

    def add_stall(
        self, name: str, kind: str, lat: float, lng: float, now: datetime, is_seed: bool = False
    ) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(stalls).values(
                    name=name, kind=kind, lat=lat, lng=lng, is_seed=is_seed, created_at=now
                )
            )
            return int(result.inserted_primary_key[0])

    # ---- devices --------------------------------------------------------
    def touch_device(self, device_hash: str, first_seen: datetime) -> datetime:
        """Register a device the first time it is seen; return its stored first_seen."""
        with self.engine.begin() as conn:
            row = conn.execute(
                select(devices.c.first_seen).where(devices.c.device_hash == device_hash)
            ).first()
            if row is None:
                try:
                    conn.execute(insert(devices).values(device_hash=device_hash, first_seen=first_seen))
                    return first_seen
                except IntegrityError:  # concurrent insert of the same device
                    row = conn.execute(
                        select(devices.c.first_seen).where(devices.c.device_hash == device_hash)
                    ).first()
            return ensure_utc(row.first_seen)

    # ---- reports --------------------------------------------------------
    def count_device_reports(self, device_hash: str, since: datetime) -> int:
        return self._count(reports.c.device_hash == device_hash, since)

    def count_network_reports(self, network_hash: str, since: datetime) -> int:
        return self._count(reports.c.network_hash == network_hash, since)

    def _count(self, condition, since: datetime) -> int:
        with self.engine.connect() as conn:
            return conn.execute(
                select(func.count()).select_from(reports).where(
                    and_(condition, reports.c.created_at >= since)
                )
            ).scalar_one()

    def device_reported_stall_since(self, device_hash: str, stall_id: int, since: datetime) -> bool:
        with self.engine.connect() as conn:
            return (
                conn.execute(
                    select(reports.c.id).where(
                        and_(
                            reports.c.device_hash == device_hash,
                            reports.c.stall_id == stall_id,
                            reports.c.created_at >= since,
                        )
                    )
                ).first()
                is not None
            )

    def add_report(
        self,
        *,
        stall_id: int,
        device_hash: str,
        network_hash: str,
        symptoms: list[str],
        eaten_at: datetime,
        onset_at: datetime,
        created_at: datetime,
        is_simulated: bool = False,
    ) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(reports).values(
                    stall_id=stall_id,
                    device_hash=device_hash,
                    network_hash=network_hash,
                    symptoms=",".join(symptoms),
                    eaten_at=eaten_at,
                    onset_at=onset_at,
                    created_at=created_at,
                    is_simulated=is_simulated,
                )
            )
            return int(result.inserted_primary_key[0])

    def reports_by_device(self, device_hash: str, limit: int = 30) -> list[dict]:
        """A reporter's own history (used for signed-in accounts)."""
        query = (
            select(
                reports.c.id, reports.c.stall_id, stalls.c.name, stalls.c.kind,
                reports.c.symptoms, reports.c.eaten_at, reports.c.created_at,
            )
            .join(stalls, stalls.c.id == reports.c.stall_id)
            .where(reports.c.device_hash == device_hash)
            .order_by(reports.c.created_at.desc())
            .limit(limit)
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        return [
            {
                "id": r.id,
                "stall_id": r.stall_id,
                "stall_name": r.name,
                "kind": r.kind,
                "symptoms": r.symptoms.split(","),
                "eaten_at": ensure_utc(r.eaten_at).isoformat(),
                "created_at": ensure_utc(r.created_at).isoformat(),
            }
            for r in rows
        ]

    def cases_since(self, since: datetime, stall_id: int | None = None) -> list[tuple[int, Case]]:
        """(stall_id, Case) pairs for meals eaten since `since`."""
        query = (
            select(reports, devices.c.first_seen)
            .join(devices, devices.c.device_hash == reports.c.device_hash)
            .where(reports.c.eaten_at >= since)
        )
        if stall_id is not None:
            query = query.where(reports.c.stall_id == stall_id)
        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        return [
            (
                r.stall_id,
                Case(
                    device_hash=r.device_hash,
                    network_hash=r.network_hash,
                    eaten_at=ensure_utc(r.eaten_at),
                    onset_at=ensure_utc(r.onset_at),
                    created_at=ensure_utc(r.created_at),
                    symptoms=tuple(r.symptoms.split(",")),
                    device_first_seen=ensure_utc(r.first_seen),
                ),
            )
            for r in rows
        ]

    # ---- alert events (audit log) --------------------------------------
    def add_event(
        self,
        *,
        stall_id: int,
        level: str,
        n_cases: int,
        p_value: float | None,
        action: str,
        created_at: datetime,
        ai_source: str | None = None,
        ai_send: bool | None = None,
        ai_confidence: float | None = None,
        ai_reasons: list[str] | None = None,
        email_id: str | None = None,
        detail: str | None = None,
    ) -> int:
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(alert_events).values(
                    stall_id=stall_id,
                    level=level,
                    n_cases=n_cases,
                    p_value=p_value,
                    action=action,
                    ai_source=ai_source,
                    ai_send=ai_send,
                    ai_confidence=ai_confidence,
                    ai_reasons=json.dumps(ai_reasons or []),
                    email_id=email_id,
                    detail=detail,
                    created_at=created_at,
                )
            )
            return int(result.inserted_primary_key[0])

    def last_event(
        self, stall_id: int, since: datetime, actions: tuple[str, ...] | None = None
    ) -> EventRow | None:
        query = select(alert_events).where(
            and_(alert_events.c.stall_id == stall_id, alert_events.c.created_at >= since)
        )
        if actions:
            query = query.where(alert_events.c.action.in_(actions))
        with self.engine.connect() as conn:
            row = conn.execute(query.order_by(alert_events.c.id.desc()).limit(1)).first()
        return _event(row) if row else None

    def recent_events(self, limit: int = 20, stall_id: int | None = None) -> list[EventRow]:
        query = select(alert_events).order_by(alert_events.c.id.desc()).limit(limit)
        if stall_id is not None:
            query = query.where(alert_events.c.stall_id == stall_id)
        with self.engine.connect() as conn:
            return [_event(r) for r in conn.execute(query)]

    # ---- demo reset -------------------------------------------------------
    def reset(self) -> None:
        """Remove all reports, devices, audit events and user-created stalls."""
        with self.engine.begin() as conn:
            conn.execute(delete(alert_events))
            conn.execute(delete(reports))
            conn.execute(delete(devices))
            conn.execute(delete(stalls).where(stalls.c.is_seed.is_(False)))
