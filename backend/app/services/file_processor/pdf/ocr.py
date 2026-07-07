"""
OCR PDF 处理策略
使用 EasyOCR 本地引擎识别 PDF 页面内容并生成 Markdown
适用于扫描件 PDF（图片型，无文本层）
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

# EasyOCR Reader 单例（避免重复初始化）
_ocr_reader = None


def _get_ocr_reader(lang: list = None):
    """获取 EasyOCR Reader 单例（懒加载）"""
    global _ocr_reader
    if lang is None:
        lang = ['ch_sim', 'en']
    if _ocr_reader is None:
        try:
            import easyocr
            _ocr_reader = easyocr.Reader(lang, gpu=False)
            logger.info("EasyOCR 引擎初始化成功")
        except ImportError:
            raise ImportError(
                "EasyOCR 未安装，请执行：\n"
                "  pip install easyocr"
            )
        except Exception as e:
            logger.error(f"EasyOCR 初始化失败：{type(e).__name__}: {e}")
            raise RuntimeError(f"EasyOCR 初始化失败：{type(e).__name__}: {e}")
    return _ocr_reader


async def ocr_processing(
    file_path: str,
    output_path: str,
    **kwargs
) -> dict:
    """
    EasyOCR PDF 转换策略

    1. 将 PDF 转为图片（复用 vision.py 的 pdf_to_images）
    2. EasyOCR 逐页识别
    3. 每页作为一个独立切片输出（用 Markdown 二级标题分隔）
       这样表格等内容不会被截断，且可按页查看

    Args:
        file_path: PDF 文件路径
        output_path: 输出 Markdown 文件路径
        **kwargs: 额外参数

    Returns:
        dict: 处理结果
    """
    try:
        print(f'执行 OCR PDF 转换策略：{file_path}')

        # 1. PDF 转图片
        from .vision import pdf_to_images, cleanup_images
        image_paths = await pdf_to_images(file_path, output_path + '_images')

        # 2. OCR 识别
        markdown_content = await ocr_images(image_paths)

        # 3. 写入输出文件
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown_content, encoding='utf-8')

        # 4. 清理临时图片
        cleanup_images(image_paths)

        print(f'OCR PDF 转换完成：{output_path}')
        return {
            'success': True,
            'output_path': str(output_path),
            'strategy': 'ocr'
        }

    except ImportError as e:
        logger.warning(f"EasyOCR 不可用：{e}")
        return {
            'success': False,
            'error': str(e),
            'strategy': 'ocr'
        }
    except Exception as e:
        logger.error(f"OCR PDF 转换失败：{e}")
        return {
            'success': False,
            'error': str(e),
            'strategy': 'ocr'
        }


async def ocr_images(image_paths: List[str], lang: list = None) -> str:
    """
    使用 EasyOCR 逐页识别图片内容

    每页输出一个 ## 二级标题，配合 markdown_structure 分割器
    可以按页自动切片，表格等内容不会被截断

    Args:
        image_paths: 图片路径列表
        lang: OCR 语言列表，默认 ['ch_sim', 'en']（简体中文+英文）

    Returns:
        str: 拼接后的 Markdown 内容
    """
    if lang is None:
        lang = ['ch_sim', 'en']
    loop = asyncio.get_event_loop()
    reader = _get_ocr_reader(lang=lang)

    all_pages = []
    for i, img_path in enumerate(image_paths):
        # EasyOCR 识别（CPU 密集，放线程池）
        result = await loop.run_in_executor(
            None,
            lambda path=img_path: reader.readtext(path, detail=0)
        )

        # EasyOCR readtext(detail=0) 返回 [text1, text2, ...]
        page_lines = [text.strip() for text in result if text and text.strip()]

        if page_lines:
            # 每页用 ## 二级标题，markdown_structure 会按此切片
            page_content = f"## 第 {i + 1} 页\n\n" + "\n".join(page_lines)
            all_pages.append(page_content)
        else:
            logger.warning(f"OCR 第 {i + 1} 页未识别到文本")

    if not all_pages:
        return ""

    return "\n\n".join(all_pages)


def is_ocr_available() -> bool:
    """检查 EasyOCR 是否可用"""
    try:
        import easyocr
        return True
    except ImportError:
        return False
