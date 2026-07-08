"""
API v1 Router
"""

from fastapi import APIRouter

from app.api.v1 import files, projects, chunks, questions, datasets, eval, models, crawler, database
from app.api.v1 import training, evaluation, system

api_router = APIRouter()

# Include sub-routers
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
# files, chunks, questions, datasets, eval 需要嵌套在 projects 下
# 通过 projects 路由中的子路由处理
api_router.include_router(files.router, prefix="/projects/{project_id}/files", tags=["files"])
api_router.include_router(chunks.router, prefix="/projects/{project_id}/chunks", tags=["chunks"])
api_router.include_router(questions.router, prefix="/projects/{project_id}/questions", tags=["questions"])
api_router.include_router(datasets.router, prefix="/projects/{project_id}/datasets", tags=["datasets"])
api_router.include_router(eval.router, prefix="/projects/{project_id}/eval", tags=["eval"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(crawler.router, prefix="/crawler", tags=["crawler"])
api_router.include_router(database.router, prefix="/database", tags=["database"])

# 训练、评估、系统管理（从微调训练模块合并）
api_router.include_router(training.router, prefix="/training", tags=["training"])
api_router.include_router(evaluation.router, prefix="/evaluation", tags=["evaluation"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
