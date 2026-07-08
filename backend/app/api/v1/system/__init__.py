"""
系统管理 API
提供前端 system/ 页面和实验记录所需的接口
"""
from fastapi import APIRouter

from app.api.response import ApiResponse
from app.services.gpu_service import get_gpu_info, get_system_info

router = APIRouter()


@router.get("/gpu")
def api_gpu_dashboard():
    """GPU 仪表盘数据"""
    gpus = get_gpu_info()
    sys_info = get_system_info()
    return ApiResponse.ok(data={
        "gpus": gpus,
        "total_count": sys_info["gpu_count"],
        "avg_utilization": sys_info["gpu_utilization_avg"],
    })


@router.get("/health")
def api_health():
    """系统健康检查"""
    gpus = get_gpu_info()
    return ApiResponse.ok(data={
        "gpu_available": len(gpus) > 0,
        "gpu_count": len(gpus),
    })
