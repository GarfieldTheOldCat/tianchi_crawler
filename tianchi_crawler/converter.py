import re
from urllib.parse import urljoin
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple, List
from bs4 import BeautifulSoup, Tag, NavigableString, Comment
import math
from dataclasses import dataclass
import html2text
import logging

logger = logging.getLogger(__name__)

# ==========================================
# 1. 数据模型定义（你提供的）
# ==========================================
@dataclass
class MarkdownGenerationResult:
    raw_markdown: str
    markdown_with_citations: str
    references_markdown: str
    fit_markdown: str
    fit_html: str


# ==========================================
# 2. 核心辅助函数（你提供的）
# ==========================================
LINK_PATTERN = re.compile(r'!?\[([^\]]+)\]\(([^)]+?)(?:\s+"([^"]*)")?\)')

def fast_urljoin(base: str, url: str) -> str:
    if url.startswith(("http://", "https://", "mailto:", "//")):
        return url
    if url.startswith("/"):
        if base.endswith("/"):
            return base[:-1] + url
        return base + url
    return urljoin(base, url)


# ==========================================
# 3. 内容过滤器（你提供的完整 PruningContentFilter）
# ==========================================
class RelevantContentFilter(ABC):
    def __init__(self, user_query: str = None):
        self.user_query = user_query
        self.excluded_tags = {"nav", "footer", "header", "aside", "script", "style", "form", "iframe", "noscript"}
        self.negative_patterns = re.compile(r"nav|footer|header|sidebar|ads|comment|promo|advert|social|share", re.I)

    @abstractmethod
    def filter_content(self, html: str) -> List[str]:
        pass


class PruningContentFilter(RelevantContentFilter):
    def __init__(
            self,
            user_query: str = None,
            min_word_threshold: int = None,
            threshold_type: str = "fixed",
            threshold: float = 0.48,
    ):
        super().__init__(user_query)
        self.min_word_threshold = min_word_threshold
        self.threshold_type = threshold_type
        self.threshold = threshold

        self.tag_importance = {
            "article": 1.5, "main": 1.4, "section": 1.3, "p": 1.2,
            "h1": 1.4, "h2": 1.3, "h3": 1.2, "div": 0.7, "span": 0.6,
        }

        self.metric_config = {
            "text_density": True, "link_density": True,
            "tag_weight": True, "class_id_weight": True, "text_length": True,
        }

        self.metric_weights = {
            "text_density": 0.4, "link_density": 0.2, "tag_weight": 0.2,
            "class_id_weight": 0.1, "text_length": 0.1,
        }

        self.tag_weights = {
            "div": 0.5, "p": 1.0, "article": 1.5, "section": 1.0,
            "span": 0.3, "li": 0.5, "ul": 0.5, "ol": 0.5,
            "h1": 1.2, "h2": 1.1, "h3": 1.0, "h4": 0.9, "h5": 0.8, "h6": 0.7,
        }

    def filter_content(self, html: str, min_word_threshold: int = None) -> List[str]:
        if not html or not isinstance(html, str):
            return []

        soup = BeautifulSoup(html, "lxml")
        if not soup.body:
            soup = BeautifulSoup(f"<body>{html}</body>", "lxml")

        self._remove_comments(soup)
        self._remove_unwanted_tags(soup)

        body = soup.find("body")
        self._prune_tree(body)

        content_blocks = []
        for element in body.children:
            if isinstance(element, str) or not hasattr(element, "name"):
                continue
            if len(element.get_text(strip=True)) > 0:
                content_blocks.append(str(element))

        return content_blocks

    def _remove_comments(self, soup):
        for element in soup(text=lambda text: isinstance(text, Comment)):
            element.extract()

    def _remove_unwanted_tags(self, soup):
        for tag in self.excluded_tags:
            for element in soup.find_all(tag):
                element.decompose()

    def _prune_tree(self, node):
        if not node or not hasattr(node, "name") or node.name is None:
            return

        text_len = len(node.get_text(strip=True))
        tag_len = len(node.encode_contents().decode("utf-8"))
        link_text_len = sum(
            len(s.strip()) for s in (a.string for a in node.find_all("a", recursive=False)) if s
        )

        metrics = {"node": node, "tag_name": node.name, "text_len": text_len, "tag_len": tag_len, "link_text_len": link_text_len}

        score = self._compute_composite_score(metrics, text_len, tag_len, link_text_len)

        if self.threshold_type == "fixed":
            should_remove = score < self.threshold
        else:
            tag_importance = self.tag_importance.get(node.name, 0.7)
            text_ratio = text_len / tag_len if tag_len > 0 else 0
            link_ratio = link_text_len / text_len if text_len > 0 else 1

            threshold = self.threshold
            if tag_importance > 1:
                threshold *= 0.8
            if text_ratio > 0.4:
                threshold *= 0.9
            if link_ratio > 0.6:
                threshold *= 1.2

            should_remove = score < threshold

        if should_remove:
            node.decompose()
        else:
            children = [child for child in node.children if hasattr(child, "name")]
            for child in children:
                self._prune_tree(child)

    def _compute_composite_score(self, metrics, text_len, tag_len, link_text_len):
        if self.min_word_threshold:
            text = metrics["node"].get_text(strip=True)
            word_count = text.count(" ") + 1
            if word_count < self.min_word_threshold:
                return -1.0

        score = 0.0
        total_weight = 0.0

        if self.metric_config["text_density"]:
            density = text_len / tag_len if tag_len > 0 else 0
            score += self.metric_weights["text_density"] * density
            total_weight += self.metric_weights["text_density"]

        if self.metric_config["link_density"]:
            density = 1 - (link_text_len / text_len if text_len > 0 else 0)
            score += self.metric_weights["link_density"] * density
            total_weight += self.metric_weights["link_density"]

        if self.metric_config["tag_weight"]:
            tag_score = self.tag_weights.get(metrics["tag_name"], 0.5)
            score += self.metric_weights["tag_weight"] * tag_score
            total_weight += self.metric_weights["tag_weight"]

        if self.metric_config["class_id_weight"]:
            class_score = self._compute_class_id_weight(metrics["node"])
            score += self.metric_weights["class_id_weight"] * max(0, class_score)
            total_weight += self.metric_weights["class_id_weight"]

        if self.metric_config["text_length"]:
            score += self.metric_weights["text_length"] * math.log(text_len + 1)
            total_weight += self.metric_weights["text_length"]

        return score / total_weight if total_weight > 0 else 0

    def _compute_class_id_weight(self, node):
        class_id_score = 0
        if "class" in node.attrs:
            classes = " ".join(node["class"])
            if self.negative_patterns.match(classes):
                class_id_score -= 0.5
        if "id" in node.attrs:
            element_id = node["id"]
            if self.negative_patterns.match(element_id):
                class_id_score -= 0.5
        return class_id_score


# ==========================================
# 4. Markdown 生成策略（你提供的完整 DefaultMarkdownGenerator）
# ==========================================
class MarkdownGenerationStrategy(ABC):
    def __init__(self, content_filter=None, options=None, content_source="cleaned_html"):
        self.content_filter = content_filter
        self.options = options or {}
        self.content_source = content_source

    @abstractmethod
    def generate_markdown(self, input_html: str, **kwargs):
        pass


class DefaultMarkdownGenerator(MarkdownGenerationStrategy):
    def convert_links_to_citations(self, markdown: str, base_url: str = "") -> Tuple[str, str]:
        link_map = {}
        url_cache = {}
        parts = []
        last_end = 0
        counter = 1

        for match in LINK_PATTERN.finditer(markdown):
            parts.append(markdown[last_end: match.start()])
            text, url, title = match.groups()

            if base_url and not url.startswith(("http://", "https://", "mailto:")):
                if url not in url_cache:
                    url_cache[url] = fast_urljoin(base_url, url)
                url = url_cache[url]

            if url not in link_map:
                desc = []
                if title: desc.append(title)
                if text and text != title: desc.append(text)
                link_map[url] = (counter, ": " + " - ".join(desc) if desc else "")
                counter += 1

            num = link_map[url][0]
            parts.append(f"{text}⟨{num}⟩" if not match.group(0).startswith("!") else f"![{text}⟨{num}⟩]")
            last_end = match.end()

        parts.append(markdown[last_end:])
        converted_text = "".join(parts)

        references = ["\n\n## References\n\n"]
        references.extend(f"⟨{num}⟩ {url}{desc}\n" for url, (num, desc) in sorted(link_map.items(), key=lambda x: x[1][0]))

        return converted_text, "".join(references)

    def generate_markdown(self, input_html: str, base_url: str = "", html2text_options=None, content_filter=None, citations=True, **kwargs):

        try:
            h = html2text.HTML2Text(baseurl=base_url)
            # logger.info(h[:1000])
            default_options = {
                "body_width": 0, "ignore_emphasis": False, "ignore_links": False,
                "ignore_images": False, "protect_links": False, "single_line_break": True,
                "mark_code": True, "escape_snob": False,
            }
            if html2text_options:
                default_options.update(html2text_options)
            for key, value in default_options.items():
                if hasattr(h, key):
                    setattr(h, key, value)

            # logger.info(input_html[:100])
            raw_markdown = h.handle(input_html or "")
            raw_markdown = raw_markdown.replace("    ```", "```")

            markdown_with_citations = raw_markdown
            references_markdown = ""
            if citations:
                markdown_with_citations, references_markdown = self.convert_links_to_citations(raw_markdown, base_url)

            fit_markdown = ""
            filtered_html = ""
            active_filter = content_filter or self.content_filter

            if active_filter:
                filtered_html_list = active_filter.filter_content(input_html)
                filtered_html = "\n".join(f"<div>{s}</div>" for s in filtered_html_list)
                fit_markdown = h.handle(filtered_html)
            # logger.info("raw: "+raw_markdown[:50])
            # logger.info("fit: "+fit_markdown[:50])

            return MarkdownGenerationResult(
                raw_markdown=raw_markdown,
                markdown_with_citations=markdown_with_citations,
                references_markdown=references_markdown,
                fit_markdown=fit_markdown,
                fit_html=filtered_html,
            )
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            return MarkdownGenerationResult(error_msg, error_msg, "", "", "")


# ==========================================
# 5. 项目统一包装函数（只返回 fit_markdown）
# ==========================================
def html_to_markdown(
    html: str,
    base_url: str = "",
    use_pruning: bool = True,
    pruning_min_word_threshold: Optional[int] = None,
    pruning_threshold_type: str = "fixed",
    pruning_threshold: float = 0.48,
    use_citations: bool = True,
    html2text_options: Optional[Dict[str, Any]] = None,
) -> str:
    """并发安全包装：每次调用都新建实例，只返回 fit_markdown"""
    if not html or not isinstance(html, str):
        return ""

    content_filter = PruningContentFilter(
        min_word_threshold=pruning_min_word_threshold,
        threshold_type=pruning_threshold_type,
        threshold=pruning_threshold,
    ) if use_pruning else None

    generator = DefaultMarkdownGenerator(
        content_filter=content_filter,
        options=html2text_options or {},
    )

    result = generator.generate_markdown(
        input_html=html,
        base_url=base_url,
        html2text_options=html2text_options,
        content_filter=content_filter,
        citations=use_citations,
    )

    return result.fit_markdown.strip()