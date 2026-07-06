"""
数据集管理 API
提供前端 data-governance/ 和 training/DataManager 页面所需接口
"""
from fastapi import APIRouter, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from typing import Optional
import os
import tempfile
import shutil
from pathlib import Path

from ..services.dataset_service import (
    list_datasets,
    upload_dataset,
    validate_dataset,
    get_dataset_versions,
    load_dataset_data,
    delete_dataset_version,
    get_dashboard_stats,
)

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "dataset_storage"
DATA_DIR.mkdir(parents=True, exist_ok=True)


@router.get("")
def api_list_datasets():
    """获取所有数据集列表（DataManager 页面的表格数据）"""
    return {"code": 0, "data": list_datasets()}


@router.post("/upload")
async def api_upload_dataset(
    file: UploadFile = File(...),
    dataset_name: str = Form(...),
    format: str = Form("jsonl"),
    description: str = Form(""),
    required_fields: str = Form(""),
):
    """
    上传数据集文件并校验

    DataManager.vue 的上传对话框调用此接口
    DataValidate.vue 的校验功能也调用此接口
    """
    # 保存上传文件
    ext = ".jsonl" if format == "jsonl" else ".json"
    save_path = DATA_DIR / f"{dataset_name}_{datetime_now_str()}{ext}"

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    fields = [f.strip() for f in required_fields.split(",") if f.strip()]

    result = upload_dataset(
        file_path=str(save_path),
        dataset_name=dataset_name,
        format_str=format,
        required_fields=fields or None,
        description=description,
    )

    return {"code": 0 if result["success"] else -1, "data": result}


@router.post("/validate")
async def api_validate_dataset(
    file: UploadFile = File(...),
    format: str = Form("jsonl"),
    required_fields: str = Form(""),
):
    """仅校验数据集，不创建版本"""
    ext = ".jsonl" if format == "jsonl" else ".json"
    save_path = DATA_DIR / f"_validate_tmp{ext}"

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    fields = [f.strip() for f in required_fields.split(",") if f.strip()]
    result = validate_dataset(str(save_path), format_str=format, required_fields=fields or None)

    # 清理临时文件
    os.remove(save_path)
    return {"code": 0, "data": result}


@router.get("/{dataset_name}/versions")
def api_get_versions(dataset_name: str):
    """获取数据集的所有版本"""
    return {"code": 0, "data": get_dataset_versions(dataset_name)}


@router.get("/{dataset_name}/data")
def api_load_data(dataset_name: str, version_id: Optional[str] = Query(None)):
    """加载数据集内容（预览）"""
    from ..services.dataset_service import get_manager
    mgr = get_manager()
    if version_id:
        data = load_dataset_data(version_id)
    else:
        versions = mgr.list_versions(dataset_name)
        if versions:
            data = load_dataset_data(versions[0].version_id)
        else:
            data = []
    return {"code": 0, "data": data}


@router.delete("/{version_id}")
def api_delete_version(version_id: str):
    """删除数据集版本"""
    ok = delete_dataset_version(version_id)
    return {"code": 0 if ok else -1, "message": "删除成功" if ok else "删除失败"}


def datetime_now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")
