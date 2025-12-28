#!/usr/bin/env python
"""
修复数据库中的错误账号记录

问题：
- nnxp47bwy@009025.xyz 是消耗邮箱，真实账号是 vethuxntarz@009025.xyz
- wbjf08wcv@009025.xyz 是消耗邮箱，真实账号是 jqqr48lgt@009025.xyz

解决：
1. 删除 nnxp47bwy 和 wbjf08wcv 的账号记录
2. 确保 vethuxntarz 和 jqqr48lgt 存在且状态正确
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from database import get_db, get_account_by_email

def fix_accounts():
    """修复账号记录"""

    # 需要删除的错误记录（消耗邮箱不应该在账号列表中）
    wrong_accounts = [
        'nnxp47bwy@009025.xyz',
        'wbjf08wcv@009025.xyz'
    ]

    # 真实验证通过的账号
    correct_accounts = [
        {
            'email': 'vethuxntarz@009025.xyz',
            'consumed_email': 'nnxp47bwy@009025.xyz',
            'note': '验证成功 | 消耗了 nnxp47bwy 作为接收邮箱'
        },
        {
            'email': 'jqqr48lgt@009025.xyz',
            'consumed_email': 'wbjf08wcv@009025.xyz',
            'note': '验证成功 | 消耗了 wbjf08wcv 作为接收邮箱'
        }
    ]

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Delete wrong account records (delete related verifications first)
        print("=" * 50)
        print("Deleting wrong account records...")
        for email in wrong_accounts:
            cursor.execute("SELECT id FROM accounts WHERE email = %s", (email,))
            row = cursor.fetchone()
            if row:
                account_id = row['id']
                cursor.execute("DELETE FROM verifications WHERE account_id = %s", (account_id,))
                ver_count = cursor.rowcount
                cursor.execute("DELETE FROM accounts WHERE id = %s", (account_id,))
                print(f"  [OK] Deleted: {email} ({ver_count} verifications)")
            else:
                print(f"  [--] Not found: {email}")

        # 2. Update/create correct account records
        print("\nUpdating correct account records...")
        for acc in correct_accounts:
            existing = get_account_by_email(acc['email'])
            if existing:
                cursor.execute("""
                    UPDATE accounts
                    SET status = 'verified',
                        consumed_email = %s,
                        note = %s,
                        updated_at = NOW()
                    WHERE email = %s
                """, (acc['consumed_email'], acc['note'], acc['email']))
                print(f"  [OK] Updated: {acc['email']} (consumed: {acc['consumed_email']})")
            else:
                cursor.execute("""
                    INSERT INTO accounts (email, password, status, consumed_email, note, created_at)
                    VALUES (%s, %s, 'verified', %s, %s, NOW())
                """, (acc['email'], '(need password from email pool)', acc['consumed_email'], acc['note']))
                print(f"  [OK] Created: {acc['email']} (consumed: {acc['consumed_email']})")

        print("\n" + "=" * 50)
        print("Fix completed!")

        # Show current verified accounts
        print("\nCurrent verified accounts:")
        cursor.execute("SELECT email, consumed_email, note FROM accounts WHERE status = 'verified'")
        for row in cursor.fetchall():
            print(f"  - {row['email']}")
            if row['consumed_email']:
                print(f"    consumed: {row['consumed_email']}")

if __name__ == "__main__":
    fix_accounts()
