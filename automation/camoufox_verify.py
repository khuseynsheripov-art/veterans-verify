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
        self.sheerid_email = account_email  # 默认 SheerID 表单用同一个邮箱
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
        """初始化 Camoufox 浏览器（支持 Profile 持久化）"""
        try:
            from camoufox.async_api import AsyncCamoufox
            from profile_manager import get_or_create_profile

            # 获取或创建 Profile 目录
            profile_path = get_or_create_profile(self.account_email)

            config = {
                "headless": self.headless,
                "geoip": True,  # 使用美国 IP 指纹
                "locale": "en-US",
                "humanize": True,  # 启用人类行为模拟
                "persistent_context": True,  # 🔥 启用持久化上下文
                "user_data_dir": str(profile_path),  # 🔥 持久化 Profile
            }

            if self.proxy:
                config["proxy"] = {"server": self.proxy}

            self.browser = await AsyncCamoufox(**config).__aenter__()
            self.page = await self.browser.new_page()

            logger.info(f"Camoufox 初始化成功 (headless={self.headless}, proxy={self.proxy or 'none'}, profile={profile_path})")
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

    async def select_combobox(self, label: str, value: str) -> bool:
        """
        选择下拉框（使用 get_by_role 更稳定）

        Args:
            label: combobox 的 name 标签（如 "Branch of service"）
            value: 要选择的选项值（精确匹配）
        """
        try:
            # 点击 combobox 打开列表
            combobox = self.page.get_by_role("combobox", name=label)
            await combobox.click(timeout=5000)
            await self.random_delay(0.3, 0.6)

            # 选择选项（精确匹配）
            option = self.page.get_by_role("option", name=value, exact=True)
            await option.click(timeout=3000)
            await self.random_delay(0.2, 0.4)
            logger.debug(f"选择 {label}: {value}")
            return True
        except Exception as e:
            logger.error(f"下拉选择失败 [{label}] -> {value}: {e}")
        return False

    # ==================== 登录/退出 ====================

    async def logout_chatgpt(self) -> bool:
        """退出当前 ChatGPT 账号"""
        logger.info("正在退出 ChatGPT...")
        try:
            # 先导航到首页
            await self.page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=15000)
            await self.random_delay(2, 3)

            # 方法1：点击用户菜单退出
            try:
                user_menu = await self.page.query_selector('[data-testid="profile-button"], button[aria-label*="profile"]')
                if user_menu:
                    await user_menu.click()
                    await self.random_delay(0.5, 1)
                    logout_btn = await self.page.query_selector('a:has-text("Log out"), button:has-text("Log out")')
                    if logout_btn:
                        await logout_btn.click()
                        await self.random_delay(2, 4)
                        logger.info("已点击退出按钮")
                        return True
            except:
                pass

            # 方法2：清除 cookies
            try:
                context = self.page.context
                await context.clear_cookies()
                await self.page.reload()
                await self.random_delay(2, 3)
                logger.info("已清除 Cookies")
                return True
            except:
                pass

            return False
        except Exception as e:
            logger.warning(f"退出登录失败: {e}")
            return False

    async def register_or_login(self, password: str) -> bool:
        """
        注册或登录 ChatGPT 账号

        流程：
        1. 打开 veterans-claim 页面
        2. 点击登录
        3. 输入邮箱
        4. 创建/输入密码
        5. 输入验证码（如需要）
        6. 处理 about-you 页面（如需要）
        """
        logger.info(f"开始登录: {self.account_email}")

        try:
            # 1. 打开 veterans-claim
            await self.page.goto(VETERANS_CLAIM_URL, wait_until="domcontentloaded", timeout=30000)
            await self.random_delay(2, 4)
            await self.screenshot("01_veterans_claim")

            # 检查是否已登录
            text = await self.page.evaluate("() => document.body?.innerText || ''")
            if "验证资格条件" in text or "Verify your eligibility" in text.lower():
                logger.info("已经登录，直接进入验证")
                return True

            # 2. 点击登录按钮
            login_btn = await self.page.query_selector('button:has-text("登录"), button:has-text("Log in"), button:has-text("Sign in")')
            if login_btn:
                await login_btn.click()
                await self.random_delay(2, 4)

            # 3. 输入邮箱
            email_input = await self.page.wait_for_selector('input[type="email"], input[name="email"]', timeout=15000)
            if email_input:
                await email_input.fill(self.account_email)
                await self.random_delay(0.5, 1)

                continue_btn = await self.page.query_selector('button:has-text("继续"), button:has-text("Continue")')
                if continue_btn:
                    await continue_btn.click()
                    await self.random_delay(2, 4)

            await self.screenshot("02_after_email")

            # 4. 输入密码
            page_text = await self.page.evaluate("() => document.body?.innerText || ''")
            password_input = await self.page.query_selector('input[type="password"]')
            if password_input:
                if "创建密码" in page_text or "Create password" in page_text:
                    logger.info("新用户，创建密码")
                else:
                    logger.info("已有用户，输入密码")

                await password_input.fill(password)
                await self.random_delay(0.5, 1)

                continue_btn = await self.page.query_selector('button:has-text("继续"), button:has-text("Continue")')
                if continue_btn:
                    await continue_btn.click()
                    await self.random_delay(3, 5)

            await self.screenshot("03_after_password")

            # 5. 检查验证码
            page_text = await self.page.evaluate("() => document.body?.innerText || ''")
            if "检查您的收件箱" in page_text or "Check your inbox" in page_text:
                logger.info("需要邮箱验证码...")
                code = await self._get_verification_code()
                if code:
                    logger.info(f"获取到验证码: {code}")
                    # 优先使用 get_by_role（更稳定）
                    code_input = self.page.get_by_role("textbox", name="代码")
                    if await code_input.count() == 0:
                        code_input = self.page.get_by_role("textbox", name="Code")
                    if await code_input.count() == 0:
                        code_input = await self.page.query_selector('input[name="code"], input[type="text"]')

                    if code_input:
                        if hasattr(code_input, 'fill'):
                            await code_input.fill(code)
                        else:
                            await code_input.fill(code)
                        await self.random_delay(0.5, 1)
                        continue_btn = await self.page.query_selector('button:has-text("继续"), button:has-text("Continue")')
                        if continue_btn:
                            await continue_btn.click()
                            await self.random_delay(3, 5)
                else:
                    logger.error("未能获取验证码")
                    return False

            # 6. 处理 about-you 页面
            if "about-you" in self.page.url:
                if not await self._handle_about_you():
                    return False

            await self.screenshot("04_login_complete")
            logger.info("登录完成")
            return True

        except Exception as e:
            logger.error(f"登录失败: {e}")
            await self.screenshot("error_login")
            return False

    async def _get_verification_code(self, max_retries: int = 30) -> Optional[str]:
        """从邮箱获取 ChatGPT 验证码"""
        try:
            email_manager = EmailManager(
                worker_domain=WORKER_DOMAIN,
                email_domain=EMAIL_DOMAIN,
                admin_password=ADMIN_PASSWORD
            )
            return email_manager.check_verification_code(
                email=self.account_email,
                max_retries=max_retries,
                interval=3.0
            )
        except Exception as e:
            logger.error(f"获取验证码失败: {e}")
            return None

    async def _handle_about_you(self) -> bool:
        """处理 about-you 确认年龄页面"""
        logger.info("处理 about-you 页面...")
        try:
            import random
            from datetime import datetime

            # 生成随机生日（25-35岁，更符合退伍军人）
            today = datetime.now()
            age = random.randint(25, 35)
            birth_year = str(today.year - age)
            birth_month = str(random.randint(1, 12))
            birth_day = str(random.randint(1, 28))

            # 等待页面加载
            await self.random_delay(1, 2)

            # 填写全名（如果有）
            name_input = self.page.get_by_role("textbox", name="全名")
            if await name_input.count() > 0:
                await name_input.fill("John Smith")
                await self.random_delay(0.3, 0.5)

            # 填写生日（spinbutton 类型）- 中英双语支持
            async def fill_spinbutton(aria_labels: list, value: str, fallback_name: str):
                """填写 spinbutton，支持中英双语"""
                for aria_label in aria_labels:
                    spinbutton = self.page.get_by_role("spinbutton", name=aria_label)
                    if await spinbutton.count() > 0:
                        await spinbutton.fill(value)
                        logger.info(f"✓ 填写 spinbutton: {value} (name='{aria_label}')")
                        return True
                # 备用选择器
                fallback = await self.page.query_selector(f'input[name="{fallback_name}"]')
                if fallback:
                    await fallback.fill(value)
                    logger.info(f"✓ 填写备用 input: {value} (name='{fallback_name}')")
                    return True
                logger.warning(f"⚠️ 未找到 spinbutton，尝试过: {aria_labels}")
                return False

            # 年份（中英双语）
            await fill_spinbutton(["年", "Year", "year"], birth_year, "year")
            await self.random_delay(0.2, 0.4)

            # 月份（中英双语）
            await fill_spinbutton(["月", "Month", "month"], birth_month, "month")
            await self.random_delay(0.2, 0.4)

            # 日期（中英双语）
            await fill_spinbutton(["日", "Day", "day"], birth_day, "day")

            await self.random_delay(0.5, 1)

            # 点击继续
            continue_btn = await self.page.query_selector('button:has-text("Continue"), button:has-text("继续")')
            if continue_btn:
                await continue_btn.click()
                await self.random_delay(2, 4)

            logger.info("about-you 处理完成")
            return True
        except Exception as e:
            logger.error(f"about-you 处理失败: {e}")
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
        """
        填写 SheerID 表单

        重要：Status 必须第一个选择，否则其他字段会被清空！

        表单结构（2025-12-27 验证）：
        - Status: combobox (动态字段，有些页面有有些没有)
        - Branch of service: combobox
        - First/Last name: textbox
        - Date of birth: combobox (month) + textbox (day/year)
        - Discharge date: combobox (month) + textbox (day/year)
        - Email: textbox
        """
        if not self.current_veteran:
            return False

        try:
            logger.info(f"开始填写表单: {self.current_veteran['first_name']} {self.current_veteran['last_name']} ({self.current_veteran['branch']})")
            await self.random_delay(1, 2)

            # 辅助函数：填写文本框
            async def fill_textbox(label: str, value: str, nth: int = 0):
                try:
                    textbox = self.page.get_by_role("textbox", name=label).nth(nth)
                    await textbox.fill(value, timeout=5000)
                    await self.random_delay(0.1, 0.3)
                    logger.debug(f"填写 {label}: {value}")
                    return True
                except Exception as e:
                    logger.warning(f"填写 {label} 失败: {e}")
                    return False

            # 1. Status (动态检测！有些页面有此字段，有些没有)
            # 必须第一个选，否则其他字段会被清空
            try:
                status_combobox = self.page.get_by_role("combobox", name="Status")
                if await status_combobox.count() > 0:
                    logger.info("检测到 Status 字段，选择 'Military Veteran or Retiree'")
                    await self.select_combobox("Status", "Military Veteran or Retiree")
                    # 选择 Status 后可能会有 "Verifying your military status" 加载
                    await self.random_delay(1.5, 2.5)
                    # 等待表单重新出现
                    try:
                        await self.page.wait_for_selector('text=Branch of service', timeout=10000)
                    except:
                        pass
                else:
                    logger.info("没有 Status 字段，跳过")
            except Exception as e:
                logger.debug(f"Status 字段检测: {e} (跳过)")
            await self.random_delay(0.3, 0.5)

            # 2. Branch of service
            await self.select_combobox("Branch of service", self.current_veteran['branch'])
            await self.random_delay(0.3, 0.5)

            # 3. First name & Last name
            await fill_textbox("First name", self.current_veteran['first_name'])
            await fill_textbox("Last name", self.current_veteran['last_name'])

            # 4. Date of birth (month combobox + day/year textbox)
            await self.select_combobox("Date of birth", self.current_veteran['birth_month'])
            await self.random_delay(0.2, 0.4)

            # Day 和 Year 有两组，第一组是 Date of birth，第二组是 Discharge date
            day_boxes = self.page.get_by_role("textbox", name="Day")
            year_boxes = self.page.get_by_role("textbox", name="Year")

            await day_boxes.nth(0).fill(self.current_veteran['birth_day'], timeout=5000)
            await self.random_delay(0.1, 0.2)
            await year_boxes.nth(0).fill(self.current_veteran['birth_year'], timeout=5000)
            await self.random_delay(0.2, 0.4)

            # 5. Discharge date (month combobox + day/year textbox)
            await self.select_combobox("Discharge date", self.discharge_date['month'])
            await self.random_delay(0.2, 0.4)

            await day_boxes.nth(1).fill(self.discharge_date['day'], timeout=5000)
            await self.random_delay(0.1, 0.2)
            await year_boxes.nth(1).fill(self.discharge_date['year'], timeout=5000)
            await self.random_delay(0.2, 0.4)

            # 6. Email
            await fill_textbox("Email address", self.sheerid_email)

            await self.screenshot("form_filled")
            logger.info("表单填写完成")
            return True

        except Exception as e:
            logger.error(f"表单填写失败: {e}")
            import traceback
            traceback.print_exc()
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
        # SheerID 验证链接发到 sheerid_email（可能是临时邮箱）
        logger.info(f"开始检查验证链接: {self.sheerid_email}")

        try:
            email_manager = EmailManager(
                worker_domain=WORKER_DOMAIN,
                email_domain=EMAIL_DOMAIN,
                admin_password=ADMIN_PASSWORD
            )

            # 查找验证链接（每 3 秒检查一次）
            link = email_manager.check_verification_link(
                email=self.sheerid_email,
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

    async def run_verify_loop(self, password: str = None, auto_login: bool = True, sheerid_email: str = None) -> bool:
        """
        运行验证循环

        Args:
            password: 账号密码（auto_login=True 时必须）
            auto_login: 是否自动登录（False = 假设已登录）
            sheerid_email: SheerID 表单用的邮箱（自有账号模式时用临时邮箱）

        Returns:
            是否验证成功
        """
        # 设置 SheerID 表单用的邮箱
        if sheerid_email:
            self.sheerid_email = sheerid_email
            logger.info(f"SheerID 表单邮箱: {sheerid_email}")

        logger.info(f"开始验证循环: {self.account_email}")
        logger.info(f"模式: {'自动登录' if auto_login else '已登录'}")

        # 初始化浏览器
        if not await self.init_browser():
            return False

        try:
            # 自动登录模式：先退出旧账号，再登录新账号
            if auto_login:
                if not password:
                    # 尝试从数据库获取密码
                    if self.account and self.account.get('password'):
                        password = self.account['password']
                    else:
                        logger.error("需要密码但未提供")
                        return False

                # 退出旧账号
                await self.logout_chatgpt()

                # 登录新账号
                if not await self.register_or_login(password):
                    logger.error("登录失败")
                    return False
            else:
                # 假设已登录，直接打开 veterans-claim
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
    """
    主函数（仅用于测试）

    生产环境请使用 app.py，其中集成了代理池管理
    """
    verifier = CamoufoxVerifier(
        account_email=email,
        headless=False,  # 调试时设为 False
        proxy=None,  # 测试时不使用代理，生产环境由 app.py 管理
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
