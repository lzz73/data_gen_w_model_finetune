"""
QA Pair Output Folders API

问答对输出文件夹管理（列表、详情、重命名、删除）
"""
import json
import logging
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import ApiResponse
from app.core.database import get_db
from app.models.models import Project, Question

router = APIRouter()

DATASETS_ROOT = Path("data")


@router.get("/qa-folders", response_model=ApiResponse)
async def list_qa_folders(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """列出项目所有问答对输出文件夹"""
    # 验证项目存在
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-qa"

    if not output_base.exists():
        return ApiResponse.ok(data={"folders": []})

    folders = []
    for item in output_base.iterdir():
        if item.is_dir():
            # 读取 summary.json
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
                "created_at": item.name,
                "total_qa_pairs": summary_data.get("created_questions", 0),
                "total_questions": summary_data.get("created_questions", 0),
                "total_answers": summary_data.get("created_answers", 0),
                "total_chunks": summary_data.get("total_chunks", 0),
                "processed_chunks": summary_data.get("processed_chunks", 0),
                "skipped_chunks": summary_data.get("skipped_chunks", 0),
                "failed_answers": summary_data.get("failed_answers", 0),
                "file_count": len(summary_data.get("files", {})),
                "files_summary": summary_data.get("files", {}),
            })

    # 按文件夹名（时间戳）降序排序
    folders.sort(key=lambda x: x["folder_name"], reverse=True)

    return ApiResponse.ok(data={"folders": folders})


@router.get("/qa-folders/{folder_name}", response_model=ApiResponse)
async def get_qa_folder_details(
    project_id: UUID,
    folder_name: str,
    db: AsyncSession = Depends(get_db),
):
    """获取问答对文件夹详情，包含每个文件的问答对数据"""
    # 验证项目存在
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-qa"
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

    # 读取每个文件的问答对
    files_data = []
    for file_id, file_info in summary.get("files", {}).items():
        qa_file = folder_path / file_id / "qa_pairs.json"
        metadata_file = folder_path / file_id / "metadata.json"

        qa_pairs = []
        metadata = {}

        if qa_file.exists():
            try:
                with open(qa_file, "r", encoding="utf-8") as f:
                    qa_data = json.load(f)
                    qa_pairs = qa_data.get("qa_pairs", [])
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
            "qa_count": file_info.get("qa_count", len(qa_pairs)),
            "chunks_processed": file_info.get("chunks_processed", 0),
            "chunks_skipped": file_info.get("chunks_skipped", 0),
            "qa_pairs": qa_pairs,
            "metadata": metadata,
        })

    return ApiResponse.ok(data={
        "folder_name": folder_name,
        "folder_path": str(folder_path),
        "summary": summary,
        "files": files_data,
    })


@router.put("/qa-folders/{folder_name}/rename", response_model=ApiResponse)
async def rename_qa_folder(
    project_id: UUID,
    folder_name: str,
    new_name: str = Query(..., description="新的文件夹名称"),
    db: AsyncSession = Depends(get_db),
):
    """重命名问答对输出文件夹"""
    # 验证项目存在
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-qa"
    old_path = output_base / folder_name
    new_path = output_base / new_name

    if not old_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    if new_path.exists():
        raise HTTPException(status_code=400, detail="Folder with new name already exists")

    shutil.move(str(old_path), str(new_path))

    return ApiResponse.ok(message=f"Folder renamed from {folder_name} to {new_name}")


@router.delete("/qa-folders/{folder_name}", response_model=ApiResponse)
async def delete_qa_folder(
    project_id: UUID,
    folder_name: str,
    db: AsyncSession = Depends(get_db),
):
    """删除问答对输出文件夹，同时删除数据库中对应的 Question 记录

    注意：与问题文件夹不同，QA 文件夹的问答对是原子生成的，
    删除时应一并清理 Question 记录（source="generated_qa"）。
    """
    # 验证项目存在
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-qa"
    folder_path = output_base / folder_name

    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    # 从 qa_pairs.json 收集 question_id
    question_ids_to_delete = []
    summary_file = folder_path / "summary.json"
    if summary_file.exists():
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                summary = json.load(f)
            for file_id in summary.get("files", {}).keys():
                qa_file = folder_path / file_id / "qa_pairs.json"
                if qa_file.exists():
                    with open(qa_file, "r", encoding="utf-8") as f:
                        qa_data = json.load(f)
                    for item in qa_data.get("qa_pairs", []):
                        q_id = item.get("question_id")
                        if q_id:
                            question_ids_to_delete.append(q_id)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Failed to read qa_pairs for folder {folder_name}: {e}"
            )

    # 删除文件夹
    shutil.rmtree(str(folder_path))

    # 删除数据库中对应的 Question 记录
    deleted_count = 0
    if question_ids_to_delete:
        from uuid import UUID as UUIDType

        uuid_list = []
        for qid in question_ids_to_delete:
            try:
                uuid_list.append(UUIDType(qid))
            except (ValueError, AttributeError):
                continue

        if uuid_list:
            result = await db.execute(
                delete(Question).where(
                    Question.id.in_(uuid_list),
                    Question.project_id == project_id,
                    Question.source == "generated_qa",
                )
            )
            deleted_count = result.rowcount
            await db.commit()

    return ApiResponse.ok(
        message=f"文件夹 {folder_name} 已删除。已清理 {deleted_count} 条问答对记录。"
    )
