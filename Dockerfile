FROM python:3.11-slim

WORKDIR /app

# 安装 Node.js 和系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装后端
COPY backend/ ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# 复制前端并构建
COPY frontend/ ./frontend/
WORKDIR /app/frontend
RUN npm install && npm run build

# 返回后端目录
WORKDIR /app

# 暴露端口
EXPOSE 8000

# 启动后端服务
CMD ["sh", "-c", "cd backend && uvicorn app:app --host 0.0.0.0 --port 8000"]
