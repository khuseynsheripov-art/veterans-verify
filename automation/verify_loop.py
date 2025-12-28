"""
Veterans Verify - 验证循环自动化

核心逻辑：
1. 检测当前页面状态
2. 失败时点击 Try Again → 换数据 → 继续
3. 成功时记录并退出
4. 循环直到成功或无数据

使用方式：
    配合 Chrome MCP 使用，提供 JavaScript 脚本

页面状态检测：
    - success: 验证成功，获得 Plus
    - check_email: 需要邮件验证
    - not_approved: 失败，需要换数据
    - unable_to_verify: 失败，需要换数据
    - verification_limit: 数据已被用，需要换数据
    - please_login: 需要登录
    - sheerid_form: 在表单页面
    - veterans_claim: 在 veterans-claim 页面
"""
import sys
import time
import random
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime

sys.path.insert(0, '.')
from database import (
    get_available_veteran,
    mark_veteran_used,
    get_account_by_email,
    update_account,
    create_verification,
    update_verification,
    get_veterans_stats,
)
from automation.config import generate_discharge_date, SHEERID_FIELDS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== 页面状态检测 ====================

def js_detect_page_state() -> str:
    """
    检测当前页面状态的 JavaScript 代码

    用于 Chrome MCP evaluate_script
    """
    return '''
() => {
    const url = window.location.href;
    const text = document.body?.innerText || '';
    const textLower = text.toLowerCase();

    // === 成功状态 ===
    if (text.includes("You've been verified") || text.includes("You have been verified")) {
        return {
            state: "success",
            message: "Verification successful!",
            url: url
        };
    }

    // === 失败状态（需要换数据）===
    if (text.includes("Not approved")) {
        return {
            state: "not_approved",
            message: "Verification rejected",
            action: "click_try_again",
            url: url
        };
    }

    if (textLower.includes("unable to verify")) {
        return {
            state: "unable_to_verify",
            message: "Unable to verify at this time",
            action: "click_try_again",
            url: url
        };
    }

    if (text.includes("Verification Limit Exceeded")) {
        return {
            state: "verification_limit",
            message: "This veteran data already used",
            action: "click_try_again",
            url: url
        };
    }

    // === 需要操作 ===
    if (text.includes("Check your email")) {
        return {
            state: "check_email",
            message: "Need to click email verification link",
            action: "wait_for_email",
            url: url
        };
    }

    if (text.includes("Please log in")) {
        return {
            state: "please_login",
            message: "Need to login first",
            action: "login",
            url: url
        };
    }

    // === 页面状态 ===
    if (text.includes("Verify My Eligibility")) {
        return {
            state: "sheerid_form",
            message: "On SheerID form page",
            action: "fill_form",
            url: url
        };
    }

    if (text.includes("验证资格条件") || text.includes("Verify your eligibility")) {
        return {
            state: "veterans_claim_logged_in",
            message: "On veterans-claim page (logged in)",
            action: "click_verify_button",
            url: url
        };
    }

    if (url.includes("veterans-claim") && (text.includes("登录") || text.includes("Log in"))) {
        return {
            state: "veterans_claim_not_logged_in",
            message: "On veterans-claim page (not logged in)",
            action: "login",
            url: url
        };
    }

    if (url.includes("chatgpt.com") && !url.includes("veterans-claim")) {
        return {
            state: "chatgpt_home",
            message: "On ChatGPT home page",
            action: "navigate_to_veterans_claim",
            url: url
        };
    }

    return {
        state: "unknown",
        message: text.substring(0, 200),
        url: url
    };
}
'''


def js_click_try_again() -> str:
    """
    点击 Try Again 按钮
    """
    return '''
() => {
    const links = document.querySelectorAll('a');
    for (const link of links) {
        if (link.textContent.includes('Try Again')) {
            link.click();
            return { success: true, message: "Clicked Try Again" };
        }
    }

    const buttons = document.querySelectorAll('button');
    for (const btn of buttons) {
        if (btn.textContent.includes('Try Again')) {
            btn.click();
            return { success: true, message: "Clicked Try Again button" };
        }
    }

    return { success: false, message: "Try Again not found" };
}
'''


def js_click_verify_button() -> str:
    """
    点击"验证资格条件"按钮
    """
    return '''
() => {
    const buttons = document.querySelectorAll('button');
    for (const btn of buttons) {
        const text = btn.textContent || '';
        if (text.includes('验证资格条件') || text.includes('Verify your eligibility') || text.includes('Verify eligibility')) {
            btn.click();
            return { success: true, message: "Clicked verify button" };
        }
    }
    return { success: false, message: "Verify button not found" };
}
'''


def js_submit_form() -> str:
    """
    点击提交按钮
    """
    return '''
() => {
    const button = document.querySelector('button[type="submit"]');
    if (button) {
        if (button.disabled) {
            return { success: false, message: "Submit button is disabled" };
        }
        button.click();
        return { success: true, message: "Form submitted" };
    }

    const verifyBtn = Array.from(document.querySelectorAll('button')).find(
        b => b.textContent.includes('Verify My Eligibility')
    );
    if (verifyBtn) {
        if (verifyBtn.disabled) {
            return { success: false, message: "Verify button is disabled" };
        }
        verifyBtn.click();
        return { success: true, message: "Clicked Verify My Eligibility" };
    }

    return { success: false, message: "Submit button not found" };
}
'''


# ==================== 表单填写 ====================

def js_fill_form(form_data: Dict) -> str:
    """
    生成填写完整表单的 JavaScript

    包含：选择下拉框 + 填写文本框
    """
    return f'''
async () => {{
    const results = [];

    // 辅助函数：填写文本框
    function fillInput(id, value) {{
        const el = document.getElementById(id);
        if (el) {{
            el.value = value;
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return true;
        }}
        return false;
    }}

    // 辅助函数：选择下拉框
    async function selectDropdown(id, value) {{
        const input = document.getElementById(id);
        if (!input) return 'not found: ' + id;

        input.click();
        input.focus();

        return new Promise(resolve => {{
            setTimeout(() => {{
                const options = document.querySelectorAll('[role="option"]');
                for (const opt of options) {{
                    if (opt.textContent.trim() === value || opt.textContent.includes(value)) {{
                        opt.click();
                        resolve('selected: ' + value);
                        return;
                    }}
                }}
                resolve('not found in options: ' + value);
            }}, 300);
        }});
    }}

    // 1. 选择 Status
    results.push(await selectDropdown('sid-military-status', 'Military Veteran'));
    await new Promise(r => setTimeout(r, 200));

    // 2. 选择 Branch
    results.push(await selectDropdown('sid-branch-of-service', '{form_data["branch"]}'));
    await new Promise(r => setTimeout(r, 200));

    // 3. 选择出生月份
    results.push(await selectDropdown('sid-birthdate__month', '{form_data["birth_month"]}'));
    await new Promise(r => setTimeout(r, 200));

    // 4. 选择退伍月份
    results.push(await selectDropdown('sid-discharge-date__month', '{form_data["discharge_month"]}'));
    await new Promise(r => setTimeout(r, 200));

    // 5. 填写文本字段
    fillInput('sid-first-name', '{form_data["first_name"]}');
    fillInput('sid-last-name', '{form_data["last_name"]}');
    fillInput('sid-birthdate-day', '{form_data["birth_day"]}');
    fillInput('sid-birthdate-year', '{form_data["birth_year"]}');
    fillInput('sid-discharge-date-day', '{form_data["discharge_day"]}');
    fillInput('sid-discharge-date-year', '{form_data["discharge_year"]}');
    fillInput('sid-email', '{form_data["email"]}');

    results.push('text fields filled');

    return {{
        success: true,
        results: results,
        formData: {{
            firstName: document.getElementById('sid-first-name')?.value,
            lastName: document.getElementById('sid-last-name')?.value,
            email: document.getElementById('sid-email')?.value
        }}
    }};
}}
'''


# ==================== 验证循环控制器 ====================

class VerifyLoopController:
    """
    验证循环控制器

    管理验证状态和数据切换
    """

    # 需要换数据的状态
    NEED_NEXT_DATA = ['not_approved', 'unable_to_verify', 'verification_limit']

    # 需要等待的状态
    NEED_WAIT = ['check_email', 'verifying']

    # 成功状态
    SUCCESS = ['success']

    def __init__(self, account_email: str):
        self.account_email = account_email
        self.account = get_account_by_email(account_email)
        if not self.account:
            raise ValueError(f"账号不存在: {account_email}")

        self.current_veteran = None
        self.discharge_date = None
        self.attempt_count = 0
        self.max_attempts = 100
        self.consumed_veterans = []

    def get_next_veteran(self) -> Optional[Dict]:
        """获取下一条军人数据"""
        if self.attempt_count >= self.max_attempts:
            logger.error(f"超过最大尝试次数 ({self.max_attempts})")
            return None

        veteran = get_available_veteran()
        if not veteran:
            logger.error("没有可用的军人数据了")
            return None

        self.current_veteran = veteran
        self.discharge_date = generate_discharge_date()
        self.attempt_count += 1

        logger.info(f"[尝试 {self.attempt_count}] 使用数据: {veteran['first_name']} {veteran['last_name']} ({veteran['branch']})")
        return veteran

    def get_form_data(self) -> Dict:
        """获取当前表单数据"""
        if not self.current_veteran:
            raise ValueError("没有当前军人数据")

        return {
            "status": "Military Veteran or Retiree",
            "branch": self.current_veteran['branch'],
            "first_name": self.current_veteran['first_name'],
            "last_name": self.current_veteran['last_name'],
            "birth_month": self.current_veteran['birth_month'],
            "birth_day": self.current_veteran['birth_day'],
            "birth_year": self.current_veteran['birth_year'],
            "discharge_month": self.discharge_date['month'],
            "discharge_day": self.discharge_date['day'],
            "discharge_year": self.discharge_date['year'],
            "email": self.account_email,
        }

    def consume_current_veteran(self, reason: str):
        """消耗当前军人数据（标记为已使用）"""
        if self.current_veteran:
            veteran_id = self.current_veteran['id']
            mark_veteran_used(veteran_id, f"{self.account_email} - {reason}")
            self.consumed_veterans.append(veteran_id)
            logger.info(f"[消耗] {veteran_id}: {reason}")
            self.current_veteran = None

    def handle_state(self, state: str, message: str = "") -> Tuple[str, Optional[Dict]]:
        """
        处理页面状态

        Returns:
            (action, data)
            action: next_data | wait | success | fill_form | click_verify | login | unknown
            data: 表单数据或其他信息
        """
        if state in self.SUCCESS:
            # 成功
            update_account(self.account_email, status="verified")
            logger.info(f"验证成功！账号 {self.account_email} 已获得 Plus")
            return "success", {"message": "Verification successful!"}

        if state in self.NEED_NEXT_DATA:
            # 需要换数据
            self.consume_current_veteran(state)
            veteran = self.get_next_veteran()
            if not veteran:
                return "no_data", {"message": "No more veteran data available"}
            return "next_data", self.get_form_data()

        if state in self.NEED_WAIT:
            # 需要等待
            return "wait", {"message": message, "state": state}

        if state == "sheerid_form":
            # 在表单页面，需要填写
            if not self.current_veteran:
                veteran = self.get_next_veteran()
                if not veteran:
                    return "no_data", {"message": "No more veteran data available"}
            return "fill_form", self.get_form_data()

        if state == "veterans_claim_logged_in":
            return "click_verify", {"message": "Click verify button"}

        if state in ["please_login", "veterans_claim_not_logged_in"]:
            return "login", {"message": "Need to login first"}

        return "unknown", {"message": message, "state": state}

    def get_stats(self) -> Dict:
        """获取当前统计"""
        v_stats = get_veterans_stats()
        return {
            "attempt_count": self.attempt_count,
            "consumed_count": len(self.consumed_veterans),
            "available_veterans": v_stats['available'],
            "total_veterans": v_stats['total'],
        }


# ==================== Chrome MCP 操作序列生成 ====================

def generate_verify_loop_instructions(controller: VerifyLoopController) -> list:
    """
    生成完整验证循环的操作指令

    给 Chrome MCP 使用
    """
    instructions = []

    # 1. 检测页面状态
    instructions.append({
        "step": 1,
        "action": "evaluate_script",
        "description": "检测页面状态",
        "script": js_detect_page_state(),
    })

    # 2. 根据状态决定下一步
    instructions.append({
        "step": 2,
        "action": "conditional",
        "description": "根据状态执行操作",
        "conditions": {
            "success": "完成，记录成功",
            "not_approved|unable_to_verify|verification_limit": "点击 Try Again，然后换数据",
            "check_email": "等待邮件验证",
            "sheerid_form": "填写表单",
            "veterans_claim_logged_in": "点击验证按钮",
            "please_login": "需要登录",
        }
    })

    return instructions


def print_operation_guide(controller: VerifyLoopController):
    """
    打印 Chrome MCP 操作指南
    """
    print("\n" + "=" * 60)
    print("Veterans Verify - Chrome MCP 验证循环指南")
    print("=" * 60)

    print(f"\n账号: {controller.account_email}")
    stats = controller.get_stats()
    print(f"可用数据: {stats['available_veterans']} / {stats['total_veterans']}")

    print("\n--- 步骤 1: 检测页面状态 ---")
    print("使用 evaluate_script 执行：")
    print(js_detect_page_state())

    print("\n--- 步骤 2: 根据状态执行 ---")
    print("""
状态处理：
  success → 完成！记录成功
  not_approved / unable_to_verify / verification_limit → 执行步骤 3
  check_email → 等待邮件，然后点击链接
  sheerid_form → 执行步骤 4
  veterans_claim_logged_in → 点击验证按钮
  please_login → 需要先登录
""")

    print("\n--- 步骤 3: 点击 Try Again ---")
    print("使用 evaluate_script 执行：")
    print(js_click_try_again())

    print("\n--- 步骤 4: 填写表单 ---")
    if controller.current_veteran:
        form_data = controller.get_form_data()
        print(f"当前数据: {form_data['first_name']} {form_data['last_name']}")
        print("使用 evaluate_script 执行：")
        print(js_fill_form(form_data))
    else:
        print("调用 controller.get_next_veteran() 获取数据后填写")

    print("\n--- 步骤 5: 提交表单 ---")
    print("使用 evaluate_script 执行：")
    print(js_submit_form())

    print("\n" + "=" * 60)


if __name__ == "__main__":
    # 测试
    import sys

    email = sys.argv[1] if len(sys.argv) > 1 else "vethuxntarz@009025.xyz"

    try:
        controller = VerifyLoopController(email)
        print_operation_guide(controller)
    except Exception as e:
        print(f"错误: {e}")
