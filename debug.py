#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta, timezone
from bot import fetch_all_rss, _now_utc, WINDOW_HOURS, _window_start_utc

print(f"当前时间 (UTC): {_now_utc()}")
print(f"时间窗口 (WINDOW_HOURS): {WINDOW_HOURS}")
print(f"窗口开始时间: {_window_start_utc()}")
print()

print("正在获取 RSS 数据...")
items = fetch_all_rss()
print(f"总共获取到 {len(items)} 条新闻")
print()

if items:
    # 按发布时间排序
    items_sorted = sorted(items, key=lambda x: x.published, reverse=True)
    print("最新的 10 条新闻:")
    for i, item in enumerate(items_sorted[:10]):
        in_window = item.published >= _window_start_utc()
        status = "✅ 在窗口内" if in_window else "❌ 不在窗口内"
        print(f"{i+1}. [{status}] {item.published} - {item.title} ({item.source})")

    print()
    in_window_count = sum(1 for i in items if i.published >= _window_start_utc())
    print(f"在时间窗口内的新闻数量: {in_window_count}")
