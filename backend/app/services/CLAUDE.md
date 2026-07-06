# 服务层规则 (backend/app/services/)

## 职责

业务逻辑实现层，封装文件处理、文本分割、任务处理等核心能力，供 API 层调用。

## 依赖规则

| 允许导入 | 禁止导入 |
|---------|---------|
| `app.models.*` | `app.api.*` |
| `app.schemas.*` | `fastapi`（框架对象） |
| `app.core.*` | — |
| 标准库、第三方库 | — |

## [禁止]

- 禁止导入 `app.api` 或 `fastapi` 的 Request/Response 对象
- 禁止直接返回 HTTP 响应，MUST 返回数据或抛出异常
- 禁止直接操作数据库 session（应通过 `get_db_session()` 上下文管理器）

## [必须]

- 耗时操作 MUST 支持异步执行（`async def` + `asyncio.create_task()`）
- 后台任务 MUST 更新 Task 表的 progress/status
- LLM API 调用 MUST 使用 `httpx.AsyncClient`
- 文件处理 MUST 通过 `process_file()` 入口函数分发到具体处理器

## 文件组织

```
backend/app/services/
├── __init__.py
├── task_processor.py         → 后台评估任务处理
├── file_processor/
│   ├── __init__.py           → process_file() 入口分发
│   ├── pdf_processor.py      → PDF 处理（default/vision 策略）
│   ├── pdf/
│   │   ├── default.py        → pdfplumber 策略
│   │   └── vision.py         → VLM 视觉策略
│   ├── docx_processor.py     → DOCX 处理
│   └── excel_processor.py    → Excel/CSV 处理
└── text_splitter/
    ├── __init__.py
    ├── splitter.py            → 分割器注册表 + 9 种分割策略
    ├── semantic_embedding.py  → 嵌入式语义分割
    └── llm_summarizer.py      → LLM 摘要服务
```
