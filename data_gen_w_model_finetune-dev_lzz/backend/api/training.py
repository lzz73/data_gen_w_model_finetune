"""
训练管理 API
提供前端 training/TrainWorkbench、TrainMonitor 页面所需接口
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional
import sys
import os
import asyncio
import json
from datetime import datetime
from pathlib import Path

from ..services.training_service import (
    list_tasks,
    get_task,
    create_task,
    cancel_task,
)
from ..services.task_runner import cancel_training
from ..services.gpu_service import get_gpu_info

router = APIRouter()

# WebSocket 连接池（用于实时推送训练状态）
_ws_clients: dict[str, set[WebSocket]] = {}


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
    """获取所有训练任务列表（Dashboard 页面的最近任务）"""
    return {"code": 0, "data": list_tasks()}


@router.get("/tasks/{task_id}")
def api_get_task(task_id: str):
    """获取单个训练任务详情"""
    task = get_task(task_id)
    if not task:
        return {"code": -1, "message": "任务不存在"}
    return {"code": 0, "data": task}


@router.post("/tasks")
def api_create_task(config: TrainConfig):
    """
    创建并启动训练任务
    TrainWorkbench.vue 的"提交训练"按钮调用此接口
    """
    task = create_task(config.model_dump())
    return {
        "code": 0,
        "message": "训练任务已提交",
        "data": {"task_id": task["task_id"]},
    }


@router.post("/tasks/fix-status")
def api_fix_status():
    """修正所有训练任务的状态（根据 output 目录是否有 checkpoint 判断是否已完成）"""
    import os
    from datetime import datetime
    from pathlib import Path
    from ..services.training_service import _tasks, _task_lock

    ROOT = Path(__file__).resolve().parent.parent.parent
    fixed = 0
    with _task_lock:
        for tid, task in _tasks.items():
            if task["status"] in ("running", "pending"):
                output_dir = ROOT / "output" / tid
                if output_dir.exists() and any(output_dir.glob("checkpoint-*")):
                    task["status"] = "completed"
                    task["progress"] = 100
                    task["eta"] = "00:00"
                    if not task.get("finished_at"):
                        task["finished_at"] = datetime.now().isoformat()
                    # 给 Web 日志补一条"训练完成"，避免用户看不到结论
                    task.setdefault("logs", []).append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "msg": "[INFO] 训练完成！（状态已根据 checkpoint 自动修正）",
                        "type": "info",
                    })
                    fixed += 1
    # 持久化到磁盘
    try:
        from ..services.training_service import _save_tasks
        _save_tasks()
    except Exception:
        pass
    return {"code": 0, "message": f"已修正 {fixed} 个任务状态", "fixed": fixed}


@router.post("/tasks/{task_id}/cancel")
def api_cancel_task(task_id: str):
    """取消/中断训练任务"""
    killed = cancel_training(task_id)
    ok = cancel_task(task_id)
    return {"code": 0 if (ok or killed) else -1, "message": "已中断" if killed else ("已取消" if ok else "任务不存在")}


class ExportConfig(BaseModel):
    task_id: str = ""
    export_dir: str = ""
    export_size: int = 5


# 导出任务状态追踪
_export_jobs: dict = {}


@router.get("/merged-models")
def api_merged_models():
    """列出所有已合并导出的模型（直接扫描目录）"""
    ROOT = Path(__file__).resolve().parent.parent.parent

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

    models = _scan(ROOT / "output" / "merged")
    return {"code": 0, "data": models[:50]}


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
        return {"code": 0, "message": "模型已加载", "data": {"device": cache[model_path][2]}}
    try:
        model, tokenizer, device = _load_model(model_path)
        cache[model_path] = (model, tokenizer, device)
        # 打印显存占用
        if device == "cuda":
            used = torch.cuda.memory_allocated() / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            return {"code": 0, "message": f"加载成功 (显存: {used:.1f}G/{total:.1f}G)", "data": {"device": device, "vram_used": round(used, 1), "vram_total": round(total, 1)}}
        return {"code": 0, "message": "加载成功 (CPU)", "data": {"device": device}}
    except Exception as e:
        return {"code": -1, "message": str(e)[:200]}


@router.post("/verify-unload")
def api_verify_unload(req: VerifyChatRequest):
    """卸载模型释放显存"""
    import gc, torch
    model_path = req.model_path
    cache = _get_chat_cache()
    if model_path not in cache:
        return {"code": 0, "message": "模型未加载"}
    model, tokenizer, device = cache.pop(model_path)
    del model, tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    vram = torch.cuda.memory_allocated() / 1024**3 if torch.cuda.is_available() else 0
    return {"code": 0, "message": f"已卸载 (当前显存占用: {vram:.1f}G)", "data": {"vram_free": round(vram, 1)}}


@router.get("/verify-status/{model_path}")
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
        return {"code": 0, "data": {"loaded": True, "device": device, "vram": round(vram, 1)}}
    return {"code": 0, "data": {"loaded": False}}


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
        return {"code": 0, "data": {"reply": reply.strip()}}
    except Exception as e:
        return {"code": -1, "message": str(e)[:200]}


@router.get("/verify-models")
def api_verify_models():
    """获取可用于在线验证的模型列表（直接扫描目录）"""
    ROOT = Path(__file__).resolve().parent.parent.parent

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

    local = _scan_models(ROOT / "models")
    merged = _scan_models(ROOT / "output" / "merged")

    return {"code": 0, "data": {"local": local, "merged": merged}}


@router.get("/lora-models")
def api_lora_models():
    """列出所有 LoRA 任务（直接扫描 output 目录）"""
    from pathlib import Path
    ROOT = Path(__file__).resolve().parent.parent.parent
    output_dir = ROOT / "output"
    lora_tasks = []

    for d in sorted(output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name == "merged":
            continue
        ckpts = sorted(d.glob("checkpoint-*"))
        if not ckpts:
            continue

        # 尝试从 tasks_history.json 获取额外信息
        task = list(filter(lambda t: t["task_id"] == d.name, list_tasks()))
        config = task[0].get("config", {}) if task else {}

        # 检查是否已合并
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

    return {"code": 0, "data": lora_tasks}


@router.post("/export")
def api_export_model(config: ExportConfig):
    """导出/合并 LoRA 模型（后台运行）"""
    import subprocess, threading
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent.parent

    task = get_task(config.task_id)
    if not task:
        return {"code": -1, "message": "任务不存在"}

    base_model = task.get("model", "") or task.get("config", {}).get("base_model", "")
    if not base_model:
        return {"code": -1, "message": "未找到基座模型路径"}

    output_dir = ROOT / "output" / config.task_id
    checkpoints = sorted(output_dir.glob("checkpoint-*"))
    if not checkpoints:
        return {"code": -1, "message": f"未找到 checkpoint: {output_dir}"}

    last_ckpt = checkpoints[-1]
    # 统一存放路径: output/merged/{task_id}/
    export_dir = config.export_dir.strip() if config.export_dir else str(output_dir / "merged")
    # 如果是相对路径，转为绝对路径
    if not os.path.isabs(export_dir):
        export_dir = str(ROOT / export_dir)
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

            process = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for i, line in enumerate(process.stdout):
                line_s = line.strip()
                # 每 10 行递增进度
                if i % 10 == 0:
                    _export_jobs[job_id]["progress"] = min(90, 30 + i // 2)
                print(f"[Export] {line_s}")
            process.wait()

            if process.returncode == 0:
                _export_jobs[job_id] = {"status": "done", "progress": 100, "dir": export_dir, "msg": "导出完成"}
                print(f"[Export] 成功: {export_dir}")
            else:
                _export_jobs[job_id] = {"status": "error", "progress": 0, "dir": export_dir, "msg": "导出失败"}
        except Exception as e:
            _export_jobs[job_id] = {"status": "error", "progress": 0, "dir": export_dir, "msg": str(e)[:100]}

    threading.Thread(target=_run_export, daemon=True).start()
    return {"code": 0, "data": {"job_id": job_id, "export_dir": export_dir}, "message": "导出中..."}


@router.get("/export/status/{job_id}")
def api_export_status(job_id: str):
    """查询导出进度"""
    job = _export_jobs.get(job_id)
    if not job:
        return {"code": -1, "message": "任务不存在"}
    return {"code": 0, "data": job}


@router.post("/tasks/{task_id}/resume")
def api_resume_task(task_id: str):
    """用原参数重新启动训练"""
    task = get_task(task_id)
    if not task:
        return {"code": -1, "message": "任务不存在"}
    config = task.get("config", {})
    if not config:
        return {"code": -1, "message": "无训练配置"}
    new_task = create_task(config)
    return {"code": 0, "message": "训练已重新启动", "data": {"task_id": new_task["task_id"]}}


@router.get("/models")
def api_supported_models():
    """获取模型列表，标注本地是否已下载 + 支持自定义路径"""
    from ..main import _MODEL_CACHE
    from ..services.model_service import get_local_models

    local_models = get_local_models()
    local_names = {m["name"] for m in local_models}
    local_paths = {m["name"]: m["path"] for m in local_models}

    # 合并：已下载的在前
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

    return {"code": 0, "data": models, "local_count": len(local_models), "total_count": len(models)}


@router.get("/gpu")
def api_gpu_info():
    """获取 GPU 状态（TrainWorkbench 的 GPU 选择页面 & TrainMonitor 的 GPU 监控）"""
    gpus = get_gpu_info()
    return {"code": 0, "data": gpus}


@router.get("/dashboard")
def api_dashboard():
    """获取仪表盘统计数据"""
    from ..services.dataset_service import get_dashboard_stats
    from ..services.gpu_service import get_system_info

    ds_stats = get_dashboard_stats()
    sys_info = get_system_info()
    tasks = list_tasks()
    running = sum(1 for t in tasks if t["status"] == "running")
    completed = sum(1 for t in tasks if t["status"] == "completed")

    return {
        "code": 0,
        "data": {
            "dataset_count": ds_stats["total_datasets"],
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
        },
    }


@router.websocket("/ws/{task_id}")
async def ws_train_monitor(websocket: WebSocket, task_id: str):
    """
    WebSocket 实时推送训练状态
    TrainMonitor.vue 通过此 WebSocket 获取实时 Logs/Loss/GPU
    """
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

            # 推送最新日志
            current_logs = task.get("logs", [])
            if len(current_logs) > last_log_count:
                new_logs = current_logs[last_log_count:]
                last_log_count = len(current_logs)
                for log in new_logs:
                    await websocket.send_json({"type": "log", "data": log})

            # 推送最新 loss 数据点（用于曲线实时更新）
            loss_history = task.get("loss_history", [])
            if len(loss_history) > last_loss_count:
                new_losses = loss_history[last_loss_count:]
                last_loss_count = len(loss_history)
                for loss_val in new_losses:
                    await websocket.send_json({"type": "loss", "value": loss_val})

            # 推送状态快照
            await websocket.send_json({
                "type": "status",
                "data": {
                    "status": task["status"],
                    "progress": task.get("progress", 0),
                    "current_loss": task.get("current_loss"),
                    "eta": task.get("eta"),
                },
            })

            # 推送 GPU 状态
            gpus = get_gpu_info()
            if gpus:
                await websocket.send_json({"type": "gpu", "data": gpus})

            # 训练结束则关闭连接
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
