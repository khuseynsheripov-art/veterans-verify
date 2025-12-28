#!/usr/bin/env python
"""
Veterans Verify - 独立运行的自动化验证脚本

使用方式：

  模式4（推荐）- 连接已打开的 Chrome:
    1. 运行 scripts/start-chrome-devtools.bat
    2. 手动登录 ChatGPT
    3. python run_verify.py --email xxx@009025.xyz

  测试模式 - 打印操作流程:
    python run_verify.py --test

  获取表单数据（不自动化）:
    python run_verify.py --data xxx@009025.xyz
"""
import os
import sys
import time
import random
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

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
VETERANS_CLAIM_URL = "https://chatgpt.com/veterans-claim"
SCREENSHOT_DIR = Path("screenshots")

# 邮箱服务配置
WORKER_DOMAIN = os.getenv("WORKER_DOMAINS", "apimail.009025.xyz").split(",")[0].strip()
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAINS", "009025.xyz").split(",")[0].strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORDS", "").split(",")[0].strip()


# ==================== 邮件验证 ====================

def get_email_jwt(email: str) -> Optional[str]:
    """从邮箱池获取邮箱 JWT"""
    try:
        from email_pool import EmailPoolManager
        pool = EmailPoolManager()
        email_data = pool.get_by_address(email)
        if email_data:
            jwt = email_data.get('jwt')
            if jwt:
                logger.info(f"从邮箱池获取到 JWT: {email}")
                return jwt
    except Exception as e:
        logger.warning(f"获取邮箱 JWT 失败: {e}")

    # 尝试从 .env 获取（用于测试）
    logger.warning(f"邮箱池中没有 {email} 的 JWT，验证链接需要手动点击")
    return None


def get_email_manager():
    """创建 EmailManager 实例"""
    from email_manager import EmailManager
    return EmailManager(
        worker_domain=WORKER_DOMAIN,
        email_domain=EMAIL_DOMAIN,
        admin_password=ADMIN_PASSWORD
    )


async def check_and_click_verification_link(page, email: str, max_retries: int = 20) -> bool:
    """
    检查并点击邮件验证链接

    Args:
        page: Playwright page
        email: 邮箱地址
        max_retries: 最大重试次数

    Returns:
        是否成功点击
    """
    logger.info(f"开始检查验证链接: {email}")

    try:
        email_manager = get_email_manager()

        # 查找验证链接（每 3 秒检查一次，最多重试 max_retries 次）
        link = email_manager.check_verification_link(
            email=email,
            max_retries=max_retries,
            interval=3.0
        )

        if link:
            logger.info(f"找到验证链接，正在访问...")
            logger.debug(f"链接: {link[:100]}...")

            # 在当前页面访问验证链接
            await page.goto(link, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # 检查页面状态
            text = await page.evaluate("() => document.body?.innerText || ''")

            if "verified" in text.lower() or "success" in text.lower():
                logger.info("验证链接点击成功！")
                return True
            elif "error" in text.lower() or "expired" in text.lower():
                logger.warning("验证链接可能已过期或无效")
                return False
            else:
                # 可能需要返回 veterans-claim 页面继续
                logger.info("已访问验证链接，返回继续检查...")
                await asyncio.sleep(2)
                await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)
                return True
        else:
            logger.warning("未找到验证链接")
            return False

    except Exception as e:
        logger.error(f"检查验证链接失败: {e}")
        return False


# ==================== 数据生成 ====================

def generate_discharge_date() -> Dict:
    """生成随机退伍日期（过去 1-11 个月内）"""
    today = datetime.now()
    months_ago = random.randint(1, 11)
    discharge = today - timedelta(days=months_ago * 30)

    months = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']

    return {
        "month": months[discharge.month - 1],
        "day": str(discharge.day),
        "year": str(discharge.year)
    }


# ==================== 页面状态检测 ====================

async def detect_page_state(page) -> Tuple[str, str]:
    """检测当前页面状态"""
    try:
        url = page.url
        text = await page.evaluate("() => document.body?.innerText || ''")
        text_lower = text.lower()

        # 成功 - 最高优先级
        if "you've been verified" in text_lower or "you have been verified" in text_lower:
            return "success", "Verification successful!"

        # 点击验证链接后显示 "already been approved" - 需要返回 veterans-claim 点击 Claim offer
        if "already been approved" in text_lower:
            return "email_verified", "Email verified, need to claim offer"

        # Stripe 支付页面 = 验证成功（显示 $0.00 免费订阅）
        if "pay.openai.com" in url:
            if "$0.00" in text or "chatgpt plus" in text_lower:
                return "success_stripe", "Verification successful! Redirected to Stripe payment"
            return "stripe_page", "On Stripe payment page"

        # Claim offer 按钮 = 验证成功（已通过 SheerID 验证）
        # veterans-claim 页面：
        #   - 未验证：显示 "Verify your eligibility" 按钮
        #   - 已验证：显示 "Claim offer" 按钮（没有验证按钮）
        if "veterans-claim" in url:
            has_claim_offer = "claim offer" in text_lower
            # 检查是否有验证按钮（未验证状态）
            has_verify_button = "verify your eligibility" in text_lower or "verify eligibility" in text_lower
            # 有 Claim offer 且没有验证按钮 = 验证成功
            if has_claim_offer and not has_verify_button:
                return "success_claim", "Verification successful! Claim offer available"

        # 失败状态 - 需要换数据
        if "not approved" in text_lower:
            return "not_approved", "Verification rejected"

        if "unable to verify" in text_lower:
            return "unable_to_verify", "Unable to verify"

        if "verification limit exceeded" in text_lower:
            return "verification_limit", "Veteran data already used"

        # 错误状态（需要点击 Try Again 重新开始）
        if "sourcesunavailable" in text_lower or "sources unavailable" in text_lower:
            return "error_sources", "SheerID sources unavailable"

        if "page you requested cannot be found" in text_lower:
            return "error_link", "Verification link invalid"

        # 需要操作
        if "check your email" in text_lower:
            return "check_email", "Need email verification"

        if "please log in" in text_lower:
            return "please_login", "Need to login first"

        # SheerID 表单页面判断 - 多种特征
        # 1. 有 "Verify My Eligibility" 按钮
        # 2. URL 包含 sheerid.com
        # 3. 有 "Branch of service" 字段
        if "verify my eligibility" in text_lower:
            return "sheerid_form", "On SheerID form"

        if "sheerid.com" in url and "branch of service" in text_lower:
            return "sheerid_form", "On SheerID form"

        if "sheerid.com" in url and "first name" in text_lower:
            return "sheerid_form", "On SheerID form"

        # error + try again 放在 sheerid_form 之后，避免误判
        if "error" in text_lower and "try again" in text_lower:
            return "error_retry", "Error occurred, need retry"

        # veterans-claim 页面判断
        if "veterans-claim" in url and ("验证资格条件" in text or "verify your eligibility" in text_lower or "verify eligibility" in text_lower):
            return "veterans_claim", "On veterans-claim (logged in)"

        if "veterans-claim" in url:
            return "veterans_claim_check", "On veterans-claim page"

        # ChatGPT 首页
        if "chatgpt.com" in url and "veterans-claim" not in url:
            return "chatgpt_home", "On ChatGPT home"

        # SheerID 页面但状态不明
        if "sheerid.com" in url:
            return "sheerid_unknown", f"On SheerID page: {text[:100]}"

        return "unknown", text[:200]

    except Exception as e:
        return "error", str(e)


# ==================== 表单操作 ====================

async def fill_sheerid_form(page, form_data: Dict) -> bool:
    """
    填写 SheerID 表单

    重要：Status 必须第一个选择，否则其他字段会被清空！

    表单结构（2025-12-26 验证）：
    - Status: combobox (必须第一个!)
    - Branch of service: combobox
    - First/Last name: textbox
    - Date of birth: combobox (month) + textbox (day/year)
    - Discharge date: combobox (month) + textbox (day/year)
    - Email: textbox
    """
    logger.info(f"填写表单: {form_data['first_name']} {form_data['last_name']} ({form_data['branch']})")

    try:
        async def select_combobox(label: str, value: str):
            """选择下拉框选项"""
            try:
                # 点击 combobox 打开列表
                combobox = page.get_by_role("combobox", name=label)
                await combobox.click(timeout=5000)
                await asyncio.sleep(0.5)

                # 选择选项
                option = page.get_by_role("option", name=value, exact=True)
                await option.click(timeout=3000)
                await asyncio.sleep(0.3)
                logger.debug(f"选择 {label}: {value}")
                return True
            except Exception as e:
                logger.warning(f"选择 {label} 失败: {e}")
                return False

        async def fill_textbox(label: str, value: str, nth: int = 0):
            """填写文本框"""
            try:
                textbox = page.get_by_role("textbox", name=label).nth(nth)
                await textbox.fill(value, timeout=5000)
                await asyncio.sleep(random.uniform(0.1, 0.3))
                logger.debug(f"填写 {label}: {value}")
                return True
            except Exception as e:
                logger.warning(f"填写 {label} 失败: {e}")
                return False

        await asyncio.sleep(1)

        # 1. Status (动态检测！有些页面有此字段，有些没有)
        # 必须第一个选，否则其他字段会被清空
        try:
            status_combobox = page.get_by_role("combobox", name="Status")
            if await status_combobox.count() > 0:
                logger.info("检测到 Status 字段，选择 'Military Veteran or Retiree'")
                await select_combobox("Status", "Military Veteran or Retiree")
                await asyncio.sleep(0.5)
            else:
                logger.info("没有 Status 字段，跳过")
        except Exception as e:
            logger.debug(f"Status 字段检测: {e} (跳过)")
        await asyncio.sleep(0.3)

        # 2. Branch of service
        await select_combobox("Branch of service", form_data['branch'])
        await asyncio.sleep(0.3)

        # 3. First name & Last name
        await fill_textbox("First name", form_data['first_name'])
        await fill_textbox("Last name", form_data['last_name'])

        # 4. Date of birth (month combobox + day/year textbox)
        await select_combobox("Date of birth", form_data['birth_month'])
        await asyncio.sleep(0.2)

        # Day 和 Year 有两组，第一组是 Date of birth，第二组是 Discharge date
        day_boxes = page.get_by_role("textbox", name="Day")
        year_boxes = page.get_by_role("textbox", name="Year")

        await day_boxes.nth(0).fill(form_data['birth_day'], timeout=5000)
        await asyncio.sleep(0.1)
        await year_boxes.nth(0).fill(form_data['birth_year'], timeout=5000)
        await asyncio.sleep(0.2)

        # 5. Discharge date (month combobox + day/year textbox)
        await select_combobox("Discharge date", form_data['discharge_month'])
        await asyncio.sleep(0.2)

        await day_boxes.nth(1).fill(form_data['discharge_day'], timeout=5000)
        await asyncio.sleep(0.1)
        await year_boxes.nth(1).fill(form_data['discharge_year'], timeout=5000)
        await asyncio.sleep(0.2)

        # 6. Email
        await fill_textbox("Email address", form_data['email'])

        logger.info("表单填写完成")
        return True

    except Exception as e:
        logger.error(f"表单填写失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def submit_form(page) -> bool:
    """提交表单"""
    try:
        for selector in ['button:has-text("Verify My Eligibility")', 'button[type="submit"]']:
            try:
                btn = await page.query_selector(selector)
                if btn and not await btn.get_attribute("disabled"):
                    await btn.click()
                    logger.info("表单已提交")
                    await asyncio.sleep(3)
                    return True
            except:
                continue
        logger.error("找不到提交按钮")
        return False
    except Exception as e:
        logger.error(f"提交失败: {e}")
        return False


async def click_try_again(page) -> bool:
    """点击 Try Again，如果没有按钮则直接导航到 veterans-claim"""
    for selector in ['a:has-text("Try Again")', 'button:has-text("Try Again")']:
        try:
            el = await page.query_selector(selector)
            if el:
                await el.click()
                await asyncio.sleep(2)
                logger.info("点击 Try Again")
                return True
        except:
            continue

    # 没有 Try Again 按钮，直接导航到 veterans-claim
    logger.info("没有 Try Again 按钮，直接导航到 veterans-claim")
    await page.goto(VETERANS_CLAIM_URL)
    await asyncio.sleep(3)
    return True


async def click_verify_button(page) -> bool:
    """点击验证按钮或 Claim offer 按钮"""
    selectors = [
        'button:has-text("Claim offer")',  # 已验证状态
        'button:has-text("验证资格条件")',
        'button:has-text("Verify your eligibility")',
        'button:has-text("Verify eligibility")'
    ]
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                await el.click()
                await asyncio.sleep(3)
                logger.info(f"点击按钮: {selector}")
                return True
        except:
            continue

    # 没找到按钮，记录警告
    logger.warning("未找到验证按钮，可能需要先退出登录或页面状态异常")
    return False


async def check_if_another_account_logged_in(page, target_email: str) -> bool:
    """
    检测是否有另一个账号登录着（需要先退出）

    返回 True = 需要先退出登录
    返回 False = 正常继续
    """
    try:
        url = page.url
        text = await page.evaluate("() => document.body?.innerText || ''")
        text_lower = text.lower()

        # 情况1：在 Stripe 支付页面（上一个验证成功后的页面）
        if "pay.openai.com" in url:
            logger.warning("检测到 Stripe 支付页面（上一个账号验证成功），需要先退出登录")
            return True

        # 情况2：veterans-claim 页面有 Claim offer 按钮（已验证成功）
        if "veterans-claim" in url:
            has_claim_offer = "claim offer" in text_lower
            has_verify_button = "verify your eligibility" in text_lower or "verify eligibility" in text_lower
            if has_claim_offer and not has_verify_button:
                logger.warning("检测到 Claim offer（上一个账号已验证），需要先退出登录")
                return True

        # 情况3：SheerID 成功页面
        if "you've been verified" in text_lower or "you have been verified" in text_lower:
            logger.warning("检测到验证成功页面（上一个账号），需要先退出登录")
            return True

        return False
    except:
        return False


async def save_screenshot(page, name: str):
    """保存截图"""
    try:
        SCREENSHOT_DIR.mkdir(exist_ok=True)
        path = SCREENSHOT_DIR / f"{name}_{int(time.time())}.png"
        await page.screenshot(path=str(path))
        logger.debug(f"截图: {path}")
    except:
        pass


async def get_logged_in_account(page) -> Optional[str]:
    """
    获取当前登录的 ChatGPT 账号邮箱

    验证成功后调用此函数，检测真实登录的账号（@ 后面的邮箱）
    这个账号才是获得 Plus 的账号，不是接收验证链接的临时邮箱

    Returns:
        登录账号的邮箱，如果未登录则返回 None
    """
    logger.info("检测当前登录的 ChatGPT 账号...")

    try:
        # 先导航到 ChatGPT 首页
        await page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # 方法1：点击用户菜单查看邮箱
        try:
            # 点击用户头像/菜单按钮
            user_menu = await page.query_selector('[data-testid="profile-button"], [aria-label*="profile"], button[class*="avatar"]')
            if user_menu:
                await user_menu.click()
                await asyncio.sleep(1)

                # 获取页面内容，查找邮箱
                text = await page.evaluate("() => document.body?.innerText || ''")

                # 匹配邮箱格式
                import re
                email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
                emails = re.findall(email_pattern, text)

                # 过滤出合理的邮箱（排除系统邮箱）
                for email in emails:
                    if not email.endswith('@openai.com') and not email.endswith('@anthropic.com'):
                        logger.info(f"✓ 检测到登录账号: {email}")
                        return email

                # 关闭菜单
                await page.keyboard.press("Escape")
        except Exception as e:
            logger.debug(f"方法1失败: {e}")

        # 方法2：从设置页面获取
        try:
            await page.goto("https://chatgpt.com/settings", wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(2)

            text = await page.evaluate("() => document.body?.innerText || ''")

            import re
            email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
            emails = re.findall(email_pattern, text)

            for email in emails:
                if not email.endswith('@openai.com'):
                    logger.info(f"✓ 检测到登录账号: {email}")
                    return email
        except Exception as e:
            logger.debug(f"方法2失败: {e}")

        logger.warning("未能检测到登录账号")
        return None

    except Exception as e:
        logger.error(f"检测登录账号失败: {e}")
        return None


async def logout_chatgpt(page) -> bool:
    """
    退出 ChatGPT 登录，为下一个账号做准备

    退出方式：
    1. 尝试点击用户菜单 → 退出登录
    2. 如果失败，清除 cookies 并刷新
    """
    logger.info("正在退出 ChatGPT 登录...")

    try:
        # 先导航到 ChatGPT 首页
        await page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # 方法1：尝试点击用户菜单退出
        try:
            # 点击用户头像/菜单按钮（通常在右上角）
            user_menu = await page.query_selector('[data-testid="profile-button"], [aria-label*="profile"], button[class*="avatar"]')
            if user_menu:
                await user_menu.click()
                await asyncio.sleep(1)

                # 点击退出登录选项
                logout_btn = await page.query_selector('a:has-text("Log out"), button:has-text("Log out"), a:has-text("退出"), button:has-text("退出")')
                if logout_btn:
                    await logout_btn.click()
                    await asyncio.sleep(3)
                    logger.info("✓ 已点击退出登录按钮")
                    return True
        except Exception as e:
            logger.debug(f"点击退出按钮失败: {e}")

        # 方法2：清除 cookies（更可靠）
        try:
            context = page.context
            await context.clear_cookies()
            await page.reload()
            await asyncio.sleep(2)
            logger.info("✓ 已清除 Cookies 并刷新页面")
            return True
        except Exception as e:
            logger.warning(f"清除 Cookies 失败: {e}")

        # 方法3：直接访问登出 URL
        try:
            await page.goto("https://chatgpt.com/auth/logout", wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(2)
            logger.info("✓ 已访问登出 URL")
            return True
        except:
            pass

        logger.warning("退出登录可能未完全成功，建议手动检查")
        return False

    except Exception as e:
        logger.error(f"退出登录失败: {e}")
        return False


# ==================== 数据获取 ====================

def get_veteran_data_from_db(email: str) -> Optional[Dict]:
    """从数据库获取军人数据，并创建 pending 验证记录"""
    try:
        from database import (get_available_veteran, get_account_by_email,
                              create_verification, get_or_create_account)

        veteran = get_available_veteran()
        if not veteran:
            logger.warning("数据库中没有可用的军人数据")
            return None

        discharge = generate_discharge_date()

        # 确保账号存在
        account = get_account_by_email(email)
        if not account:
            # 从邮箱池创建账号
            from email_pool import EmailPoolManager
            pool = EmailPoolManager()
            pool_email = pool.get_by_address(email)
            if pool_email:
                from automation.config import generate_password
                password = generate_password()
                account = get_or_create_account(email, password, jwt=pool_email.get('jwt'))
            else:
                logger.warning(f"账号 {email} 不存在且不在邮箱池中")
                return None

        # 创建验证记录（pending 状态）
        verification_id = create_verification(
            account_id=account['id'],
            veteran_id=veteran['id'],
            discharge_month=discharge['month'],
            discharge_day=discharge['day'],
            discharge_year=discharge['year']
        )
        logger.info(f"创建验证记录 #{verification_id}")

        data = {
            'id': veteran['id'],
            'verification_id': verification_id,  # 保存验证记录ID
            'branch': veteran['branch'],
            'first_name': veteran['first_name'],
            'last_name': veteran['last_name'],
            'birth_month': veteran['birth_month'],
            'birth_day': veteran['birth_day'],
            'birth_year': veteran['birth_year'],
            'discharge_month': discharge['month'],
            'discharge_day': discharge['day'],
            'discharge_year': discharge['year'],
            'email': email,
        }
        logger.info(f"获取军人数据: {data['first_name']} {data['last_name']} ({data['branch']})")
        return data
    except ImportError as e:
        logger.warning(f"模块导入失败: {e}")
        return None
    except Exception as e:
        logger.warning(f"数据库获取失败: {e}")
        return None


def get_test_veteran_data(email: str) -> Dict:
    """测试数据"""
    discharge = generate_discharge_date()
    names = [("John", "Smith", "Army"), ("Michael", "Johnson", "Navy"), ("David", "Williams", "Air Force")]
    n = random.choice(names)
    return {
        'id': f"test_{int(time.time())}",
        'branch': n[2],
        'first_name': n[0],
        'last_name': n[1],
        'birth_month': random.choice(['January', 'March', 'May', 'July', 'September', 'November']),
        'birth_day': str(random.randint(1, 28)),
        'birth_year': str(random.randint(1985, 1995)),
        'discharge_month': discharge['month'],
        'discharge_day': discharge['day'],
        'discharge_year': discharge['year'],
        'email': email,
    }


def mark_veteran_consumed(veteran_id: str, email: str, reason: str, verification_id: int = None) -> bool:
    """标记军人数据已消耗，同时更新验证记录为 failed"""
    if not veteran_id:
        logger.warning("[消耗] veteran_id 为空，跳过")
        return False

    try:
        from database import mark_veteran_used, update_verification

        # 1. 标记军人数据已使用
        mark_veteran_used(veteran_id, f"{email}: {reason}")
        logger.info(f"✓ [消耗] 军人数据 {veteran_id} 已标记为已使用 (原因: {reason})")

        # 2. 更新验证记录为 failed
        if verification_id:
            update_verification(verification_id, status='failed', error_type=reason)
            logger.info(f"✓ [消耗] 验证记录 #{verification_id} 已更新为 failed")

        return True
    except Exception as e:
        logger.error(f"✗ [消耗] 标记失败: {veteran_id} - {e}")
        return False


# ==================== 批量验证 ====================

async def run_batch_verify(target_count: int = 1):
    """
    批量验证多个邮箱，直到达到指定成功数量

    Args:
        target_count: 目标成功数量（验证成功多少个才停止）

    流程：
    1. 从邮箱池获取可用邮箱
    2. 运行单个邮箱验证
    3. 成功后退出登录，继续下一个
    4. 直到达到目标数量或邮箱池为空
    """
    from email_pool import EmailPoolManager, EmailStatus

    logger.info("=" * 60)
    logger.info(f"批量验证模式 - 目标成功数量: {target_count}")
    logger.info("=" * 60)

    pool = EmailPoolManager()
    success_count = 0
    attempt_count = 0

    while success_count < target_count:
        # 获取下一个可用邮箱
        email_data = pool.get_available()
        if not email_data:
            logger.warning("邮箱池中没有可用邮箱了！")
            break

        email = email_data['address']
        attempt_count += 1

        logger.info("")
        logger.info("=" * 50)
        logger.info(f"[{attempt_count}] 开始验证: {email}")
        logger.info(f"    进度: {success_count}/{target_count} 成功")
        logger.info("=" * 50)

        # 标记为使用中
        pool.mark_in_use(email)

        # 运行验证（批量模式：成功后退出登录）
        try:
            success = await run_verify_loop(email, logout_after_success=True)

            if success:
                success_count += 1
                pool.mark_verified(email)
                logger.info(f"✅ [{attempt_count}] 验证成功: {email} ({success_count}/{target_count})")
            else:
                pool.mark_failed(email, "验证失败")
                logger.warning(f"❌ [{attempt_count}] 验证失败: {email}")

        except Exception as e:
            pool.mark_failed(email, str(e))
            logger.error(f"❌ [{attempt_count}] 验证异常: {email} - {e}")

        # 短暂休息，避免请求过快
        if success_count < target_count:
            wait_time = random.randint(5, 15)
            logger.info(f"等待 {wait_time} 秒后继续下一个...")
            await asyncio.sleep(wait_time)

    # 统计结果
    logger.info("")
    logger.info("=" * 60)
    logger.info("批量验证完成")
    logger.info(f"  尝试: {attempt_count} 个邮箱")
    logger.info(f"  成功: {success_count} 个")
    logger.info(f"  目标: {target_count} 个")
    logger.info("=" * 60)

    return success_count >= target_count


# ==================== 主验证循环 ====================

async def run_verify_loop(email: str, logout_after_success: bool = False, chatgpt_account: str = None):
    """
    运行验证循环

    Args:
        email: 临时邮箱地址（用于接收 SheerID 验证链接）
        logout_after_success: 成功后是否退出登录（批量模式需要，单个模式不需要）
        chatgpt_account: 关联的 ChatGPT 账号邮箱（半自动模式时记录）
            - 全自动模式：email == chatgpt_account（同一个邮箱）
            - 半自动-脚本登录：用户的已有账号邮箱
            - 半自动-手动登录：用户手动登录的账号邮箱
    """
    from playwright.async_api import async_playwright

    logger.info(f"连接 Chrome: {CDP_URL}")
    logger.info(f"临时邮箱: {email}")
    if chatgpt_account and chatgpt_account != email:
        logger.info(f"关联账号: {chatgpt_account}")
        # 记录临时邮箱和 ChatGPT 账号的关联关系
        try:
            from email_pool import EmailPoolManager
            pool = EmailPoolManager()
            pool.update_linked_account(email, chatgpt_account)
        except Exception as e:
            logger.debug(f"更新关联账号跳过: {e}")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            logger.info("已连接 Chrome")

            contexts = browser.contexts
            if not contexts:
                logger.error("没有浏览器上下文，请先启动 Chrome")
                return False

            context = contexts[0]
            page = None

            # 查找 chatgpt 页面 - 只使用第一个找到的页面
            chatgpt_pages = [pg for pg in context.pages if "chatgpt.com" in pg.url]
            if chatgpt_pages:
                page = chatgpt_pages[0]
                # 如果有多个 chatgpt 页面，关闭其他的
                if len(chatgpt_pages) > 1:
                    logger.warning(f"发现 {len(chatgpt_pages)} 个 ChatGPT 页面，只使用第一个，关闭其他")
                    for pg in chatgpt_pages[1:]:
                        try:
                            await pg.close()
                        except:
                            pass
            else:
                # 没有 chatgpt 页面，创建新的
                page = await context.new_page()

            logger.info(f"当前页面: {page.url}")

            # 检测是否有另一个账号登录着（需要先退出）
            if await check_if_another_account_logged_in(page, email):
                logger.info("检测到需要先退出登录...")
                await logout_chatgpt(page)
                await asyncio.sleep(2)

            # 导航到 veterans-claim 页面
            logger.info("导航到 veterans-claim 页面...")
            await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            logger.info(f"导航后页面: {page.url}")

            # 再次检测登录状态（可能已经退出了）
            state, _ = await detect_page_state(page)
            if state == "please_login":
                logger.error("需要登录！请先手动登录 ChatGPT")
                return False

            attempt = 0
            max_attempts = 50
            consecutive_failures = 0
            current_veteran = None
            already_approved_count = 0  # 跟踪 "already been approved" 出现次数

            while attempt < max_attempts:
                attempt += 1
                state, message = await detect_page_state(page)
                logger.info(f"[{attempt}] 状态: {state} - {message}")

                # 成功（包括 Stripe 支付页面、Claim offer 页面）
                if state in ["success", "success_stripe", "success_claim"]:
                    logger.info("=" * 50)
                    logger.info("🎉 验证成功！获得 1 年 ChatGPT Plus")
                    logger.info(f"邮箱: {email}")
                    if current_veteran:
                        logger.info(f"军人: {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})")
                        logger.info(f"退伍日期: {current_veteran['discharge_month']} {current_veteran['discharge_day']}, {current_veteran['discharge_year']}")
                    if state == "success_stripe":
                        logger.info("已跳转到 Stripe 支付页面（$0.00 免费订阅）")
                    elif state == "success_claim":
                        logger.info("Claim offer 可用，验证已通过")
                    logger.info("=" * 50)
                    await save_screenshot(page, "success")

                    # 点击 Continue 按钮（仅在 SheerID 成功页面）
                    if state == "success":
                        try:
                            continue_btn = await page.query_selector('button:has-text("Continue")')
                            if continue_btn:
                                await continue_btn.click()
                                logger.info("已点击 Continue 按钮")
                                await asyncio.sleep(3)
                        except Exception as e:
                            logger.debug(f"点击 Continue 跳过: {e}")

                    # ========== 检测真实登录账号 ==========
                    # 验证成功后，Plus 给的是登录的账号，不是接收邮箱
                    # 需要检测真实登录的账号是谁
                    logged_in_account = await get_logged_in_account(page)
                    if logged_in_account:
                        logger.info(f"✓ 真实验证通过账号: {logged_in_account}")
                        if logged_in_account.lower() != email.lower():
                            logger.info(f"  → 接收邮箱 {email} 只是消耗品")
                    else:
                        logged_in_account = email  # 回退到接收邮箱
                        logger.warning(f"未能检测到登录账号，使用接收邮箱: {email}")

                    # 确定真实账号和消耗邮箱
                    real_account = logged_in_account
                    consumed_email = email if email.lower() != logged_in_account.lower() else None

                    # 保存验证成功信息到数据库
                    try:
                        from database import update_account, update_verification, get_account_by_email, create_account

                        # 1. 确保真实账号存在于数据库
                        account = get_account_by_email(real_account)
                        if not account:
                            # 如果真实账号不存在，创建一个（半自动模式可能是自有邮箱）
                            logger.info(f"真实账号 {real_account} 不在数据库，创建记录")
                            create_account(
                                email=real_account,
                                password="(自有账号)",  # 自有邮箱没有密码记录
                                status="verified"
                            )

                        # 2. 更新真实账号状态为已验证 + 记录消耗的临时邮箱
                        update_account(real_account, status="verified", consumed_email=consumed_email)

                        # 3. 更新验证记录状态为 success
                        if current_veteran and current_veteran.get('verification_id'):
                            v_id = current_veteran['verification_id']
                            update_verification(v_id, status='success')
                            logger.info(f"✓ 验证记录已更新: verification #{v_id} → success")
                            logger.info(f"  军人: {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})")

                        # 4. 保存成功信息到账号备注
                        note = f"验证成功 @ {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        if current_veteran:
                            note += f" | {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})"
                        if consumed_email:
                            note += f" | 消耗邮箱: {consumed_email}"
                        update_account(real_account, note=note)
                        logger.info("✓ 数据库状态已更新")

                    except Exception as e:
                        logger.error(f"✗ 数据库更新失败: {e}")

                    # 更新邮箱池状态
                    try:
                        from email_pool import EmailPoolManager
                        pool = EmailPoolManager()
                        veteran_info = None
                        if current_veteran:
                            veteran_info = {
                                'first_name': current_veteran['first_name'],
                                'last_name': current_veteran['last_name'],
                                'branch': current_veteran['branch'],
                                'discharge_date': f"{current_veteran['discharge_month']} {current_veteran['discharge_day']}, {current_veteran['discharge_year']}"
                            }

                        # 根据情况更新邮箱池状态
                        if consumed_email:
                            # 接收邮箱是消耗品，标记为 consumed
                            pool.mark_consumed(consumed_email, consumed_by=real_account, veteran_info=veteran_info)
                            logger.info(f"✓ 接收邮箱 {consumed_email} 已标记为 consumed（消耗品）")

                            # 真实账号如果在邮箱池中，标记为 verified
                            if pool.get_by_address(real_account):
                                pool.mark_verified(real_account, veteran_info=veteran_info)
                                logger.info(f"✓ 真实账号 {real_account} 已标记为 verified")
                        else:
                            # 接收邮箱就是真实账号（全自动模式）
                            pool.mark_verified(email, veteran_info=veteran_info)
                            logger.info("✓ 邮箱池状态已更新（含军人信息）")

                    except Exception as e:
                        logger.debug(f"邮箱池更新跳过: {e}")

                    # 根据参数决定是否退出登录
                    if logout_after_success:
                        await logout_chatgpt(page)
                        logger.info("✓ 已退出登录（批量模式）")
                    else:
                        logger.info("✓ 保持登录状态（单个模式）")

                    return True

                # 失败 - 换数据（必须清空 current_veteran 以触发获取新数据）
                if state in ["not_approved", "unable_to_verify", "verification_limit"]:
                    consecutive_failures += 1
                    logger.warning(f"验证失败: {state}，消耗当前数据，准备换下一条")
                    if current_veteran:
                        mark_veteran_consumed(
                            current_veteran['id'], email, state,
                            verification_id=current_veteran.get('verification_id')
                        )
                    # 强制清空，确保下次获取新数据
                    current_veteran = None

                    if consecutive_failures >= 3:
                        logger.warning(f"连续失败 {consecutive_failures} 次，暂停 60 秒")
                        await asyncio.sleep(60)
                        consecutive_failures = 0

                    await click_try_again(page)
                    await asyncio.sleep(3)
                    continue

                # 错误状态 - 点击 Try Again 重新开始
                if state in ["error_sources", "error_link", "error_retry"]:
                    logger.warning(f"遇到错误: {message}，消耗当前数据，准备换下一条")
                    if current_veteran:
                        mark_veteran_consumed(
                            current_veteran['id'], email, state,
                            verification_id=current_veteran.get('verification_id')
                        )
                    # 强制清空
                    current_veteran = None
                    await click_try_again(page)
                    await asyncio.sleep(3)
                    continue

                # 需要登录
                if state == "please_login":
                    logger.error("需要登录！请手动登录 ChatGPT")
                    return False

                # Stripe 支付页面（上一个账号的成功状态，需要退出登录）
                if state == "stripe_page":
                    logger.warning("检测到 Stripe 页面（上一个账号），退出登录...")
                    await logout_chatgpt(page)
                    await asyncio.sleep(2)
                    await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    continue

                # veterans-claim 页面
                if state in ["veterans_claim", "veterans_claim_check"]:
                    clicked = await click_verify_button(page)
                    if not clicked:
                        # 按钮点击失败，可能需要退出登录或刷新页面
                        logger.warning("验证按钮点击失败，尝试刷新页面...")
                        await page.reload()
                    await asyncio.sleep(3)
                    continue

                # ChatGPT 首页
                if state == "chatgpt_home":
                    await page.goto(VETERANS_CLAIM_URL)
                    await asyncio.sleep(3)
                    continue

                # SheerID 表单
                if state == "sheerid_form":
                    # 如果没有军人数据或者上一个已被消耗，获取新数据
                    if not current_veteran:
                        logger.info("=" * 40)
                        logger.info("获取新的军人数据...")
                        current_veteran = get_veteran_data_from_db(email)
                        if current_veteran:
                            logger.info(f"新数据: {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})")
                            logger.info(f"退伍日期: {current_veteran['discharge_month']} {current_veteran['discharge_day']}, {current_veteran['discharge_year']}")
                        else:
                            logger.error("=" * 40)
                            logger.error("数据库中没有可用的军人数据！")
                            logger.error("请检查数据库是否已导入 BIRLS 数据")
                            logger.error("=" * 40)
                            return False  # 没有真实数据就退出，不用假数据
                        logger.info("=" * 40)

                    if await fill_sheerid_form(page, current_veteran):
                        await save_screenshot(page, "form_filled")
                        if await submit_form(page):
                            consecutive_failures = 0
                            logger.info("表单已提交，等待结果...")
                            await asyncio.sleep(5)
                        else:
                            logger.warning("提交失败，刷新页面重试")
                            await page.reload()
                            await asyncio.sleep(3)
                    else:
                        # 填写失败，清空数据下次重新获取
                        logger.warning("表单填写失败，将获取新数据重试")
                        current_veteran = None
                    continue

                # 等待邮件 → 自动点击验证链接
                if state == "check_email":
                    logger.info("检测到需要邮件验证，开始自动获取验证链接...")
                    if await check_and_click_verification_link(page, email, max_retries=30):
                        logger.info("验证链接已点击，继续检查状态...")
                        await asyncio.sleep(5)
                    else:
                        logger.warning("自动获取验证链接失败，请手动检查邮箱")
                        await asyncio.sleep(30)
                        await page.reload()
                    continue

                # 邮件验证成功（点击链接后显示 "already been approved"）
                # 需要返回 veterans-claim 页面点击 Claim offer
                # ⚠️ 但如果重复出现多次，说明邮箱已经用过了！
                if state == "email_verified":
                    already_approved_count += 1
                    logger.info(f"检测到 'already been approved'（第 {already_approved_count} 次）")

                    if already_approved_count >= 5:
                        # 邮箱已经用过，需要换邮箱
                        logger.error("=" * 50)
                        logger.error("❌ 邮箱已经验证过！'already been approved' 出现 5+ 次")
                        logger.error(f"邮箱: {email}")
                        logger.error("解决方案: 需要使用新的临时邮箱")
                        logger.error("=" * 50)

                        # 标记邮箱为已用过
                        try:
                            from email_pool import EmailPoolManager
                            pool = EmailPoolManager()
                            pool.mark_failed(email, "email_already_used: already been approved 5+ times")
                            logger.info("✓ 邮箱已标记为 email_already_used")
                        except Exception as e:
                            logger.warning(f"标记邮箱失败: {e}")

                        return False  # 退出，提示换邮箱

                    # 正常流程，返回 veterans-claim 点击 Claim offer
                    logger.info("邮件验证成功！返回 veterans-claim 点击 Claim offer...")
                    await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    continue

                # SheerID 未知状态 - 可能是表单页面但没识别出来
                if state == "sheerid_unknown":
                    logger.info(f"SheerID 未知状态，尝试刷新并识别: {message}")
                    await asyncio.sleep(3)
                    await page.reload()
                    await asyncio.sleep(3)
                    continue

                # 未知状态 - 等待并刷新
                logger.warning(f"未知状态，等待 5 秒后刷新: {message[:100]}")
                await save_screenshot(page, "unknown")
                await asyncio.sleep(5)
                await page.reload()
                await asyncio.sleep(3)

            logger.error(f"超过最大尝试次数 ({max_attempts})")
            return False

        except Exception as e:
            logger.error(f"异常: {e}")
            import traceback
            traceback.print_exc()
            return False


# ==================== 工具函数 ====================

def print_stats():
    """打印统计"""
    try:
        from database import get_veterans_stats, get_accounts_stats
        v = get_veterans_stats()
        a = get_accounts_stats()
        print(f"军人数据: {v['available']} 可用 / {v['total']} 总计")
        print(f"账号: {a['total']} 个")
    except Exception as e:
        print(f"无法获取统计: {e}")


def print_form_data(email: str):
    """打印表单数据"""
    data = get_veteran_data_from_db(email)
    if not data:
        data = get_test_veteran_data(email)
        print("(测试数据)")

    print(f"\n军人: {data['first_name']} {data['last_name']}")
    print(f"军种: {data['branch']}")
    print(f"生日: {data['birth_month']} {data['birth_day']}, {data['birth_year']}")
    print(f"退伍: {data['discharge_month']} {data['discharge_day']}, {data['discharge_year']}")
    print(f"邮箱: {data['email']}")


def run_test_mode():
    """测试模式"""
    print("=" * 50)
    print("测试模式 - 打印操作流程")
    print("=" * 50)

    for i in range(3):
        data = get_test_veteran_data("test@009025.xyz")
        print(f"\n--- 尝试 {i+1} ---")
        print(f"军人: {data['first_name']} {data['last_name']} ({data['branch']})")
        print(f"生日: {data['birth_month']} {data['birth_day']}, {data['birth_year']}")
        print(f"退伍: {data['discharge_month']} {data['discharge_day']}, {data['discharge_year']}")


# ==================== 主函数 ====================

def main():
    global CDP_URL
    parser = argparse.ArgumentParser(description="Veterans Verify 自动化脚本")
    parser.add_argument("--email", "-e", help="临时邮箱地址（接收 SheerID 验证链接）")
    parser.add_argument("--account", "-a", help="ChatGPT 账号邮箱（半自动模式：记录是哪个账号使用了这个临时邮箱）")
    parser.add_argument("--batch", "-b", type=int, metavar="N", help="批量模式：验证成功 N 个后停止")
    parser.add_argument("--cdp", default=CDP_URL, help=f"CDP URL (默认: {CDP_URL})")
    parser.add_argument("--test", action="store_true", help="测试模式")
    parser.add_argument("--data", metavar="EMAIL", help="只获取表单数据")
    parser.add_argument("--stats", action="store_true", help="显示统计")
    parser.add_argument("--debug", "-d", action="store_true", help="调试模式")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.stats:
        print_stats()
        return

    if args.test:
        run_test_mode()
        return

    if args.data:
        print_form_data(args.data)
        return

    # 检查 Playwright
    try:
        import playwright
    except ImportError:
        print("错误: 未安装 Playwright")
        print("运行: pip install playwright && playwright install chromium")
        sys.exit(1)

    CDP_URL = args.cdp

    # 批量模式
    if args.batch:
        print("=" * 60)
        print("Veterans Verify - 批量验证模式")
        print("=" * 60)
        print(f"CDP: {CDP_URL}")
        print(f"目标: 验证成功 {args.batch} 个邮箱")
        print()
        print("请确保:")
        print("  1. 已运行 scripts/start-chrome-devtools.bat")
        print("  2. 邮箱池中有可用邮箱")
        print()

        success = asyncio.run(run_batch_verify(args.batch))
        sys.exit(0 if success else 1)

    # 单邮箱模式
    if not args.email:
        parser.print_help()
        print("\n示例:")
        print("  # 全自动模式（临时邮箱 = ChatGPT 账号）")
        print("  python run_verify.py --email xxx@009025.xyz")
        print()
        print("  # 半自动模式（临时邮箱用于验证，关联到已有账号）")
        print("  python run_verify.py --email xxx@009025.xyz --account my@gmail.com")
        print()
        print("  # 批量验证（成功 3 个后停止）")
        print("  python run_verify.py --batch 3")
        print()
        print("  # 其他")
        print("  python run_verify.py --stats")
        print("  python run_verify.py --test")
        return

    print("=" * 60)
    print("Veterans Verify - 单邮箱模式")
    print("=" * 60)
    print(f"CDP: {CDP_URL}")
    print(f"临时邮箱: {args.email}")
    if args.account:
        print(f"关联账号: {args.account}")
        print()
        print("⚠️  半自动模式说明:")
        print(f"    - 临时邮箱 {args.email} 用于接收 SheerID 验证链接")
        print(f"    - 验证成功后 Plus 会添加到账号 {args.account}")
    print()
    print("请确保:")
    print("  1. 已运行 scripts/start-chrome-devtools.bat")
    print("  2. 已在 Chrome 中登录 ChatGPT")
    print()

    success = asyncio.run(run_verify_loop(args.email, chatgpt_account=args.account))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
