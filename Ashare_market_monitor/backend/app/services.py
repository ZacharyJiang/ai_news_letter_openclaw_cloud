from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Iterable

from .config import Settings
from .data_source import AkshareDataSource
from .models import EtfFilters
from .repository import JsonRepository


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ETFService:
    def __init__(
        self,
        settings: Settings,
        repo: JsonRepository,
        data_source: AkshareDataSource,
    ) -> None:
        self._settings = settings
        self._repo = repo
        self._data_source = data_source

        self._spot_cache: list[dict[str, Any]] = []
        self._spot_ts: float = 0.0
        self._spot_lock = threading.Lock()

        self._meta = self._repo.load_meta()
        self._extreme = self._repo.load_extreme()
        self._meta_lock = threading.Lock()

        self._kline_cache: dict[str, dict[str, Any]] = {}
        self._kline_lock = threading.Lock()

        self._sync_lock = threading.Lock()
        self._sync_thread: threading.Thread | None = None
        self._sync_state = self._repo.load_sync_state()

    def get_sync_status(self) -> dict[str, Any]:
        with self._sync_lock:
            return dict(self._sync_state)

    def _set_sync_state(self, **kwargs: Any) -> None:
        with self._sync_lock:
            self._sync_state.update(kwargs)
            self._repo.save_sync_state(self._sync_state)

    def get_spot_rows(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        now = time.time()
        with self._spot_lock:
            fresh = now - self._spot_ts <= self._settings.spot_ttl_seconds
            if self._spot_cache and fresh and not force_refresh:
                return list(self._spot_cache)

        df = self._data_source.fetch_spot()
        rows = df.to_dict("records")

        with self._spot_lock:
            self._spot_cache = rows
            self._spot_ts = time.time()

        return rows

    def trigger_background_sync(self, codes: Iterable[str] | None = None, limit: int | None = None) -> bool:
        with self._sync_lock:
            if self._sync_thread and self._sync_thread.is_alive():
                return False

            thread = threading.Thread(
                target=self._sync_worker,
                args=(list(codes) if codes else None, limit),
                daemon=True,
            )
            self._sync_thread = thread
            thread.start()
            return True

    def _sync_worker(self, codes: list[str] | None, limit: int | None) -> None:
        try:
            spot_rows = self.get_spot_rows(force_refresh=True)
            code_map = {r["code"]: r for r in spot_rows}

            target_codes = codes if codes else list(code_map.keys())
            if limit and limit > 0:
                target_codes = target_codes[:limit]

            self._set_sync_state(
                running=True,
                last_start=now_iso(),
                last_error=None,
                processed=0,
                total=len(target_codes),
            )

            processed = 0
            for code in target_codes:
                row = code_map.get(code, {})
                name = row.get("name")
                current_price = row.get("price")

                try:
                    self._refresh_meta_for_code(code=code, name=name)
                    self._refresh_extreme_for_code(code=code, current_price=current_price)
                except Exception as exc:  # noqa: BLE001
                    self._set_sync_state(last_error=f"{code}: {exc}")

                processed += 1
                self._set_sync_state(processed=processed)

            self._set_sync_state(running=False, last_finish=now_iso())
        except Exception as exc:  # noqa: BLE001
            self._set_sync_state(running=False, last_error=str(exc), last_finish=now_iso())

    def _refresh_meta_for_code(self, code: str, name: str | None) -> None:
        basic = self._data_source.fetch_basic_info(code)
        fee = self._data_source.fetch_fee_info(code)

        merged = {
            "code": code,
            "name": name,
            "fund_scale_billion": basic.get("fund_scale_billion"),
            "management_fee_pct": fee.get("management_fee_pct"),
            "custody_fee_pct": fee.get("custody_fee_pct"),
            "sales_fee_pct": fee.get("sales_fee_pct"),
            "subscription_fee_pct": fee.get("subscription_fee_pct"),
            "redemption_fee_pct": fee.get("redemption_fee_pct"),
            "trading_fee_pct": fee.get("trading_fee_pct"),
            "total_fee_pct": fee.get("total_fee_pct"),
            "updated_at": now_iso(),
        }

        with self._meta_lock:
            old = self._meta.get(code, {})
            old.update({k: v for k, v in merged.items() if v is not None or k == "updated_at"})
            self._meta[code] = old
            self._repo.save_meta(self._meta)

    def _refresh_extreme_for_code(self, code: str, current_price: float | None) -> None:
        kline = self.get_kline_rows(code=code, period="day", force_refresh=False)
        if not kline:
            return

        highs = [x["high"] for x in kline if x.get("high") is not None]
        lows = [x["low"] for x in kline if x.get("low") is not None]
        if not highs or not lows:
            return

        ath = max(highs)
        atl = min(lows)

        drawdown = None
        rebound = None
        if current_price is not None and ath > 0 and atl > 0:
            drawdown = round((current_price / ath - 1) * 100, 4)
            rebound = round((current_price / atl - 1) * 100, 4)

        with self._meta_lock:
            self._extreme[code] = {
                "ath": ath,
                "atl": atl,
                "drawdown_from_ath_pct": drawdown,
                "rebound_from_atl_pct": rebound,
                "updated_at": now_iso(),
            }
            self._repo.save_extreme(self._extreme)

    def get_kline_rows(self, code: str, period: str, force_refresh: bool = False) -> list[dict[str, Any]]:
        key = f"{code}:{period}"
        now = time.time()

        with self._kline_lock:
            hit = self._kline_cache.get(key)
            if hit and not force_refresh:
                if now - hit["ts"] <= self._settings.kline_ttl_seconds:
                    return hit["rows"]

        df = self._data_source.fetch_kline(code=code, period=period)
        rows = df.to_dict("records")

        with self._kline_lock:
            self._kline_cache[key] = {"ts": time.time(), "rows": rows}

        return rows

    def get_kline_payload(self, code: str, period: str) -> dict[str, Any]:
        rows = self.get_kline_rows(code=code, period=period)
        if not rows:
            return {
                "code": code,
                "period": period,
                "ath": 0,
                "atl": 0,
                "drawdown_from_ath_pct": 0,
                "rebound_from_atl_pct": 0,
                "bars": [],
            }

        highs = [x["high"] for x in rows if x.get("high") is not None]
        lows = [x["low"] for x in rows if x.get("low") is not None]
        closes = [x["close"] for x in rows if x.get("close") is not None]

        ath = max(highs) if highs else 0
        atl = min(lows) if lows else 0
        current_price = closes[-1] if closes else 0

        drawdown = (current_price / ath - 1) * 100 if ath else 0
        rebound = (current_price / atl - 1) * 100 if atl else 0

        # keep latest extreme cache in sync
        with self._meta_lock:
            self._extreme[code] = {
                "ath": ath,
                "atl": atl,
                "drawdown_from_ath_pct": round(drawdown, 4),
                "rebound_from_atl_pct": round(rebound, 4),
                "updated_at": now_iso(),
            }
            self._repo.save_extreme(self._extreme)

        bars = []
        for r in rows:
            bars.append(
                {
                    "date": str(r.get("date")),
                    "open": float(r.get("open", 0)),
                    "close": float(r.get("close", 0)),
                    "high": float(r.get("high", 0)),
                    "low": float(r.get("low", 0)),
                    "volume": float(r["volume"]) if r.get("volume") is not None else None,
                    "amount": float(r["amount"]) if r.get("amount") is not None else None,
                    "amplitude_pct": float(r["amplitude_pct"])
                    if r.get("amplitude_pct") is not None
                    else None,
                    "change_pct": float(r["change_pct"]) if r.get("change_pct") is not None else None,
                    "change_amount": float(r["change_amount"])
                    if r.get("change_amount") is not None
                    else None,
                    "turnover_pct": float(r["turnover_pct"])
                    if r.get("turnover_pct") is not None
                    else None,
                }
            )

        return {
            "code": code,
            "period": period,
            "ath": round(ath, 4),
            "atl": round(atl, 4),
            "drawdown_from_ath_pct": round(drawdown, 4),
            "rebound_from_atl_pct": round(rebound, 4),
            "bars": bars,
        }

    def _filter_match(self, item: dict[str, Any], filters: EtfFilters) -> bool:
        if filters.keyword:
            kw = filters.keyword.lower().strip()
            if kw and kw not in item.get("code", "").lower() and kw not in item.get("name", "").lower():
                return False

        def in_range(value: float | None, lo: float | None, hi: float | None) -> bool:
            if value is None:
                return False if lo is not None or hi is not None else True
            if lo is not None and value < lo:
                return False
            if hi is not None and value > hi:
                return False
            return True

        if not in_range(item.get("price"), filters.min_price, filters.max_price):
            return False
        if not in_range(item.get("fund_scale_billion"), filters.min_scale, filters.max_scale):
            return False
        if not in_range(item.get("total_fee_pct"), filters.min_fee, filters.max_fee):
            return False

        distance_value = (
            item.get("drawdown_from_ath_pct")
            if filters.distance_mode == "from_high"
            else item.get("rebound_from_atl_pct")
        )
        if not in_range(distance_value, filters.min_distance, filters.max_distance):
            return False

        return True

    def get_list_payload(self, filters: EtfFilters) -> dict[str, Any]:
        rows = self.get_spot_rows()
        if not rows:
            return {
                "total": 0,
                "page": filters.page,
                "page_size": filters.page_size,
                "items": [],
                "sync_status": self.get_sync_status(),
            }

        with self._meta_lock:
            meta = dict(self._meta)
            ext = dict(self._extreme)

        missing_codes = [r["code"] for r in rows if r["code"] not in meta or r["code"] not in ext]
        if missing_codes:
            self.trigger_background_sync(
                codes=missing_codes,
                limit=self._settings.lazy_fill_batch_per_request,
            )

        items: list[dict[str, Any]] = []
        for row in rows:
            code = row["code"]
            m = meta.get(code, {})
            ex = ext.get(code, {})
            price = row.get("price")

            ath = ex.get("ath")
            atl = ex.get("atl")
            drawdown = ex.get("drawdown_from_ath_pct")
            rebound = ex.get("rebound_from_atl_pct")

            # realtime price can drift from cached extreme computation; refresh derived ratios on fly.
            if price is not None and ath:
                drawdown = round((price / ath - 1) * 100, 4)
            if price is not None and atl:
                rebound = round((price / atl - 1) * 100, 4)

            item = {
                "code": code,
                "name": row.get("name"),
                "market": row.get("market"),
                "price": round(float(price), 4) if price is not None else None,
                "fund_scale_billion": m.get("fund_scale_billion"),
                "management_fee_pct": m.get("management_fee_pct"),
                "custody_fee_pct": m.get("custody_fee_pct"),
                "sales_fee_pct": m.get("sales_fee_pct"),
                "subscription_fee_pct": m.get("subscription_fee_pct"),
                "redemption_fee_pct": m.get("redemption_fee_pct"),
                "trading_fee_pct": m.get("trading_fee_pct"),
                "total_fee_pct": m.get("total_fee_pct"),
                "ath": ath,
                "atl": atl,
                "drawdown_from_ath_pct": drawdown,
                "rebound_from_atl_pct": rebound,
                "updated_at": m.get("updated_at") or ex.get("updated_at"),
            }
            items.append(item)

        filtered = [x for x in items if self._filter_match(x, filters)]

        reverse = filters.order == "desc"
        sort_key = filters.sort_by

        present = [x for x in filtered if x.get(sort_key) is not None]
        missing = [x for x in filtered if x.get(sort_key) is None]
        present.sort(key=lambda x: x.get(sort_key), reverse=reverse)
        filtered = present + missing

        total = len(filtered)
        page = max(filters.page, 1)
        page_size = min(max(filters.page_size, 1), 200)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = filtered[start:end]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": page_items,
            "sync_status": self.get_sync_status(),
        }
