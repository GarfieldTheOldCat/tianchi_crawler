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
import shutil
from pathlib import Path


def ensure_playwright_browsers():
    """检测并自动安装 Chromium 浏览器"""
    # Playwright 默认的浏览器存放路径 (Windows)
    # 注意：这里的 'chromium-1208' 可能会随版本更新，但我们主要检查父目录
    browser_path = Path.home() / "AppData" / "Local" / "ms-playwright"

    # 检查 chromium 是否存在（简单判断文件夹是否存在即可）
    has_chromium = any(browser_path.glob("chromium-*")) if browser_path.exists() else False

    if not has_chromium:
        logger.info("未检测到 Chromium 浏览器，正在尝试自动安装...")
        try:
            # 使用 uv run 确保在当前虚拟环境下执行
            # 仅安装 chromium 节省内存和空间
            subprocess.run(
                ["uv", "run", "playwright", "install", "chromium"],
                check=True,
                capture_output=True
            )
            logger.info("Chromium 浏览器安装成功！")
        except Exception as e:
            logger.error(f"浏览器自动安装失败: {e}")
            logger.info("请尝试手动运行: uv run playwright install chromium")
    else:
        logger.info("Playwright 浏览器检查通过。")


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
            results_map[url] = "此url不是网页"

    if not valid_urls:
        return results_map

    # 2. 初始化爬虫 (针对 2核4G 强制开启 headless)
    # 建议此处保持 headless=True 以节省内存
    crawler = AsyncMinimalCrawler(BrowserConfig(headless=False))

    try:
        logger.info(f"正在开始抓取 {len(valid_urls)} 个网页...")

        # 3. 调用你现有的 arun_many 方法
        crawl_results = await crawler.arun_many(
            valid_urls,
            config=CrawlConfig()
        )

        # 4. 解析结果
        for r in crawl_results:
            if r.error:
                results_map[r.url] = f"抓取失败: {r.error}"
            else:
                # 优先返回 markdown，如果没有则返回 content
                results_map[r.url] = r.markdown if r.markdown else "页面内容为空"
            logger.info(r.url)
            logger.info(r.markdown)
            logger.info(len(r.markdown))

    except Exception as e:
        logger.error(f"爬虫运行异常: {str(e)}")
        for url in valid_urls:
            if url not in results_map:
                results_map[url] = f"系统异常: {str(e)}"
    finally:
        # 极其重要：在 4G 内存机器上必须确保浏览器关闭
        # 如果你的 AsyncMinimalCrawler 没有自动 close，建议在这里显式处理
        pass

    return results_map


if __name__ == "__main__":
    # 使用 stdio 传输协议，方便与 Claude Desktop 等客户端集成
    mcp.run(transport="stdio")