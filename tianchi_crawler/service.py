import asyncio
import logging
from typing import List, Dict
from urllib.parse import urlparse
from mcp.server.fastmcp import FastMCP
# 导入你现有的组件
from .config import BrowserConfig, CrawlConfig
from .crawler import AsyncMinimalCrawler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("CrawlerMCP")
import subprocess
from pathlib import Path


def ensure_playwright_browsers():
    """针对服务器和 PC 优化的环境检查"""
    # 自动适配 Linux/Windows 路径
    if sys.platform == "win32":
        browser_path = Path.home() / "AppData" / "Local" / "ms-playwright"
    else:
        browser_path = Path.home() / ".cache" / "ms-playwright"

    # 检查是否同时存在 chromium 和 headless-shell
    has_chromium = any(browser_path.glob("chromium-*")) if browser_path.exists() else False
    has_shell = any(browser_path.glob("chromium_headless_shell-*")) if browser_path.exists() else False

    if not has_chromium or not has_shell:
        logger.info("Playwright browsers missing. Starting full installation...")
        try:
            # 1. 安装核心浏览器
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

            # 2. 针对服务器报错，显式安装 headless-shell
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium-headless-shell"], check=True)

            # 3. 如果是 Linux，必须补全系统依赖
            if sys.platform.startswith("linux"):
                subprocess.run([sys.executable, "-m", "playwright", "install-deps"], check=True)

            logger.info("Installation successful.")
        except Exception as e:
            logger.error(f"Auto-install failed: {e}")


# 在初始化之前调用
ensure_playwright_browsers()

# 初始化 FastMCP
mcp = FastMCP("WebCrawlerService")


def is_valid_url(url: str) -> bool:
    """简单校验是否为合法的 HTTP/HTTPS 网页链接"""
    try:
        result = urlparse(url)
        return all([result.scheme in ["http", "https"], result.netloc])
    except:
        return False


@mcp.tool()
async def crawl_urls(urls: List[str]) -> Dict[str, str]:
    """
    抓取指定 URL 列表的内容并返回 Markdown 格式文本。

    Args:
        urls: 需要爬取的 URL 字符串列表。
    Returns:
        Dict: 键为 URL，值为页面内容或错误提示。
    """
    # 1. 过滤非法 URL
    valid_urls = []
    results_map = {}

    for url in urls:
        if is_valid_url(url):
            valid_urls.append(url)
        else:
            results_map[url] = "thi url is not a website"

    if not valid_urls:
        return results_map

    # 2. 初始化爬虫 (针对 2核4G 强制开启 headless)
    # 建议此处保持 headless=True 以节省内存
    crawler = AsyncMinimalCrawler(BrowserConfig(headless=True))

    try:
        logger.info(f"Start crawling  {len(valid_urls)} urls...")

        # 3. 调用你现有的 arun_many 方法
        crawl_results = await crawler.arun_many(
            valid_urls,
            config=CrawlConfig()
        )

        # 4. 解析结果
        for r in crawl_results:
            if r.error:
                results_map[r.url] = f"Crawl failed: {r.error}"
            else:
                # 优先返回 markdown，如果没有则返回 content
                results_map[r.url] = r.markdown if r.markdown else "empty page"
            logger.info(r.url)
            logger.info(r.markdown)
            logger.info(len(r.markdown))

    except Exception as e:
        logger.error(f"Crawler error: {str(e)}")
        for url in valid_urls:
            if url not in results_map:
                results_map[url] = f"System error: {str(e)}"
    finally:
        # 极其重要：在 4G 内存机器上必须确保浏览器关闭
        # 如果你的 AsyncMinimalCrawler 没有自动 close，建议在这里显式处理
        pass

    return results_map


if __name__ == "__main__":
    # 使用 stdio 传输协议，方便与 Claude Desktop 等客户端集成
    mcp.run(transport="stdio")
