import asyncio
import logging
from config import BrowserConfig, CrawlConfig
from crawler import AsyncMinimalCrawler

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")


async def main():
    crawler = AsyncMinimalCrawler(BrowserConfig(headless=False))

    urls = [
        "https://pubmed.ncbi.nlm.nih.gov/31959057/",
        # "https://developer.aliyun.com/article/1669242#slide-11"
    ]

    results = await crawler.arun_many(
        urls,
        config=CrawlConfig()
    )

    for r in results:
        print(f"\n{'=' * 100}")
        print(f"URL: {r.url}")
        print(f"状态: {'成功' if r.error is None else '失败'}")
        if r.error:
            print(f"错误: {r.error}")
        else:
            print(f"Markdown 前 1000 字符：\n{r.markdown}")
            print(f"Markdown 总长度: {len(r.markdown)} 字符")
        print(f"{'=' * 100}")


if __name__ == "__main__":
    asyncio.run(main())