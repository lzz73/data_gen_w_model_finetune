"""
训练任务执行器（subprocess 版本）
- 实时捕获 llamafactory 日志并推送到 WebSocket
- 支持中断训练
"""
import sys
import os
import re
import json
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR  # 项目根目录
sys.path.insert(0, str(ROOT_DIR))

from .state import _tasks, _task_lock

# 正在运行的训练进程
_running_processes: dict = {}


def _append_log(task_id: str, msg: str, log_type: str = "info"):
    with _task_lock:
        if task_id in _tasks:
            _tasks[task_id]["logs"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "msg": msg,
                "type": log_type,
            })


def _parse_llamafactory_log(line: str, task_id: str):
    """进度/loss/eta 直接从 trainer_log.jsonl 读取，无需正则"""

    # 匹配行内嵌的 loss=xxx 格式（tqdm pipe 模式的附加信息）
    m_inline = re.search(r'\bloss=([\d.]+)', line)
    if m_inline and not m_json:
        loss_val = float(m_inline.group(1))
        lr_match = re.search(r'\blr=([\d.eE+-]+)', line)
        epoch_match = re.search(r'\bepoch=([\d.]+)', line)
        with _task_lock:
            if task_id in _tasks:
                _tasks[task_id]["current_loss"] = loss_val
                _tasks[task_id]["loss_history"].append(loss_val)
                if lr_match:
                    _tasks[task_id]["learning_rate"] = float(lr_match.group(1))
                if epoch_match:
                    _tasks[task_id]["current_epoch"] = float(epoch_match.group(1))


def run_training_subprocess(task_id: str, config: dict, stage: str):
    """用 subprocess 启动 train.py 脚本，实时捕获输出"""
    _append_log(task_id, f"[INFO] 训练任务启动: {config.get('mode', 'sft').upper()} 微调")
    _append_log(task_id, f"[INFO] 基座模型: {config.get('base_model')}")
    _append_log(task_id, f"[INFO] 数据集: {config.get('dataset')}")

    with _task_lock:
        if task_id in _tasks:
            _tasks[task_id]["status"] = "running"
            _tasks[task_id]["started_at"] = datetime.now().isoformat()

    # 离线模式
    env = os.environ.copy()
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    # GPU
    gpu = config.get("gpu", "0")
    num_gpus = config.get("num_gpus", 1) or 1
    if gpu and str(gpu) != "0":
        env["CUDA_VISIBLE_DEVICES"] = str(gpu).replace("gpu-", "")

    # 构建输出目录
    custom_dir = config.get("output_dir", "")
    output_dir = custom_dir.strip() if custom_dir and custom_dir.strip() else str(ROOT_DIR / "output" / task_id)
    finetuning_type = config.get("finetuning_type", "lora")

    # 多 GPU 使用 torchrun
    if num_gpus > 1:
        _append_log(task_id, f"[INFO] 启用分布式训练: {num_gpus} 个 GPU", "info")
        cmd = [
            sys.executable, "-m", "torch.distributed.run",
            "--nproc_per_node", str(num_gpus),
            str(ROOT_DIR / "train.py"),
        ]
    else:
        cmd = [
            sys.executable, str(ROOT_DIR / "train.py"),
        ]
    cmd += [
        "--stage", stage,
        "--do_train", "True",
        "--model_name_or_path", config.get("base_model", ""),
        "--dataset", config.get("dataset", "identity"),
        "--template", config.get("template", "default"),
        "--finetuning_type", finetuning_type,
        "--output_dir", output_dir,
        "--trust_remote_code", "True",
        "--overwrite_output_dir", "True",
        "--report_to", "none",
        "--learning_rate", str(config.get("learning_rate", "1e-5")),
        "--num_train_epochs", str(config.get("num_train_epochs", 3)),
        "--per_device_train_batch_size", str(config.get("per_device_train_batch_size", 4)),
        "--cutoff_len", str(config.get("cutoff_len", 1024)),
        "--gradient_accumulation_steps", str(config.get("gradient_accumulation_steps", 4)),
        "--max_samples", str(config.get("max_samples", 100000)),
        "--lr_scheduler_type", config.get("lr_scheduler_type", "cosine"),
        "--warmup_steps", str(config.get("warmup_steps", 100)),
        "--max_grad_norm", str(config.get("max_grad_norm", "1.0")),
        "--optim", config.get("optim", "adamw_torch"),
        "--logging_steps", str(config.get("logging_steps", 50)),
        "--save_steps", str(config.get("save_steps", 100)),
        "--save_total_limit", str(config.get("save_total_limit", 5)),
        "--flash_attn", config.get("flash_attn", "auto"),
    ]

    dtype = config.get("dtype", "bf16")
    if dtype == "bf16":
        cmd += ["--bf16", "True"]
    elif dtype == "fp16":
        cmd += ["--fp16", "True"]

    if finetuning_type == "lora":
        cmd += [
            "--lora_rank", str(config.get("lora_rank", 256)),
            "--lora_alpha", str(config.get("lora_alpha", 512)),
            "--lora_dropout", str(config.get("lora_dropout", "0.01")),
            "--lora_target", config.get("lora_target", "all"),
        ]

    if config.get("do_eval", False):
        cmd += ["--do_eval", "True", "--eval_strategy", "steps",
                "--eval_steps", str(config.get("eval_steps", 50)),
                "--per_device_eval_batch_size", "4"]
        eval_ds = config.get("eval_dataset", "")
        if eval_ds:
            cmd += ["--eval_dataset", eval_ds]
        else:
            cmd += ["--val_size", str(config.get("val_size", "0.1"))]

    if config.get("resume_from_checkpoint") and config.get("checkpoint_path"):
        ckpt = config["checkpoint_path"].strip()
        cmd += ["--resume_from_checkpoint", ckpt]
        _append_log(task_id, f"[INFO] 从 checkpoint 继续: {ckpt}", "info")

    _append_log(task_id, f"[INFO] 输出目录: {output_dir}", "info")

    try:
        cwd = str(BASE_DIR)
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,  # universal newlines: \r / \n / \r\n 都识别为换行
            env=env,
        )

        _running_processes[task_id] = process
        _append_log(task_id, "[INFO] 训练进程已启动", "info")

        # —— 监控 trainer_log.jsonl 读取实时 loss ——
        log_file = Path(output_dir) / "trainer_log.jsonl"
        last_log_pos = 0
        stop_flag = threading.Event()
        train_finished = threading.Event()  # 训练完成信号

        def watch_trainer_log():
            nonlocal last_log_pos
            while not stop_flag.is_set():
                time.sleep(1)
                if log_file.exists():
                    try:
                        with open(log_file, "r", encoding="utf-8") as lf:
                            lf.seek(last_log_pos)
                            for line in lf:
                                try:
                                    data = json.loads(line)
                                    if "loss" in data:
                                        loss_val = float(data["loss"])
                                        lr_val = data.get("lr")
                                        ep_val = data.get("epoch")
                                        pct_val = data.get("percentage")
                                        remaining = data.get("remaining_time", "")
                                        cur_step = data.get("current_steps")
                                        total_step = data.get("total_steps")
                                        with _task_lock:
                                            if task_id in _tasks:
                                                _tasks[task_id]["current_loss"] = loss_val
                                                if lr_val is not None:
                                                    _tasks[task_id]["learning_rate"] = float(str(lr_val).replace("'", ""))
                                                if ep_val is not None:
                                                    _tasks[task_id]["current_epoch"] = float(ep_val)
                                                if pct_val is not None:
                                                    _tasks[task_id]["progress"] = float(pct_val)
                                                _tasks[task_id]["eta"] = str(remaining) if remaining else ""
                                                _tasks[task_id]["loss_history"].append(loss_val)
                                        step = cur_step or "?"
                                        lr_str = f"  lr={float(lr_val):.2e}" if lr_val else ""
                                        ep_str = f"  epoch={float(ep_val):.2f}" if ep_val is not None else ""
                                        _append_log(task_id, f'Step {step}/{total}  loss={loss_val:.4f}{lr_str}{ep_str}', "info")
                                        # 检测训练是否完成：step 达到 total
                                        try:
                                            if int(step) >= int(total):
                                                train_finished.set()
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                            last_log_pos = lf.tell()
                    except Exception:
                        pass

        log_watcher = threading.Thread(target=watch_trainer_log, daemon=True)
        log_watcher.start()

        # —— 流式读取 stdout（text=True 下 readline 识别 \r/\n/\r\n） ——
        import queue as _queue
        _line_q: "_queue.Queue[str]" = _queue.Queue()

        def _read_stdout_lines():
            try:
                for line in process.stdout:
                    line = line.rstrip("\r\n")
                    if line:
                        _line_q.put(line)
            except Exception:
                pass
            finally:
                _line_q.put("")  # EOF

        reader = threading.Thread(target=_read_stdout_lines, daemon=True)
        reader.start()

        # —— 主循环：透传 LlamaFactory 原始输出 ——
        skip_config = False

        while True:
            try:
                raw = _line_q.get(timeout=1)
            except _queue.Empty:
                if train_finished.is_set() or (process.poll() is not None and _line_q.empty()):
                    try:
                        raw = _line_q.get(timeout=1)
                    except _queue.Empty:
                        break
                else:
                    continue

            if not raw:
                break

            # 跳过 config JSON dump（太冗长）
            if raw.strip() == "{":
                skip_config = True; continue
            if skip_config:
                if raw.strip() == "}":
                    skip_config = False
                continue

            # 终端原样输出（LlamaFactory 原始格式）
            print(raw, flush=True)

            # Web 日志：全部写入
            log_type = "info"
            if "ERROR" in raw or "error" in raw.lower():
                log_type = "error"
            elif "WARNING" in raw or "warn" in raw.lower():
                log_type = "warn"
            _append_log(task_id, raw, log_type)

        stop_flag.set()
        try:
            process.stdout.close()
        except Exception:
            pass
        reader.join(timeout=3)
        log_watcher.join(timeout=3)

        # 等进程退出（最多 60 秒，训练本身已结束）
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        # 训练结束后绘制 loss 曲线
        try:
            _plot_loss_curve(task_id, output_dir, config.get("do_eval", False))
        except Exception as e:
            print(f"[WARN] Loss 曲线异常: {e}", flush=True)

        ret_code = process.returncode
        with _task_lock:
            if task_id in _tasks:
                t = _tasks[task_id]
                if t["status"] == "cancelled":
                    _append_log(task_id, "[WARN] 训练已被用户中断", "warn")
                elif ret_code == 0:
                    t["status"] = "completed"
                    t["progress"] = 100
                    t["finished_at"] = datetime.now().isoformat()
                    t["eta"] = "00:00"
                else:
                    t["status"] = "failed"
                    _append_log(task_id, f"[ERROR] 训练退出码: {ret_code}", "error")

        # 完成日志（放 lock 外，避免死锁）
        if ret_code == 0:
            _append_log(task_id, "=" * 50, "info")
            _append_log(task_id, "[INFO] 训练完成！", "info")
            _append_log(task_id, f"[INFO] 输出目录: {output_dir}", "info")
            _append_log(task_id, f"[INFO] Loss 曲线: {output_dir}/loss_curve.png", "info")
            _append_log(task_id, "=" * 50, "info")
            print(f"\n{'='*50}\n>>> 训练完成！输出目录: {output_dir}\n{'='*50}", flush=True)

        from .training_service import _save_tasks
        try:
            _save_tasks()
        except Exception:
            pass

    except Exception as e:
        _append_log(task_id, f"[ERROR] {str(e)}", "error")
        with _task_lock:
            if task_id in _tasks:
                _tasks[task_id]["status"] = "failed"
    finally:
        _running_processes.pop(task_id, None)


def cancel_training(task_id: str) -> bool:
    """中断训练"""
    process = _running_processes.get(task_id)
    if process:
        try:
            process.kill()
            with _task_lock:
                if task_id in _tasks:
                    _tasks[task_id]["status"] = "cancelled"
            _append_log(task_id, "[WARN] 用户中断了训练", "warn")
            return True
        except Exception:
            pass
    return False


def _plot_loss_curve(task_id: str, output_dir: str, has_eval: bool = False):
    """训练完成后自动绘制 loss 曲线并保存"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        state_file = Path(output_dir) / "trainer_state.json"
        if not state_file.exists():
            return

        state = json.loads(state_file.read_text(encoding="utf-8"))
        log_history = state.get("log_history", [])
        if not log_history:
            return

        train_steps, train_losses = [], []
        eval_steps, eval_losses = [], []

        for entry in log_history:
            if "loss" in entry and "step" in entry:
                train_steps.append(entry["step"])
                train_losses.append(entry["loss"])
            if has_eval and "eval_loss" in entry and "step" in entry:
                eval_steps.append(entry["step"])
                eval_losses.append(entry["eval_loss"])

        if not train_losses:
            return

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(train_steps, train_losses, label="Training Loss", color="#409eff", linewidth=1.5)
        ax.axhline(y=min(train_losses), color="#67c23a", linestyle="--", alpha=0.5, label=f"Min: {min(train_losses):.4f}")

        if eval_losses:
            ax.plot(eval_steps, eval_losses, label="Validation Loss", color="#f56c6c", linewidth=1.5, marker="o", markersize=3)

        ax.set_xlabel("Step")
        ax.set_ylabel("Loss")
        ax.set_title(f"Training Loss Curve")
        ax.legend()
        ax.grid(True, alpha=0.3)

        save_path = Path(output_dir) / "loss_curve.png"
        fig.savefig(str(save_path), dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  Loss 曲线已保存: {save_path}", flush=True)
        _append_log(task_id, f"Loss 曲线已保存: {save_path}", "info")
    except Exception as e:
        print(f"  [WARN] Loss 曲线绘制失败: {e}", flush=True)


# 保留旧接口兼容
run_training_inline = run_training_subprocess
