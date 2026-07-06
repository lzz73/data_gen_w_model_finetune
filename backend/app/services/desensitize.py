"""
Desensitize Engine — 脱敏引擎

提供三层脱敏能力：
1. 正则规则引擎：手机号、身份证、邮箱、银行卡、工号等 → 语义化占位符
2. 关键词匹配：项目级可配置关键词清单，精确/正则匹配
3. NER 模型辅助：调用 chat 模型识别姓名、地址、机构名

同文档内相同原文始终替换为相同占位符（通过 mapping dict 维护双向映射）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import logger
from app.services.llm_helpers import call_generation_model, LLM_SEMAPHORE


# ──────────────────────────────────────────────
# 内置正则规则
# ──────────────────────────────────────────────

BUILTIN_RULES: list[dict[str, Any]] = [
    {
        "id": "phone",
        "label": "手机号",
        "pattern": r"(?<!\d)1[3-9]\d{9}(?!\d)",
        "placeholder": "手机",
        "enabled": True,
    },
    {
        "id": "id_card",
        "label": "身份证号",
        "pattern": r"(?<!\d)[1-9]\d{5}(?:19|20)\d{3}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)",
        "placeholder": "身份证",
        "enabled": True,
    },
    {
        "id": "email",
        "label": "邮箱地址",
        "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "placeholder": "邮箱",
        "enabled": True,
    },
    {
        "id": "bank_card",
        "label": "银行卡号",
        "pattern": r"(?<!\d)62\d{14,17}(?!\d)",
        "placeholder": "银行卡",
        "enabled": True,
    },
    {
        "id": "ip_address",
        "label": "IP地址",
        "pattern": r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)",
        "placeholder": "IP地址",
        "enabled": True,
    },
    {
        "id": "employee_id",
        "label": "内部工号",
        "pattern": r"(?:工号|编号|员工号)[:：\s]*(\d{4,12})",
        "placeholder": "内部员工",
        "enabled": True,
        "group": 1,  # only mask the captured group
    },
    {
        "id": "doc_number",
        "label": "文件编号",
        "pattern": r"(?:YG-[A-Z]+-[A-Z]+\d+)",
        "placeholder": "内部编号",
        "enabled": True,
    },
]


# ──────────────────────────────────────────────
# DesensitizeEngine
# ──────────────────────────────────────────────

class DesensitizeEngine:
    """
    脱敏引擎：对文本执行正则替换 + 关键词匹配 + NER 辅助。

    用法:
        engine = DesensitizeEngine(rules_config=..., keyword_rules=...)
        clean_text, audit_records = engine.desensitize(text, file_id=..., chunk_id=...)
    """

    def __init__(
        self,
        enabled_rules: Optional[List[str]] = None,
        keyword_rules: Optional[List[Dict[str, Any]]] = None,
        mode: str = "blacklist",  # blacklist = all enabled rules; whitelist = only listed ids
    ):
        self.mode = mode
        self.keyword_rules = keyword_rules or []

        # Build active rule list
        if mode == "whitelist":
            # Only use rules whose id is in enabled_rules
            whitelist = set(enabled_rules or [])
            self.active_regex_rules = [r for r in BUILTIN_RULES if r["id"] in whitelist]
        else:
            # Use all enabled builtin rules
            if enabled_rules is not None:
                enabled_set = set(enabled_rules)
                self.active_regex_rules = [r for r in BUILTIN_RULES if r["id"] in enabled_set]
            else:
                self.active_regex_rules = [r for r in BUILTIN_RULES if r.get("enabled", True)]

        # Placeholder mapping: original_text -> placeholder
        self._placeholder_map: Dict[str, str] = {}
        # Counter per placeholder label
        self._counter: Dict[str, int] = {}

    def _get_placeholder(self, label: str, original: str) -> str:
        """Get or create a semantic placeholder for the original text."""
        if original in self._placeholder_map:
            return self._placeholder_map[original]

        idx = self._counter.get(label, 0) + 1
        self._counter[label] = idx
        placeholder = f"**{label}{chr(64 + idx) if idx <= 26 else idx}**"
        self._placeholder_map[original] = placeholder
        return placeholder

    def desensitize(
        self,
        text: str,
        file_id: Optional[str] = None,
        chunk_id: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Execute desensitization on the text.

        Returns:
            (cleaned_text, audit_records)
            audit_records: list of {rule_id, rule_type, original_text, replacement, confidence}
        """
        if not text:
            return text, []

        audit_records: List[Dict[str, Any]] = []

        # Phase 1: Regex rules
        for rule in self.active_regex_rules:
            pattern = rule["pattern"]
            label = rule["placeholder"]
            group = rule.get("group", 0)

            for match in re.finditer(pattern, text):
                if group > 0:
                    original = match.group(group)
                    start, end = match.start(group), match.end(group)
                else:
                    original = match.group(0)
                    start, end = match.start(), match.end()

                replacement = self._get_placeholder(label, original)
                # Replace in text
                text = text[:start] + replacement + text[end:]

                audit_records.append({
                    "rule_id": rule["id"],
                    "rule_type": "regex",
                    "original_text": original[:10] + ("..." if len(original) > 10 else ""),
                    "replacement": replacement,
                    "confidence": 1.0,
                    "file_id": file_id,
                    "chunk_id": chunk_id,
                })

                # After replacement, subsequent match positions shift — break and re-scan
                # For simplicity, re-run all regex rules after each replacement batch
                # (performance is fine for typical chunk sizes)
                break
            else:
                continue
            # Re-run from the beginning after a replacement
            while True:
                found_any = False
                for rule2 in self.active_regex_rules:
                    pattern2 = rule2["pattern"]
                    label2 = rule2["placeholder"]
                    group2 = rule2.get("group", 0)
                    for match2 in re.finditer(pattern2, text):
                        if group2 > 0:
                            original2 = match2.group(group2)
                            start2, end2 = match2.start(group2), match2.end(group2)
                        else:
                            original2 = match2.group(0)
                            start2, end2 = match2.start(), match2.end()
                        replacement2 = self._get_placeholder(label2, original2)
                        text = text[:start2] + replacement2 + text[end2:]
                        audit_records.append({
                            "rule_id": rule2["id"],
                            "rule_type": "regex",
                            "original_text": original2[:10] + ("..." if len(original2) > 10 else ""),
                            "replacement": replacement2,
                            "confidence": 1.0,
                            "file_id": file_id,
                            "chunk_id": chunk_id,
                        })
                        found_any = True
                        break
                    if found_any:
                        break
                if not found_any:
                    break

        # Phase 2: Keyword rules
        for kw_rule in self.keyword_rules:
            keyword = kw_rule.get("keyword", "")
            match_mode = kw_rule.get("mode", "exact")  # exact or regex
            label = kw_rule.get("placeholder", "敏感词")

            if not keyword:
                continue

            if match_mode == "exact":
                # Exact match: find all occurrences of keyword in text
                # Replace the value parts containing the keyword
                # Simple approach: find "keyword" in values and replace
                if keyword in text:
                    replacement = self._get_placeholder(label, keyword)
                    # For exact match, we replace the entire value that contains the keyword
                    # Simple: replace the keyword itself
                    text = text.replace(keyword, replacement)
                    audit_records.append({
                        "rule_id": f"keyword:{keyword}",
                        "rule_type": "keyword",
                        "original_text": keyword[:10],
                        "replacement": replacement,
                        "confidence": 1.0,
                        "file_id": file_id,
                        "chunk_id": chunk_id,
                    })
            elif match_mode == "regex":
                try:
                    for match in re.finditer(keyword, text):
                        original = match.group(0)
                        replacement = self._get_placeholder(label, original)
                        text = text.replace(original, replacement, 1)
                        audit_records.append({
                            "rule_id": f"keyword_regex:{keyword[:30]}",
                            "rule_type": "keyword",
                            "original_text": original[:10] + ("..." if len(original) > 10 else ""),
                            "replacement": replacement,
                            "confidence": 1.0,
                            "file_id": file_id,
                            "chunk_id": chunk_id,
                        })
                except re.error:
                    logger.warning(f"[脱敏] 关键词正则无效: {keyword}")

        return text, audit_records

    async def desensitize_with_ner(
        self,
        text: str,
        model_config: Any,
        file_id: Optional[str] = None,
        chunk_id: Optional[str] = None,
        temperature: float = 0.1,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Execute regex + keyword desensitization, then NER-assisted pass.

        The NER pass calls a chat model to identify entities (name, address, org)
        that regex may have missed.
        """
        # Phase 1+2: regex + keyword
        text, audit_records = self.desensitize(text, file_id=file_id, chunk_id=chunk_id)

        # Phase 3: NER
        if model_config and model_config.api_key:
            try:
                ner_prompt = f"""请识别以下文本中的个人敏感信息实体，包括：姓名、详细地址、机构名称。
输出 JSON 格式：
{{"entities": [{{"text": "原文中的实体", "type": "name/address/org", "start": 起始位置, "end": 结束位置}}]}}

如果文本中没有敏感信息，输出：{{"entities": []}}

【文本】
{text[:3000]}"""

                async with LLM_SEMAPHORE:
                    raw = await call_generation_model(
                        model_config,
                        "你是敏感信息识别助手，只输出 JSON。",
                        ner_prompt,
                        temperature=temperature,
                        json_output=True,
                    )

                try:
                    result = json.loads(raw)
                    entities = result.get("entities", [])
                except (json.JSONDecodeError, TypeError):
                    entities = []

                # Apply NER replacements (from end to start to preserve positions)
                entities.sort(key=lambda e: e.get("start", 0), reverse=True)
                for ent in entities:
                    original = ent.get("text", "")
                    ent_type = ent.get("type", "unknown")
                    if not original or original in self._placeholder_map:
                        continue  # already replaced

                    label_map = {"name": "人物", "address": "地址", "org": "机构"}
                    label = label_map.get(ent_type, "实体")
                    replacement = self._get_placeholder(label, original)
                    text = text.replace(original, replacement, 1)
                    audit_records.append({
                        "rule_id": f"ner:{ent_type}",
                        "rule_type": "ner",
                        "original_text": original[:10] + ("..." if len(original) > 10 else ""),
                        "replacement": replacement,
                        "confidence": 0.7,
                        "file_id": file_id,
                        "chunk_id": chunk_id,
                    })

            except Exception as e:
                logger.warning(f"[脱敏NER] 调用失败: {e}")

        return text, audit_records


def build_engine_from_project_config(
    extra_data: dict,
    sensitive_rules: Optional[dict] = None,
) -> tuple[DesensitizeEngine, bool]:
    """
    Build a DesensitizeEngine from project extra_data config.

    Returns:
        (engine, ner_enabled) — ner_enabled indicates whether NER pass should be applied.

    Config shape in extra_data:
    {
        "sensitive_rules": {
            "enabled": true,
            "mode": "blacklist",  // or "whitelist"
            "enabled_rules": ["phone", "id_card", "email"],
            "keyword_rules": [
                {"keyword": "薪资", "mode": "exact", "placeholder": "敏感信息"},
                {"keyword": "\\d{4}年\\d+月", "mode": "regex", "placeholder": "日期"}
            ],
            "ner_enabled": false
        },
        "desensitize_rules": {
            "keywords": ["薪资", "合同金额"],
            "match_mode": "exact"
        }
    }
    """
    sensitive_config = sensitive_rules or (extra_data.get("sensitive_rules", {}) if extra_data else {})
    desensitize_config = extra_data.get("desensitize_rules", {}) if extra_data else {}

    # Merge desensitize_rules (legacy format) into keyword_rules
    keyword_rules = list(sensitive_config.get("keyword_rules", []))
    if desensitize_config:
        keywords = desensitize_config.get("keywords", [])
        match_mode = desensitize_config.get("match_mode", "exact")
        for kw in keywords:
            keyword_rules.append({
                "keyword": kw,
                "mode": match_mode,
                "placeholder": "敏感信息",
            })

    enabled_rules = sensitive_config.get("enabled_rules")
    if enabled_rules is None:
        # Default: enable all
        enabled_rules = [r["id"] for r in BUILTIN_RULES]

    mode = sensitive_config.get("mode", "blacklist")
    ner_enabled = sensitive_config.get("ner_enabled", False)

    engine = DesensitizeEngine(
        enabled_rules=enabled_rules,
        keyword_rules=keyword_rules,
        mode=mode,
    )

    return engine, ner_enabled


async def desensitize_chunk(
    text: str,
    project_extra_data: dict,
    model_config: Any = None,
    file_id: Optional[str] = None,
    chunk_id: Optional[str] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    对文本执行完整脱敏流水线（正则 + 关键词 + 可选 NER）。

    供 chunks API 的 split 流程调用。
    根据 project.extra_data.sensitive_rules 配置决定是否启用 NER。
    """
    sensitive_config = (project_extra_data or {}).get("sensitive_rules", {})
    if not sensitive_config.get("enabled", False):
        return text, []

    engine, ner_enabled = build_engine_from_project_config(project_extra_data)

    if ner_enabled and model_config and model_config.api_key:
        return await engine.desensitize_with_ner(
            text, model_config, file_id=file_id, chunk_id=chunk_id
        )
    else:
        return engine.desensitize(text, file_id=file_id, chunk_id=chunk_id)
