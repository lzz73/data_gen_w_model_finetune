"""
Text Splitter — 基于 mistune AST 的 Markdown 结构化切片
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter
import mistune

logger = logging.getLogger(__name__)


# ============================================================
# Markdown 结构化切片的数据结构
# ============================================================

@dataclass
class ContentBlock:
    """原子内容块 — 不可再分的语义单元"""
    block_type: str    # "paragraph" | "table" | "code_block" | "list" | "thematic_break"
    raw_text: str      # 原始 markdown 文本
    char_count: int = 0

    def __post_init__(self):
        if self.char_count == 0:
            self.char_count = len(self.raw_text)


@dataclass
class HeadingNode:
    """标题树节点 — 表示一个标题及其下属内容"""
    level: int                              # 标题级别 (0=虚拟根, 1-6=实际标题)
    title: str                              # 标题文本
    heading_path: str                       # 完整路径，如 "第一章 > 1.1 概述"
    content_blocks: List[ContentBlock] = field(default_factory=list)  # 此标题直接下属的原子内容块
    children: List['HeadingNode'] = field(default_factory=list)       # 子标题节点
    char_count: int = 0                     # 递归总字符数


class TextSplitter:
    """Base text splitter"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> List[Dict]:
        """Split text into chunks"""
        raise NotImplementedError


class RecursiveTextSplitter(TextSplitter):
    """Recursive character text splitter using langchain"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50, separators: List[str] = None):
        super().__init__(chunk_size, overlap)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=separators or [
                "\n\n", "\n", ". ", " ", ",", ""
            ]
        )

    def split(self, text: str) -> List[Dict]:
        """Split text recursively"""
        chunks = self.splitter.split_text(text)
        result = []
        for i, chunk in enumerate(chunks):
            result.append({
                "index": i,
                "content": chunk.strip(),
                "word_count": len(chunk.split())
            })
        return result


# ============================================================
# MarkdownStructureSplitter — 基于标题层级树的真正结构化切片
# ============================================================

class MarkdownStructureSplitter(TextSplitter):
    """
    基于标题层级树的 Markdown 结构化切片 — 纯按结构切，不接受 chunk_size

    核心思路：
    1. 用 mistune 解析 markdown AST，正确识别标题/表格/代码块/列表
    2. 构建 HeadingNode 标题树，标题是唯一的切分边界
    3. 每个标题节点整块输出，无论多长都不截断
    4. 同父同级的小节点允许合并，减少碎片化

    保证：
    - 不同标题下的内容绝不混到同一个 chunk
    - 表格、代码块、列表不会被从中间截断
    - 代码块中的 # 不会被误识别为标题
    - 内容永远不会被按字数硬切
    """

    def __init__(self, llm_config: dict = None, custom_header_patterns: Optional[List[str]] = None, custom_footer_patterns: Optional[List[str]] = None, **kwargs):
        # 不使用基类的 chunk_size/overlap，忽略传入值
        # 传一个占位值给基类避免报错
        super().__init__(chunk_size=0, overlap=0)
        self.llm_config = llm_config
        self.custom_header_patterns = custom_header_patterns or []
        self.custom_footer_patterns = custom_footer_patterns or []

    # ============================================================
    # 1. mistune AST 解析
    # ============================================================

    def _parse_to_ast(self, text: str) -> list:
        """使用 mistune 解析 markdown，返回 token 列表"""
        md = mistune.create_markdown(renderer=None, plugins=['table', 'strikethrough'])
        tokens, _state = md.parse(text)
        return tokens

    def _extract_heading_text(self, token: dict) -> str:
        """从 heading token 的 inline children 中提取纯文本标题"""
        parts = []
        for child in token.get('children', []):
            if child.get('type') == 'text':
                parts.append(child.get('raw', ''))
            elif child.get('type') == 'codespan':
                parts.append(child.get('raw', ''))
        return ' '.join(parts).strip()

    # ============================================================
    # 2. 从源文本构建标题树
    # ============================================================

    def _build_heading_tree(self, text: str) -> HeadingNode:
        """
        解析 markdown 文本，构建标题层级树。

        策略：逐行扫描源文本，同时用 mistune tokens 做结构标注，
        避免 # in code block 误识别。
        """
        tokens = self._parse_to_ast(text)
        lines = text.split('\n')

        # ---- Phase 1: 从 mistune tokens 获取结构标注 ----
        # 标记代码块行范围
        code_block_ranges = []  # [(start_line, end_line), ...]
        in_code_fence = False
        fence_start = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('```') and not in_code_fence:
                in_code_fence = True
                fence_start = i
            elif stripped.startswith('```') and in_code_fence:
                code_block_ranges.append((fence_start, i))
                in_code_fence = False

        # 从 mistune tokens 提取标题信息（不受代码块干扰）
        mistune_headings = []  # [{level, title}]
        for t in tokens:
            if t.get('type') == 'heading':
                level = t.get('attrs', {}).get('level', 1) if t.get('attrs') else 1
                title = self._extract_heading_text(t)
                mistune_headings.append({'level': level, 'title': title})

        # ---- Phase 2: 逐行扫描源文本，用 mistune 标注辅助 ----
        blocks = self._scan_blocks(lines, code_block_ranges, mistune_headings)

        # ---- Phase 3: 将 blocks 组织为标题树 ----
        root = HeadingNode(level=0, title='', heading_path='')
        stack = [root]
        current_heading = root

        heading_idx = 0  # mistune_headings 指针

        for block in blocks:
            if block['is_heading']:
                # 用 mistune 的标题信息（避免代码块误识别）
                if heading_idx < len(mistune_headings):
                    h = mistune_headings[heading_idx]
                    level = h['level']
                    title = h['title']
                    heading_idx += 1
                else:
                    level = block.get('level', 1)
                    title = block['heading_text']

                # 弹栈找到父节点
                while len(stack) > 1 and stack[-1].level >= level:
                    stack.pop()
                parent = stack[-1]

                # 构建路径
                heading_path = f"{parent.heading_path} > {title}" if parent.heading_path else title

                node = HeadingNode(
                    level=level,
                    title=title,
                    heading_path=heading_path,
                    content_blocks=[],
                    children=[]
                )
                parent.children.append(node)
                stack.append(node)
                current_heading = node
            else:
                # 内容块，附加到当前标题节点
                cb = ContentBlock(
                    block_type=block['block_type'],
                    raw_text=block['raw_text'],
                )
                current_heading.content_blocks.append(cb)

        # 计算字符数
        self._compute_char_counts(root)
        return root

    def _scan_blocks(self, lines: List[str], code_block_ranges: list,
                     mistune_headings: list) -> List[dict]:
        """
        逐行扫描源文本，将内容分组为块。

        块类型:
        - heading: 标题行
        - code_block: 围栏代码块
        - table: 管道表格
        - list: 列表块
        - paragraph: 普通段落

        空行作为块分隔符。
        """
        blocks = []
        current_lines = []
        current_type = None  # 'paragraph' | 'table' | 'list' | 'code_block'
        in_code = False
        code_start = -1

        # 构建 code_block 行集合（快速查找）
        code_line_set = set()
        for start, end in code_block_ranges:
            for i in range(start, end + 1):
                code_line_set.add(i)

        def flush_current():
            nonlocal current_lines, current_type
            if not current_lines:
                return
            raw = '\n'.join(current_lines)
            blocks.append({
                'is_heading': False,
                'block_type': current_type or 'paragraph',
                'raw_text': raw,
            })
            current_lines = []
            current_type = None

        heading_re = re.compile(r'^(#{1,6})\s+(.+)$')
        list_item_re = re.compile(
            r'^(?:[-*+]\s+|\d+\.\s+|[一二三四五六七八九十]+[、.]\s+|\([一二三四五六七八九十\d]+\)\s+)'
        )
        table_line_re = re.compile(r'^\s*\|')

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # ---- 代码块处理 ----
            if i in code_line_set and not in_code:
                flush_current()
                in_code = True
                code_start = i
                current_type = 'code_block'
                current_lines.append(line)
                i += 1
                continue
            elif in_code:
                current_lines.append(line)
                if stripped.startswith('```') and i != code_start and i in code_line_set:
                    in_code = False
                    flush_current()
                elif i not in code_line_set:
                    in_code = False
                    flush_current()
                i += 1
                continue

            # ---- 空行 ----
            if not stripped:
                flush_current()
                i += 1
                continue

            # ---- 标题行 ----
            heading_match = heading_re.match(stripped)
            if heading_match:
                flush_current()
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                blocks.append({
                    'is_heading': True,
                    'level': level,
                    'heading_text': title,
                    'raw_text': stripped,
                })
                i += 1
                continue

            # ---- 判断当前行类型 ----
            is_table_line = bool(table_line_re.match(stripped))
            is_list_line = bool(list_item_re.match(stripped))

            if is_table_line:
                line_type = 'table'
            elif is_list_line:
                line_type = 'list'
            else:
                line_type = 'paragraph'

            # 连续同类型的行合并为一个块
            if current_type is not None and current_type != line_type:
                flush_current()
            current_type = line_type
            current_lines.append(line)
            i += 1

        # 刷新最后的块
        flush_current()

        # 合并连续的小段落
        blocks = self._merge_small_paragraphs(blocks)

        return blocks

    def _merge_small_paragraphs(self, blocks: List[dict]) -> List[dict]:
        """
        合并连续的段落块。

        将相邻的 paragraph 块合并为一个，减少碎片化。
        不能跨 heading/table/code_block/list 合并。
        """
        if not blocks:
            return blocks

        merged = []
        i = 0
        while i < len(blocks):
            block = blocks[i]
            if block['is_heading'] or block['block_type'] != 'paragraph':
                merged.append(block)
                i += 1
                continue

            # 合并所有连续的 paragraph 块
            current_text = block['raw_text']
            j = i + 1
            while j < len(blocks):
                next_block = blocks[j]
                if next_block['is_heading'] or next_block['block_type'] != 'paragraph':
                    break
                current_text += '\n\n' + next_block['raw_text']
                j += 1

            merged.append({
                'is_heading': False,
                'block_type': 'paragraph',
                'raw_text': current_text,
            })
            i = j

        return merged

    def _compute_char_counts(self, node: HeadingNode) -> int:
        """递归计算每个节点的总字符数"""
        total = sum(b.char_count for b in node.content_blocks)
        for child in node.children:
            total += self._compute_char_counts(child)
        node.char_count = total
        return total

    # ============================================================
    # 3. 递归树切分
    # ============================================================

    def _split_tree(self, node: HeadingNode) -> List[dict]:
        """
        递归地将标题树切分为 chunk 列表。

        规则（纯结构，不按字数截断）:
        1. 叶节点（无子标题）→ 按内容类型拆分：表格单独 chunk，其余合在一起
        2. 内部节点 → 先输出直接内容（同样拆分表格），再递归处理子节点
        3. 子节点中同父同级的小节点允许合并
        4. 永远不把不同标题节点的内容混到同一 chunk
        5. 表格永远单独作为一个 chunk，不和正文混在一起
        """
        results = []

        if not node.children:
            # ---- 叶节点 ----
            if not node.content_blocks:
                return results
            results.extend(self._split_node_content(node))
        else:
            # ---- 内部节点（有子标题）----
            if node.content_blocks:
                results.extend(self._split_node_content(node))

            # 处理子节点 — 同父同级小节点合并
            results.extend(self._split_children_with_merge(node))

        return results

    def _split_node_content(self, node: HeadingNode) -> List[dict]:
        """
        将一个节点的内容块拆分为 chunk 列表。

        规则:
        - 表格（table 类型）→ 每个表格单独一个 chunk
        - 非表格内容 → 合并为一个 chunk
        - 如果只有表格没有其他内容，不生成空的非表格 chunk
        """
        results = []
        non_table_blocks = []
        table_index = 0

        for block in node.content_blocks:
            if block.block_type == 'table':
                # 先把之前积累的非表格内容输出
                if non_table_blocks:
                    text = self._join_blocks(non_table_blocks)
                    results.append(self._make_chunk(
                        heading_path=node.heading_path,
                        content=text,
                        include_heading=node.level > 0,
                        heading_level=node.level,
                        heading_title=node.title,
                    ))
                    non_table_blocks = []

                # 表格单独 chunk
                table_index += 1
                table_name = f"{node.heading_path} - 表格{table_index}" if node.heading_path else f"表格{table_index}"
                results.append(self._make_chunk(
                    heading_path=table_name,
                    content=block.raw_text,
                    include_heading=False,
                ))
            else:
                non_table_blocks.append(block)

        # 输出剩余的非表格内容
        if non_table_blocks:
            text = self._join_blocks(non_table_blocks)
            results.append(self._make_chunk(
                heading_path=node.heading_path,
                content=text,
                include_heading=node.level > 0,
                heading_level=node.level,
                heading_title=node.title,
            ))

        return results

    def _split_children_with_merge(self, parent: HeadingNode) -> List[dict]:
        """
        处理父节点的子节点，同父同级的小节点允许合并。

        合并规则（纯结构，不按字数判断）:
        - 仅合并连续的同级节点
        - 有子标题的节点不参与合并（它们自身有结构）
        - 无子标题的叶节点参与合并
        - 合并后的 name 为 "父 > 子1 / 子2 / 子3"
        - 合并时仍会拆出表格单独 chunk
        """
        results = []
        merge_group = []

        def flush_merge():
            nonlocal merge_group
            if not merge_group:
                return
            if len(merge_group) == 1:
                results.extend(self._split_tree(merge_group[0]))
            else:
                names = [n.title for n in merge_group]
                if ' > ' in merge_group[0].heading_path:
                    parent_path = merge_group[0].heading_path.rsplit(' > ', 1)[0]
                    combined_name = f"{parent_path} > {' / '.join(names)}"
                else:
                    combined_name = ' / '.join(names)

                # 逐节点拆分：表格单独 chunk，非表格内容合并
                table_idx = 0
                non_table_parts = []

                for n in merge_group:
                    heading_prefix = f"{'#' * n.level} {n.title}\n\n" if n.level > 0 else ""
                    for block in n.content_blocks:
                        if block.block_type == 'table':
                            # 先输出已积累的非表格内容
                            if non_table_parts:
                                results.append(self._make_chunk(
                                    heading_path=combined_name,
                                    content='\n\n'.join(non_table_parts),
                                    include_heading=False,
                                ))
                                non_table_parts = []
                            # 表格单独 chunk
                            table_idx += 1
                            table_name = f"{combined_name} - 表格{table_idx}"
                            results.append(self._make_chunk(
                                heading_path=table_name,
                                content=block.raw_text,
                                include_heading=False,
                            ))
                        else:
                            non_table_parts.append(heading_prefix + block.raw_text)
                            heading_prefix = ""  # 只在第一个 block 前加标题

                # 输出剩余的非表格内容
                if non_table_parts:
                    results.append(self._make_chunk(
                        heading_path=combined_name,
                        content='\n\n'.join(non_table_parts),
                        include_heading=False,
                    ))
            merge_group = []

        for child in parent.children:
            if child.char_count == 0 and not child.children:
                continue

            # 有子标题的节点：先刷新合并组，再单独处理
            if child.children:
                flush_merge()
                results.extend(self._split_tree(child))
                continue

            # 叶节点：尝试加入合并组（同级别才合并）
            can_merge = (
                not merge_group or child.level == merge_group[0].level
            )

            if can_merge:
                merge_group.append(child)
            else:
                flush_merge()
                merge_group.append(child)

        flush_merge()
        return results

    # ============================================================
    # 4. 辅助方法
    # ============================================================

    def _join_blocks(self, blocks: List[ContentBlock]) -> str:
        """将多个 ContentBlock 拼接为字符串"""
        return '\n\n'.join(b.raw_text for b in blocks if b.raw_text.strip())

    def _make_chunk(self, heading_path: str, content: str,
                    include_heading: bool = False,
                    heading_level: int = 0, heading_title: str = '') -> dict:
        """生成一个 chunk dict"""
        if include_heading and heading_level > 0 and heading_title:
            content = f"{'#' * heading_level} {heading_title}\n\n{content}"

        name = heading_path

        section_for_summary = {'content': content, 'is_toc': False}
        summary = self._generate_summary(section_for_summary)

        return {
            'name': name,
            'summary': summary,
            'content': content.strip(),
            'word_count': len(content.split()),
        }

    def _make_chunk_from_blocks(self, node: HeadingNode,
                                blocks: List[ContentBlock]) -> dict:
        """从 ContentBlock 列表生成 chunk"""
        content = self._join_blocks(blocks)
        return self._make_chunk(
            heading_path=node.heading_path,
            content=content,
            include_heading=node.level > 0,
            heading_level=node.level,
            heading_title=node.title,
        )

    # ============================================================
    # 6. 保留的旧方法（页眉页脚清理、TOC 提取、摘要生成）
    # ============================================================

    def _remove_header_footer(self, text: str, custom_header_patterns: Optional[List[str]] = None, custom_footer_patterns: Optional[List[str]] = None) -> str:
        """
        清理页眉页脚内容

        移除模式:
        1. 页码标记："第 X 页 共 Y 页"
        2. 页眉分隔线："--- Page X ---"
        3. 商密标记："商密【中】"、"商密【外】"
        4. 重复的文件编号、发布日期等
        5. 自定义页眉关键词（项目级配置）
        6. 自定义页脚关键词（项目级配置）
        """
        lines = text.split('\n')
        cleaned_lines = []
        skip_next_empty = False

        for line in lines:
            stripped = line.strip()

            if re.match(r'^第\s*\d+\s*页\s*共\s*\d+\s*页\s*$', stripped):
                skip_next_empty = True
                continue
            if re.match(r'^---+\s*Page\s*\d+\s*---+$', stripped, re.IGNORECASE):
                skip_next_empty = True
                continue
            if re.match(r'^商密【[内外中]】\s*$', stripped):
                skip_next_empty = True
                continue
            if re.match(r'^文件编号\s*$', stripped) or re.match(r'^YG-CMMI-\w+-\w+\d+\s*$', stripped):
                skip_next_empty = True
                continue
            if re.match(r'^发布日期\s*$', stripped) or re.match(r'^\d{4}-\d{2}-\d{2}\s*$', stripped):
                skip_next_empty = True
                continue
            if re.match(r'^现行版本\s*$', stripped) or re.match(r'^V?\d+\.\d+\s*$', stripped):
                skip_next_empty = True
                continue
            if re.match(r'^页\s*次\s*$', stripped):
                skip_next_empty = True
                continue
            # 自定义页眉关键词过滤
            if custom_header_patterns:
                for pattern in custom_header_patterns:
                    if pattern in stripped or (re.search(pattern, stripped) if not pattern.isalnum() else False):
                        skip_next_empty = True
                        break
                if skip_next_empty:
                    continue
            # 自定义页脚关键词过滤
            if custom_footer_patterns:
                for pattern in custom_footer_patterns:
                    if pattern in stripped or (re.search(pattern, stripped) if not pattern.isalnum() else False):
                        skip_next_empty = True
                        break
                if skip_next_empty:
                    continue

            if not stripped and skip_next_empty:
                continue

            skip_next_empty = False
            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def _extract_toc_chunk(self, text: str) -> Optional[tuple]:
        """
        提取文档目录作为单独的 chunk - 智能识别各种目录格式

        支持的目录格式:
        1. 标准 Markdown 目录 (带链接)
        2. 纯文本目录
        3. 表格形式目录
        4. 多级缩进目录
        5. 带省略号分隔的目录
        6. "目    录"（带空格/Tab）格式

        返回: (chunk_dict, toc_start, toc_end) 或 None
        """
        toc_patterns = [
            r'^#{1,3}\s*目录\s*$',
            r'^#{1,3}\s*目录\s*\n',
            r'^#{1,3}\s*Table of Contents\s*$',
            r'^#{1,3}\s*Table of Contents\s*\n',
            r'^#{1,3}\s*TOC\s*$',
            r'^#{1,3}\s*TOC\s*\n',
            r'^目 [\s　]+ 录\s*$',
            r'^目 [\s　]+ 录\s*\n',
            r'^目录\s*$',
            r'^目录\s*\n',
        ]

        for pattern in toc_patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                toc_start = match.start()

                heading_match = re.match(r'^(#{0,3})', match.group().strip(), re.IGNORECASE)
                if heading_match and heading_match.group(1):
                    toc_level = len(heading_match.group(1))
                else:
                    toc_level = 2

                remaining_text = text[match.end():]

                # 找目录结束位置：
                # 目录区域 = 目录标题到下一个任何标题之前
                # 因为目录标题后面的内容（表格、页码等）都是目录的一部分，
                # 直到出现任何新标题就表示正文开始了。
                # 注意：需要排除目录区域内部可能出现的子标题（如目录里的"附件"等），
                # 所以优先用 toc_end_patterns 匹配"第X章"等明确的正文开始标记。
                next_any_heading = re.search(
                    r'^#{1,6}\s+.+$',
                    remaining_text,
                    re.MULTILINE
                )
                next_chapter = re.search(r'^#\s+.+$', remaining_text, re.MULTILINE)

                toc_end_patterns = [
                    r'^第\s*[一二三四五六七八九十]+\s*[章编部分]\s+',
                    r'^Chapter\s+\d+\s+',
                    r'^Part\s+\d+\s+',
                    r'^前言\s*$',
                    r'^前言\s*\n',
                    r'^引言\s*$',
                    r'^引言\s*\n',
                    r'^序言\s*$',
                    r'^序言\s*\n',
                ]
                toc_content_end = None
                for end_pattern in toc_end_patterns:
                    end_match = re.search(end_pattern, remaining_text, re.MULTILINE | re.IGNORECASE)
                    if end_match:
                        toc_content_end = end_match.start()
                        break

                if toc_content_end is not None:
                    toc_end = match.end() + toc_content_end
                elif next_any_heading:
                    toc_end = match.end() + next_any_heading.start()
                elif next_chapter:
                    toc_end = match.end() + next_chapter.start()
                else:
                    toc_end = len(text)

                toc_content = text[toc_start:toc_end].strip()

                if len(toc_content) >= 50:
                    return (
                        {
                            'name': '文档目录',
                            'content': toc_content,
                            'word_count': len(toc_content.split()),
                            'is_toc': True
                        },
                        toc_start,
                        toc_end,
                    )

        return None

    def _generate_summary(self, section: Dict, part_index: int = None, total_parts: int = None) -> str:
        """
        生成段落摘要 - 使用 LLM 基于内容生成简洁概括

        策略:
        1. 使用 LLM 生成摘要
        2. LLM 不可用时降级到规则式摘要
        3. 如果是分段，添加 Part 信息
        """
        if section.get('is_toc'):
            return '文档目录'

        content = section.get('content', '')
        if not content:
            return '空段落'

        if len(content) <= 100:
            summary = content.strip()
        elif self.llm_config:
            from .llm_summarizer import get_summarizer
            summarizer = get_summarizer(
                api_key=self.llm_config.get("api_key"),
                api_base=self.llm_config.get("api_base"),
                model_name=self.llm_config.get("model_name"),
            )
            logger.info(f"生成摘要 - 内容长度：{len(content)}, 前 50 字：{content[:50]}...")
            summary = summarizer.summarize(content, max_length=150)
            logger.info(f"生成的摘要：{summary[:50]}...")
        else:
            summary = self._fallback_summarize(content)

        if part_index is not None and total_parts and total_parts > 1:
            summary = f"[Part {part_index}/{total_parts}] {summary}"

        return summary

    def _fallback_summarize(self, content: str) -> str:
        """降级到规则式摘要（当 LLM 不可用时）"""
        summary_len = 100
        if len(content) <= summary_len:
            return content.strip()

        truncated = content[:summary_len]
        last_sentence_end = max(
            truncated.rfind('。'),
            truncated.rfind('！'),
            truncated.rfind('？'),
            truncated.rfind('. '),
            truncated.rfind('! '),
            truncated.rfind('? ')
        )

        if last_sentence_end > summary_len * 0.5:
            return truncated[:last_sentence_end + 1].strip()
        else:
            return truncated.rstrip() + '...'

    # ============================================================
    # 7. 主入口
    # ============================================================

    def split(self, text: str) -> List[Dict]:
        """
        基于标题层级树的 Markdown 结构化切片 — 纯结构切分，不截断

        处理流程:
        1. 清理页眉页脚
        2. 提取目录 (TOC) 作为独立 chunk
        3. 预处理：合并目录碎片、合并跨页表格
        4. 用 mistune 解析 AST + 逐行扫描构建标题树
        5. 递归树切分（只看标题边界，不看字数）
        6. 添加索引
        """
        # 1. 清理页眉页脚
        text = self._remove_header_footer(text, self.custom_header_patterns, self.custom_footer_patterns)

        # 2. 预处理：合并跨页表格、合并目录碎片（必须在提取目录之前）
        text = self._preprocess(text)

        # 3. 提取目录
        toc_result = self._extract_toc_chunk(text)
        toc_chunk = None
        if toc_result:
            toc_chunk, toc_start, toc_end = toc_result
            # 从文本中移除目录区域，避免被标题树重复处理导致碎片化
            text = text[:toc_start] + text[toc_end:]

        # 4. 构建标题树
        tree = self._build_heading_tree(text)

        # 5. 递归树切分
        processed = self._split_tree(tree)

        # 6. 目录 chunk 插入开头
        if toc_chunk:
            toc_chunk['summary'] = '文档目录'
            processed.insert(0, toc_chunk)

        # 7. 过滤空 chunk，添加索引
        processed = [c for c in processed if c.get('content', '').strip()]
        for i, chunk in enumerate(processed):
            chunk['index'] = i

        return processed

    # ============================================================
    # 预处理：合并目录碎片、合并跨页表格
    # ============================================================

    def _preprocess(self, text: str) -> str:
        """
        预处理 markdown 文本，修复 PyMuPDF4LLM 等工具的常见输出问题：

        1. 合并跨页表格：把列数相同且紧邻的多个小表格拼接成一个大表格
        2. 合并目录碎片：把散落在目录区域的零散标题/表格/文本合并
        """
        text = self._merge_cross_page_tables(text)
        text = self._merge_toc_fragments(text)
        return text

    def _merge_cross_page_tables(self, text: str) -> str:
        """
        合并跨页表格。

        判断规则：两个紧邻的 markdown 表格，如果列数相同，
        则视为同一张跨页表格，拼接在一起（去掉第二个表格的表头行）。
        """
        lines = text.split('\n')
        # 找出所有表格区域的起止行
        table_ranges = []
        in_table = False
        table_start = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('|') and '|' in stripped[1:]:
                if not in_table:
                    in_table = True
                    table_start = i
            else:
                if in_table:
                    table_ranges.append((table_start, i - 1))
                    in_table = False

        if in_table:
            table_ranges.append((table_start, len(lines) - 1))

        if len(table_ranges) < 2:
            return text

        # 计算每个表格的列数和表头
        table_info = []
        for start, end in table_ranges:
            table_lines = lines[start:end + 1]
            # 第一行是表头
            header_line = table_lines[0].strip()
            cols = header_line.count('|') - 1  # | a | b | -> 2 cols
            # 第二行是分隔线（|---|---|）
            separator_idx = -1
            for j, tl in enumerate(table_lines[1:], 1):
                if re.match(r'^\s*\|[\s\-:]+\|', tl.strip()):
                    separator_idx = j
                    break
            # 数据行（跳过表头和分隔线）
            data_start = separator_idx + 1 if separator_idx >= 0 else 1
            data_lines = table_lines[data_start:]

            table_info.append({
                'start': start,
                'end': end,
                'cols': cols,
                'header': header_line,
                'separator_idx': separator_idx,
                'data_lines': data_lines,
                'full_lines': table_lines,
            })

        # 从后往前合并，避免索引偏移
        merged = set()  # 已被合并的表格索引
        merge_groups = []  # [(idx1, idx2, ...), ...]

        for i in range(len(table_info) - 1):
            if i in merged:
                continue
            group = [i]
            j = i + 1
            while j < len(table_info):
                prev = table_info[group[-1]]
                curr = table_info[j]

                # 两个表格之间只隔着空行或页面分隔线
                gap_start = prev['end'] + 1
                gap_end = curr['start']
                gap_lines = lines[gap_start:gap_end]
                gap_text = '\n'.join(gap_lines).strip()
                # 允许空行、--- Page X ---、纯空内容
                is_gap_ok = (
                    not gap_text or
                    re.match(r'^(---+\s*Page\s*\d+\s*---+\s*)+$', gap_text, re.IGNORECASE) or
                    all(
                        not l.strip() or
                        l.strip().startswith('---') or
                        bool(re.match(r'^第\s*\d+\s*页\s*共\s*\d+\s*页\s*$', l.strip())) or
                        bool(re.match(r'^商密【[内外中]】\s*$', l.strip()))
                        for l in gap_lines
                    )
                )

                # 列数相同且间隔合法
                if is_gap_ok and prev['cols'] == curr['cols']:
                    group.append(j)
                    j += 1
                else:
                    break

            if len(group) > 1:
                merge_groups.append(group)
                for idx in group:
                    merged.add(idx)

        if not merge_groups:
            return text

        # 执行合并：替换每组表格
        result_lines = list(lines)
        # 从后往前替换，避免索引偏移
        for group in reversed(merge_groups):
            first = table_info[group[0]]
            last = table_info[group[-1]]

            # 保留第一个表格的完整内容（表头+分隔线+数据）
            # 后续表格只保留数据行（去掉表头和分隔线）
            merged_lines = list(first['full_lines'])
            for idx in group[1:]:
                merged_lines.extend(table_info[idx]['data_lines'])

            # 替换原始行
            result_lines[first['start']:last['end'] + 1] = merged_lines

        return '\n'.join(result_lines)

    def _merge_toc_fragments(self, text: str) -> str:
        """
        合并目录碎片。

        如果文档开头有"目录"标题，把它后面的零散内容（标题、表格、页码等）
        合并为一个连续的段落块，避免被切片器切碎。
        具体做法：在目录区域内的所有非空行前加一个统一标记，
        并在目录结束处加空行分隔。
        """
        # 找目录标题
        toc_match = re.search(
            r'^#{1,6}\s*目录\s*$',
            text,
            re.MULTILINE | re.IGNORECASE
        )
        if not toc_match:
            # 也试试纯"目录"文本
            toc_match = re.search(r'^目[\s　]*录\s*$', text, re.MULTILINE)
        if not toc_match:
            return text

        toc_start = toc_match.start()
        # 找目录结束位置：下一个同级或更高级标题，或者第一个"第X章"
        rest = text[toc_match.end():]
        toc_end_match = re.search(
            r'^(#{1,6}\s+.+|第[一二三四五六七八九十]+[章编部分])',
            rest,
            re.MULTILINE
        )
        if toc_end_match:
            toc_end = toc_match.end() + toc_end_match.start()
        else:
            return text  # 没找到结束边界，不处理

        # 提取目录区域内容
        toc_content = text[toc_start:toc_end]

        # 把目录区域内的零散标题行（如 ## 子目录）降级为普通文本
        # 去掉多余的 # 前缀，避免切片器把目录内部的小标题当切分边界
        toc_lines = toc_content.split('\n')
        cleaned_toc_lines = []
        for line in toc_lines:
            # 保留目录标题本身的 # ，去掉子标题的 #
            stripped = line.strip()
            if stripped.startswith('#') and stripped != toc_match.group().strip():
                # 子标题去掉 # 前缀，变成普通文本
                cleaned_line = re.sub(r'^#{1,6}\s+', '', stripped)
                cleaned_toc_lines.append(cleaned_line)
            else:
                cleaned_toc_lines.append(line)

        # 替换原始文本中的目录区域
        new_toc = '\n'.join(cleaned_toc_lines)
        text = text[:toc_start] + new_toc + text[toc_end:]

        return text


# ============================================================
# 其他分割器（未改动）
# ============================================================

class TokenSplitter(TextSplitter):
    """Split text by token count"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        super().__init__(chunk_size, overlap)

    def split(self, text: str) -> List[Dict]:
        """Split text by approximate token count"""
        words = text.split()
        chunks = []
        chunk_index = 0

        for i in range(0, len(words), self.chunk_size - self.overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)

            chunks.append({
                "index": chunk_index,
                "content": chunk_text,
                "word_count": len(chunk_words),
                "token_estimate": len(chunk_words) * 1.3  # rough token estimate
            })
            chunk_index += 1

        return chunks


class CodeSplitter(TextSplitter):
    """Split text with code awareness"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        super().__init__(chunk_size, overlap)

    def split(self, text: str) -> List[Dict]:
        """Split text preserving code blocks"""
        code_pattern = r'```[\s\S]*?```'
        parts = re.split(code_pattern, text)

        chunks = []
        chunk_index = 0
        current_chunk = ""

        for part in parts:
            if len(current_chunk) + len(part) > self.chunk_size:
                if current_chunk.strip():
                    chunks.append({
                        "index": chunk_index,
                        "content": current_chunk.strip(),
                        "word_count": len(current_chunk.split())
                    })
                    chunk_index += 1
                current_chunk = part
            else:
                current_chunk += part

        if current_chunk.strip():
            chunks.append({
                "index": chunk_index,
                "content": current_chunk.strip(),
                "word_count": len(current_chunk.split())
            })

        return chunks


class ExcelStructuredSplitter(TextSplitter):
    """
    Excel 表格结构化分割器

    核心逻辑：
    1. 使用 ExcelProcessor.extract_excel_by_row() 按行切分
    2. 每行数据成为一个独立的 chunk，包含完整的行列标题信息
    3. 支持合并单元格的自动填充处理
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50, file_path: str = None):
        super().__init__(chunk_size, overlap)
        self.file_path = file_path

    def split(self, text: str) -> List[Dict]:
        if self.file_path and (self.file_path.endswith('.xlsx') or self.file_path.endswith('.xls') or self.file_path.endswith('.csv')):
            from ..file_processor import ExcelProcessor
            processor = ExcelProcessor()
            chunks = processor.extract_excel_by_row(self.file_path)

            result = []
            for chunk in chunks:
                content = chunk.get('content', '')
                if len(content) > self.chunk_size:
                    sub_splitter = RecursiveCharacterTextSplitter(
                        chunk_size=self.chunk_size,
                        chunk_overlap=self.overlap,
                        separators=[" | ", ",", ""]
                    )
                    sub_chunks = sub_splitter.split_text(content)
                    for sub in sub_chunks:
                        result.append({
                            "index": len(result),
                            "content": sub.strip(),
                            "word_count": len(sub.split()),
                            "char_count": len(sub),
                            "metadata": chunk.get('metadata', {})
                        })
                else:
                    result.append({
                        "index": len(result),
                        "content": content,
                        "word_count": len(content.split()),
                        "char_count": len(content),
                        "metadata": chunk.get('metadata', {})
                    })

            return result

        lines = text.split('\n')
        result = []
        chunk_index = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if len(line) > self.chunk_size:
                sub_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.overlap,
                    separators=[" ", ",", ""]
                )
                sub_chunks = sub_splitter.split_text(line)
                for sub in sub_chunks:
                    result.append({
                        "index": chunk_index,
                        "content": sub.strip(),
                        "word_count": len(sub.split()),
                        "char_count": len(sub)
                    })
                    chunk_index += 1
            else:
                result.append({
                    "index": chunk_index,
                    "content": line,
                    "word_count": len(line.split()),
                    "char_count": len(line)
                })
                chunk_index += 1

        return result


class CustomSplitter(TextSplitter):
    """Custom separator splitter"""

    def __init__(self, separator: str = "\n\n", chunk_size: int = 500):
        super().__init__(chunk_size, 0)
        self.separator = separator

    def split(self, text: str) -> List[Dict]:
        """Split by custom separator"""
        parts = text.split(self.separator)
        chunks = []

        current_chunk = ""
        chunk_index = 0

        for part in parts:
            if len(current_chunk) + len(part) > self.chunk_size:
                if current_chunk.strip():
                    chunks.append({
                        "index": chunk_index,
                        "content": current_chunk.strip(),
                        "word_count": len(current_chunk.split())
                    })
                    chunk_index += 1
                current_chunk = part
            else:
                current_chunk += self.separator + part if current_chunk else part

        if current_chunk.strip():
            chunks.append({
                "index": chunk_index,
                "content": current_chunk.strip(),
                "word_count": len(current_chunk.split())
            })

        return chunks


def get_splitter(method: str, **kwargs) -> TextSplitter:
    """Get text splitter by method name"""
    from .semantic_embedding import (
        SemanticEmbeddingSplitter,
        create_embedding_provider
    )

    splitters = {
        "recursive": RecursiveTextSplitter,
        "markdown_structure": MarkdownStructureSplitter,
        "token": TokenSplitter,
        "code": CodeSplitter,
        "custom": CustomSplitter,
        "semantic": SemanticSentenceSplitter,
        "semantic_embedding": None,
        "sentence": SentenceSplitter,
        "paragraph": ParagraphSplitter,
        "excel_structured": ExcelStructuredSplitter,
    }

    if method == "semantic_embedding":
        embedding_provider = kwargs.pop('embedding_provider', None)
        if embedding_provider is None:
            provider = kwargs.pop('embedding_provider_type', 'openai')
            api_key = kwargs.pop('embedding_api_key', '')
            base_url = kwargs.pop('embedding_base_url', 'https://api.minimax.chat/v1')
            model = kwargs.pop('embedding_model', 'text-embedding-3-small')

            if api_key:
                embedding_provider = create_embedding_provider(
                    provider, api_key, base_url, model
                )

        if embedding_provider:
            return SemanticEmbeddingSplitter(
                embedding_provider=embedding_provider,
                **kwargs
            )
        else:
            method = "semantic"

    splitter_class = splitters.get(method, RecursiveTextSplitter)
    return splitter_class(**kwargs)


class SemanticSentenceSplitter(TextSplitter):
    """语义分割器 - 按段落优先，其次按句子"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        super().__init__(chunk_size, overlap)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=[
                "\n\n",
                "。",
                "！",
                "？",
                ". ",
                "! ",
                "? ",
                "\n",
                " ",
            ],
            length_function=self._count_chars
        )

    def _count_chars(self, text: str) -> int:
        chinese_chars = len(re.findall(r'[一-鿿]', text))
        other_chars = len(re.sub(r'[一-鿿]', '', text))
        return chinese_chars + int(other_chars * 1.5)

    def split(self, text: str) -> List[Dict]:
        chunks = self.splitter.split_text(text)
        result = []
        for i, chunk in enumerate(chunks):
            result.append({
                "index": i,
                "content": chunk.strip(),
                "word_count": len(chunk.split()),
                "char_count": len(chunk)
            })
        return result


class SentenceSplitter(TextSplitter):
    """严格按单句分割 - 每个chunk就是一句话"""

    def __init__(self, chunk_size: int = 200, overlap: int = 0):
        super().__init__(chunk_size, overlap)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=[
                "。",
                "！",
                "？",
                ". ",
                "! ",
                "? ",
                "\n",
                " ",
            ],
            length_function=lambda x: len(x)
        )

    def split(self, text: str) -> List[Dict]:
        chunks = self.splitter.split_text(text)
        result = []
        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if chunk:
                result.append({
                    "index": i,
                    "content": chunk,
                    "word_count": len(chunk.split()),
                    "char_count": len(chunk)
                })
        return result


class ParagraphSplitter(TextSplitter):
    """按段落分割 - 以空行分隔"""

    def __init__(self, chunk_size: int = 2000, overlap: int = 100):
        overlap = min(overlap, chunk_size // 2)
        super().__init__(chunk_size, overlap)

    def split(self, text: str) -> List[Dict]:
        paragraphs = re.split(r'\n\s*\n', text)
        result = []
        current_chunk = ""
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(para) > self.chunk_size:
                if current_chunk:
                    result.append({
                        "index": chunk_index,
                        "content": current_chunk.strip(),
                        "word_count": len(current_chunk.split()),
                        "char_count": len(current_chunk)
                    })
                    chunk_index += 1
                    current_chunk = ""

                sub_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.overlap,
                    separators=["\n", "。", "！", "？", ". ", "! ", "? "]
                )
                sub_chunks = sub_splitter.split_text(para)
                for sub in sub_chunks:
                    result.append({
                        "index": chunk_index,
                        "content": sub.strip(),
                        "word_count": len(sub.split()),
                        "char_count": len(sub)
                    })
                    chunk_index += 1
            else:
                if len(current_chunk) + len(para) > self.chunk_size:
                    if current_chunk:
                        result.append({
                            "index": chunk_index,
                            "content": current_chunk.strip(),
                            "word_count": len(current_chunk.split()),
                            "char_count": len(current_chunk)
                        })
                        chunk_index += 1
                        current_chunk = ""

                current_chunk += para + "\n\n"

        if current_chunk.strip():
            result.append({
                "index": chunk_index,
                "content": current_chunk.strip(),
                "word_count": len(current_chunk.split()),
                "char_count": len(current_chunk)
            })

        return result
