import asyncio
from fake_useragent import UserAgent

ua = UserAgent()

async def apply_stealth(page):
    """基础 stealth，仿 Crawl4AI undetected + CDP 修改"""
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => false});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
        window.chrome = { runtime: {} };
    """)
    # 随机 UA
    await page.set_extra_http_headers({"User-Agent": ua.random})