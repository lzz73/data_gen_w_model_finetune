"""
模型管理服务：检测本地已下载的模型
"""
import os
from pathlib import Path


def _scan_dir(path: Path) -> list[str]:
    """扫描目录下的模型文件夹"""
    if not path.exists():
        return []
    models = []
    for sub in path.iterdir():
        if sub.is_dir():
            # 检查是否有模型文件 (config.json, model.safetensors 等)
            has_config = (sub / "config.json").exists()
            has_weights = any(sub.glob("*.safetensors")) or any(sub.glob("*.bin"))
            if has_config:
                models.append(str(sub.resolve()))
    return models


def get_local_models() -> list[dict]:
    """扫描本地已有模型"""
    local = []

    # HuggingFace 缓存
    hf_home = os.environ.get("HF_HOME") or os.path.join(Path.home(), ".cache", "huggingface", "hub")
    hf_models = _scan_dir(Path(hf_home) / "models--")
    for m in hf_models:
        # 从路径提取模型名：models--Qwen--Qwen2-7B → Qwen/Qwen2-7B
        folder = Path(m).parent.name if "snapshots" in m else Path(m).name
        repo_id = _decode_hf_path(folder)
        local.append({"name": repo_id, "path": m, "source": "huggingface"})

    # Modelscope 缓存
    ms_home = os.environ.get("MODELSCOPE_CACHE") or os.path.join(Path.home(), ".cache", "modelscope", "hub")
    ms_models = _scan_dir(Path(ms_home))
    for m in ms_models:
        # modelscope 路径格式：xxx/xxx → xxx_xxx
        folder = Path(m).parent.name if "snapshots" in m else Path(m).name
        repo_id = folder.replace("___", "/")
        local.append({"name": repo_id, "path": m, "source": "modelscope"})

    # 当前项目的 models/ 目录
    project_models = Path(__file__).resolve().parent.parent.parent / "models"
    if project_models.exists():
        for sub in project_models.iterdir():
            if sub.is_dir() and (sub / "config.json").exists():
                local.append({"name": sub.name, "path": str(sub.resolve()), "source": "local"})

    return local


def _decode_hf_path(folder: str) -> str:
    """解码 HuggingFace 缓存目录名到 repo_id
    models--Qwen--Qwen2-7B → Qwen/Qwen2-7B
    """
    if folder.startswith("models--"):
        folder = folder[len("models--"):]
    return folder.replace("--", "/")
