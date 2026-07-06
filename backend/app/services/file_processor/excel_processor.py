"""
Excel/CSV Text Extractor
支持按行切分 Excel 表格，每行数据作为一个独立的语义切片
"""
import asyncio
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
import re


class ExcelProcessor:
    """Extract text from Excel and CSV files"""

    def extract_csv(self, file_path: str) -> str:
        """Extract text from CSV file"""
        for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig', 'latin1']:
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                return self._dataframe_to_text(df)
            except (UnicodeDecodeError, UnicodeError):
                continue
        import chardet
        with open(file_path, 'rb') as f:
            result = chardet.detect(f.read(10000))
            detected_encoding = result.get('encoding', 'utf-8')
        try:
            df = pd.read_csv(file_path, encoding=detected_encoding)
            return self._dataframe_to_text(df)
        except Exception:
            df = pd.read_csv(file_path, encoding='utf-8', errors='ignore')
            return self._dataframe_to_text(df)

    async def extract_csv_async(self, file_path: str) -> str:
        """Extract text from CSV file"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.extract_csv, file_path
        )

    def extract_excel(self, file_path: str) -> str:
        """Extract text from Excel file using markitdown"""
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(file_path)
            return result.text_content
        except Exception:
            return self._extract_excel_fallback(file_path)

    def _extract_excel_fallback(self, file_path: str) -> str:
        """Fallback: use pandas when markitdown fails"""
        sheets = pd.read_excel(file_path, sheet_name=None)
        text_parts = []
        for sheet_name, df in sheets.items():
            text_parts.append(f"=== Sheet: {sheet_name} ===\n")
            text_parts.append(self._dataframe_to_text(df))
        return "\n\n".join(text_parts)

    async def extract_excel_async(self, file_path: str) -> str:
        """Extract text from Excel file"""
        return await asyncio.get_event_loop().run_in_executor(
            None, self.extract_excel, file_path
        )

    def _dataframe_to_text(self, df: pd.DataFrame) -> str:
        """Convert DataFrame to Markdown table format"""
        if df.empty:
            return ""

        lines = []

        # 表头行
        header = "| " + " | ".join(str(col) for col in df.columns) + " |"
        lines.append(header)

        # 分隔线
        separator = "| " + " | ".join("---" for _ in df.columns) + " |"
        lines.append(separator)

        # 数据行
        for _, row in df.iterrows():
            row_line = "| " + " | ".join(str(val) for val in row.values) + " |"
            lines.append(row_line)

        return "\n".join(lines)

    def _fill_merged_cells_down(self, df: pd.DataFrame, col_indices: List[int]) -> pd.DataFrame:
        """
        向下填充合并单元格

        Args:
            df: 原始 DataFrame
            col_indices: 需要填充的列索引列表（如 [0] 表示只填充第一列的合并单元格）

        Returns:
            填充后的 DataFrame
        """
        filled_df = df.copy()
        for col_idx in col_indices:
            if col_idx < len(filled_df.columns):
                filled_df.iloc[:, col_idx] = filled_df.iloc[:, col_idx].ffill()
        return filled_df

    def extract_excel_by_row(
        self,
        file_path: str,
        row_header_cols: Optional[List[int]] = None,
        fill_merged_cells: bool = True
    ) -> List[Dict]:
        """
        按行切分 Excel 表格 - 每行数据作为一个独立的切片

        核心逻辑:
        1. 读取 Excel 文件，识别表格结构
        2. （可选）向下填充合并单元格
        3. 遍历每一行数据行
        4. 将行头（如部门、分组）和列数据（如 Q1 销售额）拼接成语义完整的切片

        切片格式示例（对应你的 Excel）:
        - 切片 1: 技术部 | 前端组 | 2024 年 Q1 销售额：100 | 2024 年 Q1 利润率：20% | 2024 年 Q2 销售额：120 | ...
        - 切片 2: 技术部 | 后端组 | 2024 年 Q1 销售额：150 | 2024 年 Q1 利润率：25% | ...
        - ...

        Args:
            file_path: Excel 文件路径
            row_header_cols: 行头列索引列表（左侧的标题列，如 [0, 1] 表示前两列是部门、分组）
                             如果为 None，自动检测文本列作为行头
            fill_merged_cells: 是否填充合并单元格（默认 True）

        Returns:
            List[Dict] - 每个 Dict 是一个切片:
            {
                "index": int,           # 切片索引
                "content": str,         # 切片内容（行列标题 + 值的拼接）
                "metadata": {
                    "sheet": str,       # Sheet 名称
                    "row": int,         # 原始行号
                    "row_headers": dict, # 行头信息（如 {"部门": "技术部", "分组": "前端组"}）
                    "data": dict        # 数据列信息（如 {"2024 年 Q1 销售额": 100, ...}）
                }
            }
        """
        all_chunks = []
        chunk_index = 0

        try:
            excel_file = pd.ExcelFile(file_path)
            sheet_names = excel_file.sheet_names
        except Exception:
            return all_chunks

        for sheet_name in sheet_names:
            try:
                # 不自动处理表头，原始读取
                df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            except Exception:
                continue

            if df_raw.empty or len(df_raw) < 2:
                continue

            # 分析表格结构
            table_info = self._analyze_table_structure(df_raw, row_header_cols)

            # 填充合并单元格
            if fill_merged_cells and table_info['merged_cols']:
                df_filled = self._fill_merged_cells_down(df_raw, table_info['merged_cols'])
            else:
                df_filled = df_raw.copy()

            # 遍历数据行
            for row_idx in range(table_info['data_start_row'], len(df_filled)):
                row = df_filled.iloc[row_idx]

                # 提取行头信息
                row_headers = {}
                for i, col_idx in enumerate(table_info['row_header_cols']):
                    # 使用列名而不是 "列 1"
                    col_name = table_info['row_header_names'][i] if i < len(table_info['row_header_names']) else f"列{col_idx + 1}"
                    val = row.iloc[col_idx]
                    if pd.notna(val) and str(val).strip():
                        row_headers[col_name] = str(val).strip()

                # 提取数据列信息
                data = {}
                for col_idx, col_name in table_info['data_columns'].items():
                    val = row.iloc[col_idx]
                    if pd.notna(val) and str(val).strip():
                        data[col_name] = str(val).strip()

                # 构建切片内容 - 每个数据点单独一行，格式：列名：值
                content_lines = []

                # 添加行头信息（如部门、分组）
                for key, val in row_headers.items():
                    content_lines.append(f"{key}: {val}")

                # 添加数据列（列名：值）
                for col_name, val in data.items():
                    content_lines.append(f"{col_name}: {val}")

                # 使用换行符连接，每个切片都是自包含的语义单元
                content = "\n".join(content_lines)

                if content.strip():
                    all_chunks.append({
                        "index": chunk_index,
                        "content": content,
                        "metadata": {
                            "sheet": sheet_name,
                            "row": row_idx + 1,
                            "row_headers": row_headers,
                            "data": data
                        }
                    })
                    chunk_index += 1

        return all_chunks

    def _analyze_table_structure(
        self,
        df: pd.DataFrame,
        row_header_cols: Optional[List[int]] = None
    ) -> Dict:
        """
        分析表格结构

        返回:
        {
            'data_start_row': int,       # 数据开始的行号（表头行数）
            'row_header_cols': List[int], # 行头列索引
            'row_header_names': List[str], # 行头列名（如 ["部门", "分组"]）
            'merged_cols': List[int],     # 需要填充的合并单元格列
            'data_columns': Dict[int, str] # 数据列索引 -> 列名
        }
        """
        result = {
            'data_start_row': 1,
            'row_header_cols': [],
            'row_header_names': [],
            'merged_cols': [],
            'data_columns': {}
        }

        # 1. 检测表头行数（处理多层表头）
        data_start_row = self._detect_header_rows(df)
        result['data_start_row'] = data_start_row

        # 2. 构建数据列的复合列名（处理多层表头）
        data_columns = self._build_column_names(df, data_start_row)

        # 3. 检测行头列
        if row_header_cols is not None:
            result['row_header_cols'] = row_header_cols
            result['merged_cols'] = row_header_cols
        else:
            # 自动检测：检查前几列哪些是文本列
            detected = self._detect_row_header_columns(df, data_start_row)
            result['row_header_cols'] = detected
            result['merged_cols'] = detected

        # 4. 构建行头列名（从表头行获取）
        row_header_names = self._build_row_header_names(df, result['row_header_cols'], data_start_row)
        result['row_header_names'] = row_header_names

        # 5. 数据列是除了行头列之外的所有列
        for col_idx in range(len(df.columns)):
            if col_idx not in result['row_header_cols']:
                result['data_columns'][col_idx] = data_columns.get(col_idx, f"列{col_idx + 1}")

        return result

    def _build_row_header_names(
        self,
        df: pd.DataFrame,
        row_header_cols: List[int],
        data_start_row: int
    ) -> List[str]:
        """
        构建行头列名

        逻辑：
        1. 从表头行（数据行前面一行）获取列名
        2. 如果是多层表头，向上查找直到找到非空值
        3. 如果都找不到，使用默认名称
        """
        header_names = []

        for col_idx in row_header_cols:
            name = None

            # 从表头行开始向上查找
            for row_idx in range(data_start_row - 1, -1, -1):
                if col_idx < len(df.iloc[row_idx]):
                    val = df.iloc[row_idx].iloc[col_idx]
                    if pd.notna(val) and str(val).strip():
                        name = str(val).strip()
                        break

            header_names.append(name if name else f"列{col_idx + 1}")

        return header_names

    def _detect_header_rows(self, df: pd.DataFrame) -> int:
        """
        检测表头行数

        检测逻辑:
        1. 检查第一行是否包含年份（如 "2024 年"）
        2. 检查第二行是否包含季度（如 "Q1"）
        3. 检查第三行是否包含指标名（如 "销售额"）

        返回表头行数（1-3）
        """
        if len(df) < 2:
            return 1

        # 检查第一行是否有年份
        first_row = df.iloc[0]
        has_year = any(
            pd.notna(v) and re.match(r'^\d{4}年$', str(v).strip())
            for v in first_row
        )

        if has_year and len(df) >= 2:
            # 检查第二行是否有季度
            second_row = df.iloc[1]
            has_quarter = any(
                pd.notna(v) and re.match(r'^Q\d+$', str(v).strip())
                for v in second_row
            )

            if has_quarter and len(df) >= 3:
                # 检查第三行是否有指标名（销售额、利润率等）
                third_row = df.iloc[2]
                has_metric = any(
                    pd.notna(v) and any(m in str(v).strip() for m in ['销售额', '利润率', '指标', '数量', '金额'])
                    for v in third_row
                )

                if has_metric:
                    # 三层表头
                    return 3
                else:
                    # 只有两层（年份 + 季度/指标混合）
                    return 2
            else:
                # 两层表头
                return 2

        return 1

    def _build_column_names(
        self,
        df: pd.DataFrame,
        data_start_row: int
    ) -> Dict[int, str]:
        """
        构建复合列名（处理多层表头）

        例如：
        - 第一行：2024 年
        - 第二行：Q1
        - 第三行：销售额
        -> 列名："2024 年 Q1 销售额"
        """
        column_names = {}

        if data_start_row == 1:
            # 单层表头，直接使用第一行
            for col_idx in range(len(df.columns)):
                val = df.iloc[0, col_idx]
                column_names[col_idx] = str(val).strip() if pd.notna(val) else f"列{col_idx + 1}"

        elif data_start_row == 2:
            # 两层表头
            row1 = df.iloc[0]  # 年份行
            row2 = df.iloc[1]  # 指标行

            # 追踪当前年份
            current_year = None

            for col_idx in range(len(df.columns)):
                val1 = row1.iloc[col_idx] if col_idx < len(row1) else None
                val2 = row2.iloc[col_idx] if col_idx < len(row2) else None

                # 检查是否是年份
                if pd.notna(val1) and re.match(r'^\d{4}年$', str(val1).strip()):
                    current_year = str(val1).strip()

                # 构建列名
                if pd.notna(val2):
                    val2_str = str(val2).strip()
                    if current_year:
                        column_names[col_idx] = f"{current_year} {val2_str}"
                    else:
                        column_names[col_idx] = val2_str
                else:
                    column_names[col_idx] = current_year if current_year else f"列{col_idx + 1}"

        elif data_start_row == 3:
            # 三层表头
            row1 = df.iloc[0]  # 年份
            row2 = df.iloc[1]  # 季度
            row3 = df.iloc[2]  # 指标

            current_year = None
            current_quarter = None

            for col_idx in range(len(df.columns)):
                val1 = row1.iloc[col_idx] if col_idx < len(row1) else None
                val2 = row2.iloc[col_idx] if col_idx < len(row2) else None
                val3 = row3.iloc[col_idx] if col_idx < len(row3) else None

                # 更新年份
                if pd.notna(val1) and re.match(r'^\d{4}年$', str(val1).strip()):
                    current_year = str(val1).strip()

                # 更新季度
                if pd.notna(val2) and re.match(r'^Q[1-4]$', str(val2).strip()):
                    current_quarter = str(val2).strip()

                # 构建列名
                if pd.notna(val3):
                    val3_str = str(val3).strip()
                    parts = []
                    if current_year:
                        parts.append(current_year)
                    if current_quarter:
                        parts.append(current_quarter)
                    parts.append(val3_str)
                    column_names[col_idx] = " ".join(parts)
                else:
                    column_names[col_idx] = f"列{col_idx + 1}"

        return column_names

    def _detect_row_header_columns(
        self,
        df: pd.DataFrame,
        data_start_row: int
    ) -> List[int]:
        """
        自动检测行头列（左侧的文本标题列）

        检测逻辑：
        1. 检查前 3 列
        2. 如果某列大部分是文本（非数值），则是行头列
        """
        header_cols = []

        for col_idx in range(min(3, len(df.columns))):
            col_data = df.iloc[data_start_row:, col_idx]

            # 统计文本数量
            text_count = sum(
                1 for v in col_data
                if pd.notna(v) and not self._is_numeric_value(v)
            )

            # 如果超过一半是文本，认为是行头列
            if len(col_data) > 0 and text_count > len(col_data) * 0.5:
                header_cols.append(col_idx)

        return header_cols

    def _is_numeric_value(self, value: Any) -> bool:
        """检测值是否是数值（包括百分比）"""
        if pd.isna(value):
            return False
        if isinstance(value, (int, float)):
            return True
        val_str = str(value).strip()
        if val_str.endswith('%'):
            return True
        try:
            float(val_str)
            return True
        except ValueError:
            return False

    def extract_excel_semantic_chunks(self, file_path: str) -> List[str]:
        """
        提取 Excel 为语义完整的切片列表（专为 RAG 优化）

        Args:
            file_path: Excel 文件路径

        Returns:
            List[str] - 每个元素是一个完整的语义切片
        """
        chunks = self.extract_excel_by_row(file_path)
        return [chunk["content"] for chunk in chunks]


async def process_csv(file_path: str) -> str:
    """Process CSV file and return text"""
    processor = ExcelProcessor()
    return await processor.extract_csv_async(file_path)


async def process_excel(file_path: str) -> str:
    """Process Excel file and return text"""
    processor = ExcelProcessor()
    return await processor.extract_excel_async(file_path)
