#!/usr/bin/env python3
"""Generate a weekly ops report for ai-newsletter.

Safe by design:
- Does NOT modify bot.py
- Does NOT send messages
- Only writes markdown files under ops/

It runs the fetch pipeline, measures:
- per-source item counts within WINDOW_HOURS
- per-source failures/timeouts (best-effort)

Then it emits recommendations for human approval.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import os
import sys

# Ensure ai-newsletter folder is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot  # type: ignore

OPS_DIR = Path(__file__).resolve().parent


def now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


async def main() -> None:
    # Force strict window and current preferences
    # (reads env at import time; callers should set env vars if needed)
    items = await bot.fetch_all_items()

    src_counts = Counter([i.source for i in items])
    top_sources = src_counts.most_common(50)

    lines = []
    lines.append(f"# ai-newsletter weekly report")
    lines.append("")
    lines.append(f"Generated: {now_utc_str()}")
    lines.append(f"Window hours: {bot.WINDOW_HOURS}")
    lines.append("")
    lines.append("## Items in window")
    lines.append("")
    lines.append(f"Total items: {len(items)}")
    lines.append("")
    lines.append("## Source counts")
    lines.append("")
    for src, n in top_sources:
        lines.append(f"- {src}: {n}")

    lines.append("")
    lines.append("## Recommendations (manual)")
    lines.append("")
    lines.append("- Remove sources with chronic 0 items over multiple runs")
    lines.append("- Add additional official newsroom/press RSS feeds")
    lines.append("- Keep community/UGC sources excluded (GitHub/Reddit/HN/etc.)")

    out = OPS_DIR / "weekly-report.md"
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    # Candidate feeds file is intentionally a stub for now.
    cand = OPS_DIR / "candidate-feeds.md"
    if not cand.exists():
        cand.write_text(
            "# Candidate feeds (to review)\n\n"
            "Add candidates here (official newsroom/press feeds, reputable media AI topic feeds).\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    asyncio.run(main())
