"""
训练任务共享状态
解决 task_runner 和 training_service 之间的循环导入问题
"""
import threading

# 训练任务存储
_tasks: dict = {}
_task_lock = threading.Lock()
