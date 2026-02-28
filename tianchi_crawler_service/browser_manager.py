from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from config import BrowserConfig
from stealth import apply_stealth
import logging

logger = logging.getLogger(__name__)


class BrowserManager:
    """改造成【单浏览器 + 多标签页】模式"""

    def __init__(self, config: BrowserConfig):
        self.config = config
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None

    async def __aenter__(self):
        """整个并发任务只启动一次浏览器"""
        self.playwright = await async_playwright().start()

        launch_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ]
        if not self.config.headless:
            launch_args.extend([
                "--start-maximized",
                "--window-position=0,0",
                "--disable-setuid-sandbox"
            ])
        if self.config.proxy:
            launch_args.append(f"--proxy-server={self.config.proxy}")

        self.browser = await self.playwright.chromium.launch(
            headless=self.config.headless,
            args=launch_args
        )

        self.context = await self.browser.new_context(
            viewport=self.config.viewport,
            locale=self.config.locale,
            timezone_id=self.config.timezone_id,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            accept_downloads=True,
        )

        logger.info(f"🚀 已启动单个浏览器窗口（Context 已创建），支持并发标签页")
        return self

    async def __aexit__(self, *args):
        """任务结束时关闭整个浏览器"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("✅ 浏览器已完全关闭")

    async def new_page(self) -> Page:
        """每次调用都创建一个新标签页（Page）"""
        page = await self.context.new_page()
        await apply_stealth(page)
        return page