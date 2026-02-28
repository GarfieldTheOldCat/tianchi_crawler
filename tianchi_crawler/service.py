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
    """
    通用检测并自动安装浏览器环境：
    - 在 Linux 服务器上精准安装轻量化 chromium-headless-shell 及系统依赖
    - 在 Windows/macOS 上安装标准 chromium 以供测试
    """

    # 1. 自动适配不同操作系统的浏览器存放路径
    if sys.platform == "win32":
        # Windows 个人 PC 路径
        base_path = Path.home() / "AppData" / "Local" / "ms-playwright"
        browser_type = "chromium"  # PC 端建议使用标准版便于调试
    elif sys.platform == "darwin":
        # macOS 路径
        base_path = Path.home() / "Library" / "Caches" / "ms-playwright"
        browser_type = "chromium"
    else:
        # Linux 服务器路径
        base_path = Path.home() / ".cache" / "ms-playwright"
        # 针对服务器 2核4G 优化：使用体积更小的 headless-shell
        browser_type = "chromium-headless-shell"

    # 2. 检查对应的浏览器内核是否存在
    # 检查文件夹名是否包含浏览器类型关键字
    has_browser = any(base_path.glob(f"{browser_type.replace('-', '_')}-*")) if base_path.exists() else False

    if not has_browser:
        logger.info(f"Browser {browser_type} not found. Starting one-time setup...")
        try:
            # 3. 安装浏览器执行程序
            # 使用 sys.executable 确保调用当前 Python 环境中的 playwright
            logger.info(f"Installing {browser_type}...")
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", browser_type],
                check=True,
                capture_output=True
            )

            # 4. 如果是 Linux，必须安装系统底层依赖库（如 libnss3, libatk 等）
            if sys.platform.startswith("linux"):
                logger.info(f"Linux detected: Installing system dependencies for {browser_type}...")
                # install-deps 是解决服务器报错 'Executable doesn't exist' 的关键
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install-deps", browser_type],
                    check=True,
                    capture_output=True
                )

            logger.info(f"Playwright {browser_type} environment is now ready.")
        except Exception as e:
            logger.error(f"Playwright setup failed: {e}")
            logger.info(f"Manual fix: run 'python -m playwright install --with-deps {browser_type}'")
    else:
        logger.info(f"Found existing {browser_type} environment.")


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
