#!/usr/bin/env python
# 临时脚本：检查账号数据
from database import get_accounts, get_verifications_by_account
import json

accs = get_accounts(limit=10)
for a in accs:
    print(f"\n{'='*50}")
    print(f"邮箱: {a['email']}")
    print(f"状态: {a['status']}")
    print(f"密码: {a['password']}")
    print(f"注册姓名: {a.get('profile_name')}")
    print(f"注册生日: {a.get('profile_birthday')}")
    print(f"备注: {a.get('note')}")

    if a.get('id'):
        vers = get_verifications_by_account(a['id'])
        print(f"验证次数: {len(vers)}")
        for v in vers:
            print(f"  - {v.get('first_name')} {v.get('last_name')} ({v.get('branch')})")
            print(f"    状态: {v.get('status')}")
            print(f"    军人生日: {v.get('birth_month')} {v.get('birth_day')}, {v.get('birth_year')}")
            print(f"    退伍日期: {v.get('discharge_month')} {v.get('discharge_day')}, {v.get('discharge_year')}")
