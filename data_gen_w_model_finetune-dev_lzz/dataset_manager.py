"""
数据集管理模块
支持 JSON/JSONL 格式，提供存储、校验和版本管理功能
"""
from __future__ import annotations


import json
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


class DataFormat(Enum):
    JSON = "json"
    JSONL = "jsonl"


@dataclass
class ValidationLevel:
    BLOCKING = "blocking"      # 阻断性问题
    WARNING = "warning"        # 警告性问题


@dataclass
class ValidationResult:
    level: ValidationLevel
    code: str
    message: str
    row: Optional[int] = None
    field: Optional[str] = None


@dataclass
class DatasetVersion:
    version_id: str
    version_number: int
    created_at: str
    file_path: str
    file_hash: str
    format: DataFormat
    row_count: int
    fields: list[str]
    model_versions: list[str] = field(default_factory=list)


@dataclass
class DatasetMetadata:
    name: str
    description: str = ""
    required_fields: list[str] = field(default_factory=list)
    min_rows: int = 10
    max_duplicate_ratio: float = 0.1


class DatasetValidator:
    """数据集校验器"""

    def __init__(self, metadata: DatasetMetadata):
        self.metadata = metadata
        self.results: list[ValidationResult] = []

    def validate(self, file_path: str, format: DataFormat) -> tuple[bool, list[ValidationResult]]:
        self.results = []
        data = self._load_data(file_path, format)
        if data is None:
            return False, self.results

        # 第一层校验：格式合法性和必填字段完整性（阻断）
        self._validate_format(data, format)
        self._validate_required_fields(data)
        self._validate_row_count(data)

        # 第二层校验：数据质量问题（不阻断）
        self._check_duplicate_ratio(data)
        self._check_consecutive_duplicates(data)
        self._check_water_plugging(data)

        blocking_errors = [r for r in self.results if r.level == ValidationLevel.BLOCKING]
        return len(blocking_errors) == 0, self.results

    def _load_data(self, file_path: str, format: DataFormat) -> Optional[list[dict]]:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if format == DataFormat.JSON:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = [data]
                else:  # JSONL
                    data = []
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            self.results.append(ValidationResult(
                                level=ValidationLevel.BLOCKING,
                                code="E001",
                                message=f"JSONL 格式错误（第 {line_num} 行）: {e}",
                                row=line_num
                            ))
                            return None
            return data
        except Exception as e:
            self.results.append(ValidationResult(
                level=ValidationLevel.BLOCKING,
                code="E000",
                message=f"文件读取失败: {e}"
            ))
            return None

    def _validate_format(self, data: list[dict], format: DataFormat):
        for i, row in enumerate(data, 1):
            if not isinstance(row, dict):
                self.results.append(ValidationResult(
                    level=ValidationLevel.BLOCKING,
                    code="E002",
                    message=f"第 {i} 行格式错误：期望 JSON 对象",
                    row=i
                ))

    def _validate_required_fields(self, data: list[dict]):
        if not self.metadata.required_fields:
            return
        for i, row in enumerate(data, 1):
            missing = [f for f in self.metadata.required_fields if f not in row]
            if missing:
                self.results.append(ValidationResult(
                    level=ValidationLevel.BLOCKING,
                    code="E003",
                    message=f"第 {i} 行缺少必填字段: {', '.join(missing)}",
                    row=i,
                    field=", ".join(missing)
                ))

    def _validate_row_count(self, data: list[dict]):
        if len(data) < self.metadata.min_rows:
            self.results.append(ValidationResult(
                level=ValidationLevel.WARNING,
                code="W001",
                message=f"数据量偏少（{len(data)} 行），建议至少 {self.metadata.min_rows} 行"
            ))

    def _check_duplicate_ratio(self, data: list[dict]):
        if not data:
            return
        texts = [json.dumps(row, sort_keys=True, ensure_ascii=False) for row in data]
        unique_texts = set(texts)
        ratio = (len(texts) - len(unique_texts)) / len(texts)
        if ratio > self.metadata.max_duplicate_ratio:
            self.results.append(ValidationResult(
                level=ValidationLevel.WARNING,
                code="W002",
                message=f"重复数据比例过高（{ratio:.1%}），建议清理"
            ))

    def _check_consecutive_duplicates(self, data: list[dict]):
        if len(data) < 3:
            return
        consecutive_count = 1
        for i in range(1, len(data)):
            if data[i] == data[i-1]:
                consecutive_count += 1
                if consecutive_count >= 3:
                    self.results.append(ValidationResult(
                        level=ValidationLevel.WARNING,
                        code="W003",
                        message=f"发现 {consecutive_count} 条连续重复数据（第 {i-2} 至 {i} 行）",
                        row=i-2
                    ))
            else:
                consecutive_count = 1

    def _check_water_plugging(self, data: list[dict]):
        if len(data) < 10:
            return
        texts = [json.dumps(row, sort_keys=True, ensure_ascii=False) for row in data]
        unique_count = len(set(texts))
        # 简单检测：如果唯一值比例低于 20%，可能是灌水数据
        if unique_count / len(texts) < 0.2:
            self.results.append(ValidationResult(
                level=ValidationLevel.WARNING,
                code="W004",
                message=f"疑似灌水数据：{unique_count} 条唯一记录 / {len(data)} 条总数"
            ))


class DatasetVersionManager:
    """数据集版本管理器"""

    def __init__(self, db_path: str, storage_dir: str):
        self.db_path = db_path
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dataset_versions (
                    version_id TEXT PRIMARY KEY,
                    version_number INTEGER NOT NULL,
                    dataset_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    format TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    fields TEXT NOT NULL,
                    description TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_dataset_refs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_version_id TEXT NOT NULL,
                    dataset_version_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(model_version_id, dataset_version_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dataset_name
                ON dataset_versions(dataset_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_version
                ON model_dataset_refs(model_version_id)
            """)

    def _compute_hash(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_next_version_number(self, dataset_name: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT MAX(version_number) FROM dataset_versions WHERE dataset_name = ?",
                (dataset_name,)
            )
            result = cursor.fetchone()[0]
            return (result or 0) + 1

    def _save_dataset_file(self, source_path: str, version_id: str) -> str:
        dest_path = self.storage_dir / f"{version_id}.jsonl"
        with open(source_path, 'rb') as src, open(dest_path, 'wb') as dst:
            dst.write(src.read())
        return str(dest_path)

    def create_version(
        self,
        dataset_name: str,
        file_path: str,
        format: DataFormat,
        description: str = ""
    ) -> DatasetVersion:
        version_number = self._get_next_version_number(dataset_name)
        version_id = f"{dataset_name}_v{version_number}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        file_hash = self._compute_hash(file_path)
        saved_path = self._save_dataset_file(file_path, version_id)

        # 读取数据信息
        with open(file_path, 'r', encoding='utf-8') as f:
            if format == DataFormat.JSON:
                data = json.load(f)
                if not isinstance(data, list):
                    data = [data]
            else:
                data = []
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))

        fields = list(set().union(*[d.keys() for d in data if isinstance(d, dict)]))

        version = DatasetVersion(
            version_id=version_id,
            version_number=version_number,
            created_at=datetime.now().isoformat(),
            file_path=saved_path,
            file_hash=file_hash,
            format=format,
            row_count=len(data),
            fields=fields
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO dataset_versions
                (version_id, version_number, dataset_name, created_at, file_path,
                 file_hash, format, row_count, fields, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                version.version_id,
                version.version_number,
                dataset_name,
                version.created_at,
                version.file_path,
                version.file_hash,
                version.format.value,
                version.row_count,
                json.dumps(version.fields),
                description
            ))

        return version

    def get_versions(self, dataset_name: str) -> list[DatasetVersion]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT version_id, version_number, created_at, file_path,
                       file_hash, format, row_count, fields, description
                FROM dataset_versions
                WHERE dataset_name = ?
                ORDER BY version_number DESC
            """, (dataset_name,))
            rows = cursor.fetchall()

        versions = []
        for row in rows:
            model_refs = self._get_model_refs(row[0])
            versions.append(DatasetVersion(
                version_id=row[0],
                version_number=row[1],
                created_at=row[2],
                file_path=row[3],
                file_hash=row[4],
                format=DataFormat(row[5]),
                row_count=row[6],
                fields=json.loads(row[7]),
                model_versions=model_refs
            ))
        return versions

    def get_version(self, version_id: str) -> Optional[DatasetVersion]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT version_id, version_number, created_at, file_path,
                       file_hash, format, row_count, fields
                FROM dataset_versions WHERE version_id = ?
            """, (version_id,))
            row = cursor.fetchone()
            if not row:
                return None
            model_refs = self._get_model_refs(row[0])
            return DatasetVersion(
                version_id=row[0],
                version_number=row[1],
                created_at=row[2],
                file_path=row[3],
                file_hash=row[4],
                format=DataFormat(row[5]),
                row_count=row[6],
                fields=json.loads(row[7]),
                model_versions=model_refs
            )

    def _get_model_refs(self, version_id: str) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT model_version_id FROM model_dataset_refs WHERE dataset_version_id = ?",
                (version_id,)
            )
            return [r[0] for r in cursor.fetchall()]

    def link_model_version(self, model_version_id: str, dataset_version_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO model_dataset_refs
                (model_version_id, dataset_version_id, created_at)
                VALUES (?, ?, ?)
            """, (model_version_id, dataset_version_id, datetime.now().isoformat()))

    def get_datasets(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT DISTINCT dataset_name FROM dataset_versions ORDER BY dataset_name"
            )
            return [r[0] for r in cursor.fetchall()]

    def load_data(self, version_id: str) -> Optional[list[dict]]:
        version = self.get_version(version_id)
        if not version:
            return None
        try:
            with open(version.file_path, 'r', encoding='utf-8') as f:
                if version.format == DataFormat.JSONL:
                    return [json.loads(line) for line in f if line.strip()]
                else:
                    data = json.load(f)
                    return data if isinstance(data, list) else [data]
        except Exception:
            return None


class DatasetManager:
    """数据集管理主类"""

    def __init__(
        self,
        db_path: str = "dataset_manager.db",
        storage_dir: str = "dataset_storage"
    ):
        self.version_manager = DatasetVersionManager(db_path, storage_dir)

    def upload(
        self,
        file_path: str,
        dataset_name: str,
        format: DataFormat,
        metadata: Optional[DatasetMetadata] = None,
        description: str = ""
    ) -> tuple[bool, str, Optional[DatasetVersion], list[ValidationResult]]:
        """
        上传数据集
        返回: (是否成功, 消息, 版本信息, 校验结果)
        """
        # 默认元数据
        if metadata is None:
            metadata = DatasetMetadata(name=dataset_name)

        # 校验
        validator = DatasetValidator(metadata)
        is_valid, results = validator.validate(file_path, format)

        blocking_errors = [r for r in results if r.level == ValidationLevel.BLOCKING]
        warnings = [r for r in results if r.level == ValidationLevel.WARNING]

        if blocking_errors:
            return False, "校验失败，存在阻断性问题", None, results

        # 创建版本
        version = self.version_manager.create_version(
            dataset_name=dataset_name,
            file_path=file_path,
            format=format,
            description=description
        )

        msg = f"上传成功"
        if warnings:
            msg += f"（{len(warnings)} 条警告）"

        return True, msg, version, results

    def list_datasets(self) -> list[str]:
        return self.version_manager.get_datasets()

    def list_versions(self, dataset_name: str) -> list[DatasetVersion]:
        return self.version_manager.get_versions(dataset_name)

    def get_version(self, version_id: str) -> Optional[DatasetVersion]:
        return self.version_manager.get_version(version_id)

    def link_model(self, model_version_id: str, dataset_version_id: str):
        self.version_manager.link_model_version(model_version_id, dataset_version_id)

    def load_data(self, version_id: str) -> Optional[list[dict]]:
        return self.version_manager.load_data(version_id)


if __name__ == "__main__":
    # 使用示例
    manager = DatasetManager()

    # 定义数据集元数据
    metadata = DatasetMetadata(
        name="train_data",
        description="训练数据集",
        required_fields=["instruction", "output"],
        min_rows=10,
        max_duplicate_ratio=0.1
    )

    # 上传数据集（JSONL 格式）
    success, msg, version, results = manager.upload(
        file_path="train.jsonl",
        dataset_name="my_dataset",
        format=DataFormat.JSONL,
        metadata=metadata
    )

    print(f"结果: {msg}")
    if version:
        print(f"版本: {version.version_id}")
        print(f"记录数: {version.row_count}")
    if results:
        print("\n校验结果:")
        for r in results:
            print(f"  [{r.level.value}] {r.code}: {r.message}")