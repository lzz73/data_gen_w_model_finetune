# 数据层规则 (backend/app/models/)

## 职责

定义 SQLAlchemy ORM 数据模型，表达数据库表结构和实体关系。

## 依赖规则

| 允许导入 | 禁止导入 |
|---------|---------|
| `app.core.database`（Base） | `app.api.*` |
| `app.models.base`（Mixins） | `app.services.*` |
| `sqlalchemy` | `fastapi` |
| 标准库 | — |

## [禁止]

- 禁止导入 `app.api` 或 `app.services` 的任何模块
- 禁止在模型中实现业务逻辑
- 禁止在模型中直接调用外部 API
- 禁止修改已有字段的类型或名称（需通过 Alembic 迁移）

## [必须]

- 所有模型 MUST 继承 `Base` 并使用 `UUIDMixin` + `TimestampMixin`
- 外键关系 MUST 使用 `relationship()` 并配置 `cascade`
- JSON 字段 MUST 使用 `Column(JSON)`，提供 `default=dict` 或 `default=list`
- 枚举值 MUST 使用字符串常量，在模型注释中说明可选值

## 文件组织

```
backend/app/models/
├── __init__.py
├── base.py         → UUIDMixin、TimestampMixin
└── models.py       → 所有 ORM 模型（Project、File、Chunk、Question 等）
```
