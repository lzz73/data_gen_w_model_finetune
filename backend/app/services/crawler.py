"""
Crawler Service — 网页爬取与内容提取（支持深度爬取）
"""
import asyncio
import logging
import re
from typing import Optional, Set, Callable
from urllib.parse import urljoin, urlparse
from html.parser import HTMLParser

import httpx
import html2text

from app.core.config import get_settings

logger = logging.getLogger("yg_dataset.crawler")
settings = get_settings()

# 静态资源后缀，遇到这些链接不跟随
SKIP_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico', '.webp',
    '.css', '.js', '.woff', '.woff2', '.ttf', '.eot',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar', '.7z', '.tar', '.gz',
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
    '.json', '.xml', '.rss', '.atom',
}


def _normalize_url(url: str) -> str:
    """标准化 URL：去 fragment、去常见追踪参数"""
    parsed = urlparse(url)
    # 去掉 #fragment
    # 去掉常见追踪参数
    clean = re.sub(r'([&?])(utm_[^&]*|fbclid|gclid|ref|source|from|spm|nsukey)=[^&]*', '', parsed._replace(fragment='').geturl())
    # 去掉末尾的 ? 或 &
    clean = clean.rstrip('?&')
    return clean


def _is_same_domain(url1: str, url2: str) -> bool:
    """判断两个 URL 是否同域"""
    p1 = urlparse(url1)
    p2 = urlparse(url2)
    return p1.netloc == p2.netloc


def _should_follow(link: str, base_url: str) -> bool:
    """判断一个链接是否应该跟随爬取"""
    if not link:
        return False
    # 必须同域
    if not _is_same_domain(link, base_url):
        return False
    # 必须是 http/https
    parsed = urlparse(link)
    if parsed.scheme not in ('http', 'https'):
        return False
    # 过滤静态资源后缀
    path_lower = parsed.path.lower().split('?')[0]
    for ext in SKIP_EXTENSIONS:
        if path_lower.endswith(ext):
            return False
    return True


class HTMLExtractor(HTMLParser):
    """从 HTML 中提取 title、links、images"""

    def __init__(self):
        super().__init__()
        self.title = None
        self._in_title = False
        self._title_parts = []
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'title':
            self._in_title = True
        elif tag == 'a' and 'href' in attrs_dict:
            self.links.append(attrs_dict['href'])
        elif tag == 'img' and 'src' in attrs_dict:
            self.images.append(attrs_dict['src'])

    def handle_data(self, data):
        if self._in_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
            self.title = ''.join(self._title_parts).strip()


def _strip_html_noise(html: str) -> str:
    """移除 script、style、nav、header、footer 等噪音标签"""
    import re
    # 移除 script 和 style 块
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # 移除 nav、header、footer
    html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
    return html


def _extract_by_selector(html: str, css_selector: str) -> str:
    """用简单的字符串匹配提取 CSS 选择器对应的子树

    不依赖 beautifulsoup，只支持简单的 .class 和 #id 选择器。
    """
    # 尝试用标准库做基本提取
    import re
    # 只支持 tag、.class、#id、tag.class、tag#id 这几种简单选择器
    sel = css_selector.strip()

    if sel.startswith('#'):
        # id 选择器
        id_val = sel[1:]
        pattern = rf'<[^>]+id\s*=\s*["\']?{re.escape(id_val)}["\']?[^>]*>(.*?)</[^>]+>'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else html

    if sel.startswith('.'):
        # class 选择器
        class_val = sel[1:]
        pattern = rf'<(\w+)[^>]*class\s*=\s*["\'][^"\']*{re.escape(class_val)}[^"\']*["\'][^>]*>(.*?)</\1>'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        return match.group(2) if match else html

    # tag 选择器 (如 article, main)
    tag = sel.split('.')[0].split('#')[0]
    if tag:
        pattern = rf'<{re.escape(tag)}[^>]*>(.*?)</{re.escape(tag)}>'
        match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1)

    return html


def html_to_markdown(html: str) -> str:
    """将 HTML 转为 Markdown"""
    h2t = html2text.HTML2Text()
    h2t.ignore_links = False
    h2t.ignore_images = False
    h2t.ignore_emphasis = False
    h2t.body_width = 0  # 不自动换行
    h2t.protect_links = True
    h2t.wrap_links = False
    return h2t.handle(html).strip()


async def crawl_page(
    url: str,
    method: str = "GET",
    css_selector: Optional[str] = None,
    extract_title: bool = True,
    extract_content: bool = True,
    extract_links: bool = False,
    extract_images: bool = False,
) -> dict:
    """
    爬取单个页面，提取内容

    Returns:
        dict with keys: url, title, content, links, images
    """
    timeout = getattr(settings, 'CRAWL_TIMEOUT', 30)

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        verify=False,  # 内网环境可能自签证书
        headers={
            "User-Agent": "YGDataset-Crawler/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    ) as client:
        if method.upper() == "POST":
            response = await client.post(url)
        else:
            response = await client.get(url)

        response.raise_for_status()
        html = response.text

    result = {
        "url": str(response.url),
        "title": None,
        "content": None,
        "links": [],
        "images": [],
    }

    # 提取 title
    if extract_title:
        extractor = HTMLExtractor()
        try:
            extractor.feed(html)
            result["title"] = extractor.title
        except Exception:
            pass

    # 提取正文
    if extract_content:
        clean_html = _strip_html_noise(html)
        if css_selector:
            clean_html = _extract_by_selector(clean_html, css_selector)
        try:
            result["content"] = html_to_markdown(clean_html)
        except Exception as e:
            logger.warning(f"HTML to Markdown conversion failed: {e}")
            result["content"] = ""

    # 提取链接
    if extract_links:
        try:
            if not extract_title:
                extractor = HTMLExtractor()
                extractor.feed(html)
            base_url = str(response.url)
            result["links"] = [
                urljoin(base_url, link)
                for link in extractor.links
                if link and not link.startswith(('#', 'javascript:', 'mailto:'))
            ]
        except Exception:
            pass

    # 提取图片
    if extract_images:
        try:
            if not extract_title and not extract_links:
                extractor = HTMLExtractor()
                extractor.feed(html)
            base_url = str(response.url)
            result["images"] = [
                urljoin(base_url, img)
                for img in extractor.images
                if img and not img.startswith('data:')
            ]
        except Exception:
            pass

    return result


async def crawl_site(
    start_url: str,
    max_pages: int = 10,
    css_selector: Optional[str] = None,
    extract_title: bool = True,
    extract_content: bool = True,
    extract_links: bool = True,  # 深度爬取默认提取链接（用于发现子页面）
    extract_images: bool = False,
    on_page_done: Optional[Callable] = None,
) -> list:
    """
    深度爬取：从起始 URL 出发，自动跟随同域链接爬取多个页面

    Args:
        start_url: 起始 URL
        max_pages: 最大爬取页数
        css_selector: CSS 选择器
        extract_title: 提取标题
        extract_content: 提取正文
        extract_links: 提取链接（深度爬取时必须开启，用于发现子页面）
        extract_images: 提取图片
        on_page_done: 每爬完一页的回调，参数为 (pages_so_far, max_pages)

    Returns:
        所有页面的爬取结果列表
    """
    # 限制 max_pages 不超过配置上限
    cap = getattr(settings, 'CRAWL_MAX_PAGES', 50)
    max_pages = min(max_pages, cap, 50)

    visited: Set[str] = set()
    queue = [start_url]
    pages = []
    base_url_normalized = _normalize_url(start_url)

    async with httpx.AsyncClient(
        timeout=getattr(settings, 'CRAWL_TIMEOUT', 30),
        follow_redirects=True,
        verify=False,
        headers={
            "User-Agent": "YGDataset-Crawler/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    ) as client:
        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            normalized = _normalize_url(url)

            # 跳过已访问的
            if normalized in visited:
                continue

            # 跳过不同域的
            if not _should_follow(normalized, base_url_normalized):
                continue

            visited.add(normalized)

            try:
                # 复用 httpx client 而非调用 crawl_page（避免重复创建 client）
                response = await client.get(normalized)
                response.raise_for_status()
                html = response.text
                final_url = str(response.url)
            except Exception as e:
                logger.warning(f"Failed to fetch {normalized}: {e}")
                continue

            # 提取内容
            page_result = {
                "url": final_url,
                "title": None,
                "content": None,
                "links": [],
                "images": [],
            }

            extractor = HTMLExtractor()
            try:
                extractor.feed(html)
            except Exception:
                pass

            if extract_title:
                page_result["title"] = extractor.title

            if extract_content:
                clean_html = _strip_html_noise(html)
                if css_selector:
                    clean_html = _extract_by_selector(clean_html, css_selector)
                try:
                    page_result["content"] = html_to_markdown(clean_html)
                except Exception as e:
                    logger.warning(f"HTML to Markdown failed for {normalized}: {e}")
                    page_result["content"] = ""

            # 提取链接（深度爬取的关键）
            all_links = [
                urljoin(final_url, link)
                for link in extractor.links
                if link and not link.startswith(('#', 'javascript:', 'mailto:'))
            ]

            if extract_links:
                page_result["links"] = all_links

            if extract_images:
                page_result["images"] = [
                    urljoin(final_url, img)
                    for img in extractor.images
                    if img and not img.startswith('data:')
                ]

            # 发现新链接，加入队列
            for link in all_links:
                link_normalized = _normalize_url(link)
                if link_normalized not in visited and _should_follow(link_normalized, base_url_normalized):
                    queue.append(link_normalized)

            pages.append(page_result)

            # 回调通知进度
            if on_page_done:
                on_page_done(pages, max_pages)

            # 请求间隔 1 秒
            if queue and len(pages) < max_pages:
                await asyncio.sleep(1)

    return pages
