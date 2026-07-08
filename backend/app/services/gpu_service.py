"""
GPU 监控服务层
提供 GPU 状态查询
"""
from __future__ import annotations
import subprocess
from typing import Optional, List, Dict


def _safe_float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def get_gpu_info() -> list[dict]:
    """
    查询 GPU 状态
    通过 nvidia-smi 获取
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = result.stdout.strip().split("\n")
        gpus = []
        for line in lines:
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue

            total_mem = _safe_float(parts[2])
            used_mem = _safe_float(parts[3])
            free_mem = _safe_float(parts[4])
            used_pct = round(used_mem / total_mem * 100, 1) if total_mem > 0 else 0

            gpus.append({
                "name": f"GPU-{parts[0]}",
                "model": parts[1],
                "total_mem_gb": round(total_mem / 1024, 1),
                "used_mem_gb": round(used_mem / 1024, 1),
                "free_mem_gb": round(free_mem / 1024, 1),
                "utilization": _safe_float(parts[5]),
                "temperature": _safe_float(parts[6]),
                "power_w": _safe_float(parts[7]) if len(parts) >= 8 else 0,
                "used_percent": used_pct,
                "status": "可用" if used_pct < 90 else "繁忙",
            })
        return gpus
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
        print(f"[GPU] nvidia-smi 查询失败: {e}")
        return []


def get_system_info() -> dict:
    """获取系统基本信息"""
    info = {
        "gpu_count": 0,
        "gpu_utilization_avg": 0,
    }
    gpus = get_gpu_info()
    if gpus:
        info["gpu_count"] = len(gpus)
        info["gpu_utilization_avg"] = round(
            sum(g["utilization"] for g in gpus) / len(gpus), 1
        )
    return info
