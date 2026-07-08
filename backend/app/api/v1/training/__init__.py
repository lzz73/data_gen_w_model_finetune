"""
训练管理 API
提供前端 training/TrainWorkbench、TrainMonitor 页面所需接口
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
import sys
import os
import asyncio
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path

from app.api.response import ApiResponse
from app.services.training_service import (
    list_tasks,
    get_task,
    create_task,
    cancel_task,
)
from app.services.task_runner import cancel_training
from app.services.gpu_service import get_gpu_info

router = APIRouter()

# WebSocket 连接池（用于实时推送训练状态）
_ws_clients: dict[str, set[WebSocket]] = {}

# 项目根目录 (platform_demo/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent

# 模型缓存（启动时加载）
_MODEL_CACHE: list[dict] = []


class TrainConfig(BaseModel):
    mode: str = "sft"
    finetuning_type: str = "lora"
    dataset: str = ""
    base_model: str = "Qwen/Qwen2-7B"
    preset: str = "standard"
    learning_rate: str = "1e-5"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    cutoff_len: int = 1024
    gradient_accumulation_steps: int = 4
    max_samples: int = 100000
    lr_scheduler_type: str = "cosine"
    warmup_steps: int = 100
    max_grad_norm: str = "1.0"
    optim: str = "adamw_torch"
    dtype: str = "bf16"
    template: str = "qwen"
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: str = "0.01"
    lora_target: str = "all"
    do_eval: bool = False
    val_size: str = "0.1"
    eval_dataset: str = ""
    eval_steps: int = 50
    save_steps: int = 100
    logging_steps: int = 50
    save_total_limit: int = 5
    flash_attn: str = "auto"
    gpu: str = "0"
    output_dir: str = ""
    resume_from_checkpoint: bool = False
    checkpoint_path: str = ""


@router.get("/tasks")
def api_list_tasks():
    """获取所有训练任务列表"""
    return ApiResponse.ok(data=list_tasks())


@router.get("/tasks/{task_id}")
def api_get_task(task_id: str):
    """获取单个训练任务详情"""
    task = get_task(task_id)
    if not task:
        return ApiResponse.fail(message="任务不存在")
    return ApiResponse.ok(data=task)


@router.post("/tasks")
def api_create_task(config: TrainConfig):
    """创建并启动训练任务"""
    task = create_task(config.model_dump())
    return ApiResponse.ok(
        data={"task_id": task["task_id"]},
        message="训练任务已提交"
    )


@router.post("/tasks/fix-status")
def api_fix_status():
    """修正所有训练任务的状态"""
    from app.services.training_state import _tasks, _task_lock

    fixed = 0
    with _task_lock:
        for tid, task in _tasks.items():
            if task["status"] in ("running", "pending"):
                output_dir = PROJECT_ROOT / "output" / tid
                if output_dir.exists() and any(output_dir.glob("checkpoint-*")):
                    task["status"] = "completed"
                    task["progress"] = 100
                    task["eta"] = "00:00"
                    if not task.get("finished_at"):
                        task["finished_at"] = datetime.now().isoformat()
                    task.setdefault("logs", []).append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "msg": "[INFO] 训练完成！（状态已根据 checkpoint 自动修正）",
                        "type": "info",
                    })
                    fixed += 1
    try:
        from app.services.training_service import _save_tasks
        _save_tasks()
    except Exception:
        pass
    return ApiResponse.ok(message=f"已修正 {fixed} 个任务状态", data={"fixed": fixed})


@router.post("/tasks/{task_id}/cancel")
def api_cancel_task(task_id: str):
    """取消/中断训练任务"""
    killed = cancel_training(task_id)
    ok = cancel_task(task_id)
    msg = "已中断" if killed else ("已取消" if ok else "任务不存在")
    return ApiResponse.ok(message=msg)


class ExportConfig(BaseModel):
    task_id: str = ""
    export_dir: str = ""
    export_size: int = 5


_export_jobs: dict = {}


@router.get("/merged-models")
def api_merged_models():
    """列出所有已合并导出的模型"""
    def _scan(path: Path) -> list[dict]:
        result = []
        if not path.exists():
            return result
        for d in sorted(path.iterdir(), key=lambda x: x.stat().st_mtime if x.is_dir() else 0, reverse=True):
            if not d.is_dir():
                continue
            has_config = (d / "config.json").exists()
            has_safetensors = any(d.glob("*.safetensors"))
            if not (has_config or has_safetensors):
                continue
            total_size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            result.append({
                "name": d.name,
                "path": str(d.resolve()),
                "size": f"{total_size / 1024**3:.1f}GB" if total_size > 1024**3 else f"{total_size / 1024**2:.1f}MB",
                "modified": str(datetime.fromtimestamp(d.stat().st_mtime))[:19],
            })
        return result

    models = _scan(PROJECT_ROOT / "output" / "merged")
    return ApiResponse.ok(data=models[:50])


class VerifyChatRequest(BaseModel):
    model_path: str
    question: str
    history: list = []
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 512


def _get_chat_cache():
    if not hasattr(_get_chat_cache, "_cache"):
        _get_chat_cache._cache = {}
    return _get_chat_cache._cache


def _load_model(model_path: str) -> tuple:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path, trust_remote_code=True, local_files_only=True,
        torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
        device_map="auto" if device == "cuda" else None,
    )
    if device == "cpu":
        model = model.to(device)
    model.eval()
    return model, tokenizer, device


@router.post("/verify-load")
def api_verify_load(req: VerifyChatRequest):
    """加载模型到显存"""
    import gc, torch
    model_path = req.model_path
    cache = _get_chat_cache()
    if model_path in cache:
        return ApiResponse.ok(message="模型已加载", data={"device": cache[model_path][2]})
    try:
        model, tokenizer, device = _load_model(model_path)
        cache[model_path] = (model, tokenizer, device)
        if device == "cuda":
            used = torch.cuda.memory_allocated() / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            return ApiResponse.ok(message=f"加载成功 (显存: {used:.1f}G/{total:.1f}G)", data={"device": device, "vram_used": round(used, 1), "vram_total": round(total, 1)})
        return ApiResponse.ok(message="加载成功 (CPU)", data={"device": device})
    except Exception as e:
        return ApiResponse.fail(message=str(e)[:200])


@router.post("/verify-unload")
def api_verify_unload(req: VerifyChatRequest):
    """卸载模型释放显存"""
    import gc, torch
    model_path = req.model_path
    cache = _get_chat_cache()
    if model_path not in cache:
        return ApiResponse.ok(message="模型未加载")
    model, tokenizer, device = cache.pop(model_path)
    del model, tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    vram = torch.cuda.memory_allocated() / 1024**3 if torch.cuda.is_available() else 0
    return ApiResponse.ok(message=f"已卸载 (当前显存占用: {vram:.1f}G)", data={"vram_free": round(vram, 1)})


@router.get("/verify-status/{model_path:path}")
def api_verify_status(model_path: str):
    """查询模型加载状态"""
    import torch
    cache = _get_chat_cache()
    key = None
    for k in cache:
        if model_path in k or k in model_path:
            key = k
            break
    if key and key in cache:
        _, _, device = cache[key]
        vram = 0
        if device == "cuda":
            vram = torch.cuda.memory_allocated() / 1024**3
        return ApiResponse.ok(data={"loaded": True, "device": device, "vram": round(vram, 1)})
    return ApiResponse.ok(data={"loaded": False})


@router.post("/verify-chat")
def api_verify_chat(req: VerifyChatRequest):
    """使用本地模型进行推理验证"""
    try:
        import torch
        from transformers import AutoTokenizer

        cache = _get_chat_cache()
        model_key = req.model_path

        if model_key not in cache:
            model, tokenizer, device = _load_model(model_key)
            cache[model_key] = (model, tokenizer, device)
        else:
            model, tokenizer, device = cache[model_key]

        messages = []
        for h in (req.history or []):
            messages.append({"role": "user", "content": h.get("user", "")})
            messages.append({"role": "assistant", "content": h.get("assistant", "")})
        messages.append({"role": "user", "content": req.question})

        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs, max_new_tokens=req.max_tokens,
                temperature=req.temperature, top_p=req.top_p,
                do_sample=True if req.temperature > 0 else False,
                pad_token_id=tokenizer.eos_token_id,
            )
        reply = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return ApiResponse.ok(data={"reply": reply.strip()})
    except Exception as e:
        return ApiResponse.fail(message=str(e)[:200])


@router.get("/verify-models")
def api_verify_models():
    """获取可用于在线验证的模型列表"""
    def _scan_models(folder: Path) -> list[dict]:
        result = []
        if not folder.exists():
            return result
        for d in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime if x.is_dir() else 0, reverse=True):
            if not d.is_dir():
                continue
            has_config = (d / "config.json").exists()
            has_safetensors = any(d.glob("*.safetensors"))
            if not (has_config or has_safetensors):
                continue
            total_size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            result.append({
                "name": d.name,
                "path": str(d.resolve()),
                "size": f"{total_size / 1024**3:.1f}GB" if total_size > 1024**3 else f"{total_size / 1024**2:.1f}MB",
            })
        return result

    local = _scan_models(PROJECT_ROOT / "models")
    merged = _scan_models(PROJECT_ROOT / "output" / "merged")
    return ApiResponse.ok(data={"local": local, "merged": merged})


@router.get("/lora-models")
def api_lora_models():
    """列出所有 LoRA 任务"""
    output_dir = PROJECT_ROOT / "output"
    lora_tasks = []

    for d in sorted(output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name == "merged":
            continue
        ckpts = sorted(d.glob("checkpoint-*"))
        if not ckpts:
            continue

        task = list(filter(lambda t: t["task_id"] == d.name, list_tasks()))
        config = task[0].get("config", {}) if task else {}

        merged_candidates = [output_dir / "merged" / d.name, d / "merged"]
        is_merged = False
        merged_path = ""
        for md in merged_candidates:
            if md.is_dir() and any(md.glob("*.safetensors")):
                is_merged = True
                merged_path = str(md.resolve())
                break

        lora_tasks.append({
            "task_id": d.name,
            "name": d.name,
            "model": config.get("base_model", str(d.resolve())),
            "config": config,
            "latest_ckpt": ckpts[-1].name,
            "is_merged": is_merged,
            "merged_path": merged_path,
            "status": "completed",
            "created_at": str(datetime.fromtimestamp(d.stat().st_mtime))[:19],
        })

    return ApiResponse.ok(data=lora_tasks)


@router.post("/export")
def api_export_model(config: ExportConfig):
    """导出/合并 LoRA 模型（后台运行）"""
    import subprocess, threading

    task = get_task(config.task_id)
    if not task:
        return ApiResponse.fail(message="任务不存在")

    base_model = task.get("model", "") or task.get("config", {}).get("base_model", "")
    if not base_model:
        return ApiResponse.fail(message="未找到基座模型路径")

    output_dir = PROJECT_ROOT / "output" / config.task_id
    checkpoints = sorted(output_dir.glob("checkpoint-*"))
    if not checkpoints:
        return ApiResponse.fail(message=f"未找到 checkpoint: {output_dir}")

    last_ckpt = checkpoints[-1]
    export_dir = config.export_dir.strip() if config.export_dir else str(output_dir / "merged")
    if not os.path.isabs(export_dir):
        export_dir = str(PROJECT_ROOT / export_dir)
    os.makedirs(export_dir, exist_ok=True)
    job_id = f"export_{config.task_id}"

    _export_jobs[job_id] = {"status": "running", "progress": 10, "dir": export_dir, "msg": "启动中..."}

    def _run_export():
        try:
            _export_jobs[job_id]["progress"] = 20
            _export_jobs[job_id]["msg"] = "正在加载模型..."
            cmd = [
                sys.executable, "-m", "llamafactory.cli", "export",
                "--model_name_or_path", base_model,
                "--adapter_name_or_path", str(last_ckpt),
                "--template", task.get("config", {}).get("template", "default"),
                "--export_dir", export_dir,
                "--export_size", str(config.export_size),
            ]
            env = os.environ.copy()
            env["HF_HUB_OFFLINE"] = "1"
            _export_jobs[job_id]["progress"] = 30
            _export_jobs[job_id]["msg"] = "正在合并 LoRA 权重..."

            process = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for i, line in enumerate(process.stdout):
                line_s = line.strip()
                if i % 10 == 0:
                    _export_jobs[job_id]["progress"] = min(90, 30 + i // 2)
                print(f"[Export] {line_s}")
            process.wait()

            if process.returncode == 0:
                _export_jobs[job_id] = {"status": "done", "progress": 100, "dir": export_dir, "msg": "导出完成"}
            else:
                _export_jobs[job_id] = {"status": "error", "progress": 0, "dir": export_dir, "msg": "导出失败"}
        except Exception as e:
            _export_jobs[job_id] = {"status": "error", "progress": 0, "dir": export_dir, "msg": str(e)[:100]}

    threading.Thread(target=_run_export, daemon=True).start()
    return ApiResponse.ok(data={"job_id": job_id, "export_dir": export_dir}, message="导出中...")


@router.get("/export/status/{job_id}")
def api_export_status(job_id: str):
    """查询导出进度"""
    job = _export_jobs.get(job_id)
    if not job:
        return ApiResponse.fail(message="任务不存在")
    return ApiResponse.ok(data=job)


@router.post("/tasks/{task_id}/resume")
def api_resume_task(task_id: str):
    """用原参数重新启动训练"""
    task = get_task(task_id)
    if not task:
        return ApiResponse.fail(message="任务不存在")
    config = task.get("config", {})
    if not config:
        return ApiResponse.fail(message="无训练配置")
    new_task = create_task(config)
    return ApiResponse.ok(message="训练已重新启动", data={"task_id": new_task["task_id"]})


@router.get("/models")
def api_supported_models():
    """获取模型列表"""
    from app.services.model_service import get_local_models

    local_models = get_local_models()
    local_names = {m["name"] for m in local_models}
    local_paths = {m["name"]: m["path"] for m in local_models}

    models = []
    seen = set()
    for m in local_models:
        seen.add(m["name"])
        models.append({
            "name": m["name"],
            "huggingface": m["name"],
            "modelscope": "",
            "local": True,
            "local_path": m["path"],
        })

    for m in _MODEL_CACHE:
        if m["name"] not in seen:
            seen.add(m["name"])
            is_local = m["name"] in local_names or m["huggingface"] in local_names
            models.append({
                "name": m["name"],
                "huggingface": m["huggingface"],
                "modelscope": m.get("modelscope", ""),
                "local": is_local,
                "local_path": local_paths.get(m["name"], ""),
            })

    return ApiResponse.ok(data={"models": models, "local_count": len(local_models), "total_count": len(models)})


@router.get("/gpu")
def api_gpu_info():
    """获取 GPU 状态"""
    gpus = get_gpu_info()
    return ApiResponse.ok(data=gpus)


@router.get("/dashboard")
def api_dashboard():
    """获取仪表盘统计数据"""
    from app.services.gpu_service import get_system_info

    sys_info = get_system_info()
    tasks = list_tasks()
    running = sum(1 for t in tasks if t["status"] == "running")
    completed = sum(1 for t in tasks if t["status"] == "completed")

    return ApiResponse.ok(data={
        "training_running": running,
        "training_completed": completed,
        "gpu_utilization": sys_info.get("gpu_utilization_avg", 0),
        "recent_tasks": [
            {
                "name": t["name"],
                "type": t["type"],
                "model": t["model"],
                "status": _status_label(t["status"]),
                "time": t["created_at"],
            }
            for t in tasks[:5]
        ],
    })


# ──────────────────────────────────────────────
# 训练数据集管理
# ──────────────────────────────────────────────

_DATASET_INFO_PATH = PROJECT_ROOT / "data" / "dataset_info.json"
_DATASET_DIR = PROJECT_ROOT / "data"
_dataset_lock = threading.Lock()


def _load_dataset_info() -> dict:
    """加载 dataset_info.json"""
    if _DATASET_INFO_PATH.exists():
        try:
            return json.loads(_DATASET_INFO_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_dataset_info(info: dict):
    """保存 dataset_info.json"""
    _DATASET_INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DATASET_INFO_PATH.write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _count_samples(file_path: Path) -> int:
    """统计数据集样本数"""
    try:
        text = file_path.read_text(encoding="utf-8")
        if file_path.suffix == ".jsonl":
            return sum(1 for line in text.strip().split("\n") if line.strip())
        elif file_path.suffix == ".json":
            data = json.loads(text)
            return len(data) if isinstance(data, list) else 1
        elif file_path.suffix == ".txt":
            return sum(1 for line in text.strip().split("\n") if line.strip())
    except Exception:
        pass
    return 0


def _detect_format(file_path: Path) -> str:
    """检测数据格式: alpaca / sharegpt"""
    try:
        text = file_path.read_text(encoding="utf-8")
        if file_path.suffix == ".jsonl":
            first_line = text.strip().split("\n")[0]
            obj = json.loads(first_line)
        elif file_path.suffix == ".json":
            data = json.loads(text)
            obj = data[0] if isinstance(data, list) else data
        else:
            return "alpaca"

        if "conversations" in obj or "messages" in obj:
            return "sharegpt"
        return "alpaca"
    except Exception:
        return "alpaca"


@router.get("/datasets")
def api_list_training_datasets():
    """列出所有可用于训练的数据集（来自 data/dataset_info.json 中的本地文件）"""
    with _dataset_lock:
        info = _load_dataset_info()

    datasets = []
    for name, meta in info.items():
        file_name = meta.get("file_name", "")
        if not file_name:
            # 远程数据集（hf_hub_url 等），跳过
            continue

        file_path = _DATASET_DIR / file_name
        samples = _count_samples(file_path) if file_path.exists() else 0
        formatting = meta.get("formatting", "alpaca")

        datasets.append({
            "name": name,
            "file_name": file_name,
            "formatting": formatting,
            "samples": samples,
            "exists": file_path.exists(),
            "size": file_path.stat().st_size if file_path.exists() else 0,
            "columns": meta.get("columns", {}),
            "tags": meta.get("tags", {}),
        })

    return ApiResponse.ok(data=datasets)


@router.post("/datasets/upload")
def api_upload_training_dataset(
    file: UploadFile = File(...),
    dataset_name: str = Form(...),
    description: str = Form(""),
):
    """上传本地训练数据集文件到 data/ 目录并注册到 dataset_info.json"""
    if not dataset_name.strip():
        return ApiResponse.fail(message="数据集名称不能为空")

    # 验证文件类型
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".jsonl", ".json", ".txt"):
        return ApiResponse.fail(message="仅支持 .jsonl / .json / .txt 格式")

    # 读取文件内容
    content = file.file.read()
    if len(content) > 500 * 1024 * 1024:  # 500MB limit
        return ApiResponse.fail(message="文件大小不能超过 500MB")

    # 保存到 data/ 目录
    safe_name = dataset_name.strip().replace(" ", "_").replace("/", "_")
    dest_filename = f"{safe_name}{suffix}"
    dest_path = _DATASET_DIR / dest_filename
    _DATASET_DIR.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(content)

    # 检测格式和统计
    formatting = _detect_format(dest_path)
    samples = _count_samples(dest_path)

    # 注册到 dataset_info.json
    with _dataset_lock:
        info = _load_dataset_info()
        entry: dict = {"file_name": dest_filename}
        if formatting != "alpaca":
            entry["formatting"] = formatting
        if description:
            entry["description"] = description
        info[dataset_name.strip()] = entry
        _save_dataset_info(info)

    return ApiResponse.ok(
        data={
            "name": dataset_name.strip(),
            "file_name": dest_filename,
            "formatting": formatting,
            "samples": samples,
            "size": len(content),
        },
        message=f"上传成功，共 {samples} 条样本",
    )


@router.post("/datasets/register")
def api_register_governance_dataset(
    body: dict,
):
    """将数据治理模块导出的数据集注册到训练数据集中

    请求体: {
        "name": "数据集名称",
        "file_name": "xxx.jsonl",  # data/ 下的文件名
        "formatting": "alpaca",   # 可选
        "description": "...",      # 可选
    }
    """
    name = body.get("name", "").strip()
    file_name = body.get("file_name", "").strip()
    if not name or not file_name:
        return ApiResponse.fail(message="name 和 file_name 不能为空")

    file_path = _DATASET_DIR / file_name
    if not file_path.exists():
        return ApiResponse.fail(message=f"文件 {file_name} 不存在于 data/ 目录")

    formatting = body.get("formatting") or _detect_format(file_path)
    samples = _count_samples(file_path)

    with _dataset_lock:
        info = _load_dataset_info()
        entry: dict = {"file_name": file_name}
        if formatting != "alpaca":
            entry["formatting"] = formatting
        desc = body.get("description", "")
        if desc:
            entry["description"] = desc
        info[name] = entry
        _save_dataset_info(info)

    return ApiResponse.ok(
        data={"name": name, "file_name": file_name, "samples": samples, "formatting": formatting},
        message=f"注册成功，共 {samples} 条样本",
    )


@router.delete("/datasets/{dataset_name}")
def api_delete_training_dataset(dataset_name: str):
    """删除训练数据集（从 dataset_info.json 移除，并删除本地文件）"""
    with _dataset_lock:
        info = _load_dataset_info()
        if dataset_name not in info:
            return ApiResponse.fail(message=f"数据集 '{dataset_name}' 不存在")

        entry = info[dataset_name]
        file_name = entry.get("file_name", "")

        # 删除文件
        if file_name:
            file_path = _DATASET_DIR / file_name
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception:
                    pass

        # 从 dataset_info.json 移除
        del info[dataset_name]
        _save_dataset_info(info)

    return ApiResponse.ok(message=f"数据集 '{dataset_name}' 已删除")


@router.get("/datasets/{dataset_name}/preview")
def api_preview_training_dataset(dataset_name: str, limit: int = 20):
    """预览训练数据集内容"""
    with _dataset_lock:
        info = _load_dataset_info()

    if dataset_name not in info:
        return ApiResponse.fail(message=f"数据集 '{dataset_name}' 不存在")

    entry = info[dataset_name]
    file_name = entry.get("file_name", "")
    if not file_name:
        return ApiResponse.fail(message="该数据集为远程数据集，不支持预览")

    file_path = _DATASET_DIR / file_name
    if not file_path.exists():
        return ApiResponse.fail(message="数据文件不存在")

    try:
        text = file_path.read_text(encoding="utf-8")
        items = []
        if file_path.suffix == ".jsonl":
            for i, line in enumerate(text.strip().split("\n")):
                if i >= limit:
                    break
                if line.strip():
                    items.append(json.loads(line))
        elif file_path.suffix == ".json":
            data = json.loads(text)
            if isinstance(data, list):
                items = data[:limit]
            else:
                items = [data]
        elif file_path.suffix == ".txt":
            for i, line in enumerate(text.strip().split("\n")):
                if i >= limit:
                    break
                if line.strip():
                    items.append({"text": line.strip()})

        return ApiResponse.ok(data=items)
    except Exception as e:
        return ApiResponse.fail(message=f"预览失败: {str(e)[:100]}")


@router.post("/datasets/export-from-governance")
def api_export_from_governance(body: dict):
    """将数据治理模块的数据集导出为 JSONL 并注册到训练数据集

    请求体: {
        "project_id": "uuid",
        "dataset_id": "uuid",
        "train_name": "数据集名称",
        "data_format": "alpaca",       # alpaca / sharegpt / llama_factory / dpo
        "split_strategy": "random",     # random / file
        "train_ratio": 0.9,
        "val_ratio": 0.05,
        "test_ratio": 0.05,
        "seed": 42,
        "batch_id": "uuid (optional)"
    }

    直接在后端完成：查询问答对 → 划分 → 写 JSONL 到 data/ → 注册到 dataset_info.json
    """
    from uuid import UUID
    from sqlalchemy import select
    from app.models.models import Dataset as GovDataset, Question

    project_id = body.get("project_id", "")
    dataset_id = body.get("dataset_id", "")
    train_name = body.get("train_name", "").strip()
    data_format = body.get("data_format", "alpaca")
    split_strategy = body.get("split_strategy", "random")
    train_ratio = float(body.get("train_ratio", 0.9))
    val_ratio = float(body.get("val_ratio", 0.05))
    test_ratio = float(body.get("test_ratio", 0.05))
    seed = int(body.get("seed", 42))
    batch_id = body.get("batch_id", "")

    if not project_id or not dataset_id or not train_name:
        return ApiResponse.fail(message="project_id、dataset_id、train_name 不能为空")

    # 直接在同步路由中创建事件循环执行异步操作
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_do_export_governance(
            project_id, dataset_id, train_name, data_format,
            split_strategy, train_ratio, val_ratio, test_ratio, seed, batch_id
        ))
        loop.close()
        return result
    except Exception as e:
        return ApiResponse.fail(message=f"导出失败: {str(e)[:200]}")


async def _do_export_governance(
    project_id: str, dataset_id: str, train_name: str,
    data_format: str, split_strategy: str,
    train_ratio: float, val_ratio: float, test_ratio: float,
    seed: int, batch_id: str,
) -> ApiResponse:
    """异步执行：从数据库查问答 → 划分 → 写 JSONL → 注册"""
    import random as rng_module
    from uuid import UUID
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal as async_session_factory
    from app.models.models import Dataset as GovDataset, Question

    async with async_session_factory() as db:
        # 查询数据集
        try:
            ds_uuid = UUID(dataset_id)
        except ValueError:
            return ApiResponse.fail(message="dataset_id 格式无效")

        dataset = await db.get(GovDataset, ds_uuid)
        if not dataset or str(dataset.project_id) != project_id:
            return ApiResponse.fail(message="数据集不存在或不属于该项目")

        # 确定批次
        extra = dataset.extra_data or {}
        effective_batch_id = batch_id or extra.get("batch_id", "")
        if not effective_batch_id:
            return ApiResponse.fail(message="未指定问答批次，无法导出")

        try:
            batch_uuid = UUID(effective_batch_id) if isinstance(effective_batch_id, str) else effective_batch_id
        except ValueError:
            return ApiResponse.fail(message="批次ID格式无效")

        # 查询问答对
        query = (
            select(Question)
            .where(
                Question.project_id == UUID(project_id),
                Question.batch_id == batch_uuid,
                Question.answer_status == "completed",
            )
            .order_by(Question.created_at)
        )
        result = await db.execute(query)
        questions = list(result.scalars().all())

        if not questions:
            return ApiResponse.fail(message="该批次没有已完成的问答对")

    # 格式化函数
    def _to_alpaca(q):
        return {"instruction": q.content or "", "input": "", "output": q.answer or ""}

    def _to_sharegpt(q):
        return {"conversations": [
            {"from": "human", "value": q.content or ""},
            {"from": "gpt", "value": q.answer or ""},
        ]}

    def _to_dpo(q):
        meta = q.generation_metadata or {}
        return {
            "instruction": q.content or "",
            "input": "",
            "chosen": q.answer or "",
            "rejected": meta.get("rejected_answer", ""),
        }

    format_fn = {"alpaca": _to_alpaca, "sharegpt": _to_sharegpt,
                 "llama_factory": _to_alpaca, "dpo": _to_dpo}.get(data_format, _to_alpaca)

    # 划分
    total_r = train_ratio + val_ratio + test_ratio
    train_r = train_ratio / total_r
    val_r = val_ratio / total_r

    if split_strategy == "file":
        # 按文件划分
        file_groups = {}
        for q in questions:
            meta = q.generation_metadata or {}
            fname = meta.get("filename", "unknown")
            file_groups.setdefault(fname, []).append(q)
        rng = rng_module.Random(seed)
        file_names = list(file_groups.keys())
        rng.shuffle(file_names)
        train, val, test_data = [], [], []
        train_target = int(len(questions) * train_r)
        val_target = int(len(questions) * val_r)
        current_count = 0
        for fname in file_names:
            group = file_groups[fname]
            if current_count < train_target:
                train.extend(group)
            elif current_count < train_target + val_target:
                val.extend(group)
            else:
                test_data.extend(group)
            current_count += len(group)
    else:
        # 随机划分
        rng = rng_module.Random(seed)
        rng.shuffle(questions)
        total = len(questions)
        train_end = int(total * train_r)
        val_end = train_end + int(total * val_r)
        train = questions[:train_end]
        val = questions[train_end:val_end]
        test_data = questions[val_end:]

    # 写 JSONL 到 data/ 目录
    _DATASET_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = train_name.replace(" ", "_").replace("/", "_")
    train_file = _DATASET_DIR / f"{safe_name}.jsonl"

    with open(train_file, "w", encoding="utf-8") as f:
        for q in train:
            f.write(json.dumps(format_fn(q), ensure_ascii=False) + "\n")

    # 如果有验证集，也写一个 val 文件
    val_file = None
    if val:
        val_file = _DATASET_DIR / f"{safe_name}_val.jsonl"
        with open(val_file, "w", encoding="utf-8") as f:
            for q in val:
                f.write(json.dumps(format_fn(q), ensure_ascii=False) + "\n")

    # 注册到 dataset_info.json
    train_count = len(train)
    val_count = len(val)
    test_count = len(test_data)

    with _dataset_lock:
        info = _load_dataset_info()
        entry = {"file_name": train_file.name}
        if data_format not in ("alpaca", "llama_factory"):
            entry["formatting"] = data_format
        info[train_name] = entry

        # 验证集也注册（可选）
        if val_file:
            val_entry = {"file_name": val_file.name}
            if data_format not in ("alpaca", "llama_factory"):
                val_entry["formatting"] = data_format
            info[train_name + "_val"] = val_entry

        _save_dataset_info(info)

    return ApiResponse.ok(
        data={
            "name": train_name,
            "train_count": train_count,
            "val_count": val_count,
            "test_count": test_count,
            "file_name": train_file.name,
        },
        message=f"导出注册成功！训练集 {train_count} 条，验证集 {val_count} 条，测试集 {test_count} 条",
    )


@router.websocket("/ws/{task_id}")
async def ws_train_monitor(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送训练状态"""
    await websocket.accept()

    if task_id not in _ws_clients:
        _ws_clients[task_id] = set()
    _ws_clients[task_id].add(websocket)

    try:
        last_log_count = 0
        last_loss_count = 0
        while True:
            task = get_task(task_id)
            if not task:
                await websocket.send_json({"type": "error", "msg": "任务不存在"})
                break

            current_logs = task.get("logs", [])
            if len(current_logs) > last_log_count:
                new_logs = current_logs[last_log_count:]
                last_log_count = len(current_logs)
                for log in new_logs:
                    await websocket.send_json({"type": "log", "data": log})

            loss_history = task.get("loss_history", [])
            if len(loss_history) > last_loss_count:
                new_losses = loss_history[last_loss_count:]
                last_loss_count = len(loss_history)
                for loss_val in new_losses:
                    await websocket.send_json({"type": "loss", "value": loss_val})

            await websocket.send_json({
                "type": "status",
                "data": {
                    "status": task["status"],
                    "progress": task.get("progress", 0),
                    "current_loss": task.get("current_loss"),
                    "eta": task.get("eta"),
                },
            })

            gpus = get_gpu_info()
            if gpus:
                await websocket.send_json({"type": "gpu", "data": gpus})

            if task["status"] in ("completed", "failed", "cancelled"):
                await websocket.send_json({"type": "done", "status": task["status"]})
                break

            await asyncio.sleep(2)

    except WebSocketDisconnect:
        pass
    finally:
        if task_id in _ws_clients:
            _ws_clients[task_id].discard(websocket)


def _status_label(status: str) -> str:
    labels = {
        "pending": "排队中",
        "running": "训练中",
        "completed": "已完成",
        "failed": "失败",
        "cancelled": "已取消",
    }
    return labels.get(status, status)


_MODEL_CACHE_JSON = PROJECT_ROOT / "data" / "_model_cache.json"


def init_model_cache():
    """初始化模型缓存，优先读本地 JSON 缓存，避免每次启动都 import llamafactory"""
    # 优先读缓存文件
    if _MODEL_CACHE_JSON.exists():
        try:
            data = json.loads(_MODEL_CACHE_JSON.read_text(encoding="utf-8"))
            _MODEL_CACHE.clear()
            _MODEL_CACHE.extend(data)
            print(f"[Backend] 已加载 {len(_MODEL_CACHE)} 个模型 (from cache)")
            return
        except Exception:
            pass

    # 缓存不存在则从 llamafactory 加载并写入缓存
    try:
        from llamafactory.extras.constants import SUPPORTED_MODELS
        _MODEL_CACHE.clear()
        _MODEL_CACHE.extend([
            {"name": name, "huggingface": paths.get("default", ""), "modelscope": paths.get("modelscope", "")}
            for name, paths in SUPPORTED_MODELS.items()
        ])
        # 写入缓存
        _MODEL_CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
        _MODEL_CACHE_JSON.write_text(json.dumps(_MODEL_CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Backend] 已加载 {len(_MODEL_CACHE)} 个模型 (from llamafactory, cached)")
    except Exception as e:
        print(f"[Backend] 模型列表加载失败: {e}, 使用内置列表")
        _MODEL_CACHE.clear()
        _MODEL_CACHE.extend(_builtin_models())


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
