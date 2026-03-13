from typing import Literal

from pydantic import BaseModel, Field


SortField = Literal[
    "code",
    "name",
    "price",
    "fund_scale_billion",
    "total_fee_pct",
    "drawdown_from_ath_pct",
    "rebound_from_atl_pct",
]
SortOrder = Literal["asc", "desc"]
DistanceMode = Literal["from_high", "from_low"]


class EtfFilters(BaseModel):
    keyword: str | None = None

    min_price: float | None = None
    max_price: float | None = None

    min_scale: float | None = Field(default=None, description="单位: 亿")
    max_scale: float | None = Field(default=None, description="单位: 亿")

    min_fee: float | None = Field(default=None, description="单位: %")
    max_fee: float | None = Field(default=None, description="单位: %")

    min_distance: float | None = Field(default=None, description="单位: %")
    max_distance: float | None = Field(default=None, description="单位: %")

    distance_mode: DistanceMode = "from_high"

    sort_by: SortField = "fund_scale_billion"
    order: SortOrder = "desc"

    page: int = 1
    page_size: int = 60


class EtfItem(BaseModel):
    code: str
    name: str
    market: str | None = None

    price: float | None = None
    fund_scale_billion: float | None = None

    management_fee_pct: float | None = None
    custody_fee_pct: float | None = None
    sales_fee_pct: float | None = None
    subscription_fee_pct: float | None = None
    redemption_fee_pct: float | None = None
    trading_fee_pct: float | None = None
    total_fee_pct: float | None = None

    ath: float | None = None
    atl: float | None = None
    drawdown_from_ath_pct: float | None = None
    rebound_from_atl_pct: float | None = None

    updated_at: str | None = None


class EtfListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[EtfItem]
    sync_status: dict


class KlineBar(BaseModel):
    date: str
    open: float
    close: float
    high: float
    low: float
    volume: float | None = None
    amount: float | None = None
    amplitude_pct: float | None = None
    change_pct: float | None = None
    change_amount: float | None = None
    turnover_pct: float | None = None


class KlineResponse(BaseModel):
    code: str
    period: str
    ath: float
    atl: float
    drawdown_from_ath_pct: float
    rebound_from_atl_pct: float
    bars: list[KlineBar]
