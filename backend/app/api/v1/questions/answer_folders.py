"""
Answers Output Folders API
"""
import json
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import ApiResponse
from app.core.database import get_db
from app.models.models import Project

router = APIRouter()

DATASETS_ROOT = Path("data")


@router.get("/answer-folders", response_model=ApiResponse)
async def list_answer_folders(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """List all generated answer output folders for a project"""
    # Verify project exists
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-answers"

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
                "total_answers": summary_data.get("created_answers", 0),
                "total_questions": summary_data.get("total_questions", 0),
                "processed_questions": summary_data.get("processed_questions", 0),
                "file_count": len(summary_data.get("files", {})),
                "files_summary": summary_data.get("files", {})
            })

    # 按文件夹名（时间戳）降序排序，最新的在前
    folders.sort(key=lambda x: x["folder_name"], reverse=True)

    return ApiResponse.ok(data={"folders": folders})


@router.get("/answer-folders/{folder_name}", response_model=ApiResponse)
async def get_answer_folder_details(
    project_id: UUID,
    folder_name: str,
    db: AsyncSession = Depends(get_db)
):
    """Get details of a specific answer output folder including answers by file"""
    # Verify project exists
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-answers"
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

    # 读取每个文件的答案
    files_data = []
    for file_id, file_info in summary.get("files", {}).items():
        answers_file = folder_path / file_id / "answers.json"
        metadata_file = folder_path / file_id / "metadata.json"

        answers = []
        metadata = {}

        if answers_file.exists():
            try:
                with open(answers_file, "r", encoding="utf-8") as f:
                    a_data = json.load(f)
                    answers = a_data.get("answers", [])
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
            "answer_count": file_info.get("answer_count", len(answers)),
            "answers": answers,
            "metadata": metadata
        })

    return ApiResponse.ok(data={
        "folder_name": folder_name,
        "folder_path": str(folder_path),
        "summary": summary,
        "files": files_data
    })


@router.put("/answer-folders/{folder_name}/rename", response_model=ApiResponse)
async def rename_answer_folder(
    project_id: UUID,
    folder_name: str,
    new_name: str = Query(..., description="新的文件夹名称"),
    db: AsyncSession = Depends(get_db)
):
    """Rename an answer output folder"""
    # Verify project exists
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-answers"
    old_path = output_base / folder_name
    new_path = output_base / new_name

    if not old_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    if new_path.exists():
        raise HTTPException(status_code=400, detail="Folder with new name already exists")

    # 重命名文件夹
    shutil.move(str(old_path), str(new_path))

    return ApiResponse.ok(message=f"Folder renamed from {folder_name} to {new_name}")


@router.delete("/answer-folders/{folder_name}", response_model=ApiResponse)
async def delete_answer_folder(
    project_id: UUID,
    folder_name: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete an answer output folder and clear answers in database"""
    # Verify project exists
    project = await db.execute(select(Project).where(Project.id == project_id))
    project = project.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    output_base = DATASETS_ROOT / str(project_id) / "generated-answers"
    folder_path = output_base / folder_name

    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    # 读取 summary.json 获取包含的问题 ID
    summary_file = folder_path / "summary.json"
    question_ids_to_clear = []
    if summary_file.exists():
        try:
            import json
            with open(summary_file, "r", encoding="utf-8") as f:
                summary = json.load(f)
            # 从 answers.json 中收集所有问题 ID
            for file_id, file_info in summary.get("files", {}).items():
                answers_json_file = folder_path / file_id / "answers.json"
                if answers_json_file.exists():
                    with open(answers_json_file, "r", encoding="utf-8") as f:
                        answers_data = json.load(f)
                    for answer_item in answers_data.get("answers", []):
                        q_id = answer_item.get("question_id")
                        if q_id:
                            question_ids_to_clear.append(q_id)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to read summary for folder {folder_name}: {e}")

    # 删除文件夹
    shutil.rmtree(str(folder_path))

    # 清空数据库中对应问题的答案
    if question_ids_to_clear:
        from uuid import UUID
        from sqlalchemy import update
        from app.models.models import Question

        # 将问题的 answer 字段设为 NULL，answer_status 设为 pending
        await db.execute(
            update(Question)
            .where(Question.id.in_([UUID(qid) for qid in question_ids_to_clear]))
            .values(answer=None, answer_status="pending", answer_error=None)
        )
        await db.commit()

    return ApiResponse.ok(message=f"Folder {folder_name} deleted successfully. Cleared {len(question_ids_to_clear)} answers in database.")
