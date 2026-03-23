# Makefile
.PHONY: help build up down logs restart clean backup prod shell

# 默认帮助
help:
	@echo "可用命令:"
	@echo "  make build    - 构建所有容器"
	@echo "  make up       - 启动所有服务"
	@echo "  make down     - 停止所有服务"
	@echo "  make logs     - 查看日志"
	@echo "  make restart  - 重启所有服务"
	@echo "  make clean    - 清理所有容器和数据"
	@echo "  make backup   - 手动执行备份"
	@echo "  make prod     - 启动生产环境（带备份服务）"
	@echo "  make shell    - 进入服务器容器"

# 构建
build:
	docker-compose build

# 启动
up:
	docker-compose up -d
	@echo "服务已启动，访问: http://localhost"

# 停止
down:
	docker-compose down

# 查看日志
logs:
	docker-compose logs -f

# 重启
restart: down up

# 清理
clean:
	docker-compose down -v
	docker system prune -f
	@echo "清理完成"

# 备份
backup:
	docker-compose exec backup /backup.sh

# 生产环境启动
prod:
	docker-compose --profile backup up -d
	@echo "生产环境已启动，包含备份服务"

# 进入服务器容器
shell:
	docker-compose exec server bash

# 查看状态
status:
	docker-compose ps
	@echo "\n📊 服务监控:"
	@python3 monitor.py 2>/dev/null || echo "请先安装requests: pip install requests"

# 初始化数据库
init-db:
	docker-compose exec server python init_db.py