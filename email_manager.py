"""
Veterans Verify - 邮箱管理
复用自 test_band_gemini_mail 项目

支持：
1. 创建临时邮箱
2. 提取 OpenAI/ChatGPT 验证码
3. 提取 SheerID 验证链接
"""
import re
import time
import random
import string
from typing import Optional, Tuple, List
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import unquote

import requests
import logging

logger = logging.getLogger(__name__)


class EmailManager:
    """邮箱管理器"""

    def __init__(self, worker_domain: str, email_domain: str, admin_password: str):
        self.worker_domain = worker_domain
        self.email_domain = email_domain
        self.admin_password = admin_password

    @staticmethod
    def generate_random_name() -> str:
        """生成随机邮箱名称"""
        letters1 = ''.join(random.choices(string.ascii_lowercase, k=4))
        numbers = ''.join(random.choices(string.digits, k=2))
        letters2 = ''.join(random.choices(string.ascii_lowercase, k=3))
        return letters1 + numbers + letters2

    def create_email(self, username: str = "") -> Tuple[Optional[str], Optional[str]]:
        """创建邮箱，返回 (jwt, email_address)"""
        try:
            name = username if username else self.generate_random_name()

            res = requests.post(
                f"https://{self.worker_domain}/admin/new_address",
                json={
                    "enablePrefix": True,
                    "name": name,
                    "domain": self.email_domain,
                },
                headers={
                    'x-admin-auth': self.admin_password,
                    "Content-Type": "application/json"
                },
                timeout=30
            )

            if res.status_code == 200:
                data = res.json()
                return data.get('jwt'), data.get('address')
            else:
                logger.error(f"创建邮箱失败: HTTP {res.status_code}")
                return None, None
        except Exception as e:
            logger.error(f"创建邮箱出错: {e}")
            return None, None

    def _get_recent_emails(self, email: str, limit: int = 10) -> List[dict]:
        """获取最近的邮件列表"""
        try:
            api_url = f"https://{self.worker_domain}/admin/mails"
            res = requests.get(
                api_url,
                params={"limit": limit, "offset": 0, "address": email},
                headers={
                    "x-admin-auth": self.admin_password,
                    "Content-Type": "application/json"
                },
                timeout=30
            )

            if res.status_code == 200:
                data = res.json()
                return data.get('results') or []
            return []
        except Exception as e:
            logger.error(f"获取邮件列表失败: {e}")
            return []

    def _is_recent_email(self, raw_content: str, max_age_minutes: int = 30) -> bool:
        """检查邮件是否是最近的"""
        try:
            received_match = re.search(r'Received:.*?;\s*(.*?)\r\n', raw_content, re.DOTALL)
            if received_match:
                date_str = received_match.group(1).strip()
                email_time = parsedate_to_datetime(date_str)
                current_time = datetime.now(timezone.utc)
                return (current_time - email_time) <= timedelta(minutes=max_age_minutes)
        except Exception as e:
            logger.warning(f"解析邮件时间失败: {e}")
        return True  # 如果无法解析时间，默认为最近的

    def _clean_email_content(self, raw_content: str) -> str:
        """清理邮件内容（处理 quoted-printable 编码等）"""
        content = raw_content.replace('=\r\n', '').replace('=\n', '')
        content = content.replace('=3D', '=')
        content = content.replace('=26', '&')
        content = content.replace('=3A', ':')
        content = content.replace('=2F', '/')
        return content

    def check_verification_code(self, email: str, max_retries: int = 20, interval: float = 3.0) -> Optional[str]:
        """
        检查验证码邮件（用于 ChatGPT/OpenAI 注册验证）

        ChatGPT 验证码格式：
        - Subject: "你的 ChatGPT 代码为 XXXXXX" 或 "Your ChatGPT code is XXXXXX"
        - Body: 也可能包含验证码
        """
        for attempt in range(max_retries):
            try:
                emails = self._get_recent_emails(email, limit=5)

                for email_data in emails:
                    raw_content = email_data.get('raw') or ''
                    if not raw_content:
                        continue

                    # 检查是否是最近的邮件
                    if not self._is_recent_email(raw_content):
                        logger.debug("忽略过期邮件")
                        continue

                    # 清理内容
                    cleaned_content = self._clean_email_content(raw_content)

                    # 【P0 修复】优先从 Subject 提取验证码
                    subject_patterns = [
                        # 中文格式：你的 ChatGPT 代码为 XXXXXX
                        r'Subject:.*?代码为\s*([A-Z0-9]{6})',
                        r'Subject:.*?验证码[：:\s]*([A-Z0-9]{6})',
                        # 英文格式：Your ChatGPT code is XXXXXX
                        r'Subject:.*?code\s+is\s+([A-Z0-9]{6})',
                        r'Subject:.*?code[：:\s]+([A-Z0-9]{6})',
                    ]
                    for pattern in subject_patterns:
                        match = re.search(pattern, raw_content, re.IGNORECASE | re.DOTALL)
                        if match:
                            code = match.group(1).upper()
                            if len(code) == 6 and code.isalnum():
                                logger.info(f"从 Subject 找到验证码: {code}")
                                return code

                    # OpenAI/ChatGPT 验证码提取模式（Body）
                    patterns = [
                        # OpenAI 常见格式
                        r'verification code[:\s]+([A-Z0-9]{6})',
                        r'code[:\s]+([A-Z0-9]{6})',
                        r'>([A-Z0-9]{6})<',
                        # 通用 6 位验证码
                        r'class=["\']?verification-code["\']?[^>]*>([A-Z0-9]{6})',
                        r'font-size:\s*\d+px[^>]*>([A-Z0-9]{6})<',
                        # 数字验证码
                        r'verification code[:\s]+(\d{6})',
                        r'>(\d{6})<',
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, cleaned_content, re.IGNORECASE | re.DOTALL)
                        if match:
                            code = match.group(1).upper()
                            if len(code) == 6 and code.isalnum():
                                logger.info(f"找到验证码: {code}")
                                return code

                    # 兜底：检查是否包含验证相关关键词
                    lowered = cleaned_content.lower()
                    keywords = ["verification", "verify", "code", "openai", "chatgpt"]
                    if any(kw in lowered for kw in keywords):
                        m = re.search(r'\b([A-Z0-9]{6})\b', cleaned_content, re.IGNORECASE)
                        if m:
                            code = m.group(1).upper()
                            if len(code) == 6 and code.isalnum():
                                logger.info(f"找到验证码(兜底): {code}")
                                return code

                logger.debug(f"等待验证码... ({attempt + 1}/{max_retries})")
                time.sleep(interval)

            except Exception as e:
                logger.error(f"检查验证码出错: {e}")
                time.sleep(interval)

        logger.warning("未能获取验证码")
        return None

    def check_verification_link(self, email: str, max_retries: int = 30, interval: float = 3.0) -> Optional[str]:
        """
        检查验证链接邮件（用于 SheerID 验证）

        SheerID 发送的邮件包含验证链接，格式如：
        - https://services.sheerid.com/verify/...
        - 或者 https://my.sheerid.com/...
        """
        for attempt in range(max_retries):
            try:
                emails = self._get_recent_emails(email, limit=10)

                for email_data in emails:
                    raw_content = email_data.get('raw') or ''
                    if not raw_content:
                        continue

                    # 检查是否是最近的邮件
                    if not self._is_recent_email(raw_content):
                        continue

                    # 检查发件人是否是 SheerID
                    from_match = re.search(r'From:.*?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', raw_content, re.IGNORECASE)
                    if from_match:
                        sender = from_match.group(1).lower()
                        if 'sheerid' not in sender and 'verify' not in sender:
                            # 不是 SheerID 的邮件，跳过
                            continue

                    # 清理内容
                    cleaned_content = self._clean_email_content(raw_content)

                    # SheerID 验证链接提取模式
                    link_patterns = [
                        # SheerID 验证链接
                        r'(https?://(?:services|my)\.sheerid\.com/verify/[^\s"\'<>]+)',
                        r'(https?://[^\s"\'<>]*sheerid[^\s"\'<>]*verify[^\s"\'<>]+)',
                        # 带 token 的链接
                        r'(https?://[^\s"\'<>]+verificationId=[^\s"\'<>]+)',
                        # href 属性中的链接
                        r'href=["\'](https?://[^\s"\'<>]*sheerid[^\s"\'<>]+)["\']',
                        r'href=3D["\'](https?://[^\s"\'<>]*sheerid[^\s"\'<>]+)["\']',
                    ]

                    for pattern in link_patterns:
                        matches = re.findall(pattern, cleaned_content, re.IGNORECASE)
                        for match in matches:
                            link = match if isinstance(match, str) else match[0]
                            # 解码 URL
                            link = unquote(link)
                            # 清理链接末尾的无效字符
                            link = re.sub(r'["\'>]+$', '', link)

                            # 验证链接格式
                            if 'sheerid' in link.lower() and ('verify' in link.lower() or 'verification' in link.lower()):
                                logger.info(f"找到验证链接: {link[:80]}...")
                                return link

                logger.debug(f"等待验证链接... ({attempt + 1}/{max_retries})")
                time.sleep(interval)

            except Exception as e:
                logger.error(f"检查验证链接出错: {e}")
                time.sleep(interval)

        logger.warning("未能获取验证链接")
        return None

    def get_all_links_from_email(self, email: str, sender_filter: str = None) -> List[str]:
        """
        获取邮件中的所有链接（用于调试）

        Args:
            email: 邮箱地址
            sender_filter: 可选的发件人过滤（如 'sheerid'）
        """
        links = []
        try:
            emails = self._get_recent_emails(email, limit=5)

            for email_data in emails:
                raw_content = email_data.get('raw') or ''
                if not raw_content:
                    continue

                # 发件人过滤
                if sender_filter:
                    from_match = re.search(r'From:.*?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', raw_content, re.IGNORECASE)
                    if from_match:
                        sender = from_match.group(1).lower()
                        if sender_filter.lower() not in sender:
                            continue

                cleaned_content = self._clean_email_content(raw_content)

                # 提取所有 https 链接
                found_links = re.findall(r'(https?://[^\s"\'<>]+)', cleaned_content)
                for link in found_links:
                    link = unquote(link)
                    link = re.sub(r'["\'>]+$', '', link)
                    if link not in links:
                        links.append(link)

        except Exception as e:
            logger.error(f"获取邮件链接出错: {e}")

        return links
