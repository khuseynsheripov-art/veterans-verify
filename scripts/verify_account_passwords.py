"""
账号密码验证脚本

功能：
1. 检查数据库和邮箱池中的密码一致性
2. 生成验证报告（不修改任何数据）
3. 可选：尝试实际登录验证密码正确性

使用方法：
    python scripts/verify_account_passwords.py --check-only    # 只检查一致性
    python scripts/verify_account_passwords.py --verify-login  # 实际登录验证（慢，有风控风险）
"""

import sys
import os
import json
import asyncio
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_accounts
from email_pool import EmailPoolManager
from run_verify import get_password_candidates


def check_password_consistency():
    """
    检查密码一致性（不登录，只对比数据）
    """
    print("\n" + "="*70)
    print("账号密码一致性检查")
    print("="*70)

    try:
        # 获取所有账号（不限制状态和数量）
        accounts = get_accounts(status=None, limit=10000)
        pool = EmailPoolManager()
    except Exception as e:
        print(f"❌ 获取数据失败: {e}")
        return

    print(f"\n总账号数: {len(accounts)}\n")

    results = {
        "check_time": datetime.now().isoformat(),
        "total_accounts": len(accounts),
        "consistent": [],      # 密码一致
        "inconsistent": [],    # 密码不一致
        "pool_only": [],       # 只有邮箱池有密码
        "db_only": [],         # 只有数据库有密码
        "no_password": []      # 都没有密码
    }

    for idx, account in enumerate(accounts, 1):
        email = account.get("email")
        is_own = account.get("is_own_account", False)

        # 获取密码候选
        candidates = get_password_candidates(email)

        # 分析密码来源
        pool_pwd = None
        db_pwd = None

        for candidate in candidates:
            if candidate["source"] == "邮箱池":
                pool_pwd = candidate["password"]
            elif candidate["source"] == "数据库":
                db_pwd = candidate["password"]

        # 构建结果
        account_info = {
            "email": email,
            "is_own_account": is_own,
            "pool_password": pool_pwd,
            "db_password": db_pwd
        }

        # 分类
        if pool_pwd and db_pwd:
            if pool_pwd == db_pwd:
                results["consistent"].append(account_info)
                print(f"[{idx:3d}] ✓ {email:<40} 一致")
            else:
                results["inconsistent"].append(account_info)
                print(f"[{idx:3d}] ⚠️ {email:<40} 不一致！")
                print(f"       邮箱池: {pool_pwd}")
                print(f"       数据库: {db_pwd}")
        elif pool_pwd and not db_pwd:
            results["pool_only"].append(account_info)
            print(f"[{idx:3d}] ℹ️ {email:<40} 仅邮箱池")
        elif db_pwd and not pool_pwd:
            results["db_only"].append(account_info)
            print(f"[{idx:3d}] ℹ️ {email:<40} 仅数据库")
        else:
            results["no_password"].append(account_info)
            print(f"[{idx:3d}] ❌ {email:<40} 无密码")

    # 保存结果
    output_file = "data/password_check_results.json"
    os.makedirs("data", exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # 打印统计
    print("\n" + "="*70)
    print("统计结果")
    print("="*70)
    print(f"✓ 密码一致:         {len(results['consistent']):3d} 个")
    print(f"⚠️ 密码不一致:       {len(results['inconsistent']):3d} 个")
    print(f"ℹ️ 仅邮箱池有密码:   {len(results['pool_only']):3d} 个")
    print(f"ℹ️ 仅数据库有密码:   {len(results['db_only']):3d} 个")
    print(f"❌ 无密码:           {len(results['no_password']):3d} 个")
    print("="*70)
    print(f"\n详细结果已保存到: {output_file}")

    # 如果有密码不一致的账号，列出详情
    if results['inconsistent']:
        print("\n⚠️ 密码不一致的账号详情:")
        print("-"*70)
        for acc in results['inconsistent']:
            print(f"\n邮箱: {acc['email']}")
            print(f"  邮箱池密码: {acc['pool_password']}")
            print(f"  数据库密码: {acc['db_password']}")
            print(f"  自有账号: {'是' if acc['is_own_account'] else '否'}")
        print("-"*70)

    return results


async def verify_with_login(email: str, password: str, timeout: int = 30) -> dict:
    """
    尝试实际登录验证密码（使用 CDP）

    返回: {
        "success": bool,     # 是否成功
        "stage": str,        # 到达的阶段
        "error": str         # 错误信息
    }
    """
    from playwright.async_api import async_playwright

    result = {
        "success": False,
        "stage": "未开始",
        "error": None
    }

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # 导航到登录页
            result["stage"] = "导航到登录页"
            await page.goto("https://chatgpt.com/auth/login", timeout=timeout*1000)
            await asyncio.sleep(2)

            # 输入邮箱
            result["stage"] = "输入邮箱"
            email_input = page.locator('input[type="email"]').first
            await email_input.fill(email)

            # 点击继续
            continue_btn = page.locator('button:has-text("Continue")').first
            await continue_btn.click()
            await asyncio.sleep(3)

            # 输入密码
            result["stage"] = "输入密码"
            password_input = page.locator('input[type="password"]').first
            await password_input.fill(password)

            # 点击继续
            continue_btn = page.locator('button:has-text("Continue")').first
            await continue_btn.click()
            await asyncio.sleep(5)

            # 检查结果
            result["stage"] = "检查登录结果"
            current_url = page.url
            text = await page.evaluate("() => document.body?.innerText || ''")
            text_lower = text.lower()

            # 判断成功标志
            if "incorrect" in text_lower or "wrong" in text_lower:
                result["stage"] = "密码错误"
                result["success"] = False
            elif "verify" in text_lower or "code" in text_lower or "chatgpt.com" in current_url:
                result["stage"] = "登录成功（等待验证码）"
                result["success"] = True
            else:
                result["stage"] = "无法判断"
                result["success"] = None
                result["error"] = f"页面内容: {text[:200]}"

            await browser.close()

    except Exception as e:
        result["error"] = str(e)
        result["success"] = False

    return result


async def verify_passwords_with_login(update_database: bool = True):
    """
    通过实际登录验证密码正确性，并更新数据库

    Args:
        update_database: 是否自动更新数据库中的正确密码（默认 True）

    功能：
    1. 遍历所有账号
    2. 尝试所有候选密码登录 ChatGPT
    3. 找到正确的密码
    4. 更新数据库，保存正确的密码

    ⚠️ 警告：
    - 这会尝试登录所有账号，可能触发风控
    - 速度很慢（每个账号约 10-15 秒）
    """
    print("\n" + "="*70)
    print("⚠️ 警告：即将尝试实际登录验证所有账号")
    print("="*70)
    print("- 这会实际登录 ChatGPT 验证密码")
    print("- 可能触发账号风控")
    print("- 速度很慢，可能需要数小时")
    if update_database:
        print("- ✅ 会自动更新数据库中的正确密码")
    else:
        print("- ⚠️ 只验证，不更新数据库")
    print()

    confirm = input("确认继续？(yes/no): ").strip().lower()
    if confirm != "yes":
        print("已取消")
        return

    # 先运行一致性检查
    print("\n先运行一致性检查...")
    check_results = check_password_consistency()

    # 验证密码不一致的账号 + 仅邮箱池有密码的账号
    inconsistent = check_results.get("inconsistent", [])
    pool_only = check_results.get("pool_only", [])

    to_verify = inconsistent + pool_only

    if not to_verify:
        print("\n✓ 所有账号密码已验证，无需重复验证")
        return

    print(f"\n需要验证的账号:")
    print(f"  密码不一致: {len(inconsistent)} 个")
    print(f"  仅邮箱池: {len(pool_only)} 个")
    print(f"  总计: {len(to_verify)} 个")
    print("\n开始验证...\n")

    verify_results = []
    updated_count = 0

    for idx, account in enumerate(to_verify, 1):
        email = account["email"]
        pool_pwd = account.get("pool_password")
        db_pwd = account.get("db_password")

        print(f"[{idx}/{len(to_verify)}] 验证账号: {email}")

        result = {
            "email": email,
            "is_own_account": account["is_own_account"],
            "pool_result": None,
            "db_result": None,
            "correct_password": None,
            "correct_source": None,
            "database_updated": False
        }

        # 构建候选密码列表
        candidates = []
        if pool_pwd:
            candidates.append(("邮箱池", pool_pwd))
        if db_pwd and db_pwd != pool_pwd:
            candidates.append(("数据库", db_pwd))

        # 尝试每个候选密码
        for source, password in candidates:
            print(f"  尝试{source}密码...")
            login_result = await verify_with_login(email, password, timeout=30)

            if source == "邮箱池":
                result["pool_result"] = login_result
            else:
                result["db_result"] = login_result

            if login_result["success"]:
                print(f"  ✓ {source}密码正确！")
                result["correct_password"] = password
                result["correct_source"] = source

                # 同步正确密码到数据库和邮箱池
                if update_database:
                    try:
                        # 1. 更新数据库
                        from database import get_account_by_email, update_account
                        db_account = get_account_by_email(email)
                        if db_account:
                            update_account(db_account['id'], password=password)
                            print(f"  ✓ 已更新数据库密码")

                        # 2. 更新邮箱池
                        pool.update_password(email, password)
                        print(f"  ✓ 已更新邮箱池密码")

                        result["database_updated"] = True
                        updated_count += 1
                        print(f"  ✅ 密码已同步到数据库和邮箱池")
                    except Exception as e:
                        print(f"  ✗ 同步密码失败: {e}")
                break
            else:
                print(f"  ✗ {source}密码错误: {login_result.get('stage')}")
                await asyncio.sleep(3)  # 失败后等待再试下一个

        if not result["correct_password"]:
            print(f"  ❌ 所有密码都错误！")

        verify_results.append(result)

        # 每验证 5 个账号休息一下
        if idx % 5 == 0:
            print(f"\n  → 已验证 {idx} 个账号，休息 30 秒...")
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(10)  # 每个账号之间等待 10 秒

    # 保存验证结果
    output_file = "data/login_verification_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "verify_time": datetime.now().isoformat(),
            "total_verified": len(verify_results),
            "database_updated": update_database,
            "updated_count": updated_count,
            "results": verify_results
        }, f, indent=2, ensure_ascii=False)

    # 打印统计
    pool_correct = sum(1 for r in verify_results if r["correct_source"] == "邮箱池")
    db_correct = sum(1 for r in verify_results if r["correct_source"] == "数据库")
    both_wrong = sum(1 for r in verify_results if not r["correct_password"])

    print("\n" + "="*70)
    print("验证结果统计")
    print("="*70)
    print(f"验证账号数: {len(verify_results)}")
    print(f"  ✓ 邮箱池密码正确: {pool_correct}")
    print(f"  ✓ 数据库密码正确: {db_correct}")
    print(f"  ❌ 两个都错误: {both_wrong}")
    if update_database:
        print(f"  📝 已更新数据库: {updated_count} 个")
    print("="*70)
    print(f"\n详细结果已保存到: {output_file}")

    if update_database and updated_count > 0:
        print("\n✅ 数据库已更新，现在密码数据与 ChatGPT 实际密码一致！")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="账号密码验证脚本")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只检查密码一致性（推荐，快速且安全）"
    )
    parser.add_argument(
        "--verify-login",
        action="store_true",
        help="通过实际登录验证密码（慢，有风控风险）"
    )

    args = parser.parse_args()

    if args.verify_login:
        asyncio.run(verify_passwords_with_login())
    else:
        # 默认只检查一致性
        check_password_consistency()


if __name__ == "__main__":
    main()
