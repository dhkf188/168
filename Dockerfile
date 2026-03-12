FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Node.js（用于构建前端）
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    node --version && \
    npm --version

# 复制 Python 依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有代码（包括前端文件）
COPY . .

# 构建前端
RUN echo "📦 安装前端依赖..." && \
    npm install && \
    echo "🔨 构建前端..." && \
    npm run build && \
    echo "📋 复制构建文件到根目录（同一级）..." && \
    cp -r dist/* . && \
    echo "✅ 前端构建完成"

# 创建存储目录
RUN mkdir -p /data/screenshots /data/logs /data/thumbnails

# 设置权限
RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
