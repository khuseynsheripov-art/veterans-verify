#!/usr/bin/env python
"""
Veterans Verify - 账号验证脚本

用途：批量检查已验证账号是否能正常登录

使用方式：
  # 检查所有已验证账号
  python check_accounts.py

  # 检查指定账号
  python check_accounts.py --email xxx@009025.xyz

  # 只检查前 N 个
  python check_accounts.py --limit 5
"""
import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / '.env.local')

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# 配置
CDP_URL = os.getenv("CDP_URL", "http://127.0.0.1:9488")
WORKER_DOMAIN = os.getenv("WORKER_DOMAINS", "apimail.009025.xyz").split(",")[0].strip()
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAINS", "009025.xyz").split(",")[0].strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORDS", "").split(",")[0].strip()


def get_email_manager():
    """创建 EmailManager 实例"""
    from email_manager import EmailManager
    return EmailManager(
        worker_domain=WORKER_DOMAIN,
        email_domain=EMAIL_DOMAIN,
        admin_password=ADMIN_PASSWORD
    )


async def check_single_account(page, email: str, password: str) -> Dict:
    """
    检查单个账号

    Returns:
        {
            'email': str,
            'login_success': bool,
            'has_claim_offer': bool,
            'has_plus': bool,
            'error': str or None
        }
    """
    result = {
        'email': email,
        'login_success': False,
        'has_claim_offer': False,
        'has_plus': False,
        'error': None
    }

    try:
        # 1. 访问登录页面
        await page.goto("https://chatgpt.com/auth/login", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # 点击 Log in 按钮
        login_btn = await page.query_selector('button:has-text("Log in")')
        if login_btn:
            await login_btn.click()
            await asyncio.sleep(3)

        # 2. 输入邮箱
        email_input = await page.query_selector('input[name="email"], input[type="email"]')
        if not email_input:
            # 等待页面加载
            await asyncio.sleep(2)
            email_input = await page.query_selector('input[name="email"], input[type="email"]')

        if email_input:
            await email_input.fill(email)
            await asyncio.sleep(0.5)

            # 点击继续
            continue_btn = await page.query_selector('button:has-text("Continue")')
            if continue_btn:
                await continue_btn.click()
                await asyncio.sleep(3)

        # 3. 输入密码
        password_input = await page.query_selector('input[type="password"]')
        if password_input:
            await password_input.fill(password)
            await asyncio.sleep(0.5)

            # 点击继续
            continue_btn = await page.query_selector('button:has-text("Continue")')
            if continue_btn:
                await continue_btn.click()
                await asyncio.sleep(5)

        # 4. 检查是否需要验证码
        text = await page.evaluate("() => document.body?.innerText || ''")
        if "check your inbox" in text.lower() or "verification code" in text.lower():
            logger.info(f"  需要验证码，尝试从邮箱获取...")

            # 获取验证码
            try:
                em = get_email_manager()
                code = em.check_verification_code(email, max_retries=10, interval=2.0)
                if code:
                    code_input = await page.query_selector('input[name="code"], input[type="text"]')
                    if code_input:
                        await code_input.fill(code)
                        await asyncio.sleep(0.5)

                        continue_btn = await page.query_selector('button:has-text("Continue")')
                        if continue_btn:
                            await continue_btn.click()
                            await asyncio.sleep(5)
                else:
                    result['error'] = "无法获取验证码"
                    return result
            except Exception as e:
                result['error'] = f"验证码获取失败: {e}"
                return result

        # 5. 检查登录状态
        await asyncio.sleep(3)
        url = page.url
        text = await page.evaluate("() => document.body?.innerText || ''")
        text_lower = text.lower()

        # 检查是否登录成功
        if "chatgpt.com" in url and "auth" not in url:
            result['login_success'] = True

            # 关闭可能的对话框
            close_btn = await page.query_selector('button:has-text("Close"), button[aria-label="Close"]')
            if close_btn:
                try:
                    await close_btn.click()
                    await asyncio.sleep(1)
                except:
                    pass

            # 检查是否有 Plus
            if "plus" in text_lower or "upgrade" not in text_lower:
                result['has_plus'] = True

        # 6. 检查 veterans-claim 页面
        if result['login_success']:
            await page.goto("https://chatgpt.com/veterans-claim", wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(3)

            text = await page.evaluate("() => document.body?.innerText || ''")
            text_lower = text.lower()

            if "claim offer" in text_lower:
                has_verify_button = "verify your eligibility" in text_lower or "verify eligibility" in text_lower
                if not has_verify_button:
                    result['has_claim_offer'] = True

        # 7. 退出登录
        await page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=10000)
        await asyncio.sleep(2)

        # 点击用户菜单
        profile_btn = await page.query_selector('button[aria-label*="profile"], [data-testid="profile-button"]')
        if profile_btn:
            await profile_btn.click()
            await asyncio.sleep(1)

            logout_btn = await page.query_selector('a:has-text("Log out"), button:has-text("Log out")')
            if logout_btn:
                await logout_btn.click()
                await asyncio.sleep(1)

                confirm_btn = await page.query_selector('button:has-text("Log out")')
                if confirm_btn:
                    await confirm_btn.click()
                    await asyncio.sleep(3)

    except Exception as e:
        result['error'] = str(e)

    return result


async def check_accounts(accounts: List[Dict]):
    """批量检查账号"""
    from playwright.async_api import async_playwright

    results = []

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            logger.info("已连接 Chrome")

            contexts = browser.contexts
            if not contexts:
                logger.error("没有浏览器上下文")
                return results

            context = contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()

            for i, account in enumerate(accounts):
                email = account['email']
                password = account['password']

                logger.info("")
                logger.info(f"[{i+1}/{len(accounts)}] 检查: {email}")

                result = await check_single_account(page, email, password)
                results.append(result)

                # 显示结果
                if result['login_success']:
                    status = "✅ 登录成功"
                    if result['has_claim_offer']:
                        status += " | Claim offer ✅"
                    else:
                        status += " | Claim offer ❌"
                else:
                    status = f"❌ 登录失败: {result['error']}"

                logger.info(f"    {status}")

                # 短暂休息
                if i < len(accounts) - 1:
                    await asyncio.sleep(3)

        except Exception as e:
            logger.error(f"检查失败: {e}")

    return results


def print_summary(results: List[Dict]):
    """打印汇总"""
    print()
    print("=" * 60)
    print("检查结果汇总")
    print("=" * 60)

    total = len(results)
    login_success = sum(1 for r in results if r['login_success'])
    claim_offer = sum(1 for r in results if r['has_claim_offer'])

    print(f"总计: {total} 个账号")
    print(f"登录成功: {login_success} 个")
    print(f"Claim offer: {claim_offer} 个")
    print()

    # 详细列表
    print("详细列表:")
    print("-" * 60)
    for r in results:
        status = "✅" if r['login_success'] else "❌"
        claim = "✅" if r['has_claim_offer'] else "❌"
        print(f"  {status} {r['email']} | Claim: {claim}")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Veterans Verify - 账号验证脚本")
    parser.add_argument("--email", "-e", help="检查指定账号")
    parser.add_argument("--limit", "-n", type=int, help="只检查前 N 个")
    parser.add_argument("--cdp", default=CDP_URL, help=f"CDP URL (默认: {CDP_URL})")

    args = parser.parse_args()

    global CDP_URL
    CDP_URL = args.cdp

    # 获取账号列表
    from database import get_accounts, get_account_by_email

    if args.email:
        account = get_account_by_email(args.email)
        if not account:
            print(f"账号不存在: {args.email}")
            return
        accounts = [account]
    else:
        accounts = get_accounts(status='verified', limit=args.limit or 100)

    if not accounts:
        print("没有找到已验证的账号")
        return

    print("=" * 60)
    print("Veterans Verify - 账号验证")
    print("=" * 60)
    print(f"CDP: {CDP_URL}")
    print(f"待检查: {len(accounts)} 个账号")
    print()
    print("请确保已运行 scripts/start-chrome-devtools.bat")
    print()

    results = asyncio.run(check_accounts(accounts))
    print_summary(results)


if __name__ == "__main__":
    main()
