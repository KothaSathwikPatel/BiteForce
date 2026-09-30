"""HTTP routes. Thin: parse input, call the service, return JSON."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from .auth import read_token
from .schemas import GoogleIn, ReportIn, SimulateIn
from .security import client_ip, valid_device_id
from .service import BiteTraceService

router = APIRouter(prefix="/api")


def get_service(request: Request) -> BiteTraceService:
    return request.app.state.service


Service = Annotated[BiteTraceService, Depends(get_service)]


def device_id(x_device_id: Annotated[str | None, Header()] = None) -> str:
    if not valid_device_id(x_device_id):
        raise HTTPException(status_code=400, detail="Missing or invalid X-Device-Id header.")
    return x_device_id  # type: ignore[return-value]


def current_user(request: Request, svc: Service) -> tuple[str, str] | None:
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    return read_token(svc.settings.secret_salt, token, svc.clock())


User = Annotated[tuple[str, str] | None, Depends(current_user)]


def require_demo(svc: Service) -> None:
    if not svc.settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found.")


@router.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config", tags=["meta"])
def config(svc: Service) -> dict[str, Any]:
    return svc.public_config()


@router.get("/stalls", tags=["stalls"])
def list_stalls(svc: Service) -> list[dict[str, Any]]:
    return svc.list_stalls()


@router.get("/stalls/{stall_id}", tags=["stalls"])
def stall_detail(stall_id: int, svc: Service) -> dict[str, Any]:
    return svc.stall_detail(stall_id)


@router.get("/alerts", tags=["alerts"])
def recent_alerts(svc: Service, limit: Annotated[int, Query(ge=1, le=50)] = 20) -> list[dict[str, Any]]:
    return svc.recent_alerts(limit)


@router.post("/reports", status_code=201, tags=["reports"])
def create_report(
    payload: ReportIn,
    request: Request,
    svc: Service,
    device: Annotated[str, Depends(device_id)],
    user: User,
) -> dict[str, Any]:
    ip = client_ip(request.headers, request.client.host if request.client else None)
    return svc.submit_report(payload, device, ip, user)


@router.post("/auth/google", tags=["account"])
def google_sign_in(payload: GoogleIn, svc: Service) -> dict[str, Any]:
    return svc.sign_in(payload.credential)


@router.get("/me/reports", tags=["account"])
def my_reports(svc: Service, user: User) -> dict[str, Any]:
    return svc.my_reports(user)


@router.post("/demo/simulate", tags=["demo"], dependencies=[Depends(require_demo)])
def simulate(payload: SimulateIn, svc: Service) -> dict[str, Any]:
    return svc.simulate_outbreak(payload.stall_id, payload.cases)


@router.post("/demo/reset", tags=["demo"], dependencies=[Depends(require_demo)])
def reset(svc: Service) -> dict[str, str]:
    svc.reset_demo()
    return {"status": "reset"}
