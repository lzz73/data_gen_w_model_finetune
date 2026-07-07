#!/bin/bash

echo "========================================="
echo "  YG-Datasets 一键启动"
echo "========================================="

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 清理可能占用端口的进程
echo -e "${YELLOW}[1/5] 清理端口...${NC}"
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "vite" 2>/dev/null
sleep 1

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
export HOST="0.0.0.0"
export DATABASE_URL="sqlite+aiosqlite:///./ygdataset.db"
echo -e "${GREEN}  启动后端 (端口 18121)...${NC}"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 18121 &
BACKEND_PID=$!

sleep 2

cd ../frontend
echo -e "${GREEN}  启动前端 (端口 5173)...${NC}"
npx vite --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

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

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
