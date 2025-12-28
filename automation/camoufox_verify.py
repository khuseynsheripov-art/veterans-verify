"""
Veterans Verify - Camoufox 无头自动化验证

特点：
1. 使用 Camoufox 浏览器（C++ 级指纹伪造）
2. 独立运行，不依赖 MCP
3. 自动验证循环：失败自动换数据重试
4. 支持代理轮换

使用方式：
    python -m automation.camoufox_verify <email>

依赖：
    pip install camoufox playwright
"""
import os
import sys
import time
import random
import asyncio
import logging
from typing import Optional, Dict, Tuple
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import (
    get_available_veteran,
    mark_veteran_used,
    get_account_by_email,
    update_account,
    get_veterans_stats,
)
from automation.config import (
    generate_discharge_date,
    VETERANS_CLAIM_URL,
    SHEERID_FIELDS,
)
from email_manager import EmailManager

# 邮箱服务配置
WORKER_DOMAIN = os.environ.get("WORKER_DOMAINS", "apimail.009025.xyz").split(";")[0].strip()
EMAIL_DOMAIN = os.environ.get("EMAIL_DOMAINS", "009025.xyz").split(";")[0].strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORDS", "").split(";")[0].strip()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== 配置 ====================

# 代理池（可选，留空则不使用代理）
PROXY_POOL = [
    # "http://user:pass@proxy1:port",
    # "http://user:pass@proxy2:port",
]

# 验证间隔（秒）
VERIFY_INTERVAL_MIN = 30
VERIFY_INTERVAL_MAX = 90

# 连续失败暂停
MAX_CONSECUTIVE_FAILURES = 5
COOLDOWN_SECONDS = 180

# 最大尝试次数
MAX_ATTEMPTS = 100


# ==================== 页面状态 ====================

class PageState:
    SUCCESS = "success"
    NOT_APPROVED = "not_approved"
    UNABLE_TO_VERIFY = "unable_to_verify"
    VERIFICATION_LIMIT = "verification_limit"
    CHECK_EMAIL = "check_email"
    PLEASE_LOGIN = "please_login"
    SHEERID_FORM = "sheerid_form"
    VETERANS_CLAIM = "veterans_claim"
    UNKNOWN = "unknown"


# 需要换数据的状态
CONSUME_STATES = [
    PageState.NOT_APPROVED,
    PageState.UNABLE_TO_VERIFY,
    PageState.VERIFICATION_LIMIT,
]


# ==================== Camoufox 验证器 ====================

class CamoufoxVerifier:
    """
    使用 Camoufox 的验证器

    Camoufox 优势：
    - Firefox C++ 级修改（非 JavaScript 注入）
    - 0% headless 检测率
    - 完整指纹伪造（Canvas、WebGL、Audio、Fonts）
    - 内置人类光标移动算法
    - GeoIP 自动指纹匹配
    """

    def __init__(
        self,
        account_email: str,
        headless: bool = True,
        proxy: str = None,
        screenshot_dir: str = "screenshots",
        require_account: bool = False  # 是否强制要求账号存在
    ):
        self.account_email = account_email
        self.account = get_account_by_email(account_email)
        if require_account and not self.account:
            raise ValueError(f"账号不存在: {account_email}")
        # 如果账号不存在，记录警告但继续（半自动模式只需要邮箱接收验证链接）
        if not self.account:
            logger.warning(f"账号不存在: {account_email}，将仅使用邮箱接收验证链接")

        self.headless = headless
        self.proxy = proxy
        self.screenshot_dir = screenshot_dir
        self.browser = None
        self.page = None

        self.current_veteran = None
        self.discharge_date = None
        self.attempt_count = 0
        self.consecutive_failures = 0

    async def init_browser(self):
        """初始化 Camoufox 浏览器"""
        try:
            from camoufox.async_api import AsyncCamoufox

            config = {
                "headless": self.headless,
                "geoip": True,  # 使用美国 IP 指纹
                "locale": "en-US",
                "humanize": True,  # 启用人类行为模拟
            }

            if self.proxy:
                config["proxy"] = {"server": self.proxy}

            self.browser = await AsyncCamoufox(**config).__aenter__()
            self.page = await self.browser.new_page()

            logger.info(f"Camoufox 初始化成功 (headless={self.headless}, proxy={self.proxy or 'none'})")
            return True
        except ImportError:
            logger.error("Camoufox 未安装，请运行: pip install camoufox")
            return False
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            return False

    async def close_browser(self):
        """关闭浏览器"""
        if self.browser:
            try:
                await self.browser.__aexit__(None, None, None)
            except:
                pass
            self.browser = None
            self.page = None

    async def screenshot(self, name: str):
        """保存截图"""
        if not self.screenshot_dir:
            return
        try:
            os.makedirs(self.screenshot_dir, exist_ok=True)
            path = os.path.join(
                self.screenshot_dir,
                f"{self.account_email}_{name}_{int(time.time())}.png"
            )
            await self.page.screenshot(path=path)
            logger.debug(f"截图: {path}")
        except Exception as e:
            logger.warning(f"截图失败: {e}")

    async def random_delay(self, min_s: float = 0.5, max_s: float = 1.5):
        """随机延迟"""
        delay = random.uniform(min_s, max_s)
        await asyncio.sleep(delay)

    async def human_type(self, selector: str, text: str):
        """模拟人类打字"""
        try:
            element = await self.page.wait_for_selector(selector, timeout=10000)
            if element:
                await element.click()
                await self.random_delay(0.1, 0.3)
                await self.page.keyboard.press("Control+a")
                await self.random_delay(0.05, 0.1)

                for char in text:
                    await self.page.keyboard.type(char)
                    await asyncio.sleep(random.uniform(0.05, 0.15))

                return True
        except Exception as e:
            logger.error(f"输入失败 [{selector}]: {e}")
            return False

    async def select_dropdown(self, selector: str, value: str) -> bool:
        """选择下拉框"""
        try:
            element = await self.page.wait_for_selector(selector, timeout=5000)
            if element:
                await element.click()
                await self.random_delay(0.3, 0.6)

                # 点击选项
                option = await self.page.wait_for_selector(
                    f'[role="option"]:has-text("{value}")',
                    timeout=3000
                )
                if option:
                    await option.click()
                    await self.random_delay(0.2, 0.4)
                    return True
        except Exception as e:
            logger.error(f"下拉选择失败 [{selector}] -> {value}: {e}")
        return False

    # ==================== 页面状态检测 ====================

    async def detect_page_state(self) -> Tuple[str, str]:
        """
        检测当前页面状态

        Returns:
            (state, message)
        """
        try:
            url = self.page.url
            content = await self.page.content()
            text = await self.page.evaluate("() => document.body?.innerText || ''")

            # 成功
            if "You've been verified" in text or "You have been verified" in text:
                return PageState.SUCCESS, "Verification successful!"

            # 失败状态
            if "Not approved" in text:
                return PageState.NOT_APPROVED, "Verification rejected"

            if "unable to verify" in text.lower():
                return PageState.UNABLE_TO_VERIFY, "Unable to verify at this time"

            if "Verification Limit Exceeded" in text:
                return PageState.VERIFICATION_LIMIT, "Veteran data already used"

            # 需要操作
            if "Check your email" in text:
                return PageState.CHECK_EMAIL, "Need email verification"

            if "Please log in" in text:
                return PageState.PLEASE_LOGIN, "Need to login first"

            # 页面判断
            if "Verify My Eligibility" in text:
                return PageState.SHEERID_FORM, "On SheerID form"

            if "验证资格条件" in text or "Verify your eligibility" in text:
                return PageState.VETERANS_CLAIM, "On veterans-claim (logged in)"

            return PageState.UNKNOWN, text[:200]

        except Exception as e:
            return PageState.UNKNOWN, str(e)

    # ==================== 验证流程 ====================

    def get_next_veteran(self) -> Optional[Dict]:
        """获取下一条军人数据"""
        veteran = get_available_veteran()
        if not veteran:
            logger.error("没有可用的军人数据了")
            return None

        self.current_veteran = veteran
        self.discharge_date = generate_discharge_date()
        self.attempt_count += 1

        logger.info(
            f"[尝试 {self.attempt_count}] "
            f"{veteran['first_name']} {veteran['last_name']} "
            f"({veteran['branch']})"
        )
        return veteran

    def consume_current_veteran(self, reason: str):
        """消耗当前军人数据"""
        if self.current_veteran:
            mark_veteran_used(
                self.current_veteran['id'],
                f"{self.account_email} - {reason}"
            )
            logger.info(f"[消耗] {self.current_veteran['id']}: {reason}")
            self.current_veteran = None

    async def fill_sheerid_form(self) -> bool:
        """填写 SheerID 表单"""
        if not self.current_veteran:
            return False

        try:
            logger.info("开始填写表单...")
            await self.random_delay(1, 2)

            # 1. Status - Military Veteran or Retiree
            await self.select_dropdown(
                '#sid-military-status',
                'Military Veteran'
            )
            await self.random_delay(0.3, 0.6)

            # 2. Branch
            await self.select_dropdown(
                '#sid-branch-of-service',
                self.current_veteran['branch']
            )
            await self.random_delay(0.3, 0.6)

            # 3. Birth Month
            await self.select_dropdown(
                '#sid-birthdate__month',
                self.current_veteran['birth_month']
            )
            await self.random_delay(0.3, 0.6)

            # 4. Discharge Month
            await self.select_dropdown(
                '#sid-discharge-date__month',
                self.discharge_date['month']
            )
            await self.random_delay(0.3, 0.6)

            # 5. 填写文本字段
            await self.human_type('#sid-first-name', self.current_veteran['first_name'])
            await self.random_delay(0.2, 0.4)

            await self.human_type('#sid-last-name', self.current_veteran['last_name'])
            await self.random_delay(0.2, 0.4)

            await self.human_type('#sid-birthdate-day', self.current_veteran['birth_day'])
            await self.random_delay(0.2, 0.4)

            await self.human_type('#sid-birthdate-year', self.current_veteran['birth_year'])
            await self.random_delay(0.2, 0.4)

            await self.human_type('#sid-discharge-date-day', self.discharge_date['day'])
            await self.random_delay(0.2, 0.4)

            await self.human_type('#sid-discharge-date-year', self.discharge_date['year'])
            await self.random_delay(0.2, 0.4)

            await self.human_type('#sid-email', self.account_email)
            await self.random_delay(0.5, 1)

            await self.screenshot("form_filled")
            logger.info("表单填写完成")
            return True

        except Exception as e:
            logger.error(f"表单填写失败: {e}")
            await self.screenshot("form_error")
            return False

    async def submit_form(self) -> bool:
        """提交表单"""
        try:
            submit_btn = await self.page.query_selector('button:has-text("Verify My Eligibility")')
            if not submit_btn:
                submit_btn = await self.page.query_selector('button[type="submit"]')

            if submit_btn:
                is_disabled = await submit_btn.get_attribute("disabled")
                if is_disabled:
                    logger.warning("提交按钮被禁用")
                    return False

                await submit_btn.click()
                await self.random_delay(2, 4)
                await self.screenshot("after_submit")
                return True

            logger.error("找不到提交按钮")
            return False

        except Exception as e:
            logger.error(f"提交失败: {e}")
            return False

    async def click_try_again(self) -> bool:
        """点击 Try Again"""
        try:
            link = await self.page.query_selector('a:has-text("Try Again")')
            if link:
                await link.click()
                await self.random_delay(2, 4)
                return True

            button = await self.page.query_selector('button:has-text("Try Again")')
            if button:
                await button.click()
                await self.random_delay(2, 4)
                return True

            return False
        except Exception as e:
            logger.error(f"点击 Try Again 失败: {e}")
            return False

    async def click_verify_button(self) -> bool:
        """点击验证按钮"""
        try:
            btn = await self.page.query_selector('button:has-text("验证资格条件")')
            if not btn:
                btn = await self.page.query_selector('button:has-text("Verify")')

            if btn:
                await btn.click()
                await self.random_delay(2, 4)
                return True
            return False
        except Exception as e:
            logger.error(f"点击验证按钮失败: {e}")
            return False

    async def check_and_click_verification_link(self, max_retries: int = 20) -> bool:
        """
        检查并点击邮件验证链接

        Returns:
            是否成功点击
        """
        logger.info(f"开始检查验证链接: {self.account_email}")

        try:
            email_manager = EmailManager(
                worker_domain=WORKER_DOMAIN,
                email_domain=EMAIL_DOMAIN,
                admin_password=ADMIN_PASSWORD
            )

            # 查找验证链接（每 3 秒检查一次）
            link = email_manager.check_verification_link(
                email=self.account_email,
                max_retries=max_retries,
                interval=3.0
            )

            if link:
                logger.info(f"找到验证链接，正在访问...")
                logger.debug(f"链接: {link[:100]}...")

                # 在当前页面访问验证链接
                await self.page.goto(link, wait_until="domcontentloaded", timeout=30000)
                await self.random_delay(2, 4)

                # 检查页面状态
                text = await self.page.evaluate("() => document.body?.innerText || ''")

                if "verified" in text.lower() or "success" in text.lower():
                    logger.info("验证链接点击成功！")
                    return True
                elif "error" in text.lower() or "expired" in text.lower():
                    logger.warning("验证链接可能已过期或无效")
                    return False
                else:
                    # 可能需要返回 veterans-claim 页面继续
                    logger.info("已访问验证链接，返回继续检查...")
                    await self.random_delay(1, 2)
                    await self.page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded")
                    await self.random_delay(2, 4)
                    return True
            else:
                logger.warning("未找到验证链接")
                return False

        except Exception as e:
            logger.error(f"检查验证链接失败: {e}")
            return False

    # ==================== 主循环 ====================

    async def run_verify_loop(self) -> bool:
        """
        运行验证循环

        Returns:
            是否验证成功
        """
        logger.info(f"开始验证循环: {self.account_email}")

        # 初始化浏览器
        if not await self.init_browser():
            return False

        try:
            # 打开 veterans-claim 页面
            await self.page.goto(VETERANS_CLAIM_URL)
            await self.random_delay(2, 4)
            await self.screenshot("start")

            while self.attempt_count < MAX_ATTEMPTS:
                # 检测页面状态
                state, message = await self.detect_page_state()
                logger.info(f"页面状态: {state} - {message}")

                # === 成功 ===
                if state == PageState.SUCCESS:
                    if self.account:
                        update_account(self.account_email, status="verified")
                    logger.info("验证成功！")
                    await self.screenshot("success")
                    return True

                # === 需要换数据的失败 ===
                if state in CONSUME_STATES:
                    self.consecutive_failures += 1
                    self.consume_current_veteran(state)

                    # 连续失败暂停
                    if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        logger.warning(f"连续失败 {self.consecutive_failures} 次，暂停 {COOLDOWN_SECONDS} 秒")
                        await asyncio.sleep(COOLDOWN_SECONDS)
                        self.consecutive_failures = 0

                    # 点击 Try Again
                    await self.click_try_again()
                    await self.random_delay(2, 4)
                    continue

                # === 需要登录 ===
                if state == PageState.PLEASE_LOGIN:
                    logger.error("需要登录，请先手动登录后重试")
                    return False

                # === 在 veterans-claim 页面 ===
                if state == PageState.VETERANS_CLAIM:
                    await self.click_verify_button()
                    await self.random_delay(2, 4)
                    continue

                # === 在表单页面 ===
                if state == PageState.SHEERID_FORM:
                    # 获取数据
                    if not self.current_veteran:
                        if not self.get_next_veteran():
                            logger.error("没有可用数据了")
                            return False

                    # 填写表单
                    if await self.fill_sheerid_form():
                        # 提交
                        await self.submit_form()
                        await self.random_delay(3, 6)
                        self.consecutive_failures = 0
                    else:
                        # 填写失败，换数据
                        self.consume_current_veteran("form_fill_error")

                    continue

                # === 等待邮件 ===
                if state == PageState.CHECK_EMAIL:
                    logger.info("检测到需要邮件验证，开始自动获取验证链接...")
                    if await self.check_and_click_verification_link(max_retries=30):
                        logger.info("验证链接已点击，继续检查状态...")
                        await self.random_delay(3, 5)
                    else:
                        logger.warning("自动获取验证链接失败，等待后重试...")
                        await asyncio.sleep(30)
                        await self.page.reload()
                    continue

                # === 未知状态 ===
                logger.warning(f"未知状态，等待后重试: {message}")
                await self.screenshot("unknown_state")
                await asyncio.sleep(10)

            logger.error(f"超过最大尝试次数 ({MAX_ATTEMPTS})")
            return False

        except Exception as e:
            logger.error(f"验证循环异常: {e}")
            await self.screenshot("error")
            return False

        finally:
            await self.close_browser()


# ==================== 入口 ====================

async def main(email: str):
    """主函数"""
    # 选择代理
    proxy = random.choice(PROXY_POOL) if PROXY_POOL else None

    verifier = CamoufoxVerifier(
        account_email=email,
        headless=False,  # 调试时设为 False
        proxy=proxy,
        screenshot_dir="screenshots"
    )

    success = await verifier.run_verify_loop()

    if success:
        print(f"\n✅ 验证成功！账号 {email} 已获得 1 年 Plus")
    else:
        print(f"\n❌ 验证失败，已尝试 {verifier.attempt_count} 次")

    stats = get_veterans_stats()
    print(f"\n剩余可用数据: {stats['available']} / {stats['total']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方式: python -m automation.camoufox_verify <email>")
        print("示例: python -m automation.camoufox_verify test@009025.xyz")
        sys.exit(1)

    email = sys.argv[1]
    asyncio.run(main(email))
