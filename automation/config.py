"""
自动化配置
"""
import os
from datetime import datetime, timedelta
import random

# URLs
VETERANS_CLAIM_URL = "https://chatgpt.com/veterans-claim"
EMAIL_ADMIN_URL = "https://one.009025.xyz/admin"
EMAIL_LOGIN_URL = "https://one.009025.xyz/"

# 邮箱服务配置
EMAIL_WORKER_URL = os.getenv("EMAIL_WORKER_URL", "https://apimail.mjj.gs")
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "009025.xyz")

# SheerID 表单字段 ID
SHEERID_FIELDS = {
    "status": "sid-military-status",
    "branch": "sid-branch-of-service",
    "first_name": "sid-first-name",
    "last_name": "sid-last-name",
    "birth_month": "sid-birthdate__month",
    "birth_day": "sid-birthdate-day",
    "birth_year": "sid-birthdate-year",
    "discharge_month": "sid-discharge-date__month",
    "discharge_day": "sid-discharge-date-day",
    "discharge_year": "sid-discharge-date-year",
    "email": "sid-email",
}

# 错误类型枚举
ERROR_TYPES = {
    "VERIFICATION_LIMIT_EXCEEDED": "军人数据已被验证过",
    "NOT_APPROVED": "邮件验证后被拒绝",
    "PLEASE_LOGIN": "需要登录 ChatGPT",
    "CHECK_EMAIL": "等待邮件验证",
    "INVALID_DISCHARGE_DATE": "退伍日期无效",
    "FORM_SUBMIT_ERROR": "表单提交失败",
    "EMAIL_TIMEOUT": "邮件等待超时",
    "NETWORK_ERROR": "网络错误",
    "UNKNOWN_ERROR": "未知错误",
}

# 页面标识
PAGE_IDENTIFIERS = {
    "veterans_claim": "veterans-claim",
    "login_or_create": "log-in-or-create-account",
    "create_password": "create-account/password",
    "email_verification": "email-verification",
    "about_you": "about-you",
    "sheerid_form": "services.sheerid.com/verify",
    "check_email": "Check your email",
    "verification_limit": "Verification Limit Exceeded",
    "not_approved": "Not approved",
    "please_login": "Please log in",
}


def generate_discharge_date():
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


def generate_password(length=16):
    """生成随机密码"""
    import string
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))
