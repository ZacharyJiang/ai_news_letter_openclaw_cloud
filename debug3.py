#!/usr/bin/env python3
import sys
import asyncio
sys.path.insert(0, '.')

from datetime import datetime, timedelta, timezone
from bot import fetch_all_items, _now_utc, _looks_like_noise

async def main():
    print(f"当前时间 (UTC): {_now_utc()}")
    print()

    print("正在调用 fetch_all_items()...")
    items = await fetch_all_items()
    print(f"fetch_all_items() 返回了 {len(items)} 条新闻")
    print()

    if items:
        print("这些新闻是:")
        for i, item in enumerate(items, 1):
            noise = _looks_like_noise(item.url, item.source)
            noise_status = "⚠️ 会被当作噪音过滤" if noise else "✅ 正常"
            print(f"{i}. [{noise_status}] {item.published} - {item.title} ({item.source})")
            print(f"   URL: {item.url}")

if __name__ == "__main__":
    asyncio.run(main())
