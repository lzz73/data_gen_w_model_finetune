"""
Field Analyzer Service

自动提取 Excel/CSV 文件的字段元信息：
- 字段名（列名）
- 数据类型（string, integer, float, date, boolean）
- 样本值（前 3 个非空值）
- 缺失率
- 默认角色（feature）
"""
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def _infer_column_type(series: pd.Series) -> str:
    """推断列的数据类型"""
    # 去掉空值
    non_null = series.dropna()
    if len(non_null) == 0:
        return "string"

    # 检查是否全是布尔
    unique_vals = set(str(v).strip().lower() for v in non_null if pd.notna(v))
    if unique_vals <= {"true", "false", "是", "否", "1", "0", "yes", "no"}:
        return "boolean"

    # 检查 pandas 原生类型
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "date"

    # 检查是否全是数值
    numeric_count = 0
    for val in non_null:
        if isinstance(val, (int, float)):
            numeric_count += 1
        elif isinstance(val, str):
            s = val.strip().rstrip("%").replace(",", "")
            try:
                float(s)
                numeric_count += 1
            except ValueError:
                pass

    if numeric_count / len(non_null) > 0.8:
        # 区分 integer vs float
        has_float = False
        for val in non_null:
            if isinstance(val, float) and not val == int(val):
                has_float = True
                break
            if isinstance(val, str):
                s = val.strip().rstrip("%").replace(",", "")
                try:
                    f = float(s)
                    if f != int(f):
                        has_float = True
                        break
                except ValueError:
                    pass
        return "float" if has_float else "integer"

    # 检查是否是日期字符串
    date_count = 0
    for val in non_null.head(20):
        if isinstance(val, str):
            s = val.strip()
            # 常见日期格式
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%d/%m/%Y"]:
                try:
                    datetime.strptime(s, fmt)
                    date_count += 1
                    break
                except ValueError:
                    continue
    if len(non_null.head(20)) > 0 and date_count / len(non_null.head(20)) > 0.5:
        return "date"

    return "string"


def _get_sample_values(series: pd.Series, n: int = 3) -> List[str]:
    """获取前 n 个非空样本值"""
    samples = []
    for val in series.dropna():
        if len(samples) >= n:
            break
        s = str(val).strip()
        if s:
            samples.append(s)
    return samples


def _compute_missing_rate(series: pd.Series) -> float:
    """计算缺失率"""
    total = len(series)
    if total == 0:
        return 0.0
    missing = series.isna().sum()
    # 也把空字符串算作缺失
    empty_str = (series.astype(str).str.strip() == "").sum()
    return round((missing + empty_str) / total, 4)


def _analyze_dataframe(df: pd.DataFrame, header_rows: int = 1) -> List[Dict[str, Any]]:
    """分析 DataFrame 的字段信息

    Args:
        df: 原始 DataFrame（含表头行）
        header_rows: 表头行数（1-3）

    Returns:
        字段信息列表
    """
    if df.empty or len(df) <= header_rows:
        return []

    # 数据区域
    data_df = df.iloc[header_rows:].reset_index(drop=True)

    # 列名：如果 header_rows == 1，用 df.iloc[0] 作为列名
    # 否则用复合列名（简化处理，直接用第一行）
    if header_rows == 1:
        col_names = [str(v).strip() if pd.notna(v) else f"列{i+1}" for i, v in enumerate(df.iloc[0])]
    else:
        # 多层表头：拼接所有表头行
        col_names = []
        for col_idx in range(len(df.columns)):
            parts = []
            for row_idx in range(header_rows):
                if col_idx < len(df.iloc[row_idx]):
                    val = df.iloc[row_idx].iloc[col_idx]
                    if pd.notna(val) and str(val).strip():
                        parts.append(str(val).strip())
            col_names.append(" ".join(parts) if parts else f"列{col_idx+1}")

    fields = []
    for col_idx in range(len(data_df.columns)):
        col_series = data_df.iloc[:, col_idx]
        name = col_names[col_idx] if col_idx < len(col_names) else f"列{col_idx+1}"

        field = {
            "name": name,
            "type": _infer_column_type(col_series),
            "sample": _get_sample_values(col_series),
            "missing_rate": _compute_missing_rate(col_series),
            "role": "feature",  # 默认都是 feature，用户后续可改
            "desensitize": False,
        }
        fields.append(field)

    return fields


def extract_field_schema(file_path: str, file_type: str) -> Dict[str, Any]:
    """提取文件的字段元信息

    Args:
        file_path: 文件路径
        file_type: 文件类型 (xlsx, xls, csv)

    Returns:
        {
            "sheets": [
                {
                    "name": "Sheet1",
                    "header_row_count": 1,
                    "data_row_count": 100,
                    "fields": [...]
                }
            ],
            "total_rows": 100,
            "fields": [...]  # 扁平化的字段列表（用于存储到 field_schema）
        }
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    if file_type == "csv":
        return _extract_csv_schema(file_path)
    else:
        return _extract_excel_schema(file_path)


def _extract_csv_schema(file_path: str) -> Dict[str, Any]:
    """提取 CSV 文件的字段信息"""
    # 多编码读取
    df = None
    for encoding in ["utf-8", "gbk", "gb2312", "utf-8-sig", "latin1"]:
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if df is None:
        try:
            import chardet
            with open(file_path, "rb") as f:
                result = chardet.detect(f.read(10000))
            detected_encoding = result.get("encoding", "utf-8")
            df = pd.read_csv(file_path, encoding=detected_encoding)
        except Exception:
            df = pd.read_csv(file_path, encoding="utf-8", errors="ignore")

    if df.empty:
        return {"sheets": [], "total_rows": 0, "fields": []}

    # CSV 第一行就是表头，pandas 已经处理了
    fields = []
    for col_name in df.columns:
        col_series = df[col_name]
        field = {
            "name": str(col_name),
            "type": _infer_column_type(col_series),
            "sample": _get_sample_values(col_series),
            "missing_rate": _compute_missing_rate(col_series),
            "role": "feature",
            "desensitize": False,
        }
        fields.append(field)

    data_row_count = len(df)

    return {
        "sheets": [{
            "name": "CSV",
            "header_row_count": 1,
            "data_row_count": data_row_count,
            "fields": fields,
        }],
        "total_rows": data_row_count,
        "fields": fields,  # 扁平化存储
    }


def _extract_excel_schema(file_path: str) -> Dict[str, Any]:
    """提取 Excel 文件的字段信息"""
    try:
        excel_file = pd.ExcelFile(file_path)
        sheet_names = excel_file.sheet_names
    except Exception as e:
        raise ValueError(f"无法读取 Excel 文件: {str(e)}")

    all_sheets = []
    all_fields = []
    total_rows = 0

    for sheet_name in sheet_names:
        try:
            # 读取原始数据（不设 header，保留表头行）
            df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception:
            continue

        if df_raw.empty or len(df_raw) < 2:
            continue

        # 检测表头行数
        header_rows = _detect_header_rows(df_raw)

        # 分析字段
        fields = _analyze_dataframe(df_raw, header_rows)
        data_row_count = len(df_raw) - header_rows

        sheet_info = {
            "name": sheet_name,
            "header_row_count": header_rows,
            "data_row_count": data_row_count,
            "fields": fields,
        }
        all_sheets.append(sheet_info)
        all_fields.extend(fields)
        total_rows += data_row_count

    return {
        "sheets": all_sheets,
        "total_rows": total_rows,
        "fields": all_fields,  # 扁平化存储
    }


def _detect_header_rows(df: pd.DataFrame) -> int:
    """检测表头行数

    复用 ExcelProcessor 的逻辑：
    - 检查第一行是否有年份
    - 检查第二行是否有季度
    - 检查第三行是否有指标名
    """
    import re

    if len(df) < 2:
        return 1

    # 检查第一行是否有年份
    first_row = df.iloc[0]
    has_year = any(
        pd.notna(v) and re.match(r"^\d{4}年?$", str(v).strip())
        for v in first_row
    )

    if has_year and len(df) >= 2:
        second_row = df.iloc[1]
        has_quarter = any(
            pd.notna(v) and re.match(r"^Q\d+$", str(v).strip())
            for v in second_row
        )

        if has_quarter and len(df) >= 3:
            third_row = df.iloc[2]
            has_metric = any(
                pd.notna(v) and any(m in str(v).strip() for m in ["销售额", "利润率", "指标", "数量", "金额"])
                for v in third_row
            )
            return 3 if has_metric else 2
        else:
            return 2

    return 1


async def extract_field_schema_async(file_path: str, file_type: str) -> Dict[str, Any]:
    """异步版本的字段提取"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, extract_field_schema, file_path, file_type
    )


def handle_missing_values(
    df: pd.DataFrame,
    field_schema: list[dict[str, Any]],
) -> pd.DataFrame:
    """根据字段配置处理缺失值。

    Args:
        df: 原始 DataFrame
        field_schema: 字段配置列表，每个字段含 missing_strategy 和 fill_value

    Returns:
        处理后的 DataFrame

    策略:
        - ignore: 不处理（默认）
        - drop_row: 删除该字段有缺失值的行
        - fill_mode: 用众数填充
        - fill_default: 用 fill_value 填充
    """
    if df.empty or not field_schema:
        return df

    # Build field name → strategy map
    strategy_map: dict[str, dict[str, Any]] = {}
    for field in field_schema:
        name = field.get("name", "")
        strategy = field.get("missing_strategy", "ignore")
        fill_value = field.get("fill_value")
        if name and strategy != "ignore":
            strategy_map[name] = {
                "strategy": strategy,
                "fill_value": fill_value,
            }

    if not strategy_map:
        return df

    result_df = df.copy()

    for col_name, config in strategy_map.items():
        if col_name not in result_df.columns:
            continue

        strategy = config["strategy"]
        col = result_df[col_name]

        # Find rows with missing values (NaN or empty string)
        is_missing = col.isna() | (col.astype(str).str.strip() == "")

        if not is_missing.any():
            continue

        if strategy == "drop_row":
            result_df = result_df[~is_missing]

        elif strategy == "fill_mode":
            # Mode: most frequent non-null value
            non_null = col.dropna()
            non_null = non_null[non_null.astype(str).str.strip() != ""]
            if len(non_null) > 0:
                mode_val = non_null.mode().iloc[0]
                result_df.loc[is_missing, col_name] = mode_val

        elif strategy == "fill_default":
            fill_val = config.get("fill_value", "")
            if fill_val is not None:
                result_df.loc[is_missing, col_name] = fill_val

    result_df = result_df.reset_index(drop=True)
    return result_df
