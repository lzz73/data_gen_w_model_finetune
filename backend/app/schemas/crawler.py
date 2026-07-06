"""
Crawler Schemas
"""
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl


class CrawlRequest(BaseModel):
    """爬取请求"""
    url: str = Field(..., description="目标 URL")
    method: str = Field(default="GET", pattern="^(GET|POST)$", description="HTTP 方法")
    css_selector: Optional[str] = Field(None, description="CSS 选择器，只提取匹配元素")
    extract_title: bool = Field(default=True, description="提取标题")
    extract_content: bool = Field(default=True, description="提取正文")
    extract_links: bool = Field(default=False, description="提取链接")
    extract_images: bool = Field(default=False, description="提取图片链接")
    project_id: Optional[str] = Field(None, description="目标项目 ID")
    max_pages: int = Field(default=10, ge=1, le=50, description="最大爬取页数")


class CrawlResultPage(BaseModel):
    """单个页面的爬取结果"""
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    links: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)


class CrawlSaveRequest(BaseModel):
    """保存爬取结果到项目"""
    task_id: str = Field(..., description="爬取任务 ID")
    project_id: str = Field(..., description="目标项目 ID")
