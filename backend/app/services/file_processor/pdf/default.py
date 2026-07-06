"""
默认 PDF 处理策略
使用 PyMuPDF4LLM 将 PDF 转换为 Markdown（保留标题层级 # ## ###）
降级备选：pdfplumber（不保留标题层级）
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def default_processing(
    file_path: str,
    output_path: str,
    **kwargs
) -> dict:
    """
    默认 PDF 转换策略

    优先使用 PyMuPDF4LLM 转换（保留标题层级），
    若不可用则降级到 pdfplumber（纯文本，无标题标记）

    Args:
        file_path: PDF 文件路径
        output_path: 输出 Markdown 文件路径
        **kwargs: 额外参数

    Returns:
        dict: 处理结果
    """
    try:
        print(f'执行默认 PDF 转换策略：{file_path}')

        # 使用 PyMuPDF4LLM 转换
        loop = asyncio.get_event_loop()
        markdown_content = await loop.run_in_executor(
            None,
            lambda: convert_pdf_to_markdown(file_path)
        )

        # 写入输出文件
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown_content, encoding='utf-8')

        print(f'PDF 转换完成：{output_path}')

        return {
            'success': True,
            'output_path': str(output_path),
            'strategy': 'default'
        }

    except Exception as e:
        print(f'默认 PDF 转换失败：{e}')
        return {
            'success': False,
            'error': str(e),
            'strategy': 'default'
        }


def convert_pdf_to_markdown(
    file_path: str,
    header_threshold: float = 0.0,
    footer_threshold: float = 100.0,
) -> str:
    """
    将 PDF 转换为 Markdown

    优先使用 PyMuPDF4LLM（保留标题层级 # ## ###），
    不可用时降级到 pdfplumber（纯文本提取）

    Args:
        file_path: PDF 文件路径
        header_threshold: 页眉过滤阈值（0-100，表示页面顶部百分比）。
            例如 10 表示过滤顶部 0%~10% 高度区域的文本。0 表示不过滤。
        footer_threshold: 页脚过滤阈值（0-100，表示页面底部百分比）。
            例如 90 表示过滤底部 90%~100% 高度区域的文本。100 表示不过滤。
    """
    # 如果配置了页眉页脚阈值，直接用 pdfplumber（支持坐标过滤）
    if header_threshold > 0 or footer_threshold < 100:
        return _convert_with_pdfplumber(
            file_path,
            header_threshold=header_threshold,
            footer_threshold=footer_threshold,
        )

    # 优先 PyMuPDF4LLM
    try:
        import pymupdf4llm
        md = pymupdf4llm.to_markdown(file_path, page_chunks=False)
        if md and md.strip():
            logger.info(f"PDF 转换成功（PyMuPDF4LLM）：{file_path}")
            return md
    except ImportError:
        logger.warning("pymupdf4llm 未安装，降级到 pdfplumber")
    except Exception as e:
        logger.warning(f"PyMuPDF4LLM 转换失败 ({e})，降级到 pdfplumber")

    # 降级：pdfplumber
    return _convert_with_pdfplumber(file_path)


def _convert_with_pdfplumber(
    file_path: str,
    header_threshold: float = 0.0,
    footer_threshold: float = 100.0,
) -> str:
    """
    使用 pdfplumber 将 PDF 转换为 Markdown（降级方案，不保留标题层级）

    Args:
        file_path: PDF 文件路径
        header_threshold: 页眉过滤阈值（0-100），过滤顶部 N% 高度的文本
        footer_threshold: 页脚过滤阈值（0-100），过滤底部 (100-N)%~100% 的文本
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("需要安装 pymupdf4llm 或 pdfplumber")

    pages_text = []
    use_layout_filter = header_threshold > 0 or footer_threshold < 100

    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            page_content = []
            page_header = f"\n\n--- Page {i + 1} ---\n\n"

            # 提取表格（不受页眉页脚过滤影响）
            tables = page.extract_tables()

            if tables:
                # 文本部分应用坐标过滤
                if use_layout_filter:
                    text_content = _extract_text_filtered(
                        page, header_threshold, footer_threshold
                    )
                else:
                    text_content = page.extract_text() or ""

                for table in tables:
                    if table:
                        md_table = _convert_table_to_markdown(table)
                        if md_table.strip():
                            page_content.append(md_table)

                if text_content.strip():
                    page_content.append(text_content)
            else:
                if use_layout_filter:
                    text_content = _extract_text_filtered(
                        page, header_threshold, footer_threshold
                    )
                else:
                    text_content = page.extract_text() or ""
                if text_content.strip():
                    page_content.append(text_content)

            if page_content:
                pages_text.append(page_header + "\n\n".join(page_content))

    return "\n\n".join(pages_text)


def _extract_text_filtered(
    page,
    header_threshold: float,
    footer_threshold: float,
) -> str:
    """提取页面文本，按 Y 坐标过滤页眉页脚区域。

    Args:
        page: pdfplumber Page 对象
        header_threshold: 页眉过滤阈值（0-100），过滤顶部 N% 高度的文本
        footer_threshold: 页脚过滤阈值（0-100），过滤底部 (100-N)%~100% 的文本
    """
    if not page.height:
        return page.extract_text() or ""

    page_height = page.height
    # header_region_bottom: 页眉区域下边界（从顶部算）
    header_cutoff = page_height * (header_threshold / 100.0)
    # footer_region_top: 页脚区域上边界（从顶部算）
    footer_cutoff = page_height * (footer_threshold / 100.0)

    try:
        # 用 chars 按坐标过滤
        chars = page.chars
        filtered_chars = [
            c for c in chars
            if header_cutoff <= c["top"] <= footer_cutoff
        ]

        if not filtered_chars:
            return ""

        # 按 (top, x0) 排序后拼接成文本
        filtered_chars.sort(key=lambda c: (round(c["top"] / 2), c["x0"]))

        # 重组文本：按行聚合
        lines: list[list[dict]] = []
        current_line: list[dict] = []
        current_top = None
        for c in filtered_chars:
            if current_top is None or abs(c["top"] - current_top) <= 3:
                current_line.append(c)
                current_top = c["top"] if current_top is None else current_top
            else:
                lines.append(current_line)
                current_line = [c]
                current_top = c["top"]
        if current_line:
            lines.append(current_line)

        text_lines = []
        for line in lines:
            line.sort(key=lambda c: c["x0"])
            text_lines.append("".join(c["text"] for c in line))

        return "\n".join(text_lines)

    except Exception as e:
        logger.warning(f"坐标过滤失败，回退普通提取: {e}")
        return page.extract_text() or ""


def _convert_table_to_markdown(table: list) -> str:
    """
    将 pdfplumber 提取的表格转换为 Markdown 格式
    """
    if not table:
        return ""

    # 过滤空行
    table = [row for row in table if any(cell is not None for cell in row)]
    if not table:
        return ""

    lines = []
    num_cols = max(len(row) for row in table)

    for row_idx, row in enumerate(table):
        # 补齐缺失的列
        while len(row) < num_cols:
            row.append("")

        # 清理单元格内容
        cells = []
        for cell in row:
            if cell is None:
                cells.append("")
            else:
                cell_text = str(cell).replace("\n", " ").replace("|", "\\|").strip()
                cells.append(cell_text)

        line = "| " + " | ".join(cells) + " |"
        lines.append(line)

        # 在第一行后添加分隔线（表头分隔线）
        if row_idx == 0:
            separator = "| " + " | ".join(["---"] * num_cols) + " |"
            lines.append(separator)

    return "\n".join(lines)
