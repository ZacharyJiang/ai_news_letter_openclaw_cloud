#!/usr/bin/env python3
import asyncio
import sys
import os

os.chdir('/root/.openclaw/workspace_coder/ai-newsletter')
sys.path.insert(0, '.')

# Load env from .env manually
with open('.env') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        os.environ[key.strip()] = value.strip().strip('"\'')

import bot

async def generate():
    items = await bot.fetch_all_items()
    if not items:
        print('NO_ITEMS')
        return
    selected = bot.select_top_items(items)
    msg = bot.build_one_message(selected)
    print(msg)

if __name__ == "__main__":
    asyncio.run(generate())
