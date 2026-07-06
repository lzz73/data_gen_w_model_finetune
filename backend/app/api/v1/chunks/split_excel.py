from typing import List, Optional

def safe_str(value) -> str:
    return str(value).strip() if value is not None else ""

def split_table_to_markdown(
    grid: List[List],
    header_row_end: int,
    header_col_end: int
) -> str:
    """
    将表格转换成 Markdown 格式

    Args:
        grid: Excel 网格数据
        header_row_end: 表头结束行号（数据开始行号）
        header_col_end: 表头结束列号（数据开始列号）

    Returns:
        str: Markdown 表格格式的字符串
    """
    if not grid or not grid[0]:
        return ""

    rows = len(grid)
    cols = len(grid[0])

    # 构建表头
    # 对于多层表头，需要合并表头行的值
    header_cells = []

    # 添加行头列的表头（部门、分组等）
    for c in range(0, header_col_end):
        full_header_parts = []
        for hr in range(0, header_row_end):
            if hr < len(grid) and c < len(grid[hr]):
                h_val = safe_str(grid[hr][c])
                if h_val:
                    full_header_parts.append(h_val)
        header_cells.append(" ".join(full_header_parts) if full_header_parts else f"列{c+1}")

    # 添加数据列的表头
    for c in range(header_col_end, cols):
        full_header_parts = []
        for hr in range(0, header_row_end):
            if hr < len(grid) and c < len(grid[hr]):
                h_val = safe_str(grid[hr][c])
                if h_val:
                    full_header_parts.append(h_val)
        header_cells.append(" ".join(full_header_parts) if full_header_parts else "")

    # 构建 Markdown 表格
    lines = []

    # 表头行
    lines.append("| " + " | ".join(header_cells) + " |")

    # 分隔线
    lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

    # 数据行 - 包含行头列
    for r in range(header_row_end, rows):
        row_cells = []
        # 添加本行的所有列（包括行头列）
        for c in range(0, cols):
            if c < len(grid[r]):
                row_cells.append(safe_str(grid[r][c]))
            else:
                row_cells.append("")
        lines.append("| " + " | ".join(row_cells) + " |")

    return "\n".join(lines)

def split_table_to_structured_texts(
    grid: List[List],
    header_row_end: int,
    header_col_end: int
) -> List[str]:
    """
    将表格按指定行列边界切分为结构化文本。
    按行切片：每行数据合并成一个文本，单元格之间用换行分隔。
    """
    if not grid or not grid[0]:
        return []

    rows = len(grid)
    cols = len(grid[0])

    print(f"[DEBUG] 表格尺寸：{rows}行 x {cols}列")
    print(f"[DEBUG] header_row_end={header_row_end}, header_col_end={header_col_end}")

    # 打印表头行
    print(f"[DEBUG] === 表头行内容 ===")
    for hr in range(0, header_row_end):
        print(f"[DEBUG] 表头行{hr}: {[safe_str(grid[hr][c]) for c in range(cols)]}")

    # 打印数据区域的前几行
    print(f"[DEBUG] === 数据区域前 5 行 ===")
    for r in range(header_row_end, min(header_row_end + 5, rows)):
        print(f"[DEBUG] 数据行{r}: {[safe_str(grid[r][c]) for c in range(cols)]}")

    structured_texts = []

    # 遍历数据区域：[header_row_end, rows)
    for r in range(header_row_end, rows):
        row_lines = []

        # 获取本行的行表头值（左侧的部门/分组，从列 0 到 header_col_end-1）
        row_header_values = []
        for hc in range(0, header_col_end):
            if hc < len(grid[r]):
                h_val = safe_str(grid[r][hc])
                if h_val:
                    row_header_values.append(h_val)
        row_header_value = "".join(row_header_values)
        print(f"[DEBUG] 行{r} 左侧表头值：'{row_header_value}'")

        # 获取列表头（从行 0 到 header_row_end-1 的所有表头行）
        col_header_map = {}
        for c in range(header_col_end, cols):
            full_header_parts = []
            for hr in range(0, header_row_end):
                if hr < len(grid) and c < len(grid[hr]):
                    h_val = safe_str(grid[hr][c])
                    if h_val:
                        full_header_parts.append(h_val)
            col_header_map[c] = "".join(full_header_parts)

        # 遍历本行的所有数据列
        for c in range(header_col_end, cols):
            value = safe_str(grid[r][c])
            if not value:
                continue

            col_header_name = col_header_map.get(c, "")
            line = f"{col_header_name}{row_header_value}{value}"
            row_lines.append(line)

        # 将同一行的所有单元格合并成一个文本
        if row_lines:
            structured_texts.append("\n".join(row_lines))
            print(f"[DEBUG] 行{r} -> 切片{len(structured_texts)} ({len(row_lines)} 条数据)")
        else:
            print(f"[DEBUG] 行{r} 没有生成任何数据（row_lines 为空）")

    print(f"[DEBUG] 最终 structured_texts 长度：{len(structured_texts)}")
    for i, text in enumerate(structured_texts):
        print(f"[DEBUG] === 切片{i+1} ===")
        print(text[:500])

    return structured_texts


def read_excel_and_split(
    grid,
    header_row_end: int,
    header_col_end: int,
) -> List[str]:
    """
    从 Excel 文件读取表格，并调用 split_table_to_structured_texts 进行切分。
    """
    return split_table_to_structured_texts(grid, header_row_end, header_col_end)
