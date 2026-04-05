#!/usr/bin/env python3
import sys
import asyncio
sys.path.insert(0, '.')

from bot import run_once

async def main():
    print("正在运行 run_once()...")
    await run_once()
    print("完成")

if __name__ == "__main__":
    asyncio.run(main())
