"""
Veterans Verify - PostgreSQL 数据库模块

数据分两类:
1. 账号 (accounts) - 持久保存，可重复使用
2. 军人 (veterans) - 消耗型，验证一次即失效

连接: postgresql://postgres:w009025.@localhost:5432/veterans_verify
"""
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import contextmanager
import logging

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# 数据库配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'w009025.'),
    'database': os.getenv('DB_NAME', 'veterans_verify'),
}


def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


@contextmanager
def get_db():
    """数据库上下文管理器"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_db():
    """初始化数据库表"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            -- 账号表 (持久保存)
            -- email = 真实登录的 ChatGPT 账号（验证成功后 Plus 给这个账号）
            -- consumed_email = 消耗的临时邮箱（用于接收 SheerID 验证链接）
            CREATE TABLE IF NOT EXISTS accounts (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                jwt TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                error_type VARCHAR(100),
                error_message TEXT,
                profile_name VARCHAR(255),
                profile_birthday VARCHAR(50),
                consumed_email VARCHAR(255),
                proxy VARCHAR(255),
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            );

            -- 军人数据表 (消耗型)
            CREATE TABLE IF NOT EXISTS veterans (
                id VARCHAR(255) PRIMARY KEY,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                birth_year VARCHAR(10) NOT NULL,
                birth_month VARCHAR(20) NOT NULL,
                birth_day VARCHAR(10) NOT NULL,
                branch VARCHAR(50) NOT NULL,
                source VARCHAR(50) DEFAULT 'BIRLS',
                used BOOLEAN DEFAULT FALSE,
                used_by VARCHAR(255),
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- 验证记录表
            CREATE TABLE IF NOT EXISTS verifications (
                id SERIAL PRIMARY KEY,
                account_id INTEGER REFERENCES accounts(id),
                veteran_id VARCHAR(255) REFERENCES veterans(id),
                discharge_month VARCHAR(20) NOT NULL,
                discharge_day VARCHAR(10) NOT NULL,
                discharge_year VARCHAR(10) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                error_type VARCHAR(100),
                error_message TEXT,
                sheerid_url TEXT,
                verify_link TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );

            -- 索引
            CREATE INDEX IF NOT EXISTS idx_veterans_used ON veterans(used);
            CREATE INDEX IF NOT EXISTS idx_veterans_branch ON veterans(branch);
            CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
            CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email);
            CREATE INDEX IF NOT EXISTS idx_verifications_account ON verifications(account_id);
            CREATE INDEX IF NOT EXISTS idx_verifications_status ON verifications(status);
        """)
        logger.info("数据库表初始化完成")


# ==================== Veterans 操作 (消耗型数据) ====================

def import_veterans_from_json(json_path: str = "data/veterans_processed.json"):
    """从 JSON 导入军人数据"""
    with open(json_path, 'r', encoding='utf-8') as f:
        veterans = json.load(f)

    with get_db() as conn:
        cursor = conn.cursor()
        imported = 0
        skipped = 0

        for v in veterans:
            try:
                cursor.execute("""
                    INSERT INTO veterans
                    (id, first_name, last_name, birth_year, birth_month, birth_day, branch, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (
                    v['id'],
                    v['first_name'],
                    v['last_name'],
                    v['birth_date']['year'],
                    v['birth_date']['month'],
                    v['birth_date']['day'],
                    v['branch'],
                    v.get('source', 'BIRLS')
                ))
                if cursor.rowcount > 0:
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(f"导入失败 {v['id']}: {e}")
                skipped += 1

        logger.info(f"导入完成: {imported} 条新增, {skipped} 条跳过")
        return imported, skipped


def import_used_veterans(json_path: str = "data/veterans_used.json"):
    """导入已使用的军人 ID"""
    if not Path(json_path).exists():
        return 0

    with open(json_path, 'r', encoding='utf-8') as f:
        used_ids = json.load(f)

    with get_db() as conn:
        cursor = conn.cursor()
        updated = 0
        for vid in used_ids:
            cursor.execute("""
                UPDATE veterans SET used = TRUE, used_at = %s WHERE id = %s AND used = FALSE
            """, (datetime.now(), vid))
            updated += cursor.rowcount

        logger.info(f"标记 {updated} 条已使用")
        return updated


def get_available_veteran(branch: str = None) -> Optional[Dict]:
    """获取一条可用的军人数据 (未被使用过的)"""
    with get_db() as conn:
        cursor = conn.cursor()
        if branch:
            cursor.execute("""
                SELECT * FROM veterans WHERE used = FALSE AND branch = %s LIMIT 1
            """, (branch,))
        else:
            cursor.execute("SELECT * FROM veterans WHERE used = FALSE LIMIT 1")

        row = cursor.fetchone()
        return dict(row) if row else None


def mark_veteran_used(veteran_id: str, used_by: str):
    """标记军人数据为已使用 (消耗掉)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE veterans SET used = TRUE, used_by = %s, used_at = %s WHERE id = %s
        """, (used_by, datetime.now(), veteran_id))
        logger.info(f"[消耗] 军人数据 {veteran_id} 已被 {used_by} 使用")


def get_veterans_stats() -> Dict:
    """获取军人数据统计"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM veterans")
        total = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as used FROM veterans WHERE used = TRUE")
        used = cursor.fetchone()['used']

        cursor.execute("""
            SELECT branch,
                   COUNT(*) as total,
                   SUM(CASE WHEN used THEN 1 ELSE 0 END) as used
            FROM veterans GROUP BY branch ORDER BY total DESC
        """)
        by_branch = {row['branch']: {'total': row['total'], 'used': row['used'] or 0}
                     for row in cursor.fetchall()}

        return {
            'total': total,
            'used': used,
            'available': total - used,
            'by_branch': by_branch
        }


# ==================== Accounts 操作 (持久保存) ====================

def create_account(email: str, password: str, jwt: str = None, **kwargs) -> int:
    """创建账号"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO accounts (email, password, jwt, status, proxy, note, created_at)
            VALUES (%s, %s, %s, 'pending', %s, %s, %s)
            RETURNING id
        """, (
            email, password, jwt,
            kwargs.get('proxy', ''),
            kwargs.get('note', ''),
            datetime.now()
        ))
        account_id = cursor.fetchone()['id']
        logger.info(f"创建账号 #{account_id}: {email}")
        return account_id


def get_account_by_email(email: str) -> Optional[Dict]:
    """根据邮箱获取账号"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE email = %s", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_account_by_id(account_id: int) -> Optional[Dict]:
    """根据 ID 获取账号"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE id = %s", (account_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_account(email: str, **kwargs):
    """更新账号信息"""
    allowed_fields = ['password', 'jwt', 'status', 'error_type', 'error_message',
                      'profile_name', 'profile_birthday', 'consumed_email', 'proxy', 'note']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return

    updates['updated_at'] = datetime.now()

    set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
    values = list(updates.values()) + [email]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE accounts SET {set_clause} WHERE email = %s", values)


def get_accounts(status: str = None, limit: int = 100) -> List[Dict]:
    """获取账号列表"""
    with get_db() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute(
                "SELECT * FROM accounts WHERE status = %s ORDER BY created_at DESC LIMIT %s",
                (status, limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM accounts ORDER BY created_at DESC LIMIT %s", (limit,)
            )
        return [dict(row) for row in cursor.fetchall()]


def get_accounts_stats() -> Dict:
    """获取账号统计"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, COUNT(*) as count FROM accounts GROUP BY status
        """)
        by_status = {row['status']: row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) as total FROM accounts")
        total = cursor.fetchone()['total']

        return {
            'total': total,
            'by_status': by_status
        }


def get_or_create_account(email: str, password: str, **kwargs) -> Dict:
    """获取或创建账号"""
    account = get_account_by_email(email)
    if account:
        return account

    account_id = create_account(email, password, **kwargs)
    return get_account_by_id(account_id)


# ==================== Verifications 操作 ====================

def create_verification(account_id: int, veteran_id: str,
                        discharge_month: str, discharge_day: str, discharge_year: str) -> int:
    """创建验证记录"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO verifications
            (account_id, veteran_id, discharge_month, discharge_day, discharge_year, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
            RETURNING id
        """, (account_id, veteran_id, discharge_month, discharge_day, discharge_year))
        return cursor.fetchone()['id']


def update_verification(verification_id: int, **kwargs):
    """更新验证记录"""
    allowed_fields = ['status', 'error_type', 'error_message', 'sheerid_url', 'verify_link']
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if 'status' in updates and updates['status'] in ('success', 'failed'):
        updates['completed_at'] = datetime.now()

    if not updates:
        return

    set_clause = ', '.join(f"{k} = %s" for k in updates.keys())
    values = list(updates.values()) + [verification_id]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE verifications SET {set_clause} WHERE id = %s", values)


def get_verifications_by_account(account_id: int) -> List[Dict]:
    """获取账号的所有验证记录（包含军人完整信息）"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.*, vt.first_name, vt.last_name, vt.branch,
                   vt.birth_month, vt.birth_day, vt.birth_year
            FROM verifications v
            JOIN veterans vt ON v.veteran_id = vt.id
            WHERE v.account_id = %s
            ORDER BY v.created_at DESC
        """, (account_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_latest_verification(account_id: int) -> Optional[Dict]:
    """获取账号最新的验证记录"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT v.*, vt.first_name, vt.last_name, vt.branch,
                   vt.birth_month, vt.birth_day, vt.birth_year
            FROM verifications v
            JOIN veterans vt ON v.veteran_id = vt.id
            WHERE v.account_id = %s
            ORDER BY v.created_at DESC LIMIT 1
        """, (account_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_verifications_stats() -> Dict:
    """获取验证统计"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT status, COUNT(*) as count FROM verifications GROUP BY status
        """)
        by_status = {row['status']: row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) as total FROM verifications")
        total = cursor.fetchone()['total']

        cursor.execute("""
            SELECT error_type, COUNT(*) as count
            FROM verifications WHERE error_type IS NOT NULL
            GROUP BY error_type ORDER BY count DESC
        """)
        by_error = {row['error_type']: row['count'] for row in cursor.fetchall()}

        return {
            'total': total,
            'by_status': by_status,
            'by_error': by_error
        }


# ==================== 迁移工具 ====================

def migrate_from_json():
    """从 JSON 文件迁移数据到 PostgreSQL"""
    logger.info("开始迁移数据到 PostgreSQL...")

    # 1. 初始化表
    init_db()

    # 2. 导入军人数据
    if Path("data/veterans_processed.json").exists():
        import_veterans_from_json()

    # 3. 导入已使用记录
    if Path("data/veterans_used.json").exists():
        import_used_veterans()

    # 4. 导入账号数据
    if Path("data/accounts.json").exists():
        with open("data/accounts.json", 'r', encoding='utf-8') as f:
            data = json.load(f)

        accounts = data.get('accounts', [])
        with get_db() as conn:
            cursor = conn.cursor()
            for acc in accounts:
                try:
                    cursor.execute("""
                        INSERT INTO accounts
                        (email, password, jwt, status, profile_name, proxy, note, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (email) DO NOTHING
                    """, (
                        acc.get('email', ''),
                        acc.get('password', ''),
                        acc.get('jwt', ''),
                        acc.get('status', 'pending'),
                        f"{acc.get('first_name', '')} {acc.get('last_name', '')}".strip(),
                        acc.get('proxy', ''),
                        acc.get('note', ''),
                        acc.get('created_at', datetime.now().isoformat())
                    ))
                except Exception as e:
                    logger.error(f"导入账号失败 {acc.get('email')}: {e}")

        logger.info(f"导入 {len(accounts)} 个账号")

    logger.info("迁移完成!")
    print_stats()


def print_stats():
    """打印统计信息"""
    print("\n" + "="*50)
    print("Veterans Verify - 数据库统计")
    print("="*50)

    v_stats = get_veterans_stats()
    print(f"\n[军人数据] (消耗型)")
    print(f"  总计: {v_stats['total']}")
    print(f"  已用: {v_stats['used']}")
    print(f"  可用: {v_stats['available']}")
    print(f"  按军种:")
    for branch, data in v_stats['by_branch'].items():
        print(f"    {branch}: {data['total']} (已用 {data['used']})")

    a_stats = get_accounts_stats()
    print(f"\n[账号] (持久保存)")
    print(f"  总计: {a_stats['total']}")
    print(f"  按状态: {a_stats['by_status']}")

    vf_stats = get_verifications_stats()
    print(f"\n[验证记录]")
    print(f"  总计: {vf_stats['total']}")
    print(f"  按状态: {vf_stats['by_status']}")
    if vf_stats['by_error']:
        print(f"  按错误: {vf_stats['by_error']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    migrate_from_json()
