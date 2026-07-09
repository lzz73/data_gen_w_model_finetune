FROM docker.1ms.run/nvidia/cuda:12.1.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# 安装 Python 3.10 + 系统依赖
RUN apt-get update && apt-get install -y \
    software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y \
    python3.10 python3.10-venv python3.10-dev python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1

# 升级 pip
RUN python3 -m pip install --upgrade pip

WORKDIR /app

# ---- 依赖安装（利用 Docker 层缓存，最耗时的放前面） ----

# PyTorch（最耗时，单独一层，用官方 cu124 源）
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    "torch>=2.4.0,<2.7.0" "torchvision>=0.19.0,<0.22.0" "torchaudio>=2.4.0,<2.7.0" \
    --index-url https://download.pytorch.org/whl/cu124 \
    --no-deps && \
    python3 -m pip install --no-cache-dir --break-system-packages \
    nvidia-cublas-cu12 nvidia-cuda-cupti-cu12 nvidia-cuda-nvrtc-cu12 \
    nvidia-cuda-runtime-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 nvidia-curand-cu12 \
    nvidia-cusolver-cu12 nvidia-cusparse-cu12 nvidia-nccl-cu12 nvidia-nvjitlink-cu12 \
    nvidia-nvtx-cu12

# 其余 Python 依赖
COPY backend/requirements.txt ./requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# ---- 应用代码（通过挂载提供，不 COPY） ----
# 只 COPY requirements.txt 用于安装依赖，代码运行时挂载

# 创建运行时目录
RUN mkdir -p /app/backend/uploads /app/backend/logs /app/backend/data \
    /app/output /app/models /app/frontend/dist /app/data

WORKDIR /app/backend

ENV HOST=0.0.0.0
ENV PORT=18121
ENV DATABASE_URL=sqlite+aiosqlite:///./ygdataset.db

EXPOSE 18121

CMD ["python3", "run.py"]
