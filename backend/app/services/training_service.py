"""
训练管理服务层
封装 llamafactory 的训练能力，管理训练任务生命周期
"""
import os
import sys
import json
import uuid
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from .training_state import _tasks, _task_lock

# 项目根目录 (platform_demo/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TASKS_FILE = BASE_DIR / "tasks_history.json"


def _generate_task_id() -> str:
    return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def list_tasks() -> list[dict]:
    """列出所有训练任务"""
    with _task_lock:
        return sorted(
            list(_tasks.values()),
            key=lambda t: t["created_at"],
            reverse=True,
        )


def get_task(task_id: str) -> Optional[dict]:
    """获取单个训练任务"""
    with _task_lock:
        return _tasks.get(task_id)


def create_task(config: dict) -> dict:
    """
    创建并启动训练任务

    config 字段:
        - mode: "sft" | "dpo" | "cpt"   (cpt 映射到 llamafactory 的 pt)
        - dataset: 数据集名称
        - base_model: 模型路径或名称
        - lr: 学习率
        - epochs: 训练轮数
        - batch_size: 批次大小
        - max_length: 截断长度
        - lora_rank: LoRA rank
        - lora_alpha: LoRA alpha
        - gpu: GPU 编号
        - preset: "quick"|"standard"|"high"|"custom"
    """
    task_id = _generate_task_id()
    now = datetime.now().isoformat()

    # 根据预设值调整参数
    preset = config.get("preset", "standard")
    preset_params = {
        "quick": {"lr": "5e-5", "epochs": 1, "batch_size": 4, "lora_rank": 8},
        "standard": {"lr": "2e-5", "epochs": 3, "batch_size": 8, "lora_rank": 16},
        "high": {"lr": "1e-5", "epochs": 5, "batch_size": 4, "lora_rank": 32},
    }
    if preset in preset_params and config.get("preset") != "custom":
        for k, v in preset_params[preset].items():
            config.setdefault(k, v)

    # 训练类型映射
    stage_map = {"sft": "sft", "dpo": "dpo", "cpt": "pt", "cot": "sft"}
    stage = stage_map.get(config.get("mode", "sft"), "sft")

    task = {
        "task_id": task_id,
        "name": f'{config.get("mode", "sft").upper()}-{_short_name(config.get("base_model", ""))}',
        "type": config.get("mode", "sft").upper(),
        "model": config.get("base_model", ""),
        "status": "pending",
        "progress": 0,
        "current_loss": None,
        "gpu_usage": None,
        "eta": None,
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "config": config,
        "logs": [],
        "loss_history": [],
    }

    with _task_lock:
        _tasks[task_id] = task

    # 持久化到磁盘
    _save_tasks()

    # 异步启动训练
    _start_training_thread(task_id, config, stage)

    return task


def _save_tasks():
    """将任务列表保存到 JSON 文件"""
    try:
        with _task_lock:
            data = {
                tid: {k: v for k, v in t.items() if k != "logs"}
                for tid, t in _tasks.items()
            }
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"[TASK] 保存任务列表失败: {e}")


def _load_tasks():
    """启动时从 JSON 文件恢复任务列表"""
    if not TASKS_FILE.exists():
        return
    try:
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        with _task_lock:
            for tid, t in data.items():
                t.setdefault("logs", [])
                t.setdefault("loss_history", [])
                _tasks[tid] = t
        print(f"[TASK] 已加载 {len(data)} 个历史训练记录")
    except Exception as e:
        print(f"[TASK] 加载任务列表失败: {e}")


# 启动时自动加载
_load_tasks()


def _start_training_thread(task_id: str, config: dict, stage: str):
    """在后台线程中启动训练"""
    def _run():
        from .task_runner import run_training_inline

        try:
            run_training_inline(task_id, config, stage)
        except Exception as e:
            with _task_lock:
                if task_id in _tasks:
                    _tasks[task_id]["status"] = "failed"
                    _tasks[task_id]["logs"].append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "msg": f"[ERROR] 训练异常: {str(e)}",
                        "type": "error",
                    })

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _short_name(path: str) -> str:
    """提取模型短名称，如 Qwen/Qwen2-7B → Qwen2-7B"""
    return path.split("/")[-1].replace("\\", "/").split("/")[-1] if path else "unknown"


def cancel_task(task_id: str) -> bool:
    """取消训练任务"""
    with _task_lock:
        if task_id in _tasks:
            _tasks[task_id]["status"] = "cancelled"
            _tasks[task_id]["logs"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "msg": "[WARN] 用户取消了训练任务",
                "type": "warn",
            })
            return True
    return False
