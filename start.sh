#!/bin/bash

echo "========================================="
echo "  YG-Datasets 一键启动"
echo "========================================="

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 清理可能占用端口的进程（WSL 下需同时清理 Windows 侧）
echo -e "${YELLOW}[1/5] 清理端口...${NC}"
# 杀 WSL 里的 uvicorn 和 vite 进程
pkill -9 -f "uvicorn" 2>/dev/null
pkill -9 -f "vite" 2>/dev/null
# 杀 Windows 侧的进程
for port in 18121 5173; do
    pid=$(netstat -ano 2>/dev/null | grep "LISTENING" | grep ":${port}" | awk '{print $NF}' | head -1)
    if [ -n "$pid" ]; then
        powershell.exe -Command "Stop-Process -Id $pid -Force" 2>/dev/null
    fi
done
sleep 2
# 二次确认，确保端口真的释放
for port in 18121 5173; do
    for i in $(seq 1 5); do
        if ! netstat -ano 2>/dev/null | grep -q ":${port}.*LISTEN"; then
            break
        fi
        sleep 1
    done
done

# 检查并创建必要目录
echo -e "${YELLOW}[2/5] 检查环境...${NC}"
mkdir -p backend/uploads
mkdir -p frontend

# 创建并激活 Python 虚拟环境 + 安装依赖
echo -e "${YELLOW}[3/5] 配置 Python 环境...${NC}"
cd backend

# venv 损坏（pip 丢失等）则重建
if [ -d "venv" ] && ! venv/bin/python -c "import pip" 2>/dev/null; then
    echo -e "${YELLOW}  venv 已损坏，重建虚拟环境...${NC}"
    rm -rf venv
fi

if [ ! -d "venv" ] || [ ! -f "venv/bin/python" ]; then
    echo -e "${YELLOW}  创建虚拟环境...${NC}"
    python3 -m venv venv
fi
source venv/bin/activate

# 用 import 检测依赖是否真的能导入，比检查文件更可靠
python -c "import uvicorn" 2>/dev/null
if [ $? -ne 0 ] || [ requirements.txt -nt venv/.deps_installed ]; then
    echo -e "${YELLOW}  安装 Python 依赖...${NC}"

    # 先装 torch（清华源 + cu121 索引，--no-deps 避免 nvidia 依赖回溯）
    if ! python -c "import torch" 2>/dev/null; then
        echo -e "${YELLOW}  安装 PyTorch (CUDA 12)...${NC}"
        pip install "torch>=2.4.0,<2.7.0" "torchvision>=0.19.0,<0.22.0" "torchaudio>=2.4.0,<2.7.0" \
            --index-url https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu121/ \
            --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
            --no-deps
        echo -e "${YELLOW}  安装 PyTorch nvidia 依赖...${NC}"
        pip install nvidia-cublas-cu12 nvidia-cuda-cupti-cu12 nvidia-cuda-nvrtc-cu12 \
            nvidia-cuda-runtime-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 nvidia-curand-cu12 \
            nvidia-cusolver-cu12 nvidia-cusparse-cu12 nvidia-nccl-cu12 nvidia-nvjitlink-cu12 \
            nvidia-nvtx-cu12 \
            --index-url https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu121/ \
            --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple
    fi

    # 再装其余所有依赖（requirements.txt 里不含 torch，不会触发 nvidia 回溯）
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    touch venv/.deps_installed
else
    echo -e "${GREEN}  Python 依赖已就绪${NC}"
fi

# 安装前端依赖
echo -e "${YELLOW}[4/5] 配置前端环境...${NC}"
cd ../frontend

# 检测 node_modules 是否有 Linux 原生绑定（WSL 下 Windows 装的 node_modules 缺这个）
NEED_REINSTALL=false
if [ ! -d "node_modules" ]; then
    NEED_REINSTALL=true
elif [ ! -f "node_modules/.bin/vite" ]; then
    NEED_REINSTALL=true
# rolldown/vite 需要 Linux native binding，Windows 装的没有
elif [ -d "node_modules/rolldown" ] && [ ! -f "node_modules/@rolldown/binding-linux-x64-gnu/package.json" ]; then
    echo -e "${YELLOW}  检测到 node_modules 为 Windows 环境安装，缺少 Linux 原生绑定${NC}"
    NEED_REINSTALL=true
fi

if [ "$NEED_REINSTALL" = true ]; then
    echo -e "${YELLOW}  安装 Node 依赖...${NC}"
    rm -rf node_modules package-lock.json
    npm install
else
    echo -e "${GREEN}  Node 依赖已就绪${NC}"
fi

# 启动服务
echo -e "${YELLOW}[5/5] 启动服务...${NC}"

cd ../backend
source venv/bin/activate
export HOST="127.0.0.1"
export DATABASE_URL="sqlite+aiosqlite:///./ygdataset.db"

# 等待端口完全释放
echo -e "${YELLOW}  等待端口释放...${NC}"
for i in $(seq 1 10); do
    if ! netstat -ano 2>/dev/null | grep -q ":18121.*LISTEN"; then
        break
    fi
    sleep 1
done

cleanup() {
    echo -e "${YELLOW}  正在停止服务...${NC}"
    # 杀整个进程组（包括 uvicorn 子进程）
    kill -- -$BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    # 确保端口释放
    for port in 18121 5173; do
        pid=$(lsof -ti :${port} 2>/dev/null)
        [ -n "$pid" ] && kill -9 $pid 2>/dev/null
    done
    echo -e "${GREEN}  服务已停止${NC}"
    exit 0
}
trap cleanup INT TERM

set -m  # 后台进程放入独立进程组，方便整组杀掉

echo -e "${GREEN}  启动后端 (端口 18121)...${NC}"
python run.py > /tmp/backend.log 2>&1 &
BACKEND_PID=$!

# 等待后端真正就绪（监听端口）
echo -e "${YELLOW}  等待后端启动...${NC}"
for i in $(seq 1 60); do
    if lsof -i :18121 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
        echo -e "${GREEN}  后端已就绪${NC}"
        break
    fi
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}  后端启动失败！日志：${NC}"
        cat /tmp/backend.log
        exit 1
    fi
    sleep 1
done

cd ../frontend
echo -e "${GREEN}  启动前端 (端口 5173)...${NC}"
npx vite --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

set +m

echo ""
echo "========================================="
echo -e "  ${GREEN}启动完成!${NC}"
echo "========================================="
echo -e "  后端：${GREEN}http://localhost:18121${NC}"
echo -e "  API 文档：${GREEN}http://localhost:18121/docs${NC}"
echo -e "  前端：${GREEN}http://localhost:5173${NC}"
echo ""
echo -e "  ${YELLOW}按 Ctrl+C 停止所有服务${NC}"
echo "========================================="

wait
