"""
PDF 处理策略模块
支持策略：default（文本提取）、ocr（EasyOCR）、vision（VLM）
"""

import logging
from pathlib import Path

from .default import default_processing, is_scanned_pdf
from .vision import vision_processing
from .ocr import ocr_processing

logger = logging.getLogger(__name__)

__all__ = [
    'default_processing',
    'ocr_processing',
    'vision_processing',
    'process_pdf',
    'is_scanned_pdf',
]


async def process_pdf(strategy: str, file_path: str, output_path: str, **kwargs):
    """
    PDF 处理策略入口

    Args:
        strategy: 处理策略
            'default' - 文本提取（PyMuPDF4LLM / pdfplumber）
            'ocr'     - EasyOCR 本地识别（适用于扫描件）
            'vision'  - VLM 视觉识别（需 API Key）
        file_path: PDF 文件路径
        output_path: 输出 Markdown 文件路径
        **kwargs: 额外参数（model_info 用于 VLM）

    Returns:
        dict: 处理结果 {'success': bool, 'output_path': str, 'error': str, 'strategy': str}
    """
    strategies = {
        'default': default_processing,
        'ocr': ocr_processing,
        'vision': vision_processing,
    }

    if strategy not in strategies:
        raise ValueError(f"不支持的 PDF 处理策略：{strategy}，可选：default, ocr, vision")

    processor = strategies[strategy]
    return await processor(file_path, output_path, **kwargs)
