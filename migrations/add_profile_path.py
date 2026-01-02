"""
数据库迁移: 添加 profile_path 字段

用途：
- 为每个账号存储独立的 Camoufox Profile 目录路径
- 持久化浏览器指纹、Cookies、LocalStorage 等

运行：
    python migrations/add_profile_path.py
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """执行迁移"""
    logger.info("开始迁移: 添加 profile_path 字段")

    with get_db() as conn:
        cursor = conn.cursor()

        # 检查字段是否已存在
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'accounts' AND column_name = 'profile_path'
        """)

        if cursor.fetchone():
            logger.info("profile_path 字段已存在，跳过迁移")
            return

        # 添加字段
        cursor.execute("""
            ALTER TABLE accounts
            ADD COLUMN profile_path VARCHAR(255)
        """)

        logger.info("✅ 成功添加 profile_path 字段")

        # 创建索引（可选，提升查询性能）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_accounts_profile_path
            ON accounts(profile_path)
        """)

        logger.info("✅ 创建索引 idx_accounts_profile_path")


def rollback():
    """回滚迁移"""
    logger.info("开始回滚: 删除 profile_path 字段")

    with get_db() as conn:
        cursor = conn.cursor()

        # 删除索引
        cursor.execute("DROP INDEX IF EXISTS idx_accounts_profile_path")

        # 删除字段
        cursor.execute("ALTER TABLE accounts DROP COLUMN IF EXISTS profile_path")

        logger.info("✅ 回滚完成")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="数据库迁移脚本")
    parser.add_argument('--rollback', action='store_true', help='回滚迁移')
    args = parser.parse_args()

    if args.rollback:
        rollback()
    else:
        migrate()
