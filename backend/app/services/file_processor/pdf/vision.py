"""
Vision PDF 处理策略
使用 VLM 模型识别 PDF 内容并生成 Markdown
参考 easy-dataset-main: lib/file/file-process/pdf/vision.js
"""

import asyncio
import base64
from pathlib import Path
from typing import Optional, List


async def vision_processing(
    file_path: str,
    output_path: str,
    model_info: Optional[dict] = None,
    **kwargs
) -> dict:
    """
    Vision PDF 转换策略

    1. 将 PDF 转为图片
    2. 使用 VLM 模型识别图片内容
    3. 生成 Markdown

    Args:
        file_path: PDF 文件路径
        output_path: 输出 Markdown 文件路径
        model_info: 模型配置 {'model_name', 'api_key', 'api_base'}
        **kwargs: 额外参数

    Returns:
        dict: 处理结果
    """
    try:
        # 1. PDF 转图片
        image_paths = await pdf_to_images(file_path, output_path + '_images')

        # 2. 使用 VLM 模型识别
        markdown_content = await recognize_with_vlm(
            image_paths,
            model_info=model_info,
            **kwargs
        )

        # 3. 写入输出文件
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown_content, encoding='utf-8')

        # 4. 清理临时图片
        cleanup_images(image_paths)

        print(f'Vision PDF 转换完成：{output_path}')

        return {
            'success': True,
            'output_path': str(output_path),
            'strategy': 'vision'
        }

    except Exception as e:
        print(f'Vision PDF 转换策略失败：{e}')
        return {
            'success': False,
            'error': str(e),
            'strategy': 'vision'
        }


async def pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 144) -> List[str]:
    """
    将 PDF 转换为图片序列

    使用 pdf2image 或 pymupdf
    """
    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        from pdf2image import convert_from_path

        print(f'将 PDF 转换为图片 (DPI={dpi})...')

        images = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: convert_from_path(pdf_path, dpi=dpi)
        )

        image_paths = []
        for i, image in enumerate(images):
            image_path = Path(output_dir) / f'page_{i + 1}.png'
            image.save(image_path, 'PNG')
            image_paths.append(str(image_path))

        return image_paths

    except ImportError:
        # 备选方案：使用 pymupdf
        try:
            import fitz  # pymupdf

            print(f'使用 pymupdf 将 PDF 转换为图片...')

            doc = fitz.open(pdf_path)
            image_paths = []

            for i in range(len(doc)):
                page = doc[i]
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)

                image_path = Path(output_dir) / f'page_{i + 1}.png'
                pix.save(str(image_path))
                image_paths.append(str(image_path))

            doc.close()
            return image_paths

        except ImportError:
            raise ImportError(
                "需要安装 pdf2image 或 pymupdf:\n"
                "  pip install pdf2image poppler-utils\n"
                "  或\n"
                "  pip install pymupdf"
            )


async def recognize_with_vlm(
    image_paths: List[str],
    model_info: Optional[dict] = None,
    **kwargs
) -> str:
    """
    使用 VLM 模型识别图片内容并生成 Markdown

    支持的模型：
    - GPT-4 Vision
    - Claude-3
    - Qwen-VL
    - 其他支持 vision 的模型
    """
    if not model_info:
        raise ValueError("需要配置 VLM 模型信息 (model_name, api_key, api_base)")

    model_name = model_info.get('model_name', '')
    api_key = model_info.get('api_key', '')
    api_base = model_info.get('api_base', '')

    # 根据模型名称选择处理方式
    if 'claude' in model_name.lower():
        return await recognize_with_claude(image_paths, model_name, api_key, api_base)
    elif 'qwen' in model_name.lower() or 'vl' in model_name.lower():
        return await recognize_with_qwen(image_paths, model_name, api_key, api_base)
    else:
        # 默认使用 OpenAI 兼容 API
        return await recognize_with_openai(image_paths, model_name, api_key, api_base)


async def recognize_with_openai(
    image_paths: List[str],
    model_name: str,
    api_key: str,
    api_base: str,
    **kwargs
) -> str:
    """使用 OpenAI 兼容 API 的 VLM 模型识别"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=api_base)

    # 提示词
    system_prompt = """你是一个专业的文档解析助手。请将 PDF 页面内容转换为格式良好的 Markdown。

要求：
1. 识别并保留文档的标题结构（# 标题 ## 子标题）
2. 识别表格并转换为 Markdown 表格
3. 识别公式并使用 LaTeX 格式
4. 识别代码块并使用 ```language 格式
5. 保留列表结构
6. 如果是图表，用文字描述图表内容
7. 输出纯 Markdown，不要其他说明

请基于提供的图片生成 Markdown 内容："""

    all_content = []

    # 批量处理（避免单次请求图片过多）
    batch_size = 5
    for i in range(0, len(image_paths), batch_size):
        batch_images = image_paths[i:i + batch_size]
        content_parts = []

        for img_path in batch_images:
            with open(img_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_data}"
                }
            })

        # 添加页码信息
        page_num = i // batch_size + 1
        content_parts.insert(0, {
            "type": "text",
            "text": f"第 {page_num} 页:"
        })

        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_parts}
            ],
            max_tokens=4096
        )

        all_content.append(response.choices[0].message.content)

    return '\n\n'.join(all_content)


async def recognize_with_claude(
    image_paths: List[str],
    model_name: str,
    api_key: str,
    api_base: str,
    **kwargs
) -> str:
    """使用 Claude 模型识别"""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key, base_url=api_base)

    system_prompt = """你是一个专业的文档解析助手。请将 PDF 页面内容转换为格式良好的 Markdown。

要求：
1. 识别并保留文档的标题结构（# 标题 ## 子标题）
2. 识别表格并转换为 Markdown 表格
3. 识别公式并使用 LaTeX 格式
4. 识别代码块并使用 ```language 格式
5. 保留列表结构
6. 如果是图表，用文字描述图表内容
7. 输出纯 Markdown，不要其他说明"""

    all_content = []

    # Claude 需要逐个处理
    for i, img_path in enumerate(image_paths):
        with open(img_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        response = await client.messages.create(
            model=model_name,
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": f"这是第 {i + 1} 页，请转换为 Markdown:"
                        }
                    ]
                }
            ]
        )

        all_content.append(response.content[0].text)

    return '\n\n'.join(all_content)


async def recognize_with_qwen(
    image_paths: List[str],
    model_name: str,
    api_key: str,
    api_base: str,
    **kwargs
) -> str:
    """使用 Qwen-VL 模型识别"""
    # Qwen-VL 使用 OpenAI 兼容 API
    return await recognize_with_openai(image_paths, model_name, api_key, api_base)


def cleanup_images(image_paths: List[str]):
    """清理临时图片文件"""
    import os

    for img_path in image_paths:
        try:
            os.remove(img_path)
        except Exception as e:
            print(f'清理图片失败：{e}')

    # 尝试删除目录
    if image_paths:
        try:
            img_dir = Path(image_paths[0]).parent
            img_dir.rmdir()  # 只在目录为空时成功
        except Exception:
            pass
