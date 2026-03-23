#!/bin/bash
# build.sh - 优化版

set -e  # 出错时停止执行

echo "========================================="
echo "🔨 构建前端..."
echo "========================================="

# 检查目录
echo "当前目录: $(pwd)"

# 安装依赖并构建
echo "📦 安装前端依赖..."
npm install

echo "🔨 构建前端..."
npm run build

# 检查构建结果
if [ ! -d "dist" ]; then
    echo "❌ 构建失败：dist目录不存在"
    exit 1
fi

echo "✅ 前端构建成功，文件数: $(find dist -type f | wc -l)"

echo "========================================="
echo "📋 准备静态文件..."
echo "========================================="

# 创建static目录（如果需要）
mkdir -p static

# 复制构建文件到static目录
echo "复制 dist/* 到 static/"
cp -r dist/* static/ 2>/dev/null || echo "⚠️ 复制失败，但继续"

# 列出生成的文件
echo "生成的文件:"
ls -la static/ | head -10

echo "========================================="
echo "✅ 构建完成！"
echo "========================================="
echo "现在可以运行："
echo "  docker-compose up -d    # 启动所有服务"
echo "  docker-compose logs -f  # 查看日志"
echo "访问地址:"
echo "  http://localhost        # 前端"
echo "  http://localhost:8000   # API"
echo "========================================="