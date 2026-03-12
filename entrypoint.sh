#!/bin/bash
# Docker入口脚本

set -e

echo "========================================="
echo "员工监控系统服务器启动"
echo "========================================="
echo "当前时间: $(date)"
echo "Python版本: $(python --version)"
echo "========================================="

# 下载Aiven CA证书（如果需要）
if [ ! -f "ca.pem" ] && [ -n "$CA_CERT_PATH" ]; then
    echo "下载Aiven CA证书..."
    curl -o ca.pem https://certs.aiven.io/ca.pem
    echo "✅ CA证书下载完成"
fi

# 等待数据库就绪
echo "[1/4] 等待数据库就绪..."
python -c "
import time
import psycopg2
import os
from urllib.parse import urlparse

db_url = os.environ.get('DATABASE_URL', '')
if not db_url:
    print('❌ DATABASE_URL 未设置')
    exit(1)

result = urlparse(db_url)
conn_params = {
    'dbname': result.path[1:],
    'user': result.username,
    'password': result.password,
    'host': result.hostname,
    'port': result.port or 5432,
    'connect_timeout': 5
}

if os.path.exists('ca.pem'):
    conn_params['sslrootcert'] = 'ca.pem'

max_retries = 30
for i in range(max_retries):
    try:
        conn = psycopg2.connect(**conn_params)
        conn.close()
        print('✅ 数据库连接成功')
        exit(0)
    except Exception as e:
        print(f'⏳ 等待数据库就绪 ({i+1}/{max_retries}): {e}')
        time.sleep(2)

print('❌ 数据库连接超时')
exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ 数据库连接失败，退出"
    exit 1
fi

# 数据库初始化
echo "[2/4] 执行数据库初始化..."
python init_db.py

if [ $? -ne 0 ]; then
    echo "❌ 数据库初始化失败，退出"
    exit 1
fi

# 验证数据库
echo "[3/4] 验证数据库..."
python -c "
from server_database import PrimarySessionLocal
from server_models import User

db = PrimarySessionLocal()
try:
    user_count = db.query(User).count()
    print(f'✅ 数据库验证成功，用户数: {user_count}')
finally:
    db.close()
"

# 启动服务器
echo "[4/4] 启动Gunicorn服务器..."
echo "工作进程数: ${GUNICORN_WORKERS:-2}"
echo "绑定端口: ${PORT:-8000}"
echo "========================================="

exec gunicorn \
    --workers ${GUNICORN_WORKERS:-2} \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:${PORT:-8000} \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level ${LOG_LEVEL:-info} \
    server_main:app