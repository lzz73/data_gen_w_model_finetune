"""
Crawler API Router — 网页爬取
"""
import asyncio
import logging
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.response import ApiResponse
from app.core.config import get_settings
from app.core.database import get_db, AsyncSessionLocal
from app.core.crud import CRUDBase
from app.core.logging import log_success, log_failure
from app.models.models import Task as TaskModel, File as FileModel
from app.schemas.crawler import CrawlRequest, CrawlSaveRequest

settings = get_settings()
router = APIRouter()
logger = logging.getLogger("yg_dataset.crawler")

task_crud = CRUDBase(TaskModel)
file_crud = CRUDBase(FileModel)


async def _run_crawl_task(task_id_str: str, request: CrawlRequest):
    """后台执行爬取任务"""
    from app.services.crawler import crawl_site

    logger.info(f"[CRAWL] Background task started for: {request.url}")
    task_uuid = UUID(task_id_str)

    async with AsyncSessionLocal() as db:
        try:
            # 更新任务状态为 running
            result = await db.execute(
                select(TaskModel).where(TaskModel.id == task_uuid)
            )
            task = result.scalar_one_or_none()
            if not task:
                return

            task.status = "running"
            task.total_count = request.max_pages
            await db.commit()

            # 进度回调：每爬完一页更新数据库（跳过前几页避免频繁写入）
            last_saved_count = 0

            async def on_page_done(pages_so_far, max_pages):
                nonlocal last_saved_count
                count = len(pages_so_far)
                # 每爬 2 页或最后一页才更新数据库，减少 SQLite 写入压力
                if count - last_saved_count >= 2 or count >= max_pages:
                    try:
                        async with AsyncSessionLocal() as progress_db:
                            r = await progress_db.execute(
                                select(TaskModel).where(TaskModel.id == task_uuid)
                            )
                            t = r.scalar_one_or_none()
                            if t:
                                t.progress = int(count / max_pages * 100)
                                t.completed_count = count
                                t.result = {"pages": [dict(p) for p in pages_so_far]}
                                await progress_db.commit()
                                last_saved_count = count
                    except Exception as e:
                        logger.warning(f"Progress update failed: {e}")

            # 执行深度爬取
            pages = await crawl_site(
                start_url=request.url,
                max_pages=request.max_pages,
                css_selector=request.css_selector,
                extract_title=request.extract_title,
                extract_content=request.extract_content,
                extract_links=True,  # 深度爬取必须提取链接
                extract_images=request.extract_images,
                on_page_done=on_page_done,
            )

            # 最终更新任务结果
            async with AsyncSessionLocal() as final_db:
                r = await final_db.execute(
                    select(TaskModel).where(TaskModel.id == task_uuid)
                )
                t = r.scalar_one_or_none()
                if t:
                    t.status = "completed"
                    t.progress = 100
                    t.completed_count = len(pages)
                    t.result = {"pages": pages}
                    await final_db.commit()

            log_success("爬取任务完成", task_id=task_id_str, url=request.url, pages=len(pages))

        except Exception as e:
            # 标记失败
            try:
                async with AsyncSessionLocal() as error_db:
                    r = await error_db.execute(
                        select(TaskModel).where(TaskModel.id == task_uuid)
                    )
                    t = r.scalar_one_or_none()
                    if t:
                        t.status = "failed"
                        t.error = str(e)
                        await error_db.commit()
            except Exception:
                pass

            log_failure("爬取任务失败", task_id=task_id_str, url=request.url, error=str(e))


@router.post("/start", response_model=ApiResponse)
async def start_crawl(
    request: CrawlRequest,
    db: AsyncSession = Depends(get_db)
):
    """发起爬取任务"""
    logger.info(f"Starting crawl: url={request.url}")

    # 创建任务记录
    task = TaskModel(
        project_id=UUID(request.project_id) if request.project_id else None,
        task_type="crawl",
        status="pending",
        progress=0,
        total_count=1,
        completed_count=0,
        detail=request.url,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    task_id_str = str(task.id)
    logger.info(f"Crawl task created: {task_id_str}, starting background work...")

    # 异步执行爬取
    asyncio.create_task(_run_crawl_task(task_id_str, request))

    return ApiResponse.ok(
        data={"task_id": task_id_str},
        message="Crawl task started"
    )


@router.get("/task/{task_id}", response_model=ApiResponse)
async def get_crawl_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """查询爬取任务状态"""
    result = await db.execute(
        select(TaskModel).where(TaskModel.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        return ApiResponse.fail(message="Task not found")

    data = {
        "task_id": str(task.id),
        "status": task.status,
        "progress": task.progress or 0,
        "url": task.detail or "",
        "error": task.error,
        "pages": (task.result or {}).get("pages", []),
    }

    return ApiResponse.ok(data=data)


@router.post("/save", response_model=ApiResponse)
async def save_crawl_result(
    request: CrawlSaveRequest,
    db: AsyncSession = Depends(get_db)
):
    """保存爬取结果到项目"""
    # 获取任务结果
    try:
        task_uuid = UUID(request.task_id)
    except ValueError:
        return ApiResponse.fail(message=f"Invalid task_id format: {request.task_id}")

    result = await db.execute(
        select(TaskModel).where(TaskModel.id == task_uuid)
    )
    task = result.scalar_one_or_none()

    if not task:
        return ApiResponse.fail(message="Task not found")

    if task.status != "completed":
        return ApiResponse.fail(message=f"Task is not completed yet (status: {task.status})")

    pages = task.result.get("pages", []) if task.result else []
    if not pages:
        return ApiResponse.fail(message="No crawl results to save")

    try:
        project_id = UUID(request.project_id)
    except ValueError:
        return ApiResponse.fail(message=f"Invalid project_id format: {request.project_id}")

    # 确保目录存在
    raw_dir = Path("./YG-Datasets/data") / str(project_id) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    ready_dir = Path("./YG-Datasets/data") / str(project_id) / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)

    file_ids = []
    saved_count = 0

    for page in pages:
        url = page.get("url", "unknown")
        title = page.get("title") or url
        content = page.get("content", "")

        if not content or not content.strip():
            logger.warning(f"Skipping page with empty content: {url}")
            continue

        # 生成有意义的文件名：用标题做文件名
        import re
        # 从标题生成安全文件名，去掉特殊字符
        safe_title = re.sub(r'[\\/:*?"<>|#\r\n]', '_', title)
        safe_title = safe_title.strip().rstrip('._')[:80]  # 限制长度
        if not safe_title:
            safe_title = "untitled"
        safe_name = f"{safe_title}.md"
        safe_filename = f"{uuid4().hex[:8]}_{safe_name}"
        file_id = uuid4()
        file_path = raw_dir / safe_filename

        # 写入 Markdown 文件到 raw 目录
        md_content = f"# {title}\n\n> 来源: {url}\n\n{content}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda p=file_path, c=md_content: p.write_text(c, encoding='utf-8')
        )

        # 同时写入 ready 目录（已经是 Markdown，不需要转换）
        ready_path = ready_dir / f"{file_id}.md"
        await loop.run_in_executor(
            None,
            lambda p=ready_path, c=md_content: p.write_text(c, encoding='utf-8')
        )

        # 创建文件记录
        db_file = FileModel(
            project_id=project_id,
            filename=safe_name,
            file_type="md",
            file_path=str(file_path),
            size=len(md_content.encode('utf-8')),
            status="pending",
        )
        db.add(db_file)
        file_ids.append(str(file_id))
        saved_count += 1

    await db.commit()

    if saved_count == 0:
        return ApiResponse.fail(message="No pages with content to save")

    log_success(
        "爬取结果保存成功",
        task_id=request.task_id,
        project_id=request.project_id,
        file_count=saved_count,
    )

    return ApiResponse.ok(
        data={"file_ids": file_ids, "count": saved_count},
        message=f"Saved {saved_count} files to project"
    )
