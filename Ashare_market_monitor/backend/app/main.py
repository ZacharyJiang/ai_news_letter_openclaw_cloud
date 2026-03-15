from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .data_source import AkshareDataSource
from .models import EtfFilters, EtfListResponse, KlineResponse
from .rate_limiter import RateLimiter
from .repository import JsonRepository
from .services import ETFService


class SyncRequest(BaseModel):
    codes: list[str] | None = None
    limit: int | None = None


repo = JsonRepository(settings.data_dir)
limiter = RateLimiter(settings.datasource_qps)
datasource = AkshareDataSource(
    limiter=limiter,
    trading_fee_pct=settings.default_trading_fee_pct,
)
service = ETFService(settings=settings, repo=repo, data_source=datasource)

app = FastAPI(title="A-Share ETF Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).resolve().parent / "web"
ASSETS_DIR = WEB_DIR / "assets"

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/", include_in_schema=False)
def web_index() -> FileResponse:
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="web page not found")
    return FileResponse(index_file)


@app.on_event("startup")
def on_startup() -> None:
    # Bootstrap metadata/extreme cache in background; non-blocking startup.
    service.trigger_background_sync(limit=settings.startup_sync_batch)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "sync_status": service.get_sync_status()}


@app.get("/api/etfs", response_model=EtfListResponse)
def list_etfs(
    keyword: str | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    min_scale: float | None = Query(default=None),
    max_scale: float | None = Query(default=None),
    min_fee: float | None = Query(default=None),
    max_fee: float | None = Query(default=None),
    min_distance: float | None = Query(default=None),
    max_distance: float | None = Query(default=None),
    distance_mode: Literal["from_high", "from_low"] = Query(default="from_high"),
    sort_by: Literal[
        "code",
        "name",
        "price",
        "fund_scale_billion",
        "total_fee_pct",
        "drawdown_from_ath_pct",
        "rebound_from_atl_pct",
    ] = Query(default="fund_scale_billion"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=60, ge=1, le=200),
) -> EtfListResponse:
    filters = EtfFilters(
        keyword=keyword,
        min_price=min_price,
        max_price=max_price,
        min_scale=min_scale,
        max_scale=max_scale,
        min_fee=min_fee,
        max_fee=max_fee,
        min_distance=min_distance,
        max_distance=max_distance,
        distance_mode=distance_mode,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
    )
    payload = service.get_list_payload(filters)
    return EtfListResponse(**payload)


@app.get("/api/etfs/{code}/kline", response_model=KlineResponse)
def get_kline(
    code: str,
    period: Literal["day", "week", "month"] = Query(default="day"),
) -> KlineResponse:
    code = code.strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="code must be 6-digit symbol")

    payload = service.get_kline_payload(code=code, period=period)
    if not payload["bars"]:
        raise HTTPException(status_code=404, detail="kline data not found")
    return KlineResponse(**payload)


@app.get("/api/sync/status")
def get_sync_status() -> dict:
    return service.get_sync_status()


@app.post("/api/sync")
def start_sync(req: SyncRequest) -> dict:
    started = service.trigger_background_sync(codes=req.codes, limit=req.limit)
    return {"started": started, "status": service.get_sync_status()}
