#!/usr/bin/env python3
import sys
import asyncio
import os
from dotenv import load_dotenv

sys.path.insert(0, '.')

# Load .env file
load_dotenv()

from bot import run_once

async def main():
    print("正在运行 run_once()...")
    token = os.getenv("OPENCLAW_TOKEN", "")
    print(f"OPENCLAW_TOKEN 已加载: {'是' if token else '否'}，长度: {len(token)}")
    await run_once()
    print("完成")

if __name__ == "__main__":
    asyncio.run(main())
