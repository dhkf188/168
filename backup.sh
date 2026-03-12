#!/bin/bash
# 数据库备份脚本

BACKUP_DIR=${BACKUP_DIR:-/backups}
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="employee_monitor_${TIMESTAMP}.sql.gz"

echo "[$(date)] 开始备份数据库到 ${FILENAME}"

# 执行备份
pg_dump -h ${PGHOST} -U ${PGUSER} -d ${PGDATABASE} | gzip > ${BACKUP_DIR}/${FILENAME}

# 检查备份是否成功
if [ $? -eq 0 ]; then
    echo "[$(date)] ✅ 备份成功: ${FILENAME}"
    
    # 获取备份大小
    SIZE=$(du -h ${BACKUP_DIR}/${FILENAME} | cut -f1)
    echo "[$(date)] 备份大小: ${SIZE}"
    
    # 删除7天前的备份
    find ${BACKUP_DIR} -name "employee_monitor_*.sql.gz" -type f -mtime +7 -delete
    
    # 保留最近30天的备份，之后每月一个
    # 可以添加更复杂的备份策略
    
    echo "[$(date)] 备份完成"
else
    echo "[$(date)] ❌ 备份失败"
    exit 1
fi