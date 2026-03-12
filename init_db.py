#!/usr/bin/env python3
"""
数据库初始化脚本
"""

import os
import logging
from datetime import datetime

from server_database import PrimarySessionLocal, engine
from server_models import Base, User, Employee
from server_auth import get_password_hash
from server_config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database():
    """初始化数据库"""
    logger.info("=" * 50)
    logger.info("数据库初始化开始")
    logger.info("=" * 50)

    # 创建所有表
    logger.info("创建数据库表...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ 数据库表创建成功")

    # 创建数据库会话
    db = PrimarySessionLocal()

    try:
        # 创建默认管理员
        admin_username = Config.ADMIN_USERNAME
        admin_password = Config.ADMIN_PASSWORD

        admin = db.query(User).filter(User.username == admin_username).first()
        if not admin:
            admin = User(
                username=admin_username,
                password_hash=get_password_hash(admin_password),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info(f"✅ 默认管理员已创建: {admin_username}")
        else:
            logger.info(f"✅ 管理员用户已存在: {admin_username}")

        # 创建示例员工（可选）
        # if db.query(Employee).count() == 0:
        #     demo_employees = [
        #         {
        #             'employee_id': 'DEMO001',
        #             'name': '张三',
        #             'department': '技术部',
        #             'position': '开发工程师',
        #             'status': 'active'
        #         },
        #         {
        #             'employee_id': 'DEMO002',
        #             'name': '李四',
        #             'department': '产品部',
        #             'position': '产品经理',
        #             'status': 'active'
        #         },
        #         {
        #             'employee_id': 'DEMO003',
        #             'name': '王五',
        #             'department': '设计部',
        #             'position': 'UI设计师',
        #             'status': 'active'
        #         }
        #     ]

        #     for emp_data in demo_employees:
        #         emp = Employee(**emp_data)
        #         db.add(emp)

        #     db.commit()
        #     logger.info(f"✅ 示例员工已创建 ({len(demo_employees)}个)")

        # 统计表数量
        from server_models import Client, Screenshot, Activity

        users = db.query(User).count()
        employees = db.query(Employee).count()
        clients = db.query(Client).count()
        screenshots = db.query(Screenshot).count()
        activities = db.query(Activity).count()

        logger.info(f"\n📊 当前数据统计:")
        logger.info(f"   - 用户数: {users}")
        logger.info(f"   - 员工数: {employees}")
        logger.info(f"   - 客户端数: {clients}")
        logger.info(f"   - 截图数: {screenshots}")
        logger.info(f"   - 活动日志: {activities}")

        logger.info(f"\n🎉 数据库初始化完成！")

    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
