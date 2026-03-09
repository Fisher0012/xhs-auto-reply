#!/usr/bin/env python3
"""
首次登录脚本（一次性使用）
运行后会弹出 Chrome 窗口，手动登录小红书，登录完成后按 Enter 保存 Cookie。
之后 xhs_reply.py 会自动复用此 Cookie，无需每次登录。
"""

import asyncio
from playwright.async_api import async_playwright
from pathlib import Path


async def login():
    print("🚀 正在启动浏览器...")
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(Path.home() / "xhs_chrome_profile"),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--no-first-run", "--no-default-browser-check"],
        )
        page = await browser.new_page()
        await page.goto("https://www.xiaohongshu.com")

        print("✅ 浏览器已打开")
        print("📱 请在弹出的 Chrome 窗口中手动登录小红书")
        print("   支持：扫码登录 / 手机号登录 / 账号密码登录")
        print("")
        input("✅ 登录完成后，回到这里按 Enter 键保存 Cookie...")

        await browser.close()
        print("✅ Cookie 已保存到 ~/xhs_chrome_profile")
        print("🎉 登录完成！以后运行 xhs_reply.py 无需再次登录")


if __name__ == "__main__":
    asyncio.run(login())
