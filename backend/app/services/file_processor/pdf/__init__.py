"""
PDF 处理策略模块
参考 easy-dataset-main 的 pdf 处理模块实现
"""

from .default import default_processing
from .vision import vision_processing

__all__ = [
    'default_processing',
    'vision_processing',
    'process_pdf'
]


async def process_pdf(strategy: str, file_path: str, output_path: str, **kwargs):
    """
    PDF 处理策略入口

    Args:
        strategy: 处理策略 ('default', 'vision')
        file_path: PDF 文件路径
        output_path: 输出 Markdown 文件路径
        **kwargs: 额外参数

    Returns:
        dict: 处理结果 {'success': bool, 'output_path': str, 'error': str}
    """
    strategies = {
        'default': default_processing,
        'vision': vision_processing,
    }

    if strategy not in strategies:
        raise ValueError(f"不支持的 PDF 处理策略：{strategy}")

    processor = strategies[strategy]
    return await processor(file_path, output_path, **kwargs)
