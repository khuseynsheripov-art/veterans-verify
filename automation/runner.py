"""
Veterans Verify - 自动化运行器

整合批量创建和表单验证两个流程

使用方式：
1. 配合 Chrome MCP 使用
2. 调用各个步骤函数
3. 根据页面状态决定下一步操作
"""
import sys
import logging
from typing import Optional, Dict, List
from datetime import datetime

sys.path.insert(0, '.')
from database import (
    get_account_by_email,
    get_accounts,
    get_available_veteran,
    mark_veteran_used,
    update_account,
    get_veterans_stats,
    get_accounts_stats,
)
from automation.batch_create import AccountCreator, create_single_account
from automation.verify_form import VeteransVerifier, get_stats as get_veteran_stats
from automation.config import (
    VETERANS_CLAIM_URL,
    EMAIL_ADMIN_URL,
    generate_discharge_date,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AutomationRunner:
    """自动化运行器"""

    def __init__(self):
        self.current_account = None
        self.current_verifier = None
        self.attempt_count = 0
        self.max_attempts = 50  # 单账号最大尝试次数

    def set_account(self, email: str) -> bool:
        """设置当前操作的账号"""
        account = get_account_by_email(email)
        if not account:
            logger.error(f"账号不存在: {email}")
            return False

        self.current_account = account
        self.current_verifier = VeteransVerifier(email)
        self.attempt_count = 0
        logger.info(f"设置账号: {email}")
        return True

    def prepare_next_attempt(self) -> Optional[Dict]:
        """
        准备下一次验证尝试

        Returns:
            表单数据 或 None
        """
        if not self.current_verifier:
            logger.error("没有设置账号")
            return None

        if self.attempt_count >= self.max_attempts:
            logger.error(f"超过最大尝试次数 ({self.max_attempts})")
            return None

        # 获取军人数据
        veteran = self.current_verifier.get_next_veteran()
        if not veteran:
            return None

        # 创建验证记录
        self.current_verifier.create_verification_record()

        # 获取表单数据
        form_data = self.current_verifier.get_form_data()
        self.attempt_count += 1

        logger.info(f"准备第 {self.attempt_count} 次尝试: {veteran['first_name']} {veteran['last_name']}")
        return form_data

    def handle_verification_result(self, result_type: str, message: str = "") -> str:
        """
        处理验证结果

        Args:
            result_type: verification_limit, not_approved, check_email, success, please_login, unknown

        Returns:
            下一步操作建议
        """
        if not self.current_verifier:
            return "error: no verifier"

        self.current_verifier.handle_result(result_type, message)

        if result_type == "success":
            return "done: verification successful"

        elif result_type == "verification_limit":
            # 数据已被用，换下一个
            return "retry: get next veteran data"

        elif result_type == "not_approved":
            # 邮件验证后被拒，换下一个
            return "retry: get next veteran data"

        elif result_type == "check_email":
            # 需要邮件验证
            return "action: check email and click verify link"

        elif result_type == "please_login":
            # 需要重新登录
            return "action: login to chatgpt first"

        else:
            return "retry: unknown error, try next"

    def get_email_login_info(self) -> Dict:
        """获取邮箱登录信息"""
        if not self.current_account:
            return {}

        return {
            "email": self.current_account['email'],
            "login_url": EMAIL_ADMIN_URL,
            "note": "在邮件列表中找到 SheerID 的邮件，点击 Finish Verifying 链接"
        }


# === 快捷函数 ===

def get_system_stats() -> Dict:
    """获取系统统计"""
    v_stats = get_veterans_stats()
    a_stats = get_accounts_stats()

    return {
        "veterans": {
            "total": v_stats['total'],
            "used": v_stats['used'],
            "available": v_stats['available'],
        },
        "accounts": a_stats,
    }


def list_available_accounts() -> List[Dict]:
    """列出可用账号（未验证的）"""
    accounts = get_accounts(status='registering', limit=50)
    accounts += get_accounts(status='pending', limit=50)
    return accounts


def quick_verify_setup(email: str) -> Dict:
    """
    快速设置验证

    Returns:
        {
            "account": {...},
            "form_data": {...},
            "discharge_date": {...},
        }
    """
    runner = AutomationRunner()
    if not runner.set_account(email):
        return {"error": f"账号不存在: {email}"}

    form_data = runner.prepare_next_attempt()
    if not form_data:
        return {"error": "没有可用的军人数据"}

    return {
        "account": {
            "email": email,
            "id": runner.current_account['id'],
        },
        "form_data": form_data,
        "veteran_id": runner.current_verifier.current_veteran['id'],
        "instructions": [
            f"1. 打开 {VETERANS_CLAIM_URL}",
            "2. 点击'验证资格条件'",
            "3. 填写表单（使用上面的 form_data）",
            "4. 提交并观察结果",
            "5. 如果需要邮件验证，去邮箱点击链接",
            "6. 如果失败，调用 quick_verify_setup 获取下一条数据",
        ]
    }


# === Chrome MCP 完整操作序列 ===

def generate_fill_form_script(form_data: Dict) -> List[Dict]:
    """
    生成填写表单的完整脚本序列

    Returns:
        [
            {"action": "select_dropdown", "field": "status", "value": "..."},
            {"action": "select_dropdown", "field": "branch", "value": "..."},
            {"action": "fill_text", "field": "first_name", "value": "..."},
            ...
        ]
    """
    return [
        # 1. 选择 Status
        {
            "action": "select_dropdown",
            "field_id": "sid-military-status",
            "value": form_data['status'],
            "js": f'''
() => {{
    const input = document.getElementById('sid-military-status');
    input.click();
    return new Promise(resolve => {{
        setTimeout(() => {{
            const options = document.querySelectorAll('[role="option"]');
            for (const opt of options) {{
                if (opt.textContent.includes('Military Veteran')) {{
                    opt.click();
                    resolve('Selected: Military Veteran or Retiree');
                    return;
                }}
            }}
            resolve('Not found');
        }}, 300);
    }});
}}
'''
        },
        # 2. 选择 Branch
        {
            "action": "select_dropdown",
            "field_id": "sid-branch-of-service",
            "value": form_data['branch'],
            "js": f'''
() => {{
    const input = document.getElementById('sid-branch-of-service');
    input.click();
    return new Promise(resolve => {{
        setTimeout(() => {{
            const options = document.querySelectorAll('[role="option"]');
            for (const opt of options) {{
                if (opt.textContent.trim() === '{form_data["branch"]}') {{
                    opt.click();
                    resolve('Selected: {form_data["branch"]}');
                    return;
                }}
            }}
            resolve('Not found');
        }}, 300);
    }});
}}
'''
        },
        # 3. 选择出生月份
        {
            "action": "select_dropdown",
            "field_id": "sid-birthdate__month",
            "value": form_data['birth_month'],
            "js": f'''
() => {{
    const input = document.getElementById('sid-birthdate__month');
    input.click();
    return new Promise(resolve => {{
        setTimeout(() => {{
            const options = document.querySelectorAll('[role="option"]');
            for (const opt of options) {{
                if (opt.textContent.trim() === '{form_data["birth_month"]}') {{
                    opt.click();
                    resolve('Selected: {form_data["birth_month"]}');
                    return;
                }}
            }}
            resolve('Not found');
        }}, 300);
    }});
}}
'''
        },
        # 4. 选择退伍月份
        {
            "action": "select_dropdown",
            "field_id": "sid-discharge-date__month",
            "value": form_data['discharge_month'],
            "js": f'''
() => {{
    const input = document.getElementById('sid-discharge-date__month');
    input.click();
    return new Promise(resolve => {{
        setTimeout(() => {{
            const options = document.querySelectorAll('[role="option"]');
            for (const opt of options) {{
                if (opt.textContent.trim() === '{form_data["discharge_month"]}') {{
                    opt.click();
                    resolve('Selected: {form_data["discharge_month"]}');
                    return;
                }}
            }}
            resolve('Not found');
        }}, 300);
    }});
}}
'''
        },
        # 5. 填写文本字段
        {
            "action": "fill_text_fields",
            "js": f'''
() => {{
    function fill(id, val) {{
        const el = document.getElementById(id);
        if (el) {{
            el.value = val;
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
    }}
    fill('sid-first-name', '{form_data["first_name"]}');
    fill('sid-last-name', '{form_data["last_name"]}');
    fill('sid-birthdate-day', '{form_data["birth_day"]}');
    fill('sid-birthdate-year', '{form_data["birth_year"]}');
    fill('sid-discharge-date-day', '{form_data["discharge_day"]}');
    fill('sid-discharge-date-year', '{form_data["discharge_year"]}');
    fill('sid-email', '{form_data["email"]}');
    return 'Text fields filled';
}}
'''
        },
    ]


def generate_detect_result_script() -> str:
    """生成检测验证结果的脚本"""
    return '''
() => {
    const url = window.location.href;
    const text = document.body?.innerText || '';

    if (text.includes('Verification Limit Exceeded')) {
        return { result: 'verification_limit', message: 'Data already used' };
    }
    if (text.includes('Not approved')) {
        return { result: 'not_approved', message: 'Verification rejected' };
    }
    if (text.includes('Check your email')) {
        return { result: 'check_email', message: 'Need email verification' };
    }
    if (text.includes('Please log in')) {
        return { result: 'please_login', message: 'Need to login first' };
    }
    if (text.includes('Verifying your military status')) {
        return { result: 'verifying', message: 'Verification in progress' };
    }
    if (url.includes('chatgpt.com') && !url.includes('veterans-claim')) {
        // 可能验证成功了
        return { result: 'possible_success', message: 'Redirected to ChatGPT' };
    }

    return { result: 'unknown', url: url, text: text.substring(0, 500) };
}
'''


if __name__ == "__main__":
    # 打印统计
    stats = get_system_stats()
    print("=== Veterans Verify 系统统计 ===")
    print(f"军人数据: {stats['veterans']['available']} 可用 / {stats['veterans']['total']} 总计")
    print(f"账号: {stats['accounts']}")
