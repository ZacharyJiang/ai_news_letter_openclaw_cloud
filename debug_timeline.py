#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta, timezone
from bot import fetch_all_rss

# 模拟 2026-03-12 12:00:47 GMT+8 = 2026-03-12 04:00:47 UTC
simulated_now = datetime(2026, 3, 12, 4, 0, 47, tzinfo=timezone.utc)
window_hours = 6.0
window_start = simulated_now - timedelta(hours=window_hours)

print(f"模拟运行时间 (UTC): {simulated_now}")
print(f"时间窗口 (WINDOW_HOURS): {window_hours}")
print(f"窗口开始时间: {window_start}")
print()

print("正在获取 RSS 数据...")
items = fetch_all_rss()
print(f"总共获取到 {len(items)} 条新闻")
print()

if items:
    # 按发布时间排序
    items_sorted = sorted(items, key=lambda x: x.published, reverse=True)
    print("在模拟时间窗口内的新闻:")
    count = 0
    for i, item in enumerate(items_sorted):
        in_window = item.published >= window_start and item.published <= simulated_now
        if in_window:
            count += 1
            print(f"{count}. {item.published} - {item.title} ({item.source})")

    print()
    print(f"在模拟时间窗口内的新闻数量: {count}")
