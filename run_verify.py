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

# 日志配置 - 确保实时输出（不缓冲）+ UTF-8 编码支持
class FlushStreamHandler(logging.StreamHandler):
    """每条日志后立即 flush，支持 UTF-8"""
    def __init__(self, stream=None):
        super().__init__(stream)
        # Windows 需要 UTF-8 编码
        if hasattr(self.stream, 'reconfigure'):
            try:
                self.stream.reconfigure(encoding='utf-8', errors='replace')
            except:
                pass

    def emit(self, record):
        try:
            super().emit(record)
            self.flush()
        except UnicodeEncodeError:
            # 回退：替换特殊字符
            record.msg = record.msg.encode('ascii', 'replace').decode('ascii')
            super().emit(record)
            self.flush()

# 配置 root logger
handler = FlushStreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)
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


# ==================== 风控检测 ====================

async def detect_captcha_or_block(page) -> Tuple[bool, str]:
    """
    检测是否触发风控（Cloudflare、reCAPTCHA、hCaptcha 等）

    Returns:
        (is_blocked, block_type)
        - is_blocked: 是否被风控
        - block_type: 风控类型（cloudflare/recaptcha/hcaptcha/rate_limit/unknown）
    """
    try:
        text = await page.evaluate("() => document.body?.innerText || ''")
        text_lower = text.lower()
        html = await page.content()
        html_lower = html.lower()

        # Cloudflare 检测
        cloudflare_markers = [
            "checking your browser",
            "just a moment",
            "ray id:",
            "cloudflare",
            "please wait while we verify",
            "ddos protection by cloudflare"
        ]
        for marker in cloudflare_markers:
            if marker in text_lower or marker in html_lower:
                return True, "cloudflare"

        # reCAPTCHA 检测
        recaptcha_markers = [
            "recaptcha",
            "g-recaptcha",
            "grecaptcha",
            "recaptcha-anchor"
        ]
        for marker in recaptcha_markers:
            if marker in html_lower:
                return True, "recaptcha"

        # hCaptcha 检测
        hcaptcha_markers = [
            "hcaptcha",
            "h-captcha"
        ]
        for marker in hcaptcha_markers:
            if marker in html_lower:
                return True, "hcaptcha"

        # 速率限制检测
        rate_limit_markers = [
            "rate limit",
            "too many requests",
            "please try again later",
            "slow down",
            "request blocked"
        ]
        for marker in rate_limit_markers:
            if marker in text_lower:
                return True, "rate_limit"

        # 通用阻止检测
        block_markers = [
            "access denied",
            "forbidden",
            "blocked",
            "not authorized"
        ]
        for marker in block_markers:
            if marker in text_lower and len(text) < 500:  # 短页面更可能是阻止页
                return True, "blocked"

        return False, ""

    except Exception as e:
        logger.debug(f"风控检测异常: {e}")
        return False, ""


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
        if "veterans-claim" in url:
            # 检测登录状态
            has_login_button = "log in" in text_lower or "sign up" in text_lower or "get started" in text_lower
            has_verify_button = "verify your eligibility" in text_lower or "verify eligibility" in text_lower or "验证资格条件" in text

            if has_login_button and not has_verify_button:
                # 有登录按钮但没有验证按钮 = 未登录
                return "veterans_claim_not_logged_in", "On veterans-claim (NOT logged in)"

            if has_verify_button:
                # 有验证按钮 = 已登录且未验证
                return "veterans_claim", "On veterans-claim (logged in, need verify)"

            # 其他情况
            return "veterans_claim_check", "On veterans-claim page (unknown state)"

        # ChatGPT 首页
        if "chatgpt.com" in url and "veterans-claim" not in url:
            return "chatgpt_home", "On ChatGPT home"

        # OpenAI 登录页面 - 需要继续登录流程
        if "auth.openai.com" in url or "auth0.openai.com" in url:
            return "auth_page", f"On auth page, need to complete login"

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


async def logout_chatgpt(page, timeout: int = 30) -> bool:
    """
    退出 ChatGPT 登录，为下一个账号做准备

    CDP 兼容版本：
    1. 优先使用 JavaScript 清除 cookies/storage（CDP 模式兼容）
    2. 尝试点击退出按钮
    3. 所有操作都有超时保护

    Args:
        page: Playwright page
        timeout: 整体超时时间（秒）
    """
    logger.info("正在退出 ChatGPT 登录...")

    try:
        # 设置整体超时
        start_time = time.time()

        def check_timeout():
            if time.time() - start_time > timeout:
                raise TimeoutError(f"退出登录超时 ({timeout}s)")

        # 先导航到 ChatGPT 首页
        try:
            await asyncio.wait_for(
                page.goto("https://chatgpt.com", wait_until="domcontentloaded"),
                timeout=15
            )
        except asyncio.TimeoutError:
            logger.warning("导航超时，继续尝试清除登录状态...")
        await asyncio.sleep(1)
        check_timeout()

        # 方法1（CDP 兼容）：使用 JavaScript 清除所有存储
        try:
            logger.debug("尝试 JavaScript 清除存储...")
            await page.evaluate("""() => {
                // 清除 localStorage
                try { localStorage.clear(); } catch(e) {}
                // 清除 sessionStorage
                try { sessionStorage.clear(); } catch(e) {}
                // 清除 cookies (通过 document.cookie)
                try {
                    document.cookie.split(';').forEach(cookie => {
                        const name = cookie.split('=')[0].trim();
                        document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/';
                        document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=.chatgpt.com';
                        document.cookie = name + '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;domain=.openai.com';
                    });
                } catch(e) {}
            }""")
            logger.info("✓ 已通过 JavaScript 清除存储")
        except Exception as e:
            logger.debug(f"JavaScript 清除存储失败: {e}")
        check_timeout()

        # 方法2：尝试点击用户菜单退出
        try:
            # 点击用户头像/菜单按钮
            user_menu = await page.query_selector('[data-testid="profile-button"], [aria-label*="profile"], button[class*="avatar"]')
            if user_menu:
                await user_menu.click()
                await asyncio.sleep(0.5)

                # 点击退出登录选项
                logout_btn = await page.query_selector('a:has-text("Log out"), button:has-text("Log out"), a:has-text("退出"), button:has-text("退出")')
                if logout_btn:
                    await logout_btn.click()
                    await asyncio.sleep(2)
                    logger.info("✓ 已点击退出登录按钮")
        except Exception as e:
            logger.debug(f"点击退出按钮失败: {e}")
        check_timeout()

        # 方法3（后备）：尝试 context.clear_cookies（非 CDP 模式）
        try:
            context = page.context
            await asyncio.wait_for(context.clear_cookies(), timeout=5)
            logger.info("✓ 已清除 Context Cookies")
        except asyncio.TimeoutError:
            logger.debug("context.clear_cookies() 超时（CDP 模式正常）")
        except Exception as e:
            logger.debug(f"清除 Cookies 失败: {e}")
        check_timeout()

        # 方法4：访问登出 URL
        try:
            await asyncio.wait_for(
                page.goto("https://chatgpt.com/auth/logout", wait_until="domcontentloaded"),
                timeout=10
            )
            await asyncio.sleep(1)
            logger.info("✓ 已访问登出 URL")
        except asyncio.TimeoutError:
            logger.debug("登出 URL 超时")
        except Exception as e:
            logger.debug(f"访问登出 URL 失败: {e}")

        # 最后刷新页面确认
        try:
            await page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(1)
        except:
            pass

        # 检查是否真的退出了
        text = await page.evaluate("() => document.body?.innerText || ''")
        if "log in" in text.lower() or "sign up" in text.lower() or "get started" in text.lower():
            logger.info("✓ 确认已退出登录")
            return True
        else:
            logger.warning("退出登录状态不确定，继续执行...")
            return True  # 继续执行，后续会处理

    except TimeoutError as e:
        logger.error(f"退出登录超时: {e}")
        return False
    except Exception as e:
        logger.error(f"退出登录失败: {e}")
        return False


# ==================== 注册/登录 ====================

def get_account_password(email: str) -> str:
    """
    获取账号密码（从数据库/邮箱池获取，如果没有则生成新密码）
    """
    # 1. 尝试从数据库获取
    try:
        from database import get_account_by_email
        account = get_account_by_email(email)
        if account and account.get('password'):
            logger.info(f"从数据库获取密码: {email}")
            return account['password']
    except Exception as e:
        logger.debug(f"数据库获取密码失败: {e}")

    # 2. 尝试从邮箱池获取
    try:
        from email_pool import EmailPoolManager
        pool = EmailPoolManager()
        email_data = pool.get_by_address(email)
        if email_data and email_data.get('password'):
            logger.info(f"从邮箱池获取密码: {email}")
            return email_data['password']
    except Exception as e:
        logger.debug(f"邮箱池获取密码失败: {e}")

    # 3. 生成新密码
    import string
    chars = string.ascii_letters + string.digits + "!@#$%"
    password = ''.join(random.choice(chars) for _ in range(16))
    logger.info(f"生成新密码: {email}")
    return password


async def get_chatgpt_verification_code(email: str, max_retries: int = 30) -> Optional[str]:
    """
    获取 ChatGPT 登录验证码（从邮箱）
    """
    try:
        email_manager = get_email_manager()
        return email_manager.check_verification_code(
            email=email,
            max_retries=max_retries,
            interval=3.0
        )
    except Exception as e:
        logger.error(f"获取验证码失败: {e}")
        return None


async def handle_about_you_page(page, email: str = None) -> bool:
    """
    处理 about-you 确认年龄页面

    Args:
        page: Playwright page 对象
        email: 邮箱地址，用于从邮箱池获取注册信息
    """
    logger.info("处理 about-you 页面...")

    # 英文月份转数字
    MONTH_TO_NUM = {
        'January': '1', 'February': '2', 'March': '3', 'April': '4',
        'May': '5', 'June': '6', 'July': '7', 'August': '8',
        'September': '9', 'October': '10', 'November': '11', 'December': '12'
    }

    try:
        # 尝试从邮箱池获取注册信息
        full_name = "John Smith"
        birth_year = str(datetime.now().year - random.randint(25, 35))
        birth_month = str(random.randint(1, 12))
        birth_day = str(random.randint(1, 28))

        if email:
            try:
                from email_pool import EmailPoolManager
                pool = EmailPoolManager()
                email_info = pool.get_by_address(email)
                if email_info:
                    # 获取保存的注册信息
                    first_name = email_info.get('first_name', 'John')
                    last_name = email_info.get('last_name', 'Smith')
                    full_name = f"{first_name} {last_name}"

                    # 转换月份：英文 → 数字
                    saved_month = email_info.get('birth_month', 'January')
                    birth_month = MONTH_TO_NUM.get(saved_month, str(random.randint(1, 12)))

                    birth_day = email_info.get('birth_day', str(random.randint(1, 28)))
                    birth_year = email_info.get('birth_year', str(datetime.now().year - 30))

                    logger.info(f"✓ 使用邮箱池注册信息: {full_name}, {birth_year}/{birth_month}/{birth_day}")
            except Exception as e:
                logger.warning(f"获取邮箱池信息失败，使用随机数据: {e}")

        await asyncio.sleep(1)

        # 填写全名
        try:
            name_input = page.get_by_role("textbox", name="全名")
            if await name_input.count() > 0:
                await name_input.fill(full_name)
                logger.info(f"✓ 填写全名: {full_name}")
                await asyncio.sleep(0.3)
        except:
            pass

        # 填写生日（spinbutton 类型）
        # 年份
        try:
            year_input = page.get_by_role("spinbutton", name="年")
            if await year_input.count() > 0:
                await year_input.fill(birth_year)
            else:
                year_input = await page.query_selector('input[name="year"]')
                if year_input:
                    await year_input.fill(birth_year)
            await asyncio.sleep(0.2)
        except:
            pass

        # 月份
        try:
            month_input = page.get_by_role("spinbutton", name="月")
            if await month_input.count() > 0:
                await month_input.fill(birth_month)
            else:
                month_input = await page.query_selector('input[name="month"]')
                if month_input:
                    await month_input.fill(birth_month)
            await asyncio.sleep(0.2)
        except:
            pass

        # 日期
        try:
            day_input = page.get_by_role("spinbutton", name="日")
            if await day_input.count() > 0:
                await day_input.fill(birth_day)
            else:
                day_input = await page.query_selector('input[name="day"]')
                if day_input:
                    await day_input.fill(birth_day)
        except:
            pass

        await asyncio.sleep(0.5)

        # 点击继续
        continue_btn = await page.query_selector('button:has-text("Continue"), button:has-text("继续")')
        if continue_btn:
            await continue_btn.click()
            await asyncio.sleep(2)

        logger.info("✓ about-you 处理完成")
        return True
    except Exception as e:
        logger.error(f"about-you 处理失败: {e}")
        return False


async def wait_for_page_change(page, original_url: str, original_text: str, timeout: int = 10) -> bool:
    """等待页面变化（URL 或内容发生变化）"""
    start = time.time()
    while time.time() - start < timeout:
        current_url = page.url
        current_text = await page.evaluate("() => document.body?.innerText?.slice(0, 500) || ''")
        if current_url != original_url or current_text != original_text[:500]:
            return True
        await asyncio.sleep(0.5)
    return False


async def register_or_login_chatgpt(page, email: str, password: str, max_retries: int = 3) -> bool:
    """
    注册或登录 ChatGPT 账号（通过页面状态检测，不依赖数据库）

    改进版本：
    - 每个操作后等待页面变化确认
    - 添加重试机制
    - 更精确的状态检测
    - 超时保护

    流程：
    1. 打开 veterans-claim 页面
    2. 检测页面状态：已登录/未登录
    3. 如未登录，点击登录按钮
    4. 输入邮箱 → 继续
    5. 根据页面判断：创建密码（新用户）/ 输入密码（已有用户）
    6. 输入验证码（如需要）
    7. 处理 about-you 页面（如需要）
    """
    logger.info(f"开始注册/登录: {email}")

    for retry in range(max_retries):
        if retry > 0:
            logger.info(f"登录重试 {retry + 1}/{max_retries}...")
            await asyncio.sleep(2)

        try:
            # 1. 打开 chatgpt.com 主页进行登录（而不是 veterans-claim）
            current_url = page.url
            already_on_auth_page = "auth.openai.com" in current_url or "auth0.openai.com" in current_url

            if already_on_auth_page:
                logger.info(f"步骤 1/7: 已在登录页面 ({current_url[:50]}...)")
            elif "chatgpt.com" not in current_url or retry > 0:
                logger.info("步骤 1/7: 打开 chatgpt.com 主页进行登录")
                await page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)
                await save_screenshot(page, "01_chatgpt_home")
            else:
                logger.info(f"步骤 1/7: 当前在 ChatGPT ({current_url[:50]}...)")

            # 2. 检测是否已登录或在登录流程中
            logger.info("步骤 2/7: 检测登录状态")

            # 等待页面加载完成
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except:
                pass

            current_url = page.url
            logger.info(f"当前 URL: {current_url}")

            # 初始化变量
            text = ""
            has_login_button = False

            # 如果已在 OpenAI 登录页面，直接跳到输入邮箱步骤
            already_on_auth_page = "auth.openai.com" in current_url or "auth0.openai.com" in current_url
            if already_on_auth_page:
                logger.info("✓ 已在 OpenAI 登录页面，跳到输入邮箱步骤")
                # 在 auth 页面时，不需要再检测其他状态，直接跳到输入邮箱
            else:
                # 在 chatgpt.com 主页检测登录状态
                text = await page.evaluate("() => document.body?.innerText || ''")
                text_lower = text.lower()

                # 在主页检测登录状态
                # 未登录标识：有登录/注册按钮
                not_logged_in_signs = ["log in", "sign up", "登录", "免费注册", "get started"]
                has_login_button = any(sign in text_lower for sign in not_logged_in_signs)

                # ⚠️ 2025-12-31 修复：正确的登录状态检测
                # 关键发现：未登录页面也有 "打开个人资料菜单" 按钮，不能用它判断已登录！
                # 正确逻辑：有"登录"按钮 = 未登录，没有"登录"按钮 = 已登录
                if has_login_button:
                    logger.info("检测到登录按钮，需要执行登录流程")
                else:
                    # 没有登录按钮，再检查是否有聊天输入框（真正已登录的标志）
                    try:
                        # 真正已登录的标志：有聊天输入框或新建聊天按钮
                        chat_input = await page.query_selector(
                            'textarea[placeholder*="消息"], '
                            'textarea[placeholder*="Message"], '
                            'button[aria-label*="新对话"], '
                            'button[aria-label*="New chat"]'
                        )
                        if chat_input:
                            logger.info("✓ 检测到已登录（有聊天输入框），跳过登录")
                            return True
                    except:
                        pass
                    logger.warning(f"页面状态不明确 (retry {retry + 1})，等待后重试...")
                    await asyncio.sleep(3)
                    continue

            # 3. 点击登录按钮（如果不在登录页面）
            # ⚠️ 2025-12-31 修复：chatgpt.com 登录是弹窗（dialog），不是跳转页面
            if not already_on_auth_page and has_login_button:
                logger.info("步骤 3/7: 点击登录按钮")

                login_clicked = False
                for selector in [
                    'button:has-text("登录")',
                    'button:has-text("Log in")',
                    'button:has-text("Sign in")',
                    'a:has-text("Log in")',
                    'button:has-text("Get started")',
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.count() > 0:
                            await btn.click(timeout=5000)
                            login_clicked = True
                            logger.info(f"✓ 点击登录按钮: {selector}")
                            break
                    except:
                        continue

                if not login_clicked:
                    logger.warning(f"未找到登录按钮 (retry {retry + 1})")
                    continue

                # 等待弹窗出现（关键！）
                logger.info("等待登录弹窗...")
                try:
                    await page.wait_for_selector("dialog", timeout=5000)
                    logger.info("✓ 弹窗已出现")
                except:
                    logger.warning("弹窗未出现，可能已跳转到登录页面")
                await asyncio.sleep(1)
                await save_screenshot(page, "02_after_login_click")

            # 4. 输入邮箱
            # ⚠️ 2025-12-31 修复：优先检测弹窗（dialog），在弹窗内操作
            logger.info("步骤 4/7: 输入邮箱")

            current_url = page.url
            logger.info(f"当前页面 URL: {current_url}")

            email_input = None
            is_dialog = False

            # 方式1：检测弹窗（chatgpt.com 主页登录会出现弹窗）
            try:
                dialog = page.locator("dialog")
                if await dialog.count() > 0 and await dialog.is_visible():
                    logger.info("✓ 检测到登录弹窗（dialog）")
                    is_dialog = True

                    # 等待弹窗内容加载
                    await asyncio.sleep(0.5)

                    # 在弹窗内查找邮箱输入框（多种方式尝试）
                    # 方式1a: 直接用 CSS 选择器在 dialog 内查找 input
                    email_input = dialog.locator('input[type="text"], input[type="email"], input:not([type])')
                    if await email_input.count() > 0:
                        logger.info("✓ 在弹窗内找到邮箱输入框 (CSS)")
                    else:
                        # 方式1b: 用 placeholder 匹配
                        email_input = dialog.locator('input[placeholder*="邮件"], input[placeholder*="email" i]')
                        if await email_input.count() > 0:
                            logger.info("✓ 在弹窗内找到邮箱输入框 (placeholder)")
                        else:
                            # 方式1c: get_by_role 作为最后尝试
                            email_input = dialog.get_by_role("textbox")
                            if await email_input.count() > 0:
                                logger.info("✓ 在弹窗内找到邮箱输入框 (role)")
            except Exception as e:
                logger.debug(f"弹窗检测失败: {e}")

            # 方式2：在 auth.openai.com 页面查找
            if email_input is None or (hasattr(email_input, 'count') and await email_input.count() == 0):
                logger.info("尝试在页面中查找邮箱输入框...")
                for selector in [
                    'input[type="email"]',
                    'input[name="email"]',
                    'input[name="username"]',
                    'input[placeholder*="邮件"]',
                    'input[placeholder*="email" i]',
                ]:
                    try:
                        email_input = await page.wait_for_selector(selector, timeout=3000)
                        if email_input:
                            logger.info(f"✓ 找到邮箱输入框: {selector}")
                            break
                    except:
                        continue

            # 方式3：使用 get_by_role（最后尝试）
            if email_input is None:
                try:
                    email_input = page.get_by_role("textbox", name="电子邮件地址")
                    if await email_input.count() > 0:
                        logger.info("✓ 通过 get_by_role 找到邮箱输入框")
                except:
                    pass

            if email_input is None or (hasattr(email_input, 'count') and await email_input.count() == 0):
                logger.error(f"未找到邮箱输入框 (retry {retry + 1})")
                await save_screenshot(page, "error_no_email_input")
                continue

            # 填写邮箱
            try:
                await email_input.click()
                await asyncio.sleep(0.3)
                await email_input.fill(email)
                await asyncio.sleep(0.5)
                logger.info(f"✓ 输入邮箱: {email}")
            except Exception as e:
                logger.error(f"填写邮箱失败: {e}")
                await save_screenshot(page, "error_fill_email")
                continue

            # 记录当前状态（用于检测页面变化）
            pre_click_url = page.url
            pre_click_text = await page.evaluate("() => document.body?.innerText?.slice(0, 500) || ''")

            # 点击继续按钮
            continue_clicked = False

            # 如果是弹窗，在弹窗内查找继续按钮
            if is_dialog:
                try:
                    dialog = page.locator("dialog")
                    continue_btn = dialog.get_by_role("button", name="继续")
                    if await continue_btn.count() == 0:
                        continue_btn = dialog.get_by_role("button", name="Continue")
                    if await continue_btn.count() > 0:
                        await continue_btn.click()
                        continue_clicked = True
                        logger.info("✓ 在弹窗内点击继续按钮")
                except Exception as e:
                    logger.debug(f"弹窗内继续按钮失败: {e}")

            # 回退：在页面中查找继续按钮
            if not continue_clicked:
                for btn_selector in [
                    'button:has-text("继续")',
                    'button:has-text("Continue")',
                    'button[type="submit"]',
                ]:
                    try:
                        continue_btn = page.locator(btn_selector).first
                        if await continue_btn.count() > 0 and await continue_btn.is_enabled():
                            await continue_btn.click()
                            continue_clicked = True
                            logger.info(f"✓ 点击继续按钮: {btn_selector}")
                            break
                    except:
                        continue

            if not continue_clicked:
                logger.warning("未找到可点击的继续按钮，尝试按 Enter")
                try:
                    await email_input.press("Enter")
                except:
                    pass

            # 等待页面变化
            await wait_for_page_change(page, pre_click_url, pre_click_text, timeout=15)
            await asyncio.sleep(2)

            await save_screenshot(page, "03_after_email")

            # 5. 检测页面状态：创建密码/输入密码
            logger.info("步骤 5/7: 处理密码")

            # 等待页面加载
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
            except:
                pass
            await asyncio.sleep(1)

            current_url = page.url
            logger.info(f"密码页面 URL: {current_url}")
            page_text = await page.evaluate("() => document.body?.innerText || ''")

            # 尝试找密码输入框
            password_input = None
            for selector in [
                'input[type="password"]',
                'input[name="password"]',
                'input[autocomplete="new-password"]',
                'input[autocomplete="current-password"]',
            ]:
                try:
                    password_input = await page.wait_for_selector(selector, timeout=5000)
                    if password_input:
                        logger.info(f"✓ 找到密码输入框: {selector}")
                        break
                except:
                    continue

            if password_input:
                if "创建密码" in page_text or "Create password" in page_text or "create a password" in page_text.lower() or "创建帐户" in page_text:
                    logger.info("新用户，创建密码")
                else:
                    logger.info("已有用户，输入密码")

                await password_input.click()
                await asyncio.sleep(0.3)
                await password_input.fill(password)
                await asyncio.sleep(0.5)
                logger.info(f"✓ 输入密码: {'*' * len(password)}")

                # 记录当前状态
                pre_click_url = page.url
                pre_click_text = await page.evaluate("() => document.body?.innerText?.slice(0, 500) || ''")

                # 点击继续按钮
                continue_clicked = False
                for btn_selector in [
                    'button:has-text("继续")',
                    'button:has-text("Continue")',
                    'button[type="submit"]',
                ]:
                    try:
                        continue_btn = page.locator(btn_selector).first
                        if await continue_btn.count() > 0 and await continue_btn.is_enabled():
                            await continue_btn.click()
                            continue_clicked = True
                            logger.info(f"✓ 点击继续按钮: {btn_selector}")
                            break
                    except:
                        continue

                if not continue_clicked:
                    logger.warning("未找到继续按钮，尝试按 Enter")
                    await password_input.press("Enter")

                await wait_for_page_change(page, pre_click_url, pre_click_text, timeout=15)
                await asyncio.sleep(2)
            else:
                logger.info("未找到密码输入框，可能不需要密码（已有会话）")

            await save_screenshot(page, "04_after_password")

            # 6. 检测是否需要验证码
            logger.info("步骤 6/7: 检测验证码需求")
            page_text = await page.evaluate("() => document.body?.innerText || ''")
            if "检查您的收件箱" in page_text or "Check your inbox" in page_text or "verify your email" in page_text.lower() or "enter the code" in page_text.lower():
                logger.info("需要邮箱验证码，等待获取...")
                code = await get_chatgpt_verification_code(email)
                if code:
                    logger.info(f"✓ 获取到验证码: {code}")
                    # 查找验证码输入框
                    code_input = None
                    for selector in [
                        'input[name="code"]',
                        'input[autocomplete="one-time-code"]',
                        'input[type="text"][maxlength="6"]',
                        'input[type="text"]',
                    ]:
                        try:
                            code_input = await page.query_selector(selector)
                            if code_input:
                                break
                        except:
                            continue

                    if code_input:
                        await code_input.fill(code)
                        await asyncio.sleep(0.5)

                        # 记录当前状态
                        pre_click_url = page.url
                        pre_click_text = await page.evaluate("() => document.body?.innerText?.slice(0, 500) || ''")

                        continue_btn = await page.query_selector(
                            'button:has-text("继续"), button:has-text("Continue"), button[type="submit"]'
                        )
                        if continue_btn:
                            await continue_btn.click()
                            await wait_for_page_change(page, pre_click_url, pre_click_text, timeout=15)
                            await asyncio.sleep(2)
                else:
                    logger.error("未能获取验证码")
                    return False

            await save_screenshot(page, "05_after_code")

            # 7. 处理 about-you 页面（如果有）
            logger.info("步骤 7/7: 检查 about-you 页面")
            if "about-you" in page.url:
                await handle_about_you_page(page, email)

            # 8. 检查最终状态
            await asyncio.sleep(2)
            current_url = page.url

            # 可能跳转到 OpenAI Platform，需要点击回到 ChatGPT
            if "platform.openai.com" in current_url:
                logger.info("跳转到 OpenAI Platform，尝试返回 ChatGPT...")
                try:
                    chatgpt_link = await page.query_selector('a:has-text("ChatGPT"), a:has-text("I\'m looking for ChatGPT")')
                    if chatgpt_link:
                        await chatgpt_link.click()
                        await asyncio.sleep(3)
                except:
                    # 直接导航回去
                    await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(3)

            await save_screenshot(page, "06_login_complete")
            logger.info("✓ 登录流程完成")

            # 保存密码到数据库（如果是新用户）
            try:
                from database import get_or_create_account
                get_or_create_account(email, password)
                logger.info("✓ 账号信息已保存到数据库")
            except Exception as e:
                logger.debug(f"保存账号信息跳过: {e}")

            return True

        except Exception as e:
            logger.error(f"登录失败 (retry {retry + 1}): {e}")
            import traceback
            traceback.print_exc()
            await save_screenshot(page, "error_login")

    logger.error(f"登录失败，已重试 {max_retries} 次")
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

async def run_verify_loop(email: str, logout_after_success: bool = False, chatgpt_account: str = None, skip_login: bool = False):
    """
    运行验证循环

    Args:
        email: 临时邮箱地址（用于接收 SheerID 验证链接）
        logout_after_success: 成功后是否退出登录（批量模式需要，单个模式不需要）
        chatgpt_account: 关联的 ChatGPT 账号邮箱（半自动模式时记录）
            - 全自动模式：email == chatgpt_account（同一个邮箱）
            - 半自动-脚本登录：用户的已有账号邮箱
            - 半自动-手动登录：用户手动登录的账号邮箱
        skip_login: 跳过登录步骤（用户已手动登录时使用）
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

            if skip_login:
                # ========== 跳过登录（用户已手动登录）==========
                logger.info("=" * 50)
                logger.info("【手动登录模式】跳过登录步骤，直接进入验证流程")
                logger.info("=" * 50)

                # 直接导航到 veterans-claim
                await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # 验证是否已登录（更宽松的检测）
                text = await page.evaluate("() => document.body?.innerText || ''")
                text_lower = text.lower()

                # 已登录的标志：有这些内容说明已登录
                logged_in_signs = [
                    "verify your eligibility",  # 验证页面
                    "claim offer",              # 领取优惠
                    "claim your offer",         # 领取优惠
                    "you've been verified",     # 已验证
                    "chatgpt plus",             # Plus 相关
                    "veteran",                  # 退伍军人相关内容
                ]

                # 未登录的标志：有 log in 但没有任何已登录标志
                has_login_button = "log in" in text_lower or "sign up" in text_lower
                has_logged_in_sign = any(sign in text_lower for sign in logged_in_signs)

                if has_login_button and not has_logged_in_sign:
                    logger.error("检测到未登录状态！请先手动登录后再继续")
                    logger.error("访问 https://chatgpt.com 登录后重试")
                    return False

                logger.info("✓ 检测到已登录状态，继续验证流程")
                logger.info(f"  页面关键词: {[s for s in logged_in_signs if s in text_lower]}")

            else:
                # ========== 每次新任务都必须先退出登录 ==========
                # 无论当前是谁登录着，都要先退出，然后用选择的邮箱登录
                logger.info("【新任务】先退出当前登录...")
                await logout_chatgpt(page)
                await asyncio.sleep(2)

                # ========== 用选择的邮箱登录/注册 ==========
                logger.info(f"开始登录/注册: {email}")
                password = get_account_password(email)
                if not await register_or_login_chatgpt(page, email, password):
                    logger.error("登录/注册失败")
                    return False

                # 登录成功后导航到 veterans-claim
                logger.info("导航到 veterans-claim 页面...")
                await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)

            logger.info(f"导航后页面: {page.url}")

            attempt = 0
            max_attempts = 50
            consecutive_failures = 0
            verify_btn_failures = 0  # 验证按钮点击失败计数
            unknown_state_count = 0  # 未知状态计数，防止一直刷新
            current_veteran = None
            already_approved_count = 0  # 跟踪 "already been approved" 出现次数

            while attempt < max_attempts:
                attempt += 1
                state, message = await detect_page_state(page)
                logger.info(f"[{attempt}] 状态: {state} - {message}")

                # ========== "You've been verified" - 验证成功！立即持久化 ==========
                if state == "success":
                    logger.info("=" * 50)
                    logger.info("🎉 检测到 'You've been verified'，验证成功！")
                    logger.info(f"接收邮箱: {email}")
                    if current_veteran:
                        logger.info(f"军人: {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})")
                    logger.info("=" * 50)
                    await save_screenshot(page, "verified_success")

                    # ========== 立即持久化（不依赖 Stripe 页面）==========
                    real_account = email  # CDP 手动模式：接收邮箱就是登录账号
                    password_used = get_account_password(real_account)

                    logger.info("持久化验证成功信息...")

                    # 1. 更新数据库
                    try:
                        from database import update_account, update_verification, get_or_create_account
                        get_or_create_account(real_account, password_used)
                        update_account(real_account, status="verified")
                        logger.info(f"✓ 数据库: {real_account} → verified")

                        if current_veteran and current_veteran.get('verification_id'):
                            v_id = current_veteran['verification_id']
                            update_verification(v_id, status='success')
                            logger.info(f"✓ 验证记录 #{v_id} → success")
                    except Exception as e:
                        logger.error(f"✗ 数据库更新失败: {e}")

                    # 2. 更新邮箱池状态
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
                        pool.mark_verified(email, veteran_info=veteran_info)
                        pool.update_password(email, password_used)
                        logger.info(f"✓ 邮箱池: {email} → verified")
                    except Exception as e:
                        logger.error(f"✗ 邮箱池更新失败: {e}")

                    logger.info("=" * 40)
                    logger.info("🎉 验证成功账号信息:")
                    logger.info(f"   账号: {real_account}")
                    logger.info(f"   密码: {password_used}")
                    if current_veteran:
                        logger.info(f"   军人: {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})")
                    logger.info("=" * 40)

                    # 尝试点击 Continue 继续领取（但已经持久化了，失败也没关系）
                    logger.info("尝试点击 Continue 领取 Plus...")
                    try:
                        continue_btn = await page.query_selector('button:has-text("Continue"), a:has-text("Continue")')
                        if continue_btn:
                            await continue_btn.click()
                            logger.info("✓ 已点击 Continue")
                            await asyncio.sleep(5)
                        else:
                            logger.warning("未找到 Continue 按钮")
                    except Exception as e:
                        logger.warning(f"点击 Continue 失败: {e}")

                    # ========== 验证成功，直接返回！不需要等 Stripe ==========
                    logger.info("✓ 验证成功完成，返回成功状态")
                    return True

                # ========== Claim offer 状态 - 已验证成功，有领取按钮 ==========
                if state == "success_claim":
                    logger.info("=" * 50)
                    logger.info("🎉 检测到 Claim offer 按钮，验证已成功！")
                    logger.info(f"接收邮箱: {email}")
                    if current_veteran:
                        logger.info(f"军人: {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})")
                    logger.info("=" * 50)
                    await save_screenshot(page, "claim_offer_success")

                    # ========== 立即持久化（与 success 状态相同）==========
                    real_account = email
                    password_used = get_account_password(real_account)
                    logger.info("持久化验证成功信息...")

                    try:
                        from database import update_account, get_or_create_account
                        get_or_create_account(real_account, password_used)
                        update_account(real_account, status="verified")
                        logger.info(f"✓ 数据库: {real_account} → verified")
                    except Exception as e:
                        logger.error(f"✗ 数据库更新失败: {e}")

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
                        pool.mark_verified(email, veteran_info=veteran_info)
                        pool.update_password(email, password_used)
                        logger.info(f"✓ 邮箱池: {email} → verified")
                    except Exception as e:
                        logger.error(f"✗ 邮箱池更新失败: {e}")

                    # 尝试点击 Claim offer（可选，已持久化）
                    try:
                        claim_btn = await page.query_selector('button:has-text("Claim offer")')
                        if claim_btn:
                            await claim_btn.click()
                            logger.info("✓ 已点击 Claim offer")
                            await asyncio.sleep(3)
                    except Exception as e:
                        logger.warning(f"点击 Claim offer 失败: {e}")

                    logger.info("✓ 验证成功完成，返回成功状态")
                    return True

                # ========== Stripe 支付页面 - 真正完成！==========
                if state == "success_stripe":
                    logger.info("=" * 50)
                    logger.info("🎉 验证成功！已跳转到 Stripe 支付页面")
                    logger.info(f"接收邮箱: {email}")
                    if current_veteran:
                        logger.info(f"军人: {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})")
                    logger.info("=" * 50)
                    await save_screenshot(page, "success_stripe")

                    # ========== 检测真实登录账号 ==========
                    # Plus 给的是登录账号，不一定是接收邮箱
                    logged_in_account = await get_logged_in_account(page)
                    if logged_in_account:
                        real_account = logged_in_account
                        logger.info(f"✓ 检测到登录账号: {real_account}")
                    else:
                        real_account = email  # 回退到接收邮箱
                        logger.warning(f"未能检测登录账号，使用接收邮箱: {email}")

                    # 判断是否消耗了临时邮箱
                    consumed_email = email if email.lower() != real_account.lower() else None
                    if consumed_email:
                        logger.info(f"   消耗的临时邮箱: {consumed_email}")

                    password_used = get_account_password(real_account)

                    logger.info("=" * 40)
                    logger.info("持久化验证成功信息...")

                    # 1. 更新数据库
                    try:
                        from database import update_account, update_verification, get_or_create_account

                        # 确保账号存在并更新状态
                        get_or_create_account(real_account, password_used)
                        update_account(real_account, status="verified", consumed_email=consumed_email)
                        logger.info(f"✓ 数据库: {real_account} → verified")

                        # 更新验证记录
                        if current_veteran and current_veteran.get('verification_id'):
                            v_id = current_veteran['verification_id']
                            update_verification(v_id, status='success')
                            logger.info(f"✓ 验证记录 #{v_id} → success")

                    except Exception as e:
                        logger.error(f"✗ 数据库更新失败: {e}")
                        import traceback
                        traceback.print_exc()

                    # 2. 更新邮箱池状态
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

                        if consumed_email:
                            # 半自动模式：接收邮箱标记为 consumed
                            pool.mark_consumed(consumed_email, consumed_by=real_account, veteran_info=veteran_info)
                            logger.info(f"✓ 邮箱池: {consumed_email} → consumed (by {real_account})")
                            # 真实账号如果在邮箱池中也标记为 verified
                            if pool.get_by_address(real_account):
                                pool.mark_verified(real_account, veteran_info=veteran_info)
                                pool.update_password(real_account, password_used)
                        else:
                            # 全自动模式：接收邮箱就是真实账号
                            pool.mark_verified(email, veteran_info=veteran_info)
                            pool.update_password(email, password_used)
                            logger.info(f"✓ 邮箱池: {email} → verified")

                    except Exception as e:
                        logger.error(f"✗ 邮箱池更新失败: {e}")
                        import traceback
                        traceback.print_exc()

                    # 3. 打印成功信息
                    logger.info("=" * 40)
                    logger.info("🎉 验证成功账号信息:")
                    logger.info(f"   账号: {real_account}")
                    logger.info(f"   密码: {password_used}")
                    if consumed_email:
                        logger.info(f"   消耗邮箱: {consumed_email}")
                    if current_veteran:
                        logger.info(f"   军人: {current_veteran['first_name']} {current_veteran['last_name']} ({current_veteran['branch']})")
                    logger.info("=" * 40)

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

                # 需要登录 → 自动登录
                if state == "please_login":
                    logger.info("检测到需要登录，开始自动登录...")
                    password = get_account_password(email)
                    if await register_or_login_chatgpt(page, email, password):
                        logger.info("✓ 自动登录成功")
                        await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                        await asyncio.sleep(3)
                    else:
                        logger.error("自动登录失败")
                        return False
                    continue

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
                        verify_btn_failures += 1
                        logger.warning(f"验证按钮点击失败 ({verify_btn_failures}/3)")

                        if verify_btn_failures >= 3:
                            # 连续3次找不到验证按钮，可能是已验证账号，尝试退出登录
                            logger.warning("连续3次找不到验证按钮，当前账号可能已验证，尝试退出登录...")
                            await logout_chatgpt(page)
                            verify_btn_failures = 0
                            await asyncio.sleep(2)
                            await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                        else:
                            await page.reload()
                    else:
                        verify_btn_failures = 0  # 成功后重置计数
                    await asyncio.sleep(3)
                    continue

                # veterans-claim 页面但未登录 → 自动登录
                if state == "veterans_claim_not_logged_in":
                    logger.info("检测到未登录状态，开始自动登录...")
                    password = get_account_password(email)
                    if await register_or_login_chatgpt(page, email, password):
                        logger.info("✓ 自动登录成功")
                        # 登录成功后导航回 veterans-claim
                        await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                        await asyncio.sleep(3)
                    else:
                        logger.error("自动登录失败")
                        return False
                    continue

                # ChatGPT 首页
                if state == "chatgpt_home":
                    await page.goto(VETERANS_CLAIM_URL)
                    await asyncio.sleep(3)
                    continue

                # OpenAI 登录页面 - 继续登录流程
                if state == "auth_page":
                    logger.info("检测到在登录页面，继续登录流程...")
                    password = get_account_password(email)
                    if await register_or_login_chatgpt(page, email, password):
                        logger.info("✓ 登录成功")
                        await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                        await asyncio.sleep(3)
                    else:
                        logger.error("登录失败")
                        return False
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
                    unknown_state_count += 1
                    if unknown_state_count >= 5:
                        logger.warning("SheerID 页面连续 5 次未识别，尝试返回 veterans-claim...")
                        await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                        unknown_state_count = 0
                    else:
                        await asyncio.sleep(3)
                        await page.reload()
                    await asyncio.sleep(3)
                    continue

                # 未知状态处理
                unknown_state_count += 1
                logger.warning(f"未知状态 ({unknown_state_count}/5): {message[:100]}")
                await save_screenshot(page, f"unknown_{unknown_state_count}")

                if unknown_state_count >= 5:
                    # 连续 5 次未知状态，尝试重新登录
                    logger.error("连续 5 次未知状态，尝试重新登录...")
                    unknown_state_count = 0

                    # 先导航到 veterans-claim 检测状态
                    await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(3)

                    # 检测是否已登录
                    text = await page.evaluate("() => document.body?.innerText || ''")
                    text_lower = text.lower()

                    if "log in" in text_lower and "verify your eligibility" not in text_lower:
                        # 未登录，重新登录
                        logger.info("检测到未登录，重新登录...")
                        password = get_account_password(email)
                        if not await register_or_login_chatgpt(page, email, password):
                            logger.error("重新登录失败")
                            return False
                        await page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                        await asyncio.sleep(3)
                else:
                    # 等待后刷新
                    await asyncio.sleep(3)
                    await page.reload()
                    await asyncio.sleep(3)
                continue

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
    parser.add_argument("--skip-login", action="store_true", help="跳过登录步骤（用户已手动登录）")
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
    if args.skip_login:
        print("  2. 已在 Chrome 中手动登录 ChatGPT（跳过登录模式）")
    else:
        print("  2. 已在 Chrome 中登录 ChatGPT")
    print()

    success = asyncio.run(run_verify_loop(
        args.email,
        chatgpt_account=args.account,
        skip_login=args.skip_login
    ))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
