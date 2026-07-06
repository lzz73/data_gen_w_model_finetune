"""
Template QA Engine — 结构化数据模板问答生成引擎

纯模板系统（不调用 LLM），通过多模板池轮换 + 字段类型感知 + 多种问法策略
生成自然、多样的问答对。
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional


# ============================================================
# 类型感知：条件描述 & 问法关键词
# ============================================================

def format_condition(name: str, value: str, field_type: str) -> str:
    """根据字段类型生成条件描述。

    Examples:
        format_condition("年龄", "25", "integer")  → "年龄为25"
        format_condition("在职", "是", "boolean")   → "在职"
        format_condition("入职日期", "2024-01", "date") → "入职日期为2024-01"
    """
    if field_type == "boolean":
        if value.strip().lower() in ("true", "是", "1", "yes"):
            return name  # "在职" 而不是 "在职是"
        return f"未{name}"  # "未在职" 而不是 "在职否"
    return f"{name}为{value}"


def question_word_for_type(field_type: str) -> str:
    """根据字段类型返回合适的疑问词。"""
    mapping = {
        "integer": "是多少",
        "float": "是多少",
        "date": "是什么时候",
        "boolean": "是否",
    }
    return mapping.get(field_type, "是什么")


def answer_connector_for_type(field_type: str) -> str:
    """根据字段类型返回答案连接词。"""
    mapping = {
        "integer": "为",
        "float": "为",
    }
    return mapping.get(field_type, "是")


# ============================================================
# 问法模板池
# ============================================================

# 正向问法模板（feature → target）
# 使用 {conditions} {target} {target_qw} 占位符
FORWARD_TEMPLATES = [
    # 风格 1：已知条件式
    "已知{conditions}，请问{target}{target_qw}？",
    # 风格 2：当…时式
    "当{first_condition}时，{target}{target_qw}？",
    # 风格 3：查询式
    "请查询{conditions}对应的{target}。",
    # 风格 4：在…条件下式
    "在{first_condition}的条件下，{target}{target_qw}？",
    # 风格 5：根据…式
    "根据{conditions}，{target}{target_qw}？",
    # 风格 6：…的情况下式
    "{first_condition}的情况下，{target}{target_qw}？",
]

# 逆向问法模板（target → feature）
REVERSE_TEMPLATES = [
    "已知{target}为{target_value}，请问{feature}是什么？",
    "{target}是{target_value}，对应的{feature}是什么？",
    "如果{target}为{target_value}，那么{feature}是什么？",
    "查找{target}为{target_value}的记录，{feature}是什么？",
]

# 多目标问法模板
MULTI_TARGET_TEMPLATES = [
    "已知{conditions}，请分别说明{target_list}的值。",
    "根据{conditions}，查询{target_list}的信息。",
    "在{first_condition}的条件下，{target_list}分别是什么？",
]

# 概括型问法模板
SUMMARY_TEMPLATES = [
    "请描述{conditions}对应的完整记录。",
    "根据{conditions}，给出该条记录的详细信息。",
    "查询{conditions}对应的所有字段信息。",
]


# ============================================================
# 答案模板
# ============================================================

def format_single_answer(target_name: str, target_value: str, field_type: str) -> str:
    """格式化单目标答案为完整句子。"""
    connector = answer_connector_for_type(field_type)
    return f"{target_name}{connector}{target_value}。"


def format_multi_answer(targets: List[Dict[str, str]]) -> str:
    """格式化多目标答案。

    Args:
        targets: [{"name": "薪资", "value": "15000", "type": "integer"}, ...]
    """
    parts = []
    for t in targets:
        connector = answer_connector_for_type(t.get("type", "string"))
        parts.append(f"{t['name']}{connector}{t['value']}")
    return "，".join(parts) + "。"


def format_summary_answer(
    features: List[Dict[str, str]],
    targets: List[Dict[str, str]],
) -> str:
    """格式化概括型答案：包含所有字段。"""
    parts = []
    for f in features:
        parts.append(f"{f['name']}为{f['value']}")
    for t in targets:
        parts.append(f"{t['name']}为{t['value']}")
    return "根据记录，" + "，".join(parts) + "。"


# ============================================================
# 脱敏处理
# ============================================================

# 模块级脱敏引擎实例缓存（用于同批次内保持占位符一致性）
_desensitize_placeholder_map: Dict[str, str] = {}
_desensitize_counter: Dict[str, int] = {}


def _get_desensitize_placeholder(field_name: str, value: str) -> str:
    """为脱敏值生成语义化占位符，同一批次内相同值始终映射到同一占位符。"""
    key = f"{field_name}:{value}"
    if key in _desensitize_placeholder_map:
        return _desensitize_placeholder_map[key]

    label = f"{field_name}值"
    idx = _desensitize_counter.get(label, 0) + 1
    _desensitize_counter[label] = idx
    placeholder = f"**{label}{chr(64 + idx) if idx <= 26 else idx}**"
    _desensitize_placeholder_map[key] = placeholder
    return placeholder


def reset_desensitize_state():
    """重置脱敏占位符映射（每次新批次调用时重置）。"""
    global _desensitize_placeholder_map, _desensitize_counter
    _desensitize_placeholder_map = {}
    _desensitize_counter = {}


def apply_desensitize(
    value: str,
    should_desensitize: bool,
    field_name: str = "",
) -> str:
    """对需要脱敏的值进行语义化占位符替换。

    替换效果：张三 → **姓名值A**，15000 → **薪资值A**
    同一字段相同值始终替换为相同占位符。
    """
    if should_desensitize and value:
        return _get_desensitize_placeholder(field_name or "敏感信息", value)
    return value


# ============================================================
# 核心：生成模板问答对
# ============================================================

def generate_template_qa_pairs(
    row_data: Dict[str, str],
    field_schema: List[Dict[str, Any]],
    questions_per_row: int = 1,
    row_index: int = 0,
) -> List[Dict[str, Any]]:
    """为单行结构化数据生成模板问答对。

    Args:
        row_data: 行数据 {"姓名": "张三", "年龄": "25", ...}
        field_schema: 字段元信息 [{"name": "姓名", "type": "string", "role": "feature", ...}, ...]
        questions_per_row: 每行生成几个问答对
        row_index: 当前行索引（用于模板轮换，避免相邻行问法重复）

    Returns:
        [{"question": str, "answer": str, "question_type": str, "template_type": str}, ...]
    """
    # 分类字段
    feature_fields = [f for f in field_schema if f.get("role") == "feature"]
    target_fields = [f for f in field_schema if f.get("role") == "target"]

    if not feature_fields or not target_fields:
        return []

    # 构建条件列表（含类型感知 + 脱敏）
    conditions = []
    for ff in feature_fields:
        fname = ff.get("name", "")
        fval = row_data.get(fname, "")
        if not fval:
            continue
        fval = apply_desensitize(fval, ff.get("desensitize", False), fname)
        ftype = ff.get("type", "string")
        conditions.append({
            "name": fname,
            "value": fval,
            "type": ftype,
            "text": format_condition(fname, fval, ftype),
        })

    if not conditions:
        return []

    # 构建目标值列表（含脱敏）
    target_values = []
    for tf in target_fields:
        tname = tf.get("name", "")
        tval = row_data.get(tname, "")
        tval = apply_desensitize(tval, tf.get("desensitize", False), tname)
        ttype = tf.get("type", "string")
        target_values.append({
            "name": tname,
            "value": tval,
            "type": ttype,
        })

    # 收集所有候选问答对
    candidates: List[Dict[str, Any]] = []

    # ---- 1. 正向问法（每个 target 一个） ----
    for ti, tv in enumerate(target_values):
        if not tv["value"]:
            continue
        # 轮换模板
        template_idx = (row_index + ti) % len(FORWARD_TEMPLATES)
        template = FORWARD_TEMPLATES[template_idx]

        condition_str = "，".join(c["text"] for c in conditions)
        first_condition = conditions[0]["text"]
        target_qw = question_word_for_type(tv["type"])

        question = template.format(
            conditions=condition_str,
            first_condition=first_condition,
            target=tv["name"],
            target_qw=target_qw,
        )

        answer = format_single_answer(tv["name"], tv["value"], tv["type"])

        candidates.append({
            "question": question,
            "answer": answer,
            "question_type": "fact",
            "template_type": "forward",
        })

    # ---- 2. 逆向问法（target → feature） ----
    # 选第一个有值的 target 和第一个有值的 feature 做逆向
    first_target_with_value = next((tv for tv in target_values if tv["value"]), None)
    if first_target_with_value and len(conditions) > 0:
        # 可以对多个 feature 做逆向
        for ci, cond in enumerate(conditions[:3]):  # 最多 3 个逆向
            template_idx = (row_index + ci) % len(REVERSE_TEMPLATES)
            template = REVERSE_TEMPLATES[template_idx]

            question = template.format(
                target=first_target_with_value["name"],
                target_value=first_target_with_value["value"],
                feature=cond["name"],
            )

            answer = format_single_answer(cond["name"], cond["value"], cond["type"])

            candidates.append({
                "question": question,
                "answer": answer,
                "question_type": "fact",
                "template_type": "reverse",
            })

    # ---- 3. 多目标问法（合并 2+ 个 target） ----
    if len(target_values) >= 2:
        valid_targets = [tv for tv in target_values if tv["value"]]
        if len(valid_targets) >= 2:
            template_idx = row_index % len(MULTI_TARGET_TEMPLATES)
            template = MULTI_TARGET_TEMPLATES[template_idx]

            condition_str = "，".join(c["text"] for c in conditions)
            first_condition = conditions[0]["text"]
            target_list = "和".join(tv["name"] for tv in valid_targets)

            question = template.format(
                conditions=condition_str,
                first_condition=first_condition,
                target_list=target_list,
            )

            answer = format_multi_answer(valid_targets)

            candidates.append({
                "question": question,
                "answer": answer,
                "question_type": "fact",
                "template_type": "multi_target",
            })

    # ---- 4. 概括型问法 ----
    if len(conditions) >= 1:
        template_idx = row_index % len(SUMMARY_TEMPLATES)
        template = SUMMARY_TEMPLATES[template_idx]

        condition_str = "，".join(c["text"] for c in conditions)

        question = template.format(conditions=condition_str)

        # 概括型答案包含所有字段
        feature_items = [{"name": c["name"], "value": c["value"]} for c in conditions]
        target_items = [{"name": tv["name"], "value": tv["value"]} for tv in target_values if tv["value"]]
        answer = format_summary_answer(feature_items, target_items)

        candidates.append({
            "question": question,
            "answer": answer,
            "question_type": "summary",
            "template_type": "summary",
        })

    # ---- 按 questions_per_row 截取，保证多样性 ----
    if questions_per_row <= 0:
        questions_per_row = 1

    # 如果候选数量 <= 需要的数量，全部返回
    if len(candidates) <= questions_per_row:
        return candidates

    # 否则按策略优先级选取：先保证每种 template_type 至少一个，再按顺序补充
    selected: List[Dict[str, Any]] = []
    seen_types: set[str] = set()

    # 第一轮：每种类型选一个
    for c in candidates:
        if c["template_type"] not in seen_types and len(selected) < questions_per_row:
            selected.append(c)
            seen_types.add(c["template_type"])

    # 第二轮：按顺序补充剩余
    for c in candidates:
        if c not in selected and len(selected) < questions_per_row:
            selected.append(c)

    return selected


# ============================================================
# 辅助：解析 chunk 内容
# ============================================================

def parse_chunk_content(content: str) -> Dict[str, str]:
    """解析结构化 chunk 内容为 key-value dict。

    Chunk 格式: "字段名: 值\\n字段名: 值"
    """
    row_data: Dict[str, str] = {}
    if not content:
        return row_data
    for line in content.split("\n"):
        line = line.strip()
        if ":" in line:
            key, val = line.split(":", 1)
            row_data[key.strip()] = val.strip()
    return row_data
