import asyncio
import logging
from typing import List, Optional
from .config import BrowserConfig, CrawlConfig
from .browser_manager import BrowserManager
from .converter import html_to_markdown
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CrawlResult(BaseModel):
    url: str
    markdown: str = ""
    html: str = ""
    status: int = 200
    screenshot: Optional[bytes] = None
    error: Optional[str] = None


class AsyncMinimalCrawler:
    def __init__(self, browser_config: BrowserConfig = None):
        self.browser_config = browser_config or BrowserConfig()

    async def arun(self, url: str, config: CrawlConfig = None) -> CrawlResult:
        results = await self.arun_many([url], config or CrawlConfig(max_concurrent=1))
        return results[0]

    async def arun_many(
            self,
            urls: List[str],
            config: CrawlConfig = None
    ) -> List[CrawlResult]:
        config = config or CrawlConfig()
        semaphore = asyncio.Semaphore(config.max_concurrent)

        # ====================== 关键修改 ======================
        # 整个并发任务只启动一次 BrowserManager（一个窗口）
        async with BrowserManager(self.browser_config) as bm:
            async def bounded_crawl(url: str) -> CrawlResult:
                async with semaphore:  # 控制同时打开的标签页数量
                    try:
                        logger.info(f"Create new tab for: {url}")
                        page = await bm.new_page()  # ← 在同一个浏览器里开新标签页

                        await page.goto(url, wait_until=config.wait_until, timeout=config.timeout)

                        if config.js_code:
                            await page.evaluate(config.js_code)

                        if config.scroll:
                            for _ in range(config.scroll_times):
                                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                await asyncio.sleep(config.scroll_delay)
                            await page.evaluate("window.scrollTo(0, 0)")

                        html = await page.content()
                        screenshot = await page.screenshot(type="png", full_page=True) if config.screenshot else None
                        # logger.info(html[:1000])

                        markdown = html_to_markdown(
                            html=html,
                            base_url=config.base_url or url,
                            use_pruning=config.use_pruning,
                            pruning_min_word_threshold=config.pruning_min_word_threshold,
                            pruning_threshold_type=config.pruning_threshold_type,
                            pruning_threshold=config.pruning_threshold,
                            use_citations=config.use_citations,
                            html2text_options=config.html2text_options,
                        )
                        # logger.info(markdown[:1000])

                        # 关闭当前标签页，释放资源
                        await page.close()

                        logger.info(f"Tab finished successfully: {url} | markdown len={len(markdown)}")
                        return CrawlResult(url=url, markdown=markdown, html=html, screenshot=screenshot)

                    except Exception as e:
                        logger.error(f"Tab failed: {url}: {type(e).__name__}: {e}", exc_info=True)
                        return CrawlResult(url=url, error=f"{type(e).__name__}: {e}")

            # 并发执行所有 URL（都在同一个浏览器窗口的不同标签页）
            tasks = [bounded_crawl(url) for url in urls]
            return await asyncio.gather(*tasks)