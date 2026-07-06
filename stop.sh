#!/usr/bin/env bash
# ============================================
#   远光微调平台 - 停止前后端服务
# ============================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="${SCRIPT_DIR}/.dev_pids"

echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}   远光微调平台 - 停止前后端服务${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# 方式1: 通过 PID 文件停止
if [ -f "$PID_FILE" ]; then
    echo -e "[信息] 通过 PID 文件停止服务..."
    while read -r pid; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo -e "${GREEN}[完成] 已停止 PID ${pid}${NC}"
        else
            echo -e "[跳过] PID ${pid} 已不存在"
        fi
    done < "$PID_FILE"
    rm -f "$PID_FILE"
else
    echo -e "[信息] 未找到 PID 文件，尝试通过端口查找..."
fi

# 方式2: 通过端口号兜底查找
echo ""
echo -e "[信息] 检查端口 8000 (后端)..."
BACKEND_PID=$(lsof -ti:8000 2>/dev/null || netstat -tlnp 2>/dev/null | grep ':8000' | awk '{print $7}' | cut -d'/' -f1 | head -1)
if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null
    echo -e "${GREEN}[完成] 已停止后端进程 (PID: ${BACKEND_PID})${NC}"
else
    echo -e "[信息] 端口 8000 无进程运行"
fi

echo -e "[信息] 检查端口 5173 (前端)..."
FRONTEND_PID=$(lsof -ti:5173 2>/dev/null || netstat -tlnp 2>/dev/null | grep ':5173' | awk '{print $7}' | cut -d'/' -f1 | head -1)
if [ -n "$FRONTEND_PID" ]; then
    kill "$FRONTEND_PID" 2>/dev/null
    echo -e "${GREEN}[完成] 已停止前端进程 (PID: ${FRONTEND_PID})${NC}"
else
    echo -e "[信息] 端口 5173 无进程运行"
fi

echo ""
echo -e "${GREEN}[完成] 所有服务已停止${NC}"
