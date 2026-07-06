"""
Datasets API Router

数据集导出：从项目的问答对中按批次筛选，按策略划分训练/验证/测试集，
导出为 JSONL 格式（支持 alpaca / sharegpt / llama_factory）。
"""
import io
import json
import random
import zipfile
from typing import Optional, List
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response import ApiResponse, PaginatedResponse
from app.core.database import get_db
from app.core.exceptions import NotFoundException, AppException
from app.core.crud import CRUDBase
from app.models.models import Dataset, Question
from app.schemas.dataset import DatasetResponse, DatasetCreateSchema

router = APIRouter()

# Initialize CRUD
dataset_crud = CRUDBase(Dataset)


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────

class ExportRequest(BaseModel):
    """导出请求参数"""
    file_format: str = Field("jsonl", pattern="^(jsonl|json|excel)$",
                             description="文件格式：jsonl / json / excel，ZIP 内文件后缀对应变化")
    data_format: str = Field("alpaca", pattern="^(alpaca|sharegpt|llama_factory)$",
                             description="数据格式：alpaca / sharegpt / llama_factory")
    batch_id: Optional[str] = Field(None, description="指定导出的问答批次ID")
    split_strategy: str = Field("random", pattern="^(random|file)$",
                                description="划分策略：random=随机打乱按比例划分，file=按来源文件划分")
    seed: int = Field(42, ge=1, le=9999, description="随机种子")
    train_ratio: float = Field(0.9, ge=0.5, le=0.98, description="训练集比例")
    val_ratio: float = Field(0.05, ge=0.01, le=0.25, description="验证集比例")
    test_ratio: float = Field(0.05, ge=0.01, le=0.25, description="测试集比例")


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _qa_to_alpaca(q: Question) -> dict:
    """将问答对转为 Alpaca 格式"""
    return {
        "instruction": q.content or "",
        "input": "",
        "output": q.answer or "",
    }


def _qa_to_sharegpt(q: Question) -> dict:
    """将问答对转为 ShareGPT 格式"""
    return {
        "conversations": [
            {"from": "human", "value": q.content or ""},
            {"from": "gpt", "value": q.answer or ""},
        ]
    }


def _qa_to_llama_factory(q: Question) -> dict:
    """将问答对转为 LLaMA Factory 格式（同 Alpaca）"""
    return _qa_to_alpaca(q)


def _qa_to_dpo(q: Question) -> dict:
    """将问答对转为 DPO 偏好格式（含 chosen 和 rejected）"""
    meta = q.generation_metadata or {}
    rejected = meta.get("rejected_answer", "")
    return {
        "instruction": q.content or "",
        "input": "",
        "chosen": q.answer or "",
        "rejected": rejected or f"[劣质回答] {q.answer}" if q.answer else "",
    }


_FORMAT_FN = {
    "alpaca": _qa_to_alpaca,
    "sharegpt": _qa_to_sharegpt,
    "llama_factory": _qa_to_llama_factory,
    "dpo": _qa_to_dpo,
}


def _split_random(questions: list, train_ratio: float, val_ratio: float, test_ratio: float, seed: int):
    """随机打乱后按比例划分"""
    rng = random.Random(seed)
    rng.shuffle(questions)

    total = len(questions)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)

    train = questions[:train_end]
    val = questions[train_end:val_end]
    test = questions[val_end:]

    return train, val, test


def _split_by_file(questions: list, train_ratio: float, val_ratio: float, test_ratio: float, seed: int):
    """按来源文件划分：将文件分组，整组分配到某个集合，避免同文件数据跨越训练和测试集"""
    # 按文件名分组
    file_groups: dict[str, list] = {}
    for q in questions:
        meta = q.generation_metadata or {}
        fname = meta.get("filename", "unknown")
        file_groups.setdefault(fname, []).append(q)

    # 随机打乱文件顺序
    rng = random.Random(seed)
    file_names = list(file_groups.keys())
    rng.shuffle(file_names)

    # 按文件粒度分配
    total = len(questions)
    train_target = int(total * train_ratio)
    val_target = int(total * val_ratio)

    train, val, test = [], [], []
    current_count = 0
    for fname in file_names:
        group = file_groups[fname]
        if current_count < train_target:
            train.extend(group)
        elif current_count < train_target + val_target:
            val.extend(group)
        else:
            test.extend(group)
        current_count += len(group)

    return train, val, test


def _write_jsonl(buffer: io.StringIO, questions: list, format_fn):
    """将问答对列表以 JSONL 格式写入 buffer"""
    for q in questions:
        line = json.dumps(format_fn(q), ensure_ascii=False)
        buffer.write(line)
        buffer.write("\n")


# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────

@router.get("", response_model=ApiResponse)
async def list_datasets(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List datasets for a project"""
    skip = (page - 1) * page_size
    datasets, total = await dataset_crud.get_multi(
        db,
        skip=skip,
        limit=page_size,
        filters={"project_id": project_id},
        order_by="created_at",
        descending=True
    )

    # 附加 question_count
    dataset_responses = []
    for d in datasets:
        resp = DatasetResponse.model_validate(d)
        resp_dict = resp.model_dump()
        # 查询该数据集对应的问答对数量
        extra = d.extra_data or {}
        batch_id = extra.get("batch_id")
        if batch_id:
            from uuid import UUID as UUIDType
            try:
                batch_uuid = UUIDType(batch_id) if isinstance(batch_id, str) else batch_id
            except (ValueError, AttributeError):
                batch_uuid = None
            if batch_uuid:
                count = await db.scalar(
                    select(func.count(Question.id)).where(
                        Question.project_id == project_id,
                        Question.batch_id == batch_uuid,
                    )
                )
                resp_dict["question_count"] = count or 0
            else:
                resp_dict["question_count"] = 0
        else:
            resp_dict["question_count"] = 0
        dataset_responses.append(resp_dict)

    return PaginatedResponse.ok(
        items=dataset_responses,
        page=page,
        page_size=page_size,
        total=total
    )


@router.post("", response_model=ApiResponse)
async def create_dataset(
    project_id: UUID,
    dataset: DatasetCreateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create a new dataset"""
    dataset_dict = dataset.model_dump()
    dataset_dict["project_id"] = project_id

    # 统计问答对数量
    extra = dataset_dict.get("extra_data") or {}
    batch_id = extra.get("batch_id")
    question_count = 0
    if batch_id:
        from uuid import UUID as UUIDType
        try:
            batch_uuid = UUIDType(batch_id) if isinstance(batch_id, str) else batch_id
        except (ValueError, AttributeError):
            batch_uuid = None
        if batch_uuid:
            question_count = await db.scalar(
                select(func.count(Question.id)).where(
                    Question.project_id == project_id,
                    Question.batch_id == batch_uuid,
                )
            ) or 0

    db_dataset = Dataset(**dataset_dict)
    db.add(db_dataset)
    await db.commit()
    await db.refresh(db_dataset)

    return ApiResponse.ok(
        data={"id": str(db_dataset.id), "question_count": question_count},
        message="Dataset created successfully"
    )


@router.get("/{dataset_id}", response_model=ApiResponse)
async def get_dataset(
    project_id: UUID,
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get dataset by ID"""
    dataset = await dataset_crud.get(db, dataset_id)
    if not dataset or dataset.project_id != project_id:
        raise NotFoundException("Dataset", dataset_id)

    return ApiResponse.ok(data=DatasetResponse.model_validate(dataset))


@router.delete("/{dataset_id}", response_model=ApiResponse)
async def delete_dataset(
    project_id: UUID,
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete dataset"""
    dataset = await dataset_crud.get(db, dataset_id)
    if not dataset or dataset.project_id != project_id:
        raise NotFoundException("Dataset", dataset_id)

    await dataset_crud.delete(db, dataset_id)
    return ApiResponse.ok(message="Dataset deleted successfully")


class BatchDeleteRequest(BaseModel):
    """批量删除数据集请求"""
    dataset_ids: List[UUID] = Field(..., min_length=1, description="数据集 ID 列表")


@router.post("/batch-delete", response_model=ApiResponse)
async def batch_delete_datasets(
    project_id: UUID,
    request: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量删除数据集"""
    deleted = 0
    not_found = 0
    for dataset_id in request.dataset_ids:
        dataset = await dataset_crud.get(db, dataset_id)
        if dataset and dataset.project_id == project_id:
            await dataset_crud.delete(db, dataset_id)
            deleted += 1
        else:
            not_found += 1

    msg = f"已删除 {deleted} 个数据集"
    if not_found > 0:
        msg += f"，{not_found} 个未找到或不属于当前项目"

    return ApiResponse.ok(data={"deleted": deleted, "not_found": not_found}, message=msg)


@router.post("/{dataset_id}/export")
async def export_dataset(
    project_id: UUID,
    dataset_id: UUID,
    request: ExportRequest,
    db: AsyncSession = Depends(get_db)
):
    """导出数据集：查询问答对 → 按策略划分训练/验证/测试集 → 返回 JSONL 文件流"""
    dataset = await dataset_crud.get(db, dataset_id)
    if not dataset or dataset.project_id != project_id:
        raise NotFoundException("Dataset", dataset_id)

    # 确定要导出的批次
    extra = dataset.extra_data or {}
    batch_id = request.batch_id or extra.get("batch_id")

    if not batch_id:
        raise AppException(message="未指定问答批次，无法导出", code="MISSING_BATCH", status_code=400)

    # 将字符串 batch_id 转为 UUID 对象
    try:
        batch_uuid = UUID(batch_id) if isinstance(batch_id, str) else batch_id
    except (ValueError, AttributeError):
        raise AppException(message="批次ID格式无效", code="INVALID_BATCH_ID", status_code=400)

    # 查询该批次的问答对
    query = (
        select(Question)
        .where(
            Question.project_id == project_id,
            Question.batch_id == batch_uuid,
            Question.answer_status == "completed",
        )
        .order_by(Question.created_at)
    )
    result = await db.execute(query)
    questions = list(result.scalars().all())

    if not questions:
        raise AppException(message="该批次没有已完成的问答对，无法导出", code="NO_DATA", status_code=400)

    # 按策略划分
    # 归一化比例
    total_ratio = request.train_ratio + request.val_ratio + request.test_ratio
    train_r = request.train_ratio / total_ratio
    val_r = request.val_ratio / total_ratio
    test_r = request.test_ratio / total_ratio

    if request.split_strategy == "file":
        train, val, test = _split_by_file(questions, train_r, val_r, test_r, request.seed)
    else:
        train, val, test = _split_random(questions, train_r, val_r, test_r, request.seed)

    # 格式化函数
    format_fn = _FORMAT_FN.get(request.data_format, _qa_to_alpaca)
    meta = {
        "dataset": dataset.name,
        "split_strategy": "随机划分" if request.split_strategy == "random" else "按文件划分",
        "seed": request.seed,
        "train_count": len(train),
        "val_count": len(val),
        "test_count": len(test),
        "file_format": request.file_format,
        "data_format": request.data_format,
        "total_count": len(questions),
    }

    file_format = request.file_format

    # 构建各集合的数据（统一先转成 dict 列表）
    splits_data = {
        "train": [format_fn(q) for q in train],
        "val": [format_fn(q) for q in val],
        "test": [format_fn(q) for q in test],
    }

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        if file_format == "jsonl":
            for split_name, items in splits_data.items():
                lines = [json.dumps(item, ensure_ascii=False) for item in items]
                content = "\n".join(lines) + "\n" if lines else ""
                zf.writestr(f"{split_name}.jsonl", content)

        elif file_format == "json":
            for split_name, items in splits_data.items():
                content = json.dumps(items, ensure_ascii=False, indent=2)
                zf.writestr(f"{split_name}.json", content)

        else:  # excel
            try:
                import openpyxl
            except ImportError:
                raise AppException(message="Excel 导出需要安装 openpyxl 库", code="MISSING_DEP", status_code=500)

            for split_name, items in splits_data.items():
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = split_name
                ws.append(["instruction", "input", "output"])
                for item in items:
                    ws.append([item.get("instruction", ""), item.get("input", ""), item.get("output", "")])
                excel_buffer = io.BytesIO()
                wb.save(excel_buffer)
                zf.writestr(f"{split_name}.xlsx", excel_buffer.getvalue())

        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

    zip_buffer.seek(0)
    filename = f"{dataset.name}.zip"
    encoded_filename = quote(filename)

    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
