"""
Projects API Router
"""
import logging
import shutil
from pathlib import Path
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.api.response import ApiResponse, PaginatedResponse
from app.core.database import get_db
from app.core.exceptions import NotFoundException, DuplicateException
from app.core.crud import CRUDBase
from app.models.models import Project, File, Chunk, Question, Dataset, EvalDataset
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectCreateSchema,
    ProjectUpdateSchema,
    ProjectStats
)

router = APIRouter()
logger = logging.getLogger("yg_dataset.projects")

# Initialize CRUD
project_crud = CRUDBase(Project)


@router.get("", response_model=PaginatedResponse)
async def list_projects(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db)
):
    """List all projects with pagination"""
    logger.info(f"Listing projects - page: {page}, page_size: {page_size}")
    skip = (page - 1) * page_size
    projects, total = await project_crud.get_multi(
        db,
        skip=skip,
        limit=page_size,
        order_by="created_at",
        descending=True
    )

    logger.info(f"Found {total} projects, returning {len(projects)} items")
    project_responses = [ProjectResponse.model_validate(p) for p in projects]
    return PaginatedResponse.ok(
        items=project_responses,
        page=page,
        page_size=page_size,
        total=total
    )


@router.post("", response_model=ApiResponse)
async def create_project(
    project: ProjectCreateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create a new project"""
    logger.info(f"Creating project: name={project.name}, description={project.description}")

    # 检查项目名是否重复
    existing = await db.scalar(
        select(Project).where(Project.name == project.name)
    )
    if existing:
        raise DuplicateException("Project", "name")

    db_project = await project_crud.create(db, project)
    logger.info(f"Project created successfully: id={db_project.id}")
    return ApiResponse.ok(
        data={"id": str(db_project.id)},
        message="Project created successfully"
    )


@router.get("/{project_id}", response_model=ApiResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get project by ID"""
    logger.info(f"Getting project: id={project_id}")
    project = await project_crud.get_or_raise(db, project_id, "Project")
    logger.info(f"Found project: name={project.name}")
    return ApiResponse.ok(data=ProjectResponse.model_validate(project))


@router.put("/{project_id}", response_model=ApiResponse)
async def update_project(
    project_id: UUID,
    project: ProjectUpdateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Update project"""
    logger.info(f"Updating project: id={project_id}")
    db_project = await project_crud.get_or_raise(db, project_id, "Project")

    # 检查项目名是否重复（排除了自身）
    update_data = project.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != db_project.name:
        existing = await db.scalar(
            select(Project).where(Project.name == update_data["name"], Project.id != project_id)
        )
        if existing:
            raise DuplicateException("Project", "name")

    # Handle extra_data merge: deep-merge instead of replace
    if "extra_data" in update_data and update_data["extra_data"] is not None:
        existing = db_project.extra_data or {}
        # Merge: new keys overwrite, existing keys preserved
        merged = {**existing, **update_data["extra_data"]}
        update_data["extra_data"] = merged

    for field, value in update_data.items():
        if hasattr(db_project, field):
            setattr(db_project, field, value)

    # SQLAlchemy JSON 列原地修改不会被检测到，需要显式标记
    if "extra_data" in update_data:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(db_project, "extra_data")

    await db.commit()
    await db.refresh(db_project)

    logger.info(f"Project updated: name={db_project.name}")
    return ApiResponse.ok(
        data=ProjectResponse.model_validate(db_project),
        message="Project updated successfully"
    )


@router.get("/{project_id}/stats", response_model=ApiResponse)
async def get_project_stats(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get project pipeline statistics for step progress"""
    logger.info(f"Getting project stats: id={project_id}")
    await project_crud.get_or_raise(db, project_id, "Project")

    file_count = await db.scalar(
        select(func.count(File.id)).where(
            File.project_id == project_id,
            File.status == 'completed'
        )
    )
    chunk_count = await db.scalar(
        select(func.count(Chunk.id)).where(
            Chunk.project_id == project_id
        )
    )
    question_count = await db.scalar(
        select(func.count(Question.id)).where(
            Question.project_id == project_id
        )
    )
    dataset_count = await db.scalar(
        select(func.count(Dataset.id)).where(
            Dataset.project_id == project_id
        )
    )
    eval_count = await db.scalar(
        select(func.count(EvalDataset.id)).where(
            EvalDataset.project_id == project_id
        )
    )

    stats = ProjectStats(
        file_count=file_count or 0,
        chunk_count=chunk_count or 0,
        question_count=question_count or 0,
        dataset_count=dataset_count or 0,
        eval_count=eval_count or 0
    )
    return ApiResponse.ok(data=stats)


@router.delete("/{project_id}", response_model=ApiResponse)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete project"""
    logger.info(f"Deleting project: id={project_id}")
    await project_crud.get_or_raise(db, project_id, "Project")
    await project_crud.delete(db, project_id)

    # 删除项目对应的本地数据目录
    project_data_dir = Path("./YG-Datasets/data") / str(project_id)
    if project_data_dir.exists():
        shutil.rmtree(project_data_dir)
        logger.info(f"Project data directory deleted: {project_data_dir}")

    logger.info(f"Project deleted: id={project_id}")
    return ApiResponse.ok(message="Project deleted successfully")
