"""
Questions Output Folders API
"""
import json
import os
import shutil
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import ApiResponse
from app.core.database import get_db
from app.models.models import Project

router = APIRouter()

DATASETS_ROOT = Path("data")


@router.get("/output-folders", response_model=ApiResponse)
async def list_output_folders(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """List all generated question output folders for a project"""
    # Verify project exists
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-questions"

    if not output_base.exists():
        return ApiResponse.ok(data={"folders": []})

    folders = []
    for item in output_base.iterdir():
        if item.is_dir():
            # 尝试读取 summary.json 获取统计信息
            summary_file = item / "summary.json"
            summary_data = {}
            if summary_file.exists():
                try:
                    with open(summary_file, "r", encoding="utf-8") as f:
                        summary_data = json.load(f)
                except Exception:
                    pass

            folders.append({
                "folder_name": item.name,
                "folder_path": str(item),
                "created_at": item.name,  # 文件夹名就是时间戳
                "total_questions": summary_data.get("created_questions", 0),
                "total_chunks": summary_data.get("total_chunks", 0),
                "processed_chunks": summary_data.get("processed_chunks", 0),
                "skipped_chunks": summary_data.get("skipped_chunks", 0),
                "file_count": len(summary_data.get("files", {})),
                "files_summary": summary_data.get("files", {})
            })

    # 按文件夹名（时间戳）降序排序，最新的在前
    folders.sort(key=lambda x: x["folder_name"], reverse=True)

    return ApiResponse.ok(data={"folders": folders})


@router.get("/output-folders/{folder_name}", response_model=ApiResponse)
async def get_folder_details(
    project_id: UUID,
    folder_name: str,
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific output folder including questions by file"""
    # Verify project exists
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-questions"
    folder_path = output_base / folder_name

    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    # 读取 summary.json
    summary_file = folder_path / "summary.json"
    if not summary_file.exists():
        raise HTTPException(status_code=404, detail="Summary file not found")

    try:
        with open(summary_file, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read summary: {str(e)}")

    # 读取每个文件的问题
    files_data = []
    for file_id, file_info in summary.get("files", {}).items():
        questions_file = folder_path / file_id / "questions.json"
        metadata_file = folder_path / file_id / "metadata.json"

        questions = []
        metadata = {}

        if questions_file.exists():
            try:
                with open(questions_file, "r", encoding="utf-8") as f:
                    q_data = json.load(f)
                    questions = q_data.get("questions", [])
            except Exception:
                pass

        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                pass

        files_data.append({
            "file_id": file_id,
            "file_name": file_info.get("filename", "未知文件"),
            "question_count": file_info.get("question_count", len(questions)),
            "chunks_processed": file_info.get("chunks_processed", 0),
            "chunks_skipped": file_info.get("chunks_skipped", 0),
            "questions": questions,
            "metadata": metadata
        })

    return ApiResponse.ok(data={
        "folder_name": folder_name,
        "folder_path": str(folder_path),
        "summary": summary,
        "files": files_data
    })


@router.put("/output-folders/{folder_name}/rename", response_model=ApiResponse)
async def rename_folder(
    project_id: UUID,
    folder_name: str,
    new_name: str = Query(..., description="新的文件夹名称"),
    db: AsyncSession = Depends(get_db)
):
    """Rename an output folder"""
    # Verify project exists
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-questions"
    old_path = output_base / folder_name
    new_path = output_base / new_name

    if not old_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    if new_path.exists():
        raise HTTPException(status_code=400, detail="Folder with new name already exists")

    # 重命名文件夹
    shutil.move(str(old_path), str(new_path))

    return ApiResponse.ok(message=f"Folder renamed from {folder_name} to {new_name}")


@router.delete("/output-folders/{folder_name}", response_model=ApiResponse)
async def delete_folder(
    project_id: UUID,
    folder_name: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete an output folder"""
    # Verify project exists
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-questions"
    folder_path = output_base / folder_name

    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    # 删除文件夹
    shutil.rmtree(str(folder_path))

    return ApiResponse.ok(message=f"Folder {folder_name} deleted successfully")
