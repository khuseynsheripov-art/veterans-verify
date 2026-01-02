"""
Veterans Verify - 邮箱池管理
批量创建和管理临时邮箱

功能：
1. 批量创建邮箱（模式1）
2. 持久化存储（data/email_pool.json）
3. 状态管理：available | in_use | verified | failed
4. 选择/使用邮箱
5. 存储注册信息（姓名、生日）用于重新登录
"""
import json
import random
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum
import logging

from email_manager import EmailManager
from automation.config import generate_password

logger = logging.getLogger(__name__)

# 随机姓名列表
FIRST_NAMES = ['James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph', 'Thomas', 'Charles',
               'Mary', 'Patricia', 'Jennifer', 'Linda', 'Elizabeth', 'Barbara', 'Susan', 'Jessica', 'Sarah', 'Karen']
LAST_NAMES = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez',
              'Wilson', 'Anderson', 'Taylor', 'Thomas', 'Moore', 'Jackson', 'Martin', 'Lee', 'Thompson', 'White']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


def generate_random_profile() -> Dict:
    """生成随机的注册信息（姓名、生日）"""
    return {
        'first_name': random.choice(FIRST_NAMES),
        'last_name': random.choice(LAST_NAMES),
        'birth_month': random.choice(MONTHS),
        'birth_day': str(random.randint(1, 28)),
        'birth_year': str(random.randint(1970, 2000))
    }


class EmailStatus(str, Enum):
    """邮箱状态"""
    AVAILABLE = "available"    # 可用（未使用）
    IN_USE = "in_use"          # 使用中（正在验证）
    VERIFIED = "verified"      # 已验证成功（此邮箱本身注册的 ChatGPT 验证成功）
    CONSUMED = "consumed"      # 已消耗（作为接收邮箱被其他账号使用，不能再用）
    FAILED = "failed"          # 验证失败


class EmailPoolManager:
    """邮箱池管理器"""

    def __init__(self, data_file: str = "./data/email_pool.json"):
        self.data_file = Path(data_file)
        self._lock = threading.Lock()
        self._pool: List[Dict] = []
        self._load()

    def _load(self):
        """从文件加载邮箱池"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._pool = data.get('emails', [])
                logger.info(f"[EmailPool] 加载了 {len(self._pool)} 个邮箱")
            except Exception as e:
                logger.error(f"[EmailPool] 加载失败: {e}")
                self._pool = []
        else:
            self._pool = []
            self._save()

    def _save(self):
        """保存邮箱池到文件"""
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'emails': self._pool,
                    'updated_at': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[EmailPool] 保存失败: {e}")

    def create_emails(self, email_manager: EmailManager, count: int = 1) -> List[Dict]:
        """
        批量创建邮箱

        Args:
            email_manager: EmailManager 实例
            count: 创建数量

        Returns:
            创建的邮箱列表
        """
        created = []
        for i in range(count):
            jwt, address = email_manager.create_email()
            if jwt and address:
                # 生成随机注册信息
                profile = generate_random_profile()

                # 生成 ChatGPT 登录密码
                password = generate_password()

                email_data = {
                    'address': address,
                    'jwt': jwt,
                    'password': password,  # ChatGPT 登录密码（创建时生成，保持一致）
                    'status': EmailStatus.AVAILABLE.value,
                    'linked_account': None,  # 关联的 ChatGPT 账号
                    'created_at': datetime.now().isoformat(),
                    'used_at': None,
                    'verified_at': None,
                    'error_message': None,
                    # 注册信息（ChatGPT 注册时使用，保持一致）
                    'first_name': profile['first_name'],
                    'last_name': profile['last_name'],
                    'birth_month': profile['birth_month'],
                    'birth_day': profile['birth_day'],
                    'birth_year': profile['birth_year']
                }
                with self._lock:
                    self._pool.append(email_data)
                created.append(email_data)
                logger.info(f"[EmailPool] 创建邮箱 {i+1}/{count}: {address} ({profile['first_name']} {profile['last_name']})")
            else:
                logger.warning(f"[EmailPool] 创建邮箱 {i+1}/{count} 失败")

        if created:
            with self._lock:
                self._save()

        return created

    def get_available(self) -> Optional[Dict]:
        """
        获取一个可用的邮箱

        Returns:
            邮箱数据，或 None（如果没有可用的）
        """
        with self._lock:
            for email in self._pool:
                if email['status'] == EmailStatus.AVAILABLE.value:
                    return email.copy()
        return None

    def mark_in_use(self, address: str, linked_account: str = None) -> bool:
        """
        标记邮箱为使用中

        Args:
            address: 邮箱地址
            linked_account: 关联的 ChatGPT 账号（半自动模式时记录登录的账号邮箱）

        Returns:
            是否成功
        """
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    email['status'] = EmailStatus.IN_USE.value
                    email['used_at'] = datetime.now().isoformat()
                    if linked_account:
                        email['linked_account'] = linked_account
                    self._save()
                    return True
        return False

    def update_linked_account(self, address: str, linked_account: str) -> bool:
        """
        更新邮箱关联的 ChatGPT 账号

        用于半自动模式：记录这个临时邮箱给哪个 ChatGPT 账号验证用的

        Args:
            address: 临时邮箱地址
            linked_account: 关联的 ChatGPT 账号邮箱

        Returns:
            是否成功
        """
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    email['linked_account'] = linked_account
                    email['linked_at'] = datetime.now().isoformat()
                    self._save()
                    logger.info(f"[EmailPool] {address} 关联到账号 {linked_account}")
                    return True
        return False

    def mark_verified(self, address: str, veteran_info: dict = None) -> bool:
        """
        标记邮箱验证成功

        Args:
            address: 邮箱地址
            veteran_info: 可选，成功使用的军人信息
                {
                    'first_name': 'John',
                    'last_name': 'Smith',
                    'branch': 'Army',
                    'discharge_date': 'June 15, 2024'
                }

        Returns:
            是否成功
        """
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    email['status'] = EmailStatus.VERIFIED.value
                    email['verified_at'] = datetime.now().isoformat()
                    if veteran_info:
                        email['verified_veteran'] = veteran_info
                    self._save()
                    return True
        return False

    def update_password(self, address: str, password: str) -> bool:
        """保存账号密码到邮箱池"""
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    email['password'] = password
                    self._save()
                    return True
        return False

    def update_profile(self, address: str, first_name: str, last_name: str,
                       birth_month: str, birth_day: str, birth_year: str) -> bool:
        """
        更新邮箱的注册信息（用于手动修改注册时填写的姓名/生日）

        Args:
            address: 邮箱地址
            first_name: 名
            last_name: 姓
            birth_month: 出生月 (如 "September")
            birth_day: 出生日 (如 "25")
            birth_year: 出生年 (如 "1999")

        Returns:
            是否成功
        """
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    email['first_name'] = first_name
                    email['last_name'] = last_name
                    email['birth_month'] = birth_month
                    email['birth_day'] = birth_day
                    email['birth_year'] = birth_year
                    self._save()
                    logger.info(f"[EmailPool] 更新注册信息: {address} -> {first_name} {last_name}")
                    return True
        return False

    def mark_failed(self, address: str, error_message: str = None) -> bool:
        """标记邮箱验证失败"""
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    email['status'] = EmailStatus.FAILED.value
                    email['error_message'] = error_message
                    self._save()
                    return True
        return False

    def mark_consumed(self, address: str, consumed_by: str, veteran_info: dict = None) -> bool:
        """
        标记邮箱已消耗（作为接收邮箱被其他账号使用）

        Args:
            address: 被消耗的临时邮箱地址
            consumed_by: 消耗这个邮箱的 ChatGPT 账号
            veteran_info: 可选，验证成功使用的军人信息

        Returns:
            是否成功
        """
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    email['status'] = EmailStatus.CONSUMED.value
                    email['consumed_by'] = consumed_by
                    email['consumed_at'] = datetime.now().isoformat()
                    if veteran_info:
                        email['verified_veteran'] = veteran_info
                    self._save()
                    logger.info(f"[EmailPool] {address} 已消耗，被 {consumed_by} 使用")
                    return True
        return False

    def is_consumed_or_verified(self, address: str) -> bool:
        """检查邮箱是否已经被消耗或验证过（不能再用）"""
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    return email['status'] in [EmailStatus.CONSUMED.value, EmailStatus.VERIFIED.value]
        return False

    def reset_to_available(self, address: str) -> bool:
        """重置邮箱为可用状态"""
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    email['status'] = EmailStatus.AVAILABLE.value
                    email['linked_account'] = None
                    email['used_at'] = None
                    email['verified_at'] = None
                    email['error_message'] = None
                    self._save()
                    return True
        return False

    def get_by_address(self, address: str) -> Optional[Dict]:
        """通过地址获取邮箱数据"""
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    return email.copy()
        return None

    def delete(self, address: str) -> bool:
        """删除邮箱"""
        with self._lock:
            for i, email in enumerate(self._pool):
                if email['address'] == address:
                    del self._pool[i]
                    self._save()
                    return True
        return False

    def list_all(self) -> List[Dict]:
        """获取所有邮箱"""
        with self._lock:
            return [e.copy() for e in self._pool]

    def list_by_status(self, status: EmailStatus) -> List[Dict]:
        """按状态筛选邮箱"""
        with self._lock:
            return [e.copy() for e in self._pool if e['status'] == status.value]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            stats = {
                'total': len(self._pool),
                'available': 0,
                'in_use': 0,
                'verified': 0,
                'consumed': 0,  # 新增：已消耗
                'failed': 0
            }
            for email in self._pool:
                status = email.get('status', EmailStatus.AVAILABLE.value)
                if status in stats:
                    stats[status] += 1
            return stats

    def ensure_password(self, address: str) -> Optional[str]:
        """
        确保邮箱有密码，如果没有则生成一个

        用于修复旧数据（创建时没有生成密码的邮箱）

        Returns:
            密码字符串，或 None（如果邮箱不存在）
        """
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    if not email.get('password'):
                        # 生成并保存密码
                        email['password'] = generate_password()
                        self._save()
                        logger.info(f"[EmailPool] 为 {address} 生成密码")
                    return email['password']
        return None

    def migrate_add_passwords(self) -> int:
        """
        迁移：为所有没有密码的邮箱生成密码

        Returns:
            修复的邮箱数量
        """
        count = 0
        with self._lock:
            for email in self._pool:
                if not email.get('password'):
                    email['password'] = generate_password()
                    count += 1
                    logger.info(f"[EmailPool] 迁移: 为 {email['address']} 生成密码")
            if count > 0:
                self._save()
        return count

    def add_external(self, address: str, jwt: str) -> bool:
        """
        添加外部邮箱（用于半自动模式）

        当用户提供已有的临时邮箱地址和 JWT 时使用

        Args:
            address: 邮箱地址
            jwt: 邮箱 JWT 凭证

        Returns:
            是否成功
        """
        # 检查是否已存在
        with self._lock:
            for email in self._pool:
                if email['address'] == address:
                    # 更新 JWT
                    email['jwt'] = jwt
                    self._save()
                    return True

            # 添加新的 - 自动生成注册信息
            profile = generate_random_profile()
            password = generate_password()

            email_data = {
                'address': address,
                'jwt': jwt,
                'password': password,  # ChatGPT 登录密码
                'status': EmailStatus.AVAILABLE.value,
                'linked_account': None,
                'created_at': datetime.now().isoformat(),
                'used_at': None,
                'verified_at': None,
                'error_message': None,
                'is_external': True,  # 标记为外部添加
                # 注册信息（ChatGPT 注册时使用）
                'first_name': profile['first_name'],
                'last_name': profile['last_name'],
                'birth_month': profile['birth_month'],
                'birth_day': profile['birth_day'],
                'birth_year': profile['birth_year']
            }
            self._pool.append(email_data)
            self._save()
            logger.info(f"[EmailPool] 添加外部邮箱: {address} ({profile['first_name']} {profile['last_name']})")
            return True

    def sync_from_database(self) -> int:
        """
        从数据库同步状态到邮箱池

        解决问题：验证成功后数据库更新了，但邮箱池没更新
        这个方法会检查数据库中的 verified 账号，同步到邮箱池

        Returns:
            同步的邮箱数量
        """
        try:
            from database import get_accounts
            accounts = get_accounts()
        except Exception as e:
            logger.error(f"[EmailPool] 同步失败，无法读取数据库: {e}")
            return 0

        count = 0
        with self._lock:
            for account in accounts:
                email = account.get('email', '')
                status = account.get('status', '')

                # 只同步 verified 状态
                if status != 'verified':
                    continue

                # 查找邮箱池中的记录
                for pool_email in self._pool:
                    if pool_email['address'] == email:
                        if pool_email['status'] != EmailStatus.VERIFIED.value:
                            pool_email['status'] = EmailStatus.VERIFIED.value
                            pool_email['verified_at'] = datetime.now().isoformat()
                            count += 1
                            logger.info(f"[EmailPool] 同步: {email} → verified")
                        break

            if count > 0:
                self._save()

        logger.info(f"[EmailPool] 同步完成，更新了 {count} 个邮箱状态")
        return count

    def migrate_add_profiles(self) -> int:
        """
        迁移：为所有没有注册信息的邮箱生成随机信息

        某些邮箱（如外部添加的旧数据）可能没有 first_name、birth_* 等字段，
        这个方法会为它们补充随机生成的注册信息。

        Returns:
            修复的邮箱数量
        """
        count = 0
        with self._lock:
            for email in self._pool:
                # 检查是否缺少注册信息
                if not email.get('first_name') or not email.get('birth_month'):
                    profile = generate_random_profile()
                    email['first_name'] = profile['first_name']
                    email['last_name'] = profile['last_name']
                    email['birth_month'] = profile['birth_month']
                    email['birth_day'] = profile['birth_day']
                    email['birth_year'] = profile['birth_year']
                    count += 1
                    logger.info(f"[EmailPool] 迁移: 为 {email['address']} 生成注册信息 ({profile['first_name']} {profile['last_name']})")
            if count > 0:
                self._save()
        return count
