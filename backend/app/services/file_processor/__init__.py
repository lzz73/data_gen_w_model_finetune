"""
File Processing Services
参考 easy-dataset-main 的文件处理模块实现

支持的文件类型和转换策略:
- PDF: default (pdfplumber), vision (VLM 模型)
- DOCX: mammoth + markdownify
- XLSX/CSV: pandas 读取
- MD/TXT: 直接读取
"""

from .pdf import process_pdf
from .docx_processor import process_docx
from .excel_processor import process_csv, process_excel, ExcelProcessor


__all__ = [
    'process_pdf',
    'process_docx',
    'process_csv',
    'process_excel',
    'process_file'
]


async def process_file(
    file_path: str,
    output_path: str,
    file_type: str,
    strategy: str = 'default',
    **kwargs
) -> dict:
    """
    文件处理入口

    Args:
        file_path: 输入文件路径
        output_path: 输出 Markdown 文件路径
        file_type: 文件类型 ('pdf', 'docx', 'xlsx', 'csv', 'md', 'txt')
        strategy: 处理策略 (仅 PDF 支持：'default', 'vision')
        **kwargs: 额外参数

    Returns:
        dict: 处理结果

    参考 easy-dataset-main:
    - lib/file/file-process/pdf/index.js
    - lib/file/file-process/get-content.js
    """
    file_type = file_type.lower()

    if file_type == 'pdf':
        return await process_pdf(strategy, file_path, output_path, **kwargs)

    elif file_type == 'docx':
        return await process_docx(file_path, output_path, **kwargs)

    elif file_type == 'csv':
        from pathlib import Path
        content = await process_csv(file_path)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding='utf-8')
        return {
            'success': True,
            'output_path': str(output_path),
            'format': 'csv'
        }

    elif file_type in ('xlsx', 'xls'):
        from pathlib import Path

        # 检查是否按行切分模式
        split_by_row = kwargs.get('split_by_row', False)

        if split_by_row:
            # 按行切分模式：每个行数据作为一个独立的 chunk 文件
            processor = ExcelProcessor()
            chunks = processor.extract_excel_by_row(file_path)

            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            # 保存每个 chunk 到单独的文件
            chunk_paths = []
            for chunk in chunks:
                chunk_file = output.parent / f"{output.stem}_chunk_{chunk['index']}{output.suffix}"
                chunk_file.write_text(chunk['content'], encoding='utf-8')
                chunk_paths.append(str(chunk_file))

            return {
                'success': True,
                'output_path': str(output_path),
                'chunk_paths': chunk_paths,
                'format': 'xlsx_by_row',
                'chunks_count': len(chunks)
            }
        else:
            # 传统模式：整个表格作为一个文件
            content = await process_excel(file_path)
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content, encoding='utf-8')
            return {
                'success': True,
                'output_path': str(output_path),
                'format': 'xlsx'
            }

    elif file_type in ('md', 'markdown', 'txt'):
        # 直接复制内容
        from pathlib import Path

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        # 尝试多种编码读取
        content = None
        for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            # 如果所有编码都失败，使用 binary 方式读取并尝试解码
            with open(file_path, 'rb') as f:
                content = f.read().decode('utf-8', errors='ignore')

        # 写入目标文件
        output.write_text(content, encoding='utf-8')

        return {
            'success': True,
            'output_path': str(output_path),
            'format': file_type
        }

    else:
        # 其他类型尝试使用 MarkItDown
        try:
            from markitdown import MarkItDown

            markitdown = MarkItDown()
            result = markitdown.convert(file_path)

            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result.text_content, encoding='utf-8')

            return {
                'success': True,
                'output_path': str(output_path),
                'format': 'markitdown'
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'不支持的文件类型：{file_type}, {str(e)}'
            }
