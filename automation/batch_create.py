"""
Veterans Verify - 批量创建账号自动化

流程：
1. 创建临时邮箱
2. 打开 veterans-claim
3. 注册 ChatGPT 账号
4. 输入验证码
5. 保存账号信息

持久化保存：
- 邮箱地址（用于登录邮箱前端）
- ChatGPT 密码
- 账号状态
"""
import sys
import time
import random
import string
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Tuple

sys.path.insert(0, '.')
from database import (
    create_account,
    get_account_by_email,
    update_account,
    get_accounts_stats,
)
from automation.config import (
    VETERANS_CLAIM_URL,
    EMAIL_WORKER_URL,
    EMAIL_DOMAIN,
    generate_password,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AccountCreator:
    """账号创建器"""

    def __init__(self):
        self.current_email = None
        self.current_password = None
        self.current_jwt = None

    def create_temp_email(self) -> Optional[Dict]:
        """
        创建临时邮箱

        Returns:
            {
                "email": "xxx@009025.xyz",
                "jwt": "eyJ...",  # 用于 API 查询邮件
            }
        """
        try:
            # 生成随机邮箱前缀
            prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
            email = f"{prefix}@{EMAIL_DOMAIN}"

            # 调用 API 创建邮箱
            url = f"{EMAIL_WORKER_URL}/api/new_address"
            payload = {"name": prefix}
            headers = {"Content-Type": "application/json"}

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                jwt = data.get('jwt', '')
                address = data.get('address', email)

                self.current_email = address
                self.current_jwt = jwt

                logger.info(f"创建邮箱成功: {address}")
                return {
                    "email": address,
                    "jwt": jwt,
                }
            else:
                logger.error(f"创建邮箱失败: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"创建邮箱异常: {e}")
            return None

    def generate_chatgpt_password(self) -> str:
        """生成 ChatGPT 密码（至少12位）"""
        self.current_password = generate_password(16)
        return self.current_password

    def save_account(self, **kwargs) -> int:
        """
        保存账号到数据库

        Args:
            **kwargs: 额外的账号信息

        Returns:
            account_id
        """
        if not self.current_email:
            raise ValueError("没有当前邮箱")

        # 检查是否已存在
        existing = get_account_by_email(self.current_email)
        if existing:
            logger.warning(f"账号已存在: {self.current_email}")
            return existing['id']

        account_id = create_account(
            email=self.current_email,
            password=self.current_password or "",
            jwt=self.current_jwt or "",
            **kwargs
        )
        logger.info(f"保存账号 #{account_id}: {self.current_email}")
        return account_id

    def get_verification_code(self, timeout: int = 120) -> Optional[str]:
        """
        从临时邮箱获取验证码

        Args:
            timeout: 超时时间（秒）

        Returns:
            6位验证码 或 None
        """
        if not self.current_jwt:
            logger.error("没有 JWT，无法查询邮件")
            return None

        import re
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                url = f"{EMAIL_WORKER_URL}/api/mail"
                headers = {
                    "Authorization": f"Bearer {self.current_jwt}",
                    "Content-Type": "application/json"
                }

                response = requests.get(url, headers=headers, timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    mails = data.get('data', [])

                    for mail in mails:
                        subject = mail.get('subject', '')
                        # 匹配验证码
                        patterns = [
                            r'代码为\s*([A-Z0-9]{6})',
                            r'code\s+is\s+([A-Z0-9]{6})',
                            r'([A-Z0-9]{6})',
                        ]
                        for pattern in patterns:
                            match = re.search(pattern, subject, re.IGNORECASE)
                            if match:
                                code = match.group(1)
                                logger.info(f"获取验证码: {code}")
                                return code

                logger.info(f"等待验证码... ({int(time.time() - start_time)}s)")
                time.sleep(5)

            except Exception as e:
                logger.error(f"查询邮件异常: {e}")
                time.sleep(5)

        logger.error(f"验证码超时 ({timeout}s)")
        return None


def create_single_account() -> Optional[Dict]:
    """
    创建单个账号

    Returns:
        {
            "email": "xxx@009025.xyz",
            "password": "xxx",
            "jwt": "xxx",
            "account_id": 123
        }
    """
    creator = AccountCreator()

    # 1. 创建临时邮箱
    email_info = creator.create_temp_email()
    if not email_info:
        return None

    # 2. 生成密码
    password = creator.generate_chatgpt_password()

    # 3. 保存账号
    account_id = creator.save_account(
        note=f"Created at {datetime.now().isoformat()}"
    )

    return {
        "email": email_info['email'],
        "password": password,
        "jwt": email_info.get('jwt', ''),
        "account_id": account_id
    }


def get_stats():
    """获取账号统计"""
    return get_accounts_stats()


# === Chrome MCP 辅助函数 ===

def js_fill_email(email: str) -> str:
    """填写邮箱的 JS"""
    return f'''
() => {{
    const input = document.querySelector('input[type="email"]') ||
                  document.querySelector('input[name="email"]') ||
                  document.querySelector('input[autocomplete="email"]');
    if (input) {{
        input.value = '{email}';
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return 'Email filled: ' + input.value;
    }}
    return 'Email input not found';
}}
'''


def js_fill_password(password: str) -> str:
    """填写密码的 JS"""
    return f'''
() => {{
    const input = document.querySelector('input[type="password"]');
    if (input) {{
        input.value = '{password}';
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return 'Password filled';
    }}
    return 'Password input not found';
}}
'''


def js_fill_verification_code(code: str) -> str:
    """填写验证码的 JS"""
    return f'''
() => {{
    const input = document.querySelector('input[name="code"]') ||
                  document.querySelector('input[autocomplete="one-time-code"]');
    if (input) {{
        input.value = '{code}';
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return 'Code filled: ' + input.value;
    }}
    return 'Code input not found';
}}
'''


def js_click_continue() -> str:
    """点击继续按钮的 JS"""
    return '''
() => {
    const btn = document.querySelector('button[type="submit"]') ||
                document.querySelector('button:has-text("继续")') ||
                document.querySelector('button:has-text("Continue")');
    if (btn && !btn.disabled) {
        btn.click();
        return 'Clicked continue';
    }
    return 'Continue button not found or disabled';
}
'''


def js_detect_registration_page() -> str:
    """检测注册页面状态的 JS"""
    return '''
() => {
    const url = window.location.href;
    const bodyText = document.body?.innerText || '';

    if (url.includes('log-in-or-create-account')) {
        return { state: 'login_or_create', url };
    }
    if (url.includes('create-account/password')) {
        return { state: 'create_password', url };
    }
    if (url.includes('email-verification')) {
        return { state: 'email_verification', url };
    }
    if (url.includes('about-you')) {
        return { state: 'about_you', url };
    }
    if (url.includes('veterans-claim')) {
        if (bodyText.includes('验证资格条件')) {
            return { state: 'logged_in', url };
        }
        return { state: 'veterans_claim', url };
    }
    if (url.includes('platform.openai.com')) {
        return { state: 'openai_platform', url };
    }

    return { state: 'unknown', url };
}
'''


if __name__ == "__main__":
    # 测试创建账号
    print("测试创建账号...")
    result = create_single_account()
    if result:
        print(f"成功: {result['email']}")
        print(f"密码: {result['password']}")
    else:
        print("失败")
