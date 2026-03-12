#!/usr/bin/env python3
"""
Aiven PostgreSQL 连接测试脚本
"""

import os
import sys
import psycopg2
from urllib.parse import urlparse


def test_aiven_connection(database_url, ca_cert_path=None):
    """测试Aiven数据库连接"""
    print(f"测试连接: {database_url}")
    
    # 解析URL
    result = urlparse(database_url)
    
    # 提取连接信息
    dbname = result.path[1:]
    user = result.username
    password = result.password
    host = result.hostname
    port = result.port or 5432
    
    # 连接参数
    conn_params = {
        'dbname': dbname,
        'user': user,
        'password': password,
        'host': host,
        'port': port,
        'sslmode': 'require'
    }
    
    # 如果提供了CA证书
    if ca_cert_path and os.path.exists(ca_cert_path):
        conn_params['sslrootcert'] = ca_cert_path
        print(f"使用CA证书: {ca_cert_path}")
    
    try:
        # 连接数据库
        conn = psycopg2.connect(**conn_params)
        cursor = conn.cursor()
        
        # 执行简单查询
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ 连接成功!")
        print(f"数据库版本: {version[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False


def main():
    """主函数"""
    database_url = os.environ.get('DATABASE_URL')
    ca_cert_path = os.environ.get('CA_CERT_PATH', 'ca.pem')
    
    if not database_url:
        print("错误: 未设置 DATABASE_URL 环境变量")
        print("请设置: export DATABASE_URL='postgresql://user:pass@host:port/dbname?sslmode=require'")
        sys.exit(1)
    
    print("=" * 50)
    print("Aiven PostgreSQL 连接测试")
    print("=" * 50)
    
    # 测试连接
    success = test_aiven_connection(database_url, ca_cert_path)
    
    if success:
        print("\n✅ 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 测试失败，请检查配置")
        sys.exit(1)


if __name__ == '__main__':
    main()