# API 层规则 (backend/app/api/)

## 职责

HTTP 请求入口，负责路由定义、参数校验、调用服务层、返回统一响应。

## 依赖规则

| 允许导入 | 禁止导入 |
|---------|---------|
| `app.services.*` | — |
| `app.models.*` | — |
| `app.schemas.*` | — |
| `app.core.*` | — |
| `fastapi`、`pydantic` | — |

## [禁止]

- 禁止在路由中直接实现业务逻辑，MUST 委托给 services 层
- 禁止直接 `open()` 读写文件，MUST 通过服务层操作
- 禁止直接构造 SQL 查询，MUST 使用 ORM 或 CRUDBase
- 禁止返回原始 dict，MUST 使用 `ApiResponse.ok()` / `ApiResponse.fail()`

## [必须]

- 所有路由函数 MUST 使用 `async def`
- 所有路由 MUST 使用 Pydantic Schema 做参数校验
- 异常处理 MUST 通过全局 exception_handler 统一处理
- 新增路由模块 MUST 在 `v1/__init__.py` 中注册

## 文件组织

```
backend/app/api/
├── __init__.py
├── dependencies.py      → FastAPI 依赖注入（API Key 验证）
├── response.py          → ApiResponse / PaginatedResponse 统一响应
└── v1/
    ├── __init__.py      → 路由聚合，所有子路由在此注册
    ├── projects/        → 项目管理 CRUD
    ├── files/           → 文件上传和管理
    ├── chunks/          → 文本分块管理
    ├── questions/       → 问答生成和管理
    ├── datasets/        → 数据集导出
    ├── eval/            → 评估管理
    └── models/          → 模型配置管理
```
