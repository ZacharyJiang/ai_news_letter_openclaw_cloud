import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    # Cache
    spot_ttl_seconds: int = int(os.getenv("SPOT_TTL_SECONDS", "15"))
    kline_ttl_seconds: int = int(os.getenv("KLINE_TTL_SECONDS", "600"))

    # Rate limit for external data API
    datasource_qps: float = float(os.getenv("DATASOURCE_QPS", "2.0"))

    # Estimated A-share ETF trading commission percent (single side)
    default_trading_fee_pct: float = float(os.getenv("DEFAULT_TRADING_FEE_PCT", "0.03"))

    # Background sync configuration
    startup_sync_batch: int = int(os.getenv("STARTUP_SYNC_BATCH", "120"))
    lazy_fill_batch_per_request: int = int(os.getenv("LAZY_FILL_BATCH_PER_REQUEST", "20"))

    # Storage path
    data_dir: str = os.getenv("DATA_DIR", "backend/data")


settings = Settings()
