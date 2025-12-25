"""
Veterans Verify - 浏览器自动化核心
使用 Camoufox 实现最强反检测

完整流程：
1. 创建临时邮箱
2. 注册/登录 ChatGPT（邮箱验证码）
3. 进入 SheerID Veterans 验证表单
4. 填写军人信息（真实 BIRLS 数据 + 随机退伍日期）
5. 提交表单，等待邮件验证链接
6. 点击链接完成验证
"""
import os
import re
import time
import random
import asyncio
from enum import Enum
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class VerifyStatus(Enum):
    """验证状态"""
    PENDING = "pending"
    CREATING_EMAIL = "creating_email"
    REGISTERING_CHATGPT = "registering_chatgpt"
    WAITING_CHATGPT_CODE = "waiting_chatgpt_code"
    CONFIRMING_AGE = "confirming_age"  # 新增：确认年龄页面
    OPENING_SHEERID = "opening_sheerid"
    FILLING_FORM = "filling_form"
    SUBMITTING = "submitting"
    WAITING_VERIFY_LINK = "waiting_verify_link"
    CLICKING_LINK = "clicking_link"
    CHECKING_RESULT = "checking_result"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class VerifyTask:
    """验证任务"""
    task_id: str
    status: VerifyStatus = VerifyStatus.PENDING
    email: Optional[str] = None
    password: str = ""
    first_name: str = ""
    last_name: str = ""
    branch: str = "Army"
    birth_date: Dict[str, str] = field(default_factory=lambda: {"month": "January", "day": "15", "year": "1985"})
    discharge_date: Dict[str, str] = field(default_factory=lambda: {"month": "June", "day": "20", "year": "2024"})
    error_message: Optional[str] = None
    error_type: Optional[str] = None  # 错误分类
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    screenshots: list = field(default_factory=list)  # 截图路径列表


class HumanBehavior:
    """人类行为模拟"""

    def __init__(self, delay_min: int = 50, delay_max: int = 150):
        self.delay_min = delay_min
        self.delay_max = delay_max

    def random_delay(self, base: float = 1.0, variance: float = 0.5) -> float:
        """生成正态分布随机延迟"""
        delay = random.gauss(base, variance)
        return max(0.1, delay)

    def typing_delay(self) -> float:
        """打字延迟（ms 转 s）"""
        return random.randint(self.delay_min, self.delay_max) / 1000

    @staticmethod
    def generate_random_birthday(min_age: int = 20, max_age: int = 25) -> Dict[str, str]:
        """
        生成随机生日（用于确认年龄页面）

        Args:
            min_age: 最小年龄（默认 20）
            max_age: 最大年龄（默认 25）

        Returns:
            {"year": "2002", "month": "3", "day": "15"}
        """
        today = datetime.now()
        age = random.randint(min_age, max_age)
        birth_year = today.year - age
        birth_month = random.randint(1, 12)
        birth_day = random.randint(1, 28)  # 避免月份天数问题

        return {
            "year": str(birth_year),
            "month": str(birth_month),
            "day": str(birth_day)
        }

    @staticmethod
    def generate_random_name() -> str:
        """生成随机英文名（用于确认年龄页面）"""
        first_names = [
            "James", "John", "Michael", "David", "Chris", "Daniel", "Matthew", "Andrew",
            "Emily", "Sarah", "Jessica", "Ashley", "Amanda", "Jennifer", "Elizabeth", "Rachel"
        ]
        last_names = [
            "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson",
            "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin", "Lee", "Harris"
        ]
        return f"{random.choice(first_names)} {random.choice(last_names)}"


class BrowserWorker:
    """浏览器自动化工作器"""

    # URLs
    VETERANS_CLAIM_URL = "https://chatgpt.com/veterans-claim"
    SHEERID_URL = "https://services.sheerid.com/verify/690415d58971e73ca187d8c9/"

    # 表单选项
    BRANCH_OPTIONS = [
        "Air Force", "Army", "Coast Guard",
        "Marine Corps", "Navy", "Space Force"
    ]

    def __init__(self, headless: bool = True, screenshot_dir: str = None):
        self.headless = headless
        self.human = HumanBehavior()
        self.browser = None
        self.page = None
        self.screenshot_dir = screenshot_dir

    async def init_browser(self):
        """初始化 Camoufox 浏览器"""
        try:
            from camoufox.async_api import AsyncCamoufox

            self.browser = await AsyncCamoufox(
                headless=self.headless,
                geoip=True,  # 使用美国 IP 指纹
                locale="en-US",
                humanize=True,
            ).__aenter__()

            self.page = await self.browser.new_page()
            logger.info("[Browser] Camoufox 初始化成功")
            return True
        except Exception as e:
            logger.error(f"[Browser] 初始化失败: {e}")
            return False

    async def close_browser(self):
        """关闭浏览器"""
        try:
            if self.browser:
                await self.browser.__aexit__(None, None, None)
                self.browser = None
                self.page = None
        except Exception as e:
            logger.error(f"[Browser] 关闭失败: {e}")

    async def take_screenshot(self, task: VerifyTask, name: str):
        """截图保存"""
        if not self.screenshot_dir:
            return
        try:
            os.makedirs(self.screenshot_dir, exist_ok=True)
            path = os.path.join(self.screenshot_dir, f"{task.task_id}_{name}_{int(time.time())}.png")
            await self.page.screenshot(path=path)
            task.screenshots.append(path)
            logger.debug(f"[Screenshot] 保存: {path}")
        except Exception as e:
            logger.warning(f"[Screenshot] 失败: {e}")

    async def human_type(self, selector: str, text: str, clear_first: bool = True):
        """人类式输入"""
        try:
            element = await self.page.wait_for_selector(selector, timeout=10000)
            if element:
                await element.click()
                await asyncio.sleep(self.human.random_delay(0.2, 0.1))

                if clear_first:
                    await self.page.keyboard.press("Control+a")
                    await asyncio.sleep(0.1)

                for char in text:
                    await self.page.keyboard.type(char)
                    await asyncio.sleep(self.human.typing_delay())

                return True
        except Exception as e:
            logger.error(f"[Input] 输入失败 {selector}: {e}")
            return False

    async def click_element(self, selector: str, timeout: int = 10000) -> bool:
        """点击元素"""
        try:
            element = await self.page.wait_for_selector(selector, timeout=timeout)
            if element:
                await asyncio.sleep(self.human.random_delay(0.3, 0.1))
                await element.click()
                return True
        except Exception as e:
            logger.error(f"[Click] 点击失败 {selector}: {e}")
            return False

    async def select_dropdown(self, trigger_selector: str, option_text: str) -> bool:
        """选择下拉选项"""
        try:
            # 点击触发下拉
            await self.click_element(trigger_selector)
            await asyncio.sleep(self.human.random_delay(0.5, 0.2))

            # 点击选项
            option_selector = f'[role="option"]:has-text("{option_text}"), li:has-text("{option_text}"), div[role="listbox"] >> text="{option_text}"'
            await self.click_element(option_selector, timeout=5000)
            await asyncio.sleep(self.human.random_delay(0.3, 0.1))

            return True
        except Exception as e:
            logger.error(f"[Dropdown] 选择失败 {option_text}: {e}")
            return False

    # ==================== 确认年龄页面 ====================

    async def handle_about_you_page(self, task: VerifyTask) -> bool:
        """
        处理确认年龄页面 (auth.openai.com/about-you)

        此页面在新用户注册后出现，需要填写：
        1. 全名（随机生成）
        2. 生日（20-25岁之间）
        """
        current_url = self.page.url
        if "about-you" not in current_url:
            return True  # 不在此页面，跳过

        task.status = VerifyStatus.CONFIRMING_AGE
        logger.info(f"[Task {task.task_id}] 处理确认年龄页面")

        try:
            await asyncio.sleep(self.human.random_delay(1.0, 0.3))

            # 生成随机信息（20-25岁）
            random_name = self.human.generate_random_name()
            random_birthday = self.human.generate_random_birthday(min_age=20, max_age=25)

            logger.debug(f"[Task {task.task_id}] 随机姓名: {random_name}, 生日: {random_birthday}")

            # 1. 填写全名
            name_input = await self.page.wait_for_selector('input[name="name"]', timeout=10000)
            if name_input:
                await self.human_type('input[name="name"]', random_name)
                await asyncio.sleep(self.human.random_delay(0.3, 0.1))

            # 2. 填写生日（年、月、日 spinbutton）
            # 根据 page-selectors.md：spinbutton "年, 生日日期" / "月, 生日日期" / "日, 生日日期"
            # 使用 input[type="number"] 选择器

            # 年份
            year_input = await self.page.query_selector('input[type="number"][aria-label*="年"]')
            if year_input:
                await year_input.click()
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Control+a")
                await self.page.keyboard.type(random_birthday["year"])
                await asyncio.sleep(self.human.random_delay(0.2, 0.1))

            # 月份
            month_input = await self.page.query_selector('input[type="number"][aria-label*="月"]')
            if month_input:
                await month_input.click()
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Control+a")
                await self.page.keyboard.type(random_birthday["month"])
                await asyncio.sleep(self.human.random_delay(0.2, 0.1))

            # 日期
            day_input = await self.page.query_selector('input[type="number"][aria-label*="日"]')
            if day_input:
                await day_input.click()
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Control+a")
                await self.page.keyboard.type(random_birthday["day"])
                await asyncio.sleep(self.human.random_delay(0.2, 0.1))

            await self.take_screenshot(task, "04b_about_you_filled")

            # 3. 点击继续按钮
            continue_btn = await self.page.query_selector('button[type="submit"]')
            if continue_btn:
                await continue_btn.click()
                await asyncio.sleep(self.human.random_delay(3.0, 1.0))

            await self.take_screenshot(task, "04c_after_about_you")
            logger.info(f"[Task {task.task_id}] 确认年龄页面完成")
            return True

        except Exception as e:
            logger.error(f"[Task {task.task_id}] 确认年龄页面失败: {e}")
            task.error_message = f"确认年龄页面失败: {e}"
            task.error_type = "ABOUT_YOU_ERROR"
            await self.take_screenshot(task, "error_about_you")
            return False

    # ==================== ChatGPT 注册流程 ====================

    async def register_chatgpt(self, task: VerifyTask, email_manager) -> bool:
        """
        注册 ChatGPT 账号

        流程：
        1. 打开 veterans-claim 页面
        2. 点击登录
        3. 输入邮箱
        4. 创建密码
        5. 输入邮箱验证码
        """
        task.status = VerifyStatus.REGISTERING_CHATGPT

        try:
            # 1. 打开 Veterans Claim 页面
            logger.info(f"[Task {task.task_id}] 打开 Veterans Claim 页面")
            await self.page.goto(self.VETERANS_CLAIM_URL)
            await asyncio.sleep(self.human.random_delay(3.0, 1.0))
            await self.take_screenshot(task, "01_veterans_claim")

            # 2. 点击登录按钮
            login_btn = await self.page.query_selector('button:has-text("登录"), button:has-text("Log in"), button:has-text("Sign in")')
            if login_btn:
                await login_btn.click()
                await asyncio.sleep(self.human.random_delay(3.0, 1.0))
            await self.take_screenshot(task, "02_login_page")

            # 3. 输入邮箱
            email_input = await self.page.wait_for_selector('input[type="email"], input[name="email"], input[autocomplete="email"]', timeout=15000)
            if email_input:
                await self.human_type('input[type="email"], input[name="email"], input[autocomplete="email"]', task.email)
                await asyncio.sleep(self.human.random_delay(0.5, 0.2))

                # 点击继续
                continue_btn = await self.page.query_selector('button:has-text("继续"), button:has-text("Continue")')
                if continue_btn:
                    await continue_btn.click()
                    await asyncio.sleep(self.human.random_delay(3.0, 1.0))

            await self.take_screenshot(task, "03_after_email")

            # 检查页面状态
            page_content = await self.page.content()

            # 4a. 如果是新用户，需要创建密码
            if "创建密码" in page_content or "Create password" in page_content or "password" in await self.page.url():
                logger.info(f"[Task {task.task_id}] 新用户，创建密码")
                password_input = await self.page.wait_for_selector('input[type="password"]', timeout=10000)
                if password_input:
                    await self.human_type('input[type="password"]', task.password)
                    await asyncio.sleep(self.human.random_delay(0.5, 0.2))

                    continue_btn = await self.page.query_selector('button:has-text("继续"), button:has-text("Continue")')
                    if continue_btn:
                        await continue_btn.click()
                        await asyncio.sleep(self.human.random_delay(3.0, 1.0))

                await self.take_screenshot(task, "04_after_password")

            # 4b. 如果是老用户，输入密码登录
            elif "输入密码" in page_content or "Enter password" in page_content:
                logger.info(f"[Task {task.task_id}] 已存在用户，输入密码")
                password_input = await self.page.wait_for_selector('input[type="password"]', timeout=10000)
                if password_input:
                    await self.human_type('input[type="password"]', task.password)
                    await asyncio.sleep(self.human.random_delay(0.5, 0.2))

                    continue_btn = await self.page.query_selector('button:has-text("继续"), button:has-text("Continue")')
                    if continue_btn:
                        await continue_btn.click()
                        await asyncio.sleep(self.human.random_delay(3.0, 1.0))

            # 5. 检查是否需要邮箱验证码
            page_content = await self.page.content()
            if "检查您的收件箱" in page_content or "Check your inbox" in page_content or "verification" in page_content.lower():
                task.status = VerifyStatus.WAITING_CHATGPT_CODE
                logger.info(f"[Task {task.task_id}] 等待 ChatGPT 邮箱验证码...")

                # 从邮箱获取验证码
                code = email_manager.check_verification_code(task.email, max_retries=30, interval=3.0)
                if code:
                    logger.info(f"[Task {task.task_id}] 获取到验证码: {code}")
                    code_input = await self.page.wait_for_selector('input[type="text"], input[aria-label*="代码"], input[aria-label*="code"]', timeout=10000)
                    if code_input:
                        await self.human_type('input[type="text"], input[aria-label*="代码"], input[aria-label*="code"]', code)
                        await asyncio.sleep(self.human.random_delay(0.5, 0.2))

                        continue_btn = await self.page.query_selector('button:has-text("继续"), button:has-text("Continue")')
                        if continue_btn:
                            await continue_btn.click()
                            await asyncio.sleep(self.human.random_delay(3.0, 1.0))
                else:
                    task.error_message = "未能获取 ChatGPT 邮箱验证码"
                    task.error_type = "CHATGPT_CODE_TIMEOUT"
                    return False

            await self.take_screenshot(task, "05_after_login")

            # 【新增】检查并处理确认年龄页面 (about-you)
            current_url = self.page.url
            if "about-you" in current_url:
                if not await self.handle_about_you_page(task):
                    return False

            logger.info(f"[Task {task.task_id}] ChatGPT 登录/注册完成")
            return True

        except Exception as e:
            logger.error(f"[Task {task.task_id}] ChatGPT 注册失败: {e}")
            task.error_message = str(e)
            task.error_type = "CHATGPT_REGISTER_ERROR"
            await self.take_screenshot(task, "error_chatgpt")
            return False

    # ==================== SheerID 验证流程 ====================

    async def fill_sheerid_form(self, task: VerifyTask) -> bool:
        """
        填写 SheerID Veterans 验证表单

        字段顺序（来自 page-selectors.md MCP 探索）：
        1. Status (下拉) - 【新增】Military Veteran or Retiree
        2. Branch of service (下拉)
        3. First name (文本)
        4. Last name (文本)
        5. Date of birth (月下拉 + 日 + 年)
        6. Discharge date (月下拉 + 日 + 年)
        7. Email (文本)
        """
        task.status = VerifyStatus.FILLING_FORM
        logger.info(f"[Task {task.task_id}] 开始填写 SheerID 表单")

        try:
            # 等待表单加载
            await asyncio.sleep(self.human.random_delay(2.0, 0.5))
            await self.take_screenshot(task, "06_sheerid_form")

            # 【新增】1. Status - 选择 "Military Veteran or Retiree"
            logger.debug(f"[Task {task.task_id}] 选择 Status: Military Veteran or Retiree")
            status_selector = '[aria-label="Status"], [data-testid="status"], button:has-text("Status")'
            await self.select_dropdown(status_selector, "Military Veteran or Retiree")
            await asyncio.sleep(self.human.random_delay(0.5, 0.2))

            # 2. Branch of service
            logger.debug(f"[Task {task.task_id}] 选择 Branch: {task.branch}")
            branch_selector = '[aria-label="Branch of service"], [data-testid="branch"], button:has-text("Branch")'
            await self.select_dropdown(branch_selector, task.branch)
            await asyncio.sleep(self.human.random_delay(0.5, 0.2))

            # 3. First name
            logger.debug(f"[Task {task.task_id}] 输入 First name: {task.first_name}")
            await self.human_type('input[aria-label="First name"], input[name="firstName"], input[placeholder*="First"]', task.first_name)
            await asyncio.sleep(self.human.random_delay(0.3, 0.1))

            # 4. Last name
            logger.debug(f"[Task {task.task_id}] 输入 Last name: {task.last_name}")
            await self.human_type('input[aria-label="Last name"], input[name="lastName"], input[placeholder*="Last"]', task.last_name)
            await asyncio.sleep(self.human.random_delay(0.3, 0.1))

            # 5. Date of birth (根据 page-selectors.md 更新选择器)
            logger.debug(f"[Task {task.task_id}] 填写 DOB: {task.birth_date}")

            # DOB Month (下拉) - 使用更精确的选择器
            dob_month_selector = '[aria-label*="Date of birth"] button, [data-testid="dob-month"]'
            await self.select_dropdown(dob_month_selector, task.birth_date["month"])
            await asyncio.sleep(self.human.random_delay(0.3, 0.1))

            # DOB Day - 第1个 Day 输入框
            dob_day_inputs = await self.page.query_selector_all('input[aria-label="Day"], input[placeholder="Day"]')
            if dob_day_inputs and len(dob_day_inputs) > 0:
                await dob_day_inputs[0].click()
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Control+a")
                for char in task.birth_date["day"]:
                    await self.page.keyboard.type(char)
                    await asyncio.sleep(self.human.typing_delay())
            await asyncio.sleep(self.human.random_delay(0.2, 0.1))

            # DOB Year - 第1个 Year 输入框
            dob_year_inputs = await self.page.query_selector_all('input[aria-label="Year"], input[placeholder="Year"]')
            if dob_year_inputs and len(dob_year_inputs) > 0:
                await dob_year_inputs[0].click()
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Control+a")
                for char in task.birth_date["year"]:
                    await self.page.keyboard.type(char)
                    await asyncio.sleep(self.human.typing_delay())
            await asyncio.sleep(self.human.random_delay(0.3, 0.1))

            # 6. Discharge date
            logger.debug(f"[Task {task.task_id}] 填写 Discharge: {task.discharge_date}")

            # Discharge Month (下拉) - 使用更精确的选择器
            discharge_month_selector = '[aria-label*="Discharge date"] button, [data-testid="discharge-month"]'
            await self.select_dropdown(discharge_month_selector, task.discharge_date["month"])
            await asyncio.sleep(self.human.random_delay(0.3, 0.1))

            # Discharge Day - 第2个 Day 输入框
            if dob_day_inputs and len(dob_day_inputs) > 1:
                await dob_day_inputs[1].click()
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Control+a")
                for char in task.discharge_date["day"]:
                    await self.page.keyboard.type(char)
                    await asyncio.sleep(self.human.typing_delay())
            await asyncio.sleep(self.human.random_delay(0.2, 0.1))

            # Discharge Year - 第2个 Year 输入框
            if dob_year_inputs and len(dob_year_inputs) > 1:
                await dob_year_inputs[1].click()
                await asyncio.sleep(0.1)
                await self.page.keyboard.press("Control+a")
                for char in task.discharge_date["year"]:
                    await self.page.keyboard.type(char)
                    await asyncio.sleep(self.human.typing_delay())
            await asyncio.sleep(self.human.random_delay(0.3, 0.1))

            # 7. Email
            logger.debug(f"[Task {task.task_id}] 输入 Email: {task.email}")
            await self.human_type('input[aria-label*="Email"], input[type="email"], input[name="email"]', task.email)
            await asyncio.sleep(self.human.random_delay(0.5, 0.2))

            await self.take_screenshot(task, "07_form_filled")
            logger.info(f"[Task {task.task_id}] 表单填写完成")
            return True

        except Exception as e:
            logger.error(f"[Task {task.task_id}] 填写表单失败: {e}")
            task.error_message = str(e)
            task.error_type = "FORM_FILL_ERROR"
            await self.take_screenshot(task, "error_form")
            return False

    async def submit_and_wait_link(self, task: VerifyTask, email_manager) -> Tuple[bool, str]:
        """
        提交表单并等待验证链接

        返回：(成功?, 页面状态或错误信息)
        """
        task.status = VerifyStatus.SUBMITTING
        logger.info(f"[Task {task.task_id}] 提交表单")

        try:
            # 点击提交按钮
            submit_btn = await self.page.query_selector('button:has-text("Verify My Eligibility"), button:has-text("Verify"), button[type="submit"]')
            if submit_btn:
                is_disabled = await submit_btn.get_attribute("disabled")
                if is_disabled:
                    task.error_type = "SUBMIT_DISABLED"
                    return False, "提交按钮被禁用，表单可能未填完整"

                await submit_btn.click()
                await asyncio.sleep(self.human.random_delay(3.0, 1.0))

            await self.take_screenshot(task, "08_after_submit")

            # 检查提交后的页面状态
            page_content = await self.page.content()
            page_url = await self.page.url()

            # 检查各种状态
            status = await self.analyze_page_status(page_content, page_url)
            logger.info(f"[Task {task.task_id}] 页面状态: {status}")

            if status == "need_email_link":
                # 需要邮件验证链接
                task.status = VerifyStatus.WAITING_VERIFY_LINK
                logger.info(f"[Task {task.task_id}] 等待 SheerID 验证邮件链接...")

                verify_link = email_manager.check_verification_link(task.email, max_retries=30, interval=3.0)
                if verify_link:
                    logger.info(f"[Task {task.task_id}] 获取到验证链接")
                    task.status = VerifyStatus.CLICKING_LINK

                    # 点击链接
                    await self.page.goto(verify_link)
                    await asyncio.sleep(self.human.random_delay(3.0, 1.0))
                    await self.take_screenshot(task, "09_after_link")

                    # 再次检查状态
                    final_content = await self.page.content()
                    final_url = await self.page.url()
                    final_status = await self.analyze_page_status(final_content, final_url)

                    return final_status == "success", final_status
                else:
                    task.error_type = "VERIFY_LINK_TIMEOUT"
                    return False, "未能获取验证链接"

            elif status == "success":
                return True, status

            elif status == "already_verified":
                task.error_type = "ALREADY_VERIFIED"
                return False, "该信息已被验证过"

            elif status == "invalid_info":
                task.error_type = "INVALID_INFO"
                return False, "信息无法验证"

            else:
                task.error_type = status.upper()
                return False, status

        except Exception as e:
            logger.error(f"[Task {task.task_id}] 提交失败: {e}")
            task.error_type = "SUBMIT_ERROR"
            await self.take_screenshot(task, "error_submit")
            return False, str(e)

    async def analyze_page_status(self, content: str, url: str) -> str:
        """分析页面状态"""
        content_lower = content.lower()

        # 成功
        if any(kw in content_lower for kw in ["success", "verified", "congratulations", "veterans-claim"]):
            if "chatgpt.com" in url:
                return "success"

        # 需要邮件链接
        if any(kw in content_lower for kw in ["check your email", "sent you an email", "verify your email", "邮件"]):
            return "need_email_link"

        # 已验证过
        if any(kw in content_lower for kw in ["already verified", "previously verified", "已验证"]):
            return "already_verified"

        # 信息无效
        if any(kw in content_lower for kw in ["unable to verify", "could not verify", "invalid", "无法验证"]):
            return "invalid_info"

        # 需要登录
        if "please log in" in content_lower or "must be logged in" in content_lower:
            return "need_login"

        # 超过尝试次数
        if "too many attempts" in content_lower or "try again later" in content_lower:
            return "rate_limited"

        return "unknown"

    # ==================== 完整验证流程 ====================

    async def run_verification(self, task: VerifyTask, email_manager, veteran_data_manager=None) -> bool:
        """
        执行完整验证流程

        1. 初始化浏览器
        2. 创建临时邮箱
        3. 获取军人数据（如果提供了 veteran_data_manager）
        4. 注册/登录 ChatGPT
        5. 进入 SheerID 验证
        6. 填写表单
        7. 提交并等待验证链接
        8. 点击链接完成验证
        """
        try:
            # 1. 初始化浏览器
            if not await self.init_browser():
                task.status = VerifyStatus.FAILED
                task.error_message = "浏览器初始化失败"
                task.error_type = "BROWSER_INIT_ERROR"
                return False

            # 2. 创建临时邮箱
            task.status = VerifyStatus.CREATING_EMAIL
            jwt, email = email_manager.create_email()
            if not email:
                task.status = VerifyStatus.FAILED
                task.error_message = "创建邮箱失败"
                task.error_type = "EMAIL_CREATE_ERROR"
                return False
            task.email = email
            task.password = self.generate_password()
            logger.info(f"[Task {task.task_id}] 邮箱创建成功: {email}")

            # 3. 获取军人数据
            if veteran_data_manager and not task.first_name:
                vet_data = veteran_data_manager.get_random_veteran()
                if vet_data:
                    task.first_name = vet_data["first_name"]
                    task.last_name = vet_data["last_name"]
                    task.birth_date = vet_data["birth_date"]
                    task.branch = vet_data["branch"]
                    task.discharge_date = vet_data["discharge_date"]
                    logger.info(f"[Task {task.task_id}] 使用军人数据: {task.first_name} {task.last_name}, {task.branch}")

            # 4. 注册/登录 ChatGPT
            if not await self.register_chatgpt(task, email_manager):
                task.status = VerifyStatus.FAILED
                return False

            # 5. 进入 SheerID 验证
            task.status = VerifyStatus.OPENING_SHEERID
            current_url = await self.page.url()

            # 检查是否已经在 SheerID 页面或需要手动导航
            if "sheerid" not in current_url.lower():
                # 可能需要点击按钮进入验证
                verify_btn = await self.page.query_selector('button:has-text("Verify"), a:has-text("Verify"), button:has-text("验证")')
                if verify_btn:
                    await verify_btn.click()
                    await asyncio.sleep(self.human.random_delay(3.0, 1.0))
                else:
                    # 直接导航到 SheerID
                    await self.page.goto(self.SHEERID_URL)
                    await asyncio.sleep(self.human.random_delay(3.0, 1.0))

            # 6. 填写表单
            if not await self.fill_sheerid_form(task):
                task.status = VerifyStatus.FAILED
                return False

            # 7. 提交并等待验证
            task.status = VerifyStatus.CHECKING_RESULT
            success, result = await self.submit_and_wait_link(task, email_manager)

            if success:
                task.status = VerifyStatus.SUCCESS
                task.completed_at = datetime.now()
                logger.info(f"[Task {task.task_id}] 验证成功！")
                await self.take_screenshot(task, "10_success")
                return True
            else:
                task.status = VerifyStatus.FAILED
                task.error_message = result
                logger.warning(f"[Task {task.task_id}] 验证失败: {result}")
                await self.take_screenshot(task, "10_failed")
                return False

        except Exception as e:
            logger.error(f"[Task {task.task_id}] 验证流程异常: {e}")
            task.status = VerifyStatus.FAILED
            task.error_message = str(e)
            task.error_type = "UNEXPECTED_ERROR"
            await self.take_screenshot(task, "error_unexpected")
            return False

        finally:
            await self.close_browser()

    @staticmethod
    def generate_password() -> str:
        """生成随机密码（符合 OpenAI 要求：12+ 字符）"""
        import string
        chars = string.ascii_letters + string.digits + "!@#$%"
        password = ''.join(random.choices(chars, k=16))
        return password


# ==================== 测试 ====================

async def test_worker():
    """测试浏览器工作器"""
    from veteran_data import VeteranDataManager

    logging.basicConfig(level=logging.INFO)

    # 初始化数据管理器
    data_manager = VeteranDataManager()
    vet_data = data_manager.get_random_veteran()

    if vet_data:
        print(f"\n测试数据:")
        print(f"  姓名: {vet_data['first_name']} {vet_data['last_name']}")
        print(f"  生日: {vet_data['birth_date']}")
        print(f"  军种: {vet_data['branch']}")
        print(f"  退伍: {vet_data['discharge_date']}")

    task = VerifyTask(
        task_id="test-001",
        first_name=vet_data["first_name"] if vet_data else "John",
        last_name=vet_data["last_name"] if vet_data else "Smith",
        branch=vet_data["branch"] if vet_data else "Army",
        birth_date=vet_data["birth_date"] if vet_data else {"month": "March", "day": "15", "year": "1985"},
        discharge_date=vet_data["discharge_date"] if vet_data else {"month": "August", "day": "20", "year": "2024"},
    )

    worker = BrowserWorker(headless=False, screenshot_dir="screenshots")
    print(f"\nTask: {task}")

    # 测试时只初始化浏览器并打开页面
    if await worker.init_browser():
        await worker.page.goto(BrowserWorker.VETERANS_CLAIM_URL)
        print("\n浏览器已打开 Veterans Claim 页面，可手动测试")
        input("按 Enter 关闭浏览器...")
        await worker.close_browser()


if __name__ == "__main__":
    asyncio.run(test_worker())
