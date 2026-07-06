"""
FastAPI 后端主入口
衔接前端 Vue3 界面 → dataset_manager.py（数据管理）→ llamafactory（模型微调）
"""
import sys
import os
from pathlib import Path

# 将项目根目录加入 sys.path，使后端能导入 llamafactory 和 dataset_manager
# __file__ = data_gen_w_model_finetune-dev_lzz/backend/main.py
# .parent.parent = data_gen_w_model_finetune-dev_lzz/
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .api import datasets, training, system, evaluation

# 模块级全局：启动时预加载模型列表
_MODEL_CACHE: list[dict] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Backend] 服务启动中...")
    # 预加载模型列表
    try:
        from llamafactory.extras.constants import SUPPORTED_MODELS
        _MODEL_CACHE.clear()
        _MODEL_CACHE.extend([
            {"name": name, "huggingface": paths.get("default", ""), "modelscope": paths.get("modelscope", "")}
            for name, paths in SUPPORTED_MODELS.items()
        ])
        print(f"[Backend] 已加载 {len(_MODEL_CACHE)} 个模型")
    except Exception as e:
        print(f"[Backend] 模型列表加载失败: {e}, 使用内置列表")
        _MODEL_CACHE.clear()
        _MODEL_CACHE.extend(_builtin_models())
    yield
    print("[Backend] 服务关闭")


def _builtin_models() -> list[dict]:
    """内置常用模型列表"""
    return [
        {"name": "Qwen2-0.5B", "huggingface": "Qwen/Qwen2-0.5B", "modelscope": ""},
        {"name": "Qwen2-1.5B", "huggingface": "Qwen/Qwen2-1.5B", "modelscope": ""},
        {"name": "Qwen2-7B", "huggingface": "Qwen/Qwen2-7B", "modelscope": ""},
        {"name": "Qwen2-7B-Instruct", "huggingface": "Qwen/Qwen2-7B-Instruct", "modelscope": ""},
        {"name": "Qwen2-14B", "huggingface": "Qwen/Qwen2-14B", "modelscope": ""},
        {"name": "Qwen2-72B", "huggingface": "Qwen/Qwen2-72B", "modelscope": ""},
        {"name": "Qwen2.5-0.5B", "huggingface": "Qwen/Qwen2.5-0.5B", "modelscope": ""},
        {"name": "Qwen2.5-7B", "huggingface": "Qwen/Qwen2.5-7B", "modelscope": ""},
        {"name": "Qwen2.5-14B", "huggingface": "Qwen/Qwen2.5-14B", "modelscope": ""},
        {"name": "Qwen2.5-32B", "huggingface": "Qwen/Qwen2.5-32B", "modelscope": ""},
        {"name": "Qwen2.5-72B", "huggingface": "Qwen/Qwen2.5-72B", "modelscope": ""},
        {"name": "Llama-3.1-8B", "huggingface": "meta-llama/Llama-3.1-8B", "modelscope": ""},
        {"name": "Llama-3.1-8B-Instruct", "huggingface": "meta-llama/Llama-3.1-8B-Instruct", "modelscope": ""},
        {"name": "Llama-3.1-70B", "huggingface": "meta-llama/Llama-3.1-70B", "modelscope": ""},
        {"name": "DeepSeek-R1-Distill-Qwen-1.5B", "huggingface": "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B", "modelscope": ""},
        {"name": "DeepSeek-R1-Distill-Qwen-7B", "huggingface": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "modelscope": ""},
        {"name": "DeepSeek-R1-Distill-Llama-8B", "huggingface": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B", "modelscope": ""},
        {"name": "Gemma-2-9B", "huggingface": "google/gemma-2-9b", "modelscope": ""},
        {"name": "Gemma-2-27B", "huggingface": "google/gemma-2-27b", "modelscope": ""},
        {"name": "Mistral-7B", "huggingface": "mistralai/Mistral-7B-v0.3", "modelscope": ""},
        {"name": "Yi-1.5-6B", "huggingface": "01-ai/Yi-1.5-6B", "modelscope": ""},
        {"name": "Yi-1.5-9B", "huggingface": "01-ai/Yi-1.5-9B", "modelscope": ""},
        {"name": "ChatGLM3-6B", "huggingface": "THUDM/chatglm3-6b", "modelscope": ""},
        {"name": "Baichuan2-7B", "huggingface": "baichuan-inc/Baichuan2-7B-Base", "modelscope": ""},
    ]


app = FastAPI(
    title="数据治理 & 模型微调平台 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 允许前端跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(datasets.router, prefix="/api/datasets", tags=["数据集管理"])
app.include_router(training.router, prefix="/api/training", tags=["模型训练"])
app.include_router(evaluation.router, prefix="/api/evaluation", tags=["评估工作台"])
app.include_router(system.router, prefix="/api/system", tags=["系统管理"])


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "data_gen_w_model_finetune"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True, log_level="warning")
