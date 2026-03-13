from __future__ import annotations

from datetime import datetime
from typing import Any

import akshare as ak
import pandas as pd

from .rate_limiter import RateLimiter
from .utils import min_non_none, parse_percent, parse_scale_to_billion, safe_float


PERIOD_MAP = {
    "day": "daily",
    "week": "weekly",
    "month": "monthly",
}


def infer_market(code: str) -> str:
    if code.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


class AkshareDataSource:
    def __init__(self, limiter: RateLimiter, trading_fee_pct: float) -> None:
        self._limiter = limiter
        self._trading_fee_pct = trading_fee_pct

    def fetch_spot(self) -> pd.DataFrame:
        self._limiter.wait()
        df = ak.fund_etf_spot_em()
        if df is None or df.empty:
            return pd.DataFrame(columns=["code", "name", "price", "market"])

        columns = {c.strip(): c for c in df.columns}
        code_col = columns.get("代码") or columns.get("基金代码")
        name_col = columns.get("名称") or columns.get("基金简称")
        price_col = columns.get("最新价") or columns.get("最新") or columns.get("现价")

        if not code_col or not name_col or not price_col:
            raise RuntimeError(f"Unexpected spot schema: {list(df.columns)}")

        out = pd.DataFrame(
            {
                "code": df[code_col].astype(str).str.zfill(6),
                "name": df[name_col].astype(str),
                "price": pd.to_numeric(df[price_col], errors="coerce"),
            }
        )
        out["market"] = out["code"].map(infer_market)
        out = out.dropna(subset=["code", "name"]).drop_duplicates(subset=["code"])
        return out

    def fetch_basic_info(self, code: str) -> dict[str, Any]:
        self._limiter.wait()
        try:
            df = ak.fund_individual_basic_info_xq(symbol=code)
        except Exception:
            return {}

        if df is None or df.empty:
            return {}

        result: dict[str, Any] = {}

        lower_map = {str(k).strip(): str(v).strip() for k, v in zip(df.iloc[:, 0], df.iloc[:, 1])}
        scale_text = lower_map.get("最新规模") or lower_map.get("基金规模")

        if scale_text:
            result["fund_scale_billion"] = parse_scale_to_billion(scale_text)

        if "基金全称" in lower_map:
            result["full_name"] = lower_map["基金全称"]
        if "基金类型" in lower_map:
            result["fund_type"] = lower_map["基金类型"]

        return result

    def fetch_fee_info(self, code: str) -> dict[str, Any]:
        self._limiter.wait()
        try:
            df = ak.fund_individual_detail_info_xq(symbol=code)
        except Exception:
            return {
                "management_fee_pct": None,
                "custody_fee_pct": None,
                "sales_fee_pct": None,
                "subscription_fee_pct": None,
                "redemption_fee_pct": None,
                "trading_fee_pct": self._trading_fee_pct,
                "total_fee_pct": None,
            }

        if df is None or df.empty:
            return {
                "management_fee_pct": None,
                "custody_fee_pct": None,
                "sales_fee_pct": None,
                "subscription_fee_pct": None,
                "redemption_fee_pct": None,
                "trading_fee_pct": self._trading_fee_pct,
                "total_fee_pct": None,
            }

        columns = [str(c).strip() for c in df.columns]
        df2 = df.copy()
        df2.columns = columns

        management = None
        custody = None
        sales = None
        sub_candidates: list[float] = []
        red_candidates: list[float] = []

        if {"费用类型", "条件或名称", "费用"}.issubset(set(columns)):
            for _, row in df2.iterrows():
                fee_type = str(row.get("费用类型", "")).strip()
                cond = str(row.get("条件或名称", "")).strip()
                fee = parse_percent(row.get("费用"))

                if fee is None:
                    continue

                if fee_type == "买入规则":
                    sub_candidates.append(fee)
                elif fee_type == "卖出规则":
                    red_candidates.append(fee)
                elif fee_type == "其他费用":
                    if "管理" in cond:
                        management = fee
                    elif "托管" in cond:
                        custody = fee
                    elif "销售" in cond:
                        sales = fee
        else:
            # Fallback for schema variants: two-column table with item-value.
            for _, row in df2.iterrows():
                key = str(row.iloc[0])
                value = parse_percent(row.iloc[1] if len(row) > 1 else None)
                if value is None:
                    continue
                if "管理费" in key:
                    management = value
                elif "托管费" in key:
                    custody = value
                elif "销售服务费" in key:
                    sales = value
                elif "申购" in key:
                    sub_candidates.append(value)
                elif "赎回" in key:
                    red_candidates.append(value)

        subscription = min_non_none(sub_candidates)
        redemption = min_non_none(red_candidates)
        trading = self._trading_fee_pct

        parts = [management, custody, sales, subscription, redemption, trading]
        if any(v is not None for v in parts):
            total = sum(v for v in parts if v is not None)
        else:
            total = None

        return {
            "management_fee_pct": management,
            "custody_fee_pct": custody,
            "sales_fee_pct": sales,
            "subscription_fee_pct": subscription,
            "redemption_fee_pct": redemption,
            "trading_fee_pct": trading,
            "total_fee_pct": total,
        }

    def fetch_kline(self, code: str, period: str) -> pd.DataFrame:
        ak_period = PERIOD_MAP.get(period, "daily")
        self._limiter.wait()

        # Use broad date range to get full-history bars.
        try:
            df = ak.fund_etf_hist_em(
                symbol=code,
                period=ak_period,
                start_date="19900101",
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="",
            )
        except TypeError:
            # Some akshare versions may not support adjust arg.
            df = ak.fund_etf_hist_em(
                symbol=code,
                period=ak_period,
                start_date="19900101",
                end_date=datetime.now().strftime("%Y%m%d"),
            )

        if df is None or df.empty:
            return pd.DataFrame(
                columns=[
                    "date",
                    "open",
                    "close",
                    "high",
                    "low",
                    "volume",
                    "amount",
                    "amplitude_pct",
                    "change_pct",
                    "change_amount",
                    "turnover_pct",
                ]
            )

        columns = {c.strip(): c for c in df.columns}

        out = pd.DataFrame(
            {
                "date": df[columns.get("日期", df.columns[0])].astype(str),
                "open": pd.to_numeric(df[columns.get("开盘")], errors="coerce"),
                "close": pd.to_numeric(df[columns.get("收盘")], errors="coerce"),
                "high": pd.to_numeric(df[columns.get("最高")], errors="coerce"),
                "low": pd.to_numeric(df[columns.get("最低")], errors="coerce"),
                "volume": pd.to_numeric(df[columns.get("成交量")], errors="coerce")
                if columns.get("成交量")
                else None,
                "amount": pd.to_numeric(df[columns.get("成交额")], errors="coerce")
                if columns.get("成交额")
                else None,
                "amplitude_pct": pd.to_numeric(df[columns.get("振幅")], errors="coerce")
                if columns.get("振幅")
                else None,
                "change_pct": pd.to_numeric(df[columns.get("涨跌幅")], errors="coerce")
                if columns.get("涨跌幅")
                else None,
                "change_amount": pd.to_numeric(df[columns.get("涨跌额")], errors="coerce")
                if columns.get("涨跌额")
                else None,
                "turnover_pct": pd.to_numeric(df[columns.get("换手率")], errors="coerce")
                if columns.get("换手率")
                else None,
            }
        )

        out = out.dropna(subset=["date", "open", "close", "high", "low"])
        out = out.sort_values(by="date")
        return out

    def fetch_scale_from_spot(self, row: pd.Series) -> float | None:
        # fallback placeholder: spot data usually doesn't include规模
        maybe = row.get("基金规模") or row.get("规模")
        return parse_scale_to_billion(maybe)

    def normalize_price(self, value: object) -> float | None:
        return safe_float(value)
