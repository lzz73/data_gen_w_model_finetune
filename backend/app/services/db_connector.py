"""
数据库连接服务

支持 MySQL / PostgreSQL / SQLite 数据库直连，提取表结构和数据。
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pandas as pd
from sqlalchemy import create_engine, inspect, text

logger = logging.getLogger(__name__)


def build_db_url(
    db_type: str,
    host: str,
    port: Optional[int],
    user: str,
    password: str,
    database: str,
) -> str:
    """根据数据库类型构建连接 URL。

    Args:
        db_type: 数据库类型 (mysql, postgresql, sqlite)
        host: 主机地址
        port: 端口号
        user: 用户名
        password: 密码
        database: 数据库名

    Returns:
        SQLAlchemy 连接 URL
    """
    if db_type == "sqlite":
        return f"sqlite:///{database}"

    if db_type == "mysql":
        actual_port = port or 3306
        return f"mysql+pymysql://{user}:{password}@{host}:{actual_port}/{database}?charset=utf8mb4"

    if db_type == "postgresql":
        actual_port = port or 5432
        return f"postgresql+psycopg2://{user}:{password}@{host}:{actual_port}/{database}"

    raise ValueError(f"不支持的数据库类型: {db_type}")


def test_connection(db_url: str) -> Dict[str, Any]:
    """测试数据库连接。

    Returns:
        {"success": True/False, "message": "..."}
    """
    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return {"success": True, "message": "连接成功"}
    except Exception as e:
        logger.warning(f"数据库连接失败: {e}")
        return {"success": False, "message": str(e)}


def list_tables(db_url: str) -> List[Dict[str, Any]]:
    """获取数据库中所有表的信息。

    Returns:
        [{"name": "table1", "row_count": 100, "columns": [...]}, ...]
    """
    engine = create_engine(db_url)
    inspector = inspect(engine)

    tables = []
    for table_name in inspector.get_table_names():
        try:
            columns = inspector.get_columns(table_name)
            col_info = [
                {
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": col.get("nullable", True),
                }
                for col in columns
            ]

            # 获取行数估算
            row_count = 0
            try:
                with engine.connect() as conn:
                    result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                    row = result.fetchone()
                    row_count = row[0] if row else 0
            except Exception:
                # 某些表可能无权限
                pass

            tables.append({
                "name": table_name,
                "row_count": row_count,
                "columns": col_info,
            })
        except Exception as e:
            logger.warning(f"获取表 {table_name} 信息失败: {e}")
            continue

    engine.dispose()
    return tables


def extract_table_to_csv(
    db_url: str,
    table_name: str,
    output_dir: str,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """从数据库中提取表数据并保存为 CSV 文件。

    Args:
        db_url: 数据库连接 URL
        table_name: 表名
        output_dir: 输出目录
        limit: 最大行数限制

    Returns:
        {"file_path": "...", "row_count": N, "columns": [...]}
    """
    engine = create_engine(db_url)

    query = f'SELECT * FROM "{table_name}"'
    if limit:
        query += f" LIMIT {limit}"

    df = pd.read_sql(query, engine)
    engine.dispose()

    if df.empty:
        return {
            "file_path": "",
            "row_count": 0,
            "columns": [],
        }

    # 保存为 CSV
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_filename = f"{table_name}_{uuid4().hex[:8]}.csv"
    csv_path = output_path / csv_filename
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # 提取字段信息（复用 field_analyzer 逻辑）
    from app.services.field_analyzer import extract_field_schema
    field_info = extract_field_schema(str(csv_path), "csv")

    return {
        "file_path": str(csv_path),
        "row_count": len(df),
        "columns": field_info.get("fields", []),
    }


def extract_table_preview(
    db_url: str,
    table_name: str,
    sample_rows: int = 5,
) -> Dict[str, Any]:
    """预览表数据（仅读取少量行）。

    Args:
        db_url: 数据库连接 URL
        table_name: 表名
        sample_rows: 预览行数

    Returns:
        {"columns": [...], "rows": [...], "total_count": N}
    """
    engine = create_engine(db_url)

    # 获取总行数
    with engine.connect() as conn:
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        total_count = result.fetchone()[0]

    # 读取预览数据
    df = pd.read_sql(
        f'SELECT * FROM "{table_name}" LIMIT {sample_rows}',
        engine,
    )
    engine.dispose()

    columns = list(df.columns)
    rows = df.values.tolist()

    return {
        "columns": columns,
        "rows": rows,
        "total_count": total_count,
    }
