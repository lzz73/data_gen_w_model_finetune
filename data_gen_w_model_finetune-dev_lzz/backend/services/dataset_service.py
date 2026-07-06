"""
数据集管理服务层
封装 dataset_manager.py 的功能，提供业务逻辑
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from dataset_manager import (
    DatasetManager, DataFormat, DatasetMetadata, DatasetVersion, ValidationResult
)

# 数据存储路径放在 test/ 目录下
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 全局单例
_mgr: Optional[DatasetManager] = None


def get_manager() -> DatasetManager:
    global _mgr
    if _mgr is None:
        _mgr = DatasetManager(
            db_path=str(BASE_DIR / "dataset_manager.db"),
            storage_dir=str(BASE_DIR / "dataset_storage"),
        )
    return _mgr


def list_datasets() -> list[dict]:
    """列出所有数据集及其最新版本（含校验详情）"""
    mgr = get_manager()
    dataset_names = mgr.list_datasets()
    result = []
    for name in dataset_names:
        versions = mgr.list_versions(name)
        if versions:
            latest = versions[0]
            # 读取上次校验结果
            vinfo = _get_validation_info(latest.version_id)
            result.append({
                "name": name,
                "format": latest.format.value,
                "samples": latest.row_count,
                "version": f"v{latest.version_number}",
                "version_id": latest.version_id,
                "fields": latest.fields,
                "created_at": latest.created_at,
                "hash": latest.file_hash[:12],
                "validation": vinfo,
            })
    return result


def _save_validation_info(version_id: str, is_valid: bool, results: list[dict]):
    """存储校验结果到 sidecar 文件"""
    import json
    info = {
        "success": is_valid,
        "blocking_count": len([r for r in results if r.get("level") == "blocking"]),
        "warning_count": len([r for r in results if r.get("level") == "warning"]),
        "errors": [
            r for r in results if r.get("level") == "blocking"
        ],
        "warnings": [
            r for r in results if r.get("level") == "warning"
        ],
    }
    p = BASE_DIR / "dataset_storage" / f"{version_id}_validation.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(info, ensure_ascii=False, indent=2))


def _get_validation_info(version_id: str) -> dict:
    """读取校验结果，无记录时返回未知状态"""
    import json
    p = BASE_DIR / "dataset_storage" / f"{version_id}_validation.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"success": None, "blocking_count": 0, "warning_count": 0, "errors": [], "warnings": []}


def upload_dataset(
    file_path: str,
    dataset_name: str,
    format_str: str = "jsonl",
    required_fields: Optional[list[str]] = None,
    description: str = "",
) -> dict:
    """上传并校验数据集"""
    mgr = get_manager()
    fmt = DataFormat.JSONL if format_str == "jsonl" else DataFormat.JSON

    metadata = DatasetMetadata(
        name=dataset_name,
        description=description,
        required_fields=required_fields or [],
    )
    success, msg, version, results = mgr.upload(
        file_path=file_path,
        dataset_name=dataset_name,
        format=fmt,
        metadata=metadata,
        description=description,
    )

    vr_list = [
        {"level": r.level, "code": r.code, "message": r.message, "row": r.row, "field": r.field}
        for r in results
    ]
    if version:
        _save_validation_info(version.version_id, success, vr_list)
        # 自动注册到 llamaFactory 的 dataset_info.json
        _sync_to_llamafactory(file_path, dataset_name, fmt)

    return {
        "success": success,
        "message": msg,
        "version": {
            "version_id": version.version_id,
            "version_number": version.version_number,
            "row_count": version.row_count,
            "fields": version.fields,
            "created_at": version.created_at,
        } if version else None,
        "validation_results": vr_list,
    }


def validate_dataset(
    file_path: str,
    format_str: str = "jsonl",
    required_fields: Optional[list[str]] = None,
) -> dict:
    """仅校验数据集（不创建版本）"""
    mgr = get_manager()
    fmt = DataFormat.JSONL if format_str == "jsonl" else DataFormat.JSON
    metadata = DatasetMetadata(
        name="_validate_",
        required_fields=required_fields or [],
    )
    from dataset_manager import DatasetValidator
    validator = DatasetValidator(metadata)
    is_valid, results = validator.validate(file_path, fmt)

    return {
        "is_valid": is_valid,
        "total_errors": len([r for r in results if r.level == "blocking"]),
        "total_warnings": len([r for r in results if r.level == "warning"]),
        "results": [
            {"level": r.level, "code": r.code, "message": r.message, "row": r.row, "field": r.field}
            for r in results
        ],
    }


def get_dataset_versions(dataset_name: str) -> list[dict]:
    """获取数据集所有版本"""
    mgr = get_manager()
    versions = mgr.list_versions(dataset_name)
    return [
        {
            "version_id": v.version_id,
            "version_number": v.version_number,
            "row_count": v.row_count,
            "fields": v.fields,
            "format": v.format.value,
            "hash": v.file_hash[:16],
            "created_at": v.created_at,
        }
        for v in versions
    ]


def load_dataset_data(version_id: str) -> list[dict]:
    """加载数据集实际内容"""
    mgr = get_manager()
    return mgr.load_data(version_id) or []


def delete_dataset_version(version_id: str) -> bool:
    """删除数据集版本（简化：仅从数据库移除记录）"""
    import sqlite3
    try:
        conn = sqlite3.connect(str(BASE_DIR / "dataset_manager.db"))
        conn.execute("DELETE FROM dataset_versions WHERE version_id = ?", (version_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_dashboard_stats() -> dict:
    """获取仪表盘统计数据"""
    mgr = get_manager()
    datasets = mgr.list_datasets()
    total_samples = 0
    for name in datasets:
        versions = mgr.list_versions(name)
        if versions:
            total_samples += versions[0].row_count
    return {
        "total_datasets": len(datasets),
        "total_samples": total_samples,
    }


def _sync_to_llamafactory(file_path: str, dataset_name: str, fmt: DataFormat):
    """
    将上传的数据集自动注册到 llamaFactory 的 data/dataset_info.json
    - 复制数据文件到 data/ 目录
    - 自动检测数据类型（SFT/DPO/ShareGPT等）
    - 在 dataset_info.json 中添加正确格式的条目
    """
    import json, shutil
    data_dir = BASE_DIR / "data"
    info_file = data_dir / "dataset_info.json"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 复制数据文件
    ext = ".jsonl" if fmt == DataFormat.JSONL else ".json"
    dest = data_dir / f"{dataset_name}{ext}"
    shutil.copy2(file_path, dest)

    # 读取前 3 条数据，自动判断类型
    samples = []
    with open(file_path, "r", encoding="utf-8") as f:
        if fmt == DataFormat.JSONL:
            for i, line in enumerate(f):
                if i >= 3:
                    break
                try:
                    samples.append(json.loads(line.strip()))
                except Exception:
                    pass
        else:
            data = json.load(f)
            samples = data[:3] if isinstance(data, list) else [data]

    entry = {"file_name": f"{dataset_name}{ext}"}

    if samples:
        keys = set(samples[0].keys())
        # DPO 格式: {prompt, chosen, rejected}
        if keys >= {"prompt", "chosen", "rejected"}:
            entry["ranking"] = True
            print(f"[Dataset] 检测到 DPO 格式")
        # KTO 格式: {prompt, completion, label}
        elif keys >= {"prompt", "completion"} and "label" in keys:
            entry["ranking"] = True
            print(f"[Dataset] 检测到 KTO 格式")
        # ShareGPT 格式: {conversations, ...}
        elif "conversations" in keys:
            entry["formatting"] = "sharegpt"
            entry["columns"] = {"messages": "conversations"}
            # 检测是否有 tools 字段
            if "tools" in keys:
                entry["columns"]["tools"] = "tools"
            print(f"[Dataset] 检测到 ShareGPT 格式")
        # messages 格式
        elif "messages" in keys:
            entry["formatting"] = "sharegpt"
            entry["columns"] = {"messages": "messages"}
            print(f"[Dataset] 检测到 messages 格式")
        # SFT 格式: {instruction, output}
        elif keys >= {"instruction", "output"}:
            print(f"[Dataset] 检测到 SFT (alpaca) 格式")
        else:
            print(f"[Dataset] 检测到未知格式，字段: {', '.join(sorted(keys))}")

    # 更新 dataset_info.json
    info = {}
    if info_file.exists():
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    info[dataset_name] = entry
    info_file.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Dataset] 已注册 '{dataset_name}' -> {info_file}")


def register_all_datasets():
    """一键同步所有已上传数据集到 llamaFactory（用于批量修复）"""
    import json, shutil
    mgr = get_manager()
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    info_file = data_dir / "dataset_info.json"

    info = {}
    if info_file.exists():
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    for name in mgr.list_datasets():
        versions = mgr.list_versions(name)
        if not versions:
            continue
        v = versions[0]
        ext = ".jsonl" if v.format == DataFormat.JSONL else ".json"
        dest = data_dir / f"{name}{ext}"
        if not dest.exists():
            shutil.copy2(v.file_path, dest)
        info[name] = {"file_name": f"{name}{ext}"}

    info_file.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Dataset] 已注册 {len(info)} 个数据集")
    return list(info.keys())
