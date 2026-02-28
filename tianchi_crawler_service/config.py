from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class BrowserConfig(BaseModel):
    headless: bool = True
    user_data_dir: Optional[str] = None
    proxy: Optional[str] = None
    viewport: dict = Field(default_factory=lambda: {"width": 1920, "height": 1080})
    locale: str = "zh-CN"
    timezone_id: str = "Asia/Shanghai"


class CrawlConfig(BaseModel):
    # 原有参数
    wait_until: str = "networkidle"
    timeout: int = 30000
    scroll: bool = True
    scroll_times: int = 5
    scroll_delay: float = 1.0
    js_code: Optional[str] = None
    screenshot: bool = False

    # 并发控制
    max_concurrent: int = 5

    # Crawl4AI v2 风格 Pruning + Markdown 参数（默认值与你 v2.py 一致）
    use_pruning: bool = True
    pruning_min_word_threshold: Optional[int] = None
    pruning_threshold_type: str = "dynamic"
    pruning_threshold: float = 0.6
    use_citations: bool = True
    base_url: str = ""

    # html2text 配置（支持传入）
    html2text_options: Dict[str, Any] = Field(default_factory=lambda: {
        "ignore_links": False,
        "escape_html": False,
        "body_width": 0,
        "single_line_break": True,
        "mark_code": True,
    })