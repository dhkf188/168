#!/bin/bash
# deploy.sh - 一键部署脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}🚀 员工监控系统一键部署脚本${NC}"
echo -e "${GREEN}=========================================${NC}"

# 检查Docker
echo -e "${YELLOW}📋 检查Docker环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker已安装: $(docker --version)${NC}"

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose已安装: $(docker-compose --version)${NC}"

# 创建.env文件
if [ ! -f .env ]; then
    echo -e "${YELLOW}📝 创建.env配置文件...${NC}"
    cat > .env << EOF
# 自动生成的配置文件
DB_PASSWORD=$(openssl rand -base64 32 | tr -d /=+ | cut -c -20)
BACKUP_DB_PASSWORD=$(openssl rand -base64 32 | tr -d /=+ | cut -c -20)
SECRET_KEY=$(openssl rand -base64 32)
ADMIN_PASSWORD=$(openssl rand -base64 12)
DEBUG=false
EOF
    echo -e "${GREEN}✅ .env文件已创建${NC}"
else
    echo -e "${GREEN}✅ .env文件已存在${NC}"
fi

# 创建备份目录
mkdir -p backups

# 给脚本执行权限
chmod +x entrypoint.sh backup.sh build.sh

# 构建前端
echo -e "${YELLOW}🔨 构建前端...${NC}"
./build.sh

# 停止旧容器
echo -e "${YELLOW}🛑 停止旧容器...${NC}"
docker-compose down

# 构建新镜像
echo -e "${YELLOW}🐳 构建Docker镜像...${NC}"
docker-compose build

# 启动服务
echo -e "${YELLOW}▶️ 启动服务...${NC}"
docker-compose up -d

# 等待服务启动
echo -e "${YELLOW}⏳ 等待服务启动...${NC}"
sleep 10

# 检查服务状态
echo -e "${YELLOW}📊 检查服务状态...${NC}"
docker-compose ps

# 测试API
echo -e "${YELLOW}🔍 测试API...${NC}"
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo -e "${GREEN}✅ API健康检查通过${NC}"
else
    echo -e "${RED}⚠️ API健康检查失败，请检查日志${NC}"
fi

# 显示访问信息
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}✅ 部署完成！${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "访问地址:"
echo -e "  ${YELLOW}前端:${NC} http://localhost"
echo -e "  ${YELLOW}API:${NC} http://localhost:8000"
echo -e "  ${YELLOW}API文档:${NC} http://localhost:8000/api/docs"
echo ""
echo -e "管理员账号: ${YELLOW}admin${NC}"
echo -e "管理员密码: ${YELLOW}$(grep ADMIN_PASSWORD .env | cut -d= -f2)${NC}"
echo ""
echo -e "常用命令:"
echo -e "  ${YELLOW}查看日志:${NC} docker-compose logs -f"
echo -e "  ${YELLOW}停止服务:${NC} docker-compose down"
echo -e "  ${YELLOW}重启服务:${NC} docker-compose restart"
echo -e "  ${YELLOW}执行备份:${NC} docker-compose exec backup /backup.sh"
echo -e "${GREEN}=========================================${NC}"