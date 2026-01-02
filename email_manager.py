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
        # 创建不使用系统代理的 session
        self._session = requests.Session()
        self._session.trust_env = False  # 绕过系统代理

        # 调试日志：打印配置信息（隐藏密码）
        pwd_masked = '*' * min(len(admin_password), 8) if admin_password else '(空)'
        logger.info(f"[EmailManager] 初始化: worker={worker_domain}, domain={email_domain}, pwd={pwd_masked}")

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """统一请求方法（绕过代理）"""
        url = f"https://{self.worker_domain}{path}"
        kwargs.setdefault('timeout', 30)
        kwargs.setdefault('headers', {})
        kwargs['headers']['x-admin-auth'] = self.admin_password
        kwargs['headers']['Content-Type'] = 'application/json'
        return self._session.request(method, url, **kwargs)

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

            logger.debug(f"[EmailManager] 创建邮箱请求: name={name}, domain={self.email_domain}")

            res = self._request('POST', '/admin/new_address', json={
                "enablePrefix": True,
                "name": name,
                "domain": self.email_domain,
            })

            if res.status_code == 200:
                data = res.json()
                address = data.get('address')
                logger.info(f"[EmailManager] ✓ 创建成功: {address}")
                return data.get('jwt'), address
            else:
                # 增强错误日志：打印响应内容
                try:
                    error_body = res.text[:300]
                except:
                    error_body = "(无法读取响应)"
                logger.error(f"[EmailManager] 创建邮箱失败: HTTP {res.status_code}")
                logger.error(f"[EmailManager] 响应内容: {error_body}")
                logger.error(f"[EmailManager] 请检查: 1) WORKER_DOMAINS 是否正确  2) ADMIN_PASSWORDS 是否匹配 Worker 密码")
                return None, None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[EmailManager] 连接失败: {e}")
            logger.error(f"[EmailManager] 请检查: WORKER_DOMAINS={self.worker_domain} 是否可访问")
            return None, None
        except Exception as e:
            logger.error(f"[EmailManager] 创建邮箱出错: {e}")
            return None, None

    def _get_recent_emails(self, email: str, limit: int = 10) -> List[dict]:
        """获取最近的邮件列表"""
        try:
            res = self._request('GET', '/admin/mails', params={
                "limit": limit, "offset": 0, "address": email
            })

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

    def _decode_subject(self, raw_content: str) -> str:
        """解码 Subject 行（处理 Base64 和 Quoted-Printable 编码）"""
        import base64
        from email.header import decode_header

        # 提取 Subject 行
        subject_match = re.search(r'Subject:\s*(.+?)(?:\r?\n(?!\s)|\r?\n\r?\n)', raw_content, re.DOTALL)
        if not subject_match:
            return ""

        subject_raw = subject_match.group(1).strip()
        # 处理多行 Subject（折叠行以空格开头）
        subject_raw = re.sub(r'\r?\n\s+', ' ', subject_raw)

        try:
            # 使用 email 库解码
            decoded_parts = decode_header(subject_raw)
            subject = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    subject += part.decode(encoding or 'utf-8', errors='ignore')
                else:
                    subject += part
            return subject
        except Exception:
            return subject_raw

    def check_verification_code(self, email: str, max_retries: int = 20, interval: float = 3.0) -> Optional[str]:
        """
        检查验证码邮件（用于 ChatGPT/OpenAI 注册验证）

        ChatGPT 验证码格式：
        - Subject: "你的 ChatGPT 代码为 XXXXXX" 或 "Your ChatGPT code is XXXXXX"
        - Body: 也可能包含验证码
        """
        # 排除常见误识别的 6 位字符串
        EXCLUDE_CODES = {'OPENAI', 'CHATGP', '009025', '000000'}

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

                    # 检查发件人是否是 OpenAI/ChatGPT（排除 SheerID 邮件）
                    from_match = re.search(r'From:.*?([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', raw_content, re.IGNORECASE)
                    if from_match:
                        sender = from_match.group(1).lower()
                        # 只处理 OpenAI 的邮件，跳过 SheerID 等其他邮件
                        if 'sheerid' in sender or 'verify@' in sender:
                            logger.debug(f"跳过非 OpenAI 邮件: {sender}")
                            continue
                        if 'openai' not in sender and 'chatgpt' not in sender:
                            # 不是 OpenAI 的邮件，跳过
                            logger.debug(f"跳过非 OpenAI 邮件: {sender}")
                            continue

                    # 【P0 修复】优先从解码后的 Subject 提取验证码
                    subject = self._decode_subject(raw_content)
                    if subject:
                        # Subject 格式：你的 ChatGPT 代码为 625386
                        subject_patterns = [
                            r'代码为\s*([A-Z0-9]{6})',
                            r'验证码[：:\s]*([A-Z0-9]{6})',
                            r'code\s+is\s+([A-Z0-9]{6})',
                            r'code[：:\s]+([A-Z0-9]{6})',
                            r'\b(\d{6})\b',  # 纯数字验证码
                        ]
                        for pattern in subject_patterns:
                            match = re.search(pattern, subject, re.IGNORECASE)
                            if match:
                                code = match.group(1).upper()
                                if len(code) == 6 and code.isalnum() and code not in EXCLUDE_CODES:
                                    logger.info(f"从 Subject 找到验证码: {code}")
                                    return code

                    # 清理内容
                    cleaned_content = self._clean_email_content(raw_content)

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
                            if len(code) == 6 and code.isalnum() and code not in EXCLUDE_CODES:
                                logger.info(f"找到验证码: {code}")
                                return code

                    # 兜底：检查是否包含验证相关关键词
                    lowered = cleaned_content.lower()
                    keywords = ["verification", "verify", "code", "openai", "chatgpt"]
                    if any(kw in lowered for kw in keywords):
                        # 优先匹配纯数字验证码
                        for m in re.finditer(r'\b(\d{6})\b', cleaned_content):
                            code = m.group(1)
                            if code not in EXCLUDE_CODES:
                                logger.info(f"找到验证码(兜底-数字): {code}")
                                return code
                        # 再匹配字母数字混合
                        for m in re.finditer(r'\b([A-Z0-9]{6})\b', cleaned_content, re.IGNORECASE):
                            code = m.group(1).upper()
                            if code not in EXCLUDE_CODES:
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
                            # 清理链接末尾的无效字符（包括括号、引号等）
                            link = re.sub(r'["\'>)(\]\[]+$', '', link)

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
