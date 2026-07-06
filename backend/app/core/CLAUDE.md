# 横切关注点层规则 (backend/app/core/)

## 职责

提供基础设施能力：配置管理、数据库连接、日志系统、异常定义、通用 CRUD、认证鉴权。

## 依赖规则

| 允许导入 | 禁止导入 |
|---------|---------|
| 标准库 | `app.api.*` |
| `pydantic`、`pydantic_settings` | `app.services.*` |
| `sqlalchemy` | `app.models.models`（仅 database.py 可导入 base） |
| 第三方基础库 | — |

## [禁止]

- 禁止导入 `app.api`、`app.services` 的任何模块
- 禁止导入具体的业务模型（`app.models.models` 中的具体类）
- 禁止在 core 层实现业务逻辑
- 禁止硬编码配置值，MUST 通过 `Settings` 类定义

## [必须]

- 配置项 MUST 在 `Settings` 类中定义默认值和类型
- 新增异常 MUST 继承 `AppException`
- 数据库操作 MUST 使用异步引擎（`create_async_engine`）
- 日志初始化 MUST 通过 `setup_logging()` 统一配置

## 文件组织

```
backend/app/core/
├── __init__.py
├── config.py       → Settings(BaseSettings) 配置管理，@lru_cache 缓存
├── database.py     → 异步 SQLAlchemy 引擎、session、init_db()
├── logging.py      → 日志配置（console + file + success/failure）
├── exceptions.py   → 异常层次（AppException 及子类）
├── crud.py         → CRUDBase[ModelType] 通用增删改查
└── auth.py         → API Key 认证
```
