"""
Veterans Verify - 表单填写 + 验证自动化

流程：
1. 打开 veterans-claim 页面
2. 点击"验证资格条件"进入 SheerID
3. 填写表单（消耗一条军人数据）
4. 提交并等待结果
5. 如果需要邮件验证 → 登录邮箱 → 点击链接
6. 检查最终结果
7. 失败则换下一条数据重试

一个账号可以多次尝试，直到成功
"""
import sys
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Tuple

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
from automation.config import (
    VETERANS_CLAIM_URL,
    EMAIL_ADMIN_URL,
    SHEERID_FIELDS,
    ERROR_TYPES,
    PAGE_IDENTIFIERS,
    generate_discharge_date,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VeteransVerifier:
    """Veterans 验证自动化"""

    def __init__(self, account_email: str):
        """
        初始化验证器

        Args:
            account_email: ChatGPT 账号邮箱（同时也是临时邮箱地址）
        """
        self.account_email = account_email
        self.account = get_account_by_email(account_email)
        if not self.account:
            raise ValueError(f"账号不存在: {account_email}")

        self.current_veteran = None
        self.current_verification_id = None
        self.discharge_date = None

    def get_next_veteran(self, branch: str = None) -> Optional[Dict]:
        """获取下一条可用的军人数据"""
        veteran = get_available_veteran(branch)
        if not veteran:
            logger.error("没有可用的军人数据了！")
            return None

        self.current_veteran = veteran
        self.discharge_date = generate_discharge_date()

        logger.info(f"获取军人数据: {veteran['first_name']} {veteran['last_name']} ({veteran['branch']})")
        return veteran

    def create_verification_record(self) -> int:
        """创建验证记录"""
        if not self.current_veteran or not self.discharge_date:
            raise ValueError("没有当前军人数据")

        verification_id = create_verification(
            account_id=self.account['id'],
            veteran_id=self.current_veteran['id'],
            discharge_month=self.discharge_date['month'],
            discharge_day=self.discharge_date['day'],
            discharge_year=self.discharge_date['year']
        )
        self.current_verification_id = verification_id
        logger.info(f"创建验证记录 #{verification_id}")
        return verification_id

    def mark_current_veteran_used(self, reason: str):
        """标记当前军人数据为已使用"""
        if self.current_veteran:
            mark_veteran_used(
                self.current_veteran['id'],
                f"{self.account_email} - {reason}"
            )
            logger.info(f"标记已使用: {self.current_veteran['id']} - {reason}")

    def update_verification_status(self, status: str, error_type: str = None, error_message: str = None):
        """更新验证状态"""
        if self.current_verification_id:
            update_verification(
                self.current_verification_id,
                status=status,
                error_type=error_type,
                error_message=error_message
            )

    def get_form_data(self) -> Dict:
        """获取表单填写数据"""
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

    def run_single_attempt(self) -> Tuple[bool, str]:
        """
        执行单次验证尝试

        Returns:
            (success, message)
        """
        # 1. 获取军人数据
        if not self.get_next_veteran():
            return False, "没有可用的军人数据"

        # 2. 创建验证记录
        self.create_verification_record()
        self.update_verification_status("in_progress")

        # 3. 返回表单数据（实际填写由外部 Chrome MCP 执行）
        form_data = self.get_form_data()
        logger.info(f"表单数据准备完成: {form_data['first_name']} {form_data['last_name']}")

        return True, "数据准备完成，等待表单填写"

    def handle_result(self, result_type: str, message: str = ""):
        """
        处理验证结果

        Args:
            result_type: 结果类型（success, verification_limit, not_approved, check_email, etc.）
            message: 额外信息
        """
        if result_type == "success":
            self.update_verification_status("success")
            update_account(self.account_email, status="verified")
            logger.info(f"验证成功！账号 {self.account_email} 已获得 Plus")

        elif result_type == "verification_limit":
            self.mark_current_veteran_used("Verification Limit Exceeded")
            self.update_verification_status("failed", "VERIFICATION_LIMIT_EXCEEDED", message)
            logger.warning(f"军人数据已被使用: {self.current_veteran['id']}")

        elif result_type == "not_approved":
            self.mark_current_veteran_used("Not approved")
            self.update_verification_status("failed", "NOT_APPROVED", message)
            logger.warning(f"验证被拒绝: {self.current_veteran['id']}")

        elif result_type == "check_email":
            self.update_verification_status("pending_email")
            logger.info("等待邮件验证...")

        elif result_type == "please_login":
            self.update_verification_status("failed", "PLEASE_LOGIN", "需要重新登录")
            logger.error("需要登录 ChatGPT")

        else:
            self.update_verification_status("failed", "UNKNOWN_ERROR", message)
            logger.error(f"未知错误: {message}")


def get_stats():
    """获取当前统计"""
    stats = get_veterans_stats()
    return {
        "total": stats['total'],
        "used": stats['used'],
        "available": stats['available'],
        "by_branch": stats['by_branch']
    }


# === Chrome MCP 辅助函数 ===

def js_fill_sheerid_form(form_data: Dict) -> str:
    """
    生成填写 SheerID 表单的 JavaScript 代码

    用于 Chrome MCP evaluate_script
    """
    return f'''
() => {{
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

    // 填写文本字段
    fillInput('sid-first-name', '{form_data["first_name"]}');
    fillInput('sid-last-name', '{form_data["last_name"]}');
    fillInput('sid-birthdate-day', '{form_data["birth_day"]}');
    fillInput('sid-birthdate-year', '{form_data["birth_year"]}');
    fillInput('sid-discharge-date-day', '{form_data["discharge_day"]}');
    fillInput('sid-discharge-date-year', '{form_data["discharge_year"]}');
    fillInput('sid-email', '{form_data["email"]}');

    return {{
        firstName: document.getElementById('sid-first-name')?.value,
        lastName: document.getElementById('sid-last-name')?.value,
        email: document.getElementById('sid-email')?.value
    }};
}}
'''


def js_select_dropdown(field_id: str, value: str) -> str:
    """
    生成选择下拉框的 JavaScript 代码

    用于 Chrome MCP evaluate_script
    """
    return f'''
() => {{
    const input = document.getElementById('{field_id}');
    if (!input) return 'Input not found: {field_id}';

    input.click();
    input.focus();

    return new Promise(resolve => {{
        setTimeout(() => {{
            const options = document.querySelectorAll('[role="option"]');
            for (const opt of options) {{
                if (opt.textContent.trim() === '{value}' || opt.textContent.includes('{value}')) {{
                    opt.click();
                    resolve('Selected: ' + opt.textContent);
                    return;
                }}
            }}
            const texts = [];
            options.forEach(opt => texts.push(opt.textContent.trim()));
            resolve('Not found. Options: ' + texts.join(' | '));
        }}, 300);
    }});
}}
'''


def js_detect_page_state() -> str:
    """
    生成检测当前页面状态的 JavaScript 代码
    """
    return '''
() => {
    const url = window.location.href;
    const bodyText = document.body?.innerText || '';

    // 检测各种状态
    if (bodyText.includes('Verification Limit Exceeded')) {
        return { state: 'verification_limit', url };
    }
    if (bodyText.includes('Not approved')) {
        return { state: 'not_approved', url };
    }
    if (bodyText.includes('Check your email')) {
        return { state: 'check_email', url };
    }
    if (bodyText.includes('Please log in')) {
        return { state: 'please_login', url };
    }
    if (bodyText.includes('Verify My Eligibility')) {
        return { state: 'sheerid_form', url };
    }
    if (bodyText.includes('验证资格条件')) {
        return { state: 'veterans_claim_logged_in', url };
    }
    if (bodyText.includes('登录') && url.includes('veterans-claim')) {
        return { state: 'veterans_claim_not_logged_in', url };
    }
    if (url.includes('chatgpt.com') && !url.includes('veterans-claim')) {
        return { state: 'chatgpt_home', url };
    }

    return { state: 'unknown', url, text: bodyText.substring(0, 200) };
}
'''


def js_find_sheerid_verify_link() -> str:
    """
    在邮件页面查找 SheerID 验证链接
    """
    return '''
() => {
    // 查找包含 emailToken 的链接
    const links = document.querySelectorAll('a');
    for (const link of links) {
        const href = link.href || '';
        if (href.includes('sheerid.com') && href.includes('emailToken')) {
            return { found: true, url: href, text: link.textContent };
        }
        if (link.textContent.includes('Finish Verifying')) {
            return { found: true, url: href, text: link.textContent };
        }
    }
    return { found: false };
}
'''


if __name__ == "__main__":
    # 测试
    stats = get_stats()
    print(f"可用军人数据: {stats['available']}")

    # 示例用法
    # verifier = VeteransVerifier("test@009025.xyz")
    # success, msg = verifier.run_single_attempt()
    # print(f"Result: {success}, {msg}")
