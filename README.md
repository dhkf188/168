# 员工截图监控系统 - 完整增强版

## 📋 项目简介

企业级员工行为监控系统，自动监控员工电脑屏幕，提供完整的管理后台和数据分析功能。

### ✨ 主要特性

#### 客户端功能

- ✅ 自动截图（可配置间隔，默认5分钟）
- ✅ 多服务器自动检测和故障转移
- ✅ 系统托盘图标管理
- ✅ 开机自启动
- ✅ 图片加密支持
- ✅ 相似度检测（避免重复上传）
- ✅ 批量上传
- ✅ 心跳保活
- ✅ 离线模式支持
- ✅ 配置动态加载

#### 服务器功能

- ✅ FastAPI高性能框架
- ✅ 多数据库支持（主备切换）
- ✅ 自动数据清理（保留最近4小时）
- ✅ JWT认证
- ✅ 完整的API文档
- ✅ 健康检查
- ✅ 活动日志

#### 后台管理

- ✅ Vue3 + Element Plus现代化界面
- ✅ 响应式设计
- ✅ 实时数据统计
- ✅ 员工管理
- ✅ 截图查看（按日期筛选）
- ✅ 客户端管理
- ✅ 数据分析图表

## 🚀 快速开始

### 使用 Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/employee-monitor.git
cd employee-monitor

# 2. 复制环境变量配置
cp .env.example .env
# 编辑 .env 文件，修改数据库密码和密钥

# 3. 启动所有服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f

# 5. 访问系统
# 后台管理: http://localhost
# API文档: http://localhost:8000/api/docs
```
