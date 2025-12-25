"""
Veterans Verify - 账号管理模块

参考 test_band_gemini_mail 项目架构
实现批量创建临时邮箱 + 注册 ChatGPT + Veterans 验证
"""
import os
import json
import threading
import queue
import time
import random
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class AccountStatus(Enum):
    """账号状态"""
    PENDING = "pending"                    # 等待处理
    CREATING_EMAIL = "creating_email"      # 创建邮箱中
    REGISTERING_CHATGPT = "registering"    # 注册 ChatGPT 中
    WAITING_CHATGPT_CODE = "waiting_code"  # 等待 ChatGPT 验证码
    CHATGPT_READY = "chatgpt_ready"        # ChatGPT 注册完成
    OPENING_SHEERID = "opening_sheerid"    # 打开 SheerID 页面
    FILLING_FORM = "filling_form"          # 填写表单中
    WAITING_VERIFY_LINK = "waiting_link"   # 等待验证链接
    CLICKING_LINK = "clicking_link"        # 点击验证链接
    SUCCESS = "success"                    # 验证成功
    FAILED = "failed"                      # 失败


@dataclass
class AccountInfo:
    """账号信息"""
    # 基本信息
    account_id: str = ""               # 唯一ID
    email: str = ""                    # 临时邮箱
    password: str = ""                 # ChatGPT 密码
    jwt: str = ""                      # 邮箱 JWT

    # 军人信息（来自 BIRLS）
    first_name: str = ""
    last_name: str = ""
    branch: str = ""                   # 军种
    birth_date: Dict[str, str] = field(default_factory=dict)      # {"month": "March", "day": "15", "year": "1985"}
    discharge_date: Dict[str, str] = field(default_factory=dict)  # {"month": "June", "day": "20", "year": "2024"}

    # 状态
    status: AccountStatus = AccountStatus.PENDING
    error_message: str = ""
    error_type: str = ""               # 错误分类

    # Profile 相关
    profile_id: str = ""
    profile_group: str = ""
    proxy: str = ""

    # 时间戳
    created_at: str = ""
    updated_at: str = ""

    # 配置
    email_config: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转为字典（用于 API 返回）"""
        return {
            "account_id": self.account_id,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "branch": self.branch,
            "birth_date": self.birth_date,
            "discharge_date": self.discharge_date,
            "status": self.status.value,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "profile_id": self.profile_id,
            "proxy": self.proxy,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_storage_dict(self) -> Dict:
        """转为存储字典"""
        return {
            "account_id": self.account_id,
            "email": self.email,
            "password": self.password,
            "jwt": self.jwt,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "branch": self.branch,
            "birth_date": self.birth_date,
            "discharge_date": self.discharge_date,
            "status": self.status.value,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "profile_id": self.profile_id,
            "profile_group": self.profile_group,
            "proxy": self.proxy,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_storage_dict(cls, data: Dict, email_config: Optional[Dict] = None) -> "AccountInfo":
        """从存储字典恢复"""
        status_val = data.get("status", "pending")
        try:
            status = AccountStatus(status_val)
        except ValueError:
            status = AccountStatus.PENDING

        return cls(
            account_id=data.get("account_id", ""),
            email=data.get("email", ""),
            password=data.get("password", ""),
            jwt=data.get("jwt", ""),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            branch=data.get("branch", ""),
            birth_date=data.get("birth_date", {}),
            discharge_date=data.get("discharge_date", {}),
            status=status,
            error_message=data.get("error_message", ""),
            error_type=data.get("error_type", ""),
            profile_id=data.get("profile_id", ""),
            profile_group=data.get("profile_group", ""),
            proxy=data.get("proxy", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            email_config=email_config or {},
        )


class AccountManager:
    """
    账号管理器

    功能：
    1. 批量创建临时邮箱
    2. 管理账号队列
    3. 调度浏览器工作器
    4. 持久化账号数据
    5. 止损机制
    """

    def __init__(self, config, veteran_data_manager=None):
        self.config = config
        self.veteran_data_manager = veteran_data_manager

        # 账号存储
        self.accounts: Dict[str, AccountInfo] = {}
        self.accounts_lock = threading.Lock()

        # 工作器管理
        self.workers: Dict[int, Any] = {}
        self.workers_lock = threading.Lock()

        # 任务队列
        self.task_queue = queue.Queue()

        # 止损状态
        self._consecutive_failures = 0
        self._cooldown_until = 0.0
        self._cooldown_lock = threading.Lock()

        # 持久化
        self._persist_enabled = os.getenv("PERSIST_DATA", "false").lower() == "true"
        self._accounts_file = os.getenv("ACCOUNTS_FILE", "./data/accounts.json")
        self._save_lock = threading.Lock()
        self._last_save_time = 0.0

        # 加载已保存的账号
        self._load_accounts()

        # 启动后台任务处理器
        self._start_task_processor()

    # ==================== 账号创建 ====================

    def create_account(
        self,
        profile_group: str = "",
        profile_id: str = "",
        async_mode: bool = True
    ) -> (Optional[AccountInfo], Optional[str]):
        """
        创建单个账号

        流程：
        1. 创建临时邮箱
        2. 获取军人数据
        3. 加入验证队列
        """
        from email_manager import EmailManager
        import uuid

        # 1. 获取邮箱配置
        email_config = self.config.get_random_email_config()
        if not email_config:
            return None, "没有配置邮箱服务"

        # 2. 创建临时邮箱
        email_manager = EmailManager(
            email_config["worker_domain"],
            email_config["email_domain"],
            email_config["admin_password"]
        )
        jwt, email = email_manager.create_email()
        if not jwt or not email:
            return None, "创建邮箱失败"

        # 3. 获取军人数据
        vet_data = None
        if self.veteran_data_manager:
            vet_data = self.veteran_data_manager.get_random_veteran()

        if not vet_data:
            return None, "获取军人数据失败"

        # 4. 生成密码
        password = self._generate_password()

        # 5. 创建账号对象
        account = AccountInfo(
            account_id=str(uuid.uuid4())[:8],
            email=email,
            password=password,
            jwt=jwt,
            first_name=vet_data["first_name"],
            last_name=vet_data["last_name"],
            branch=vet_data["branch"],
            birth_date=vet_data["birth_date"],
            discharge_date=vet_data["discharge_date"],
            status=AccountStatus.PENDING,
            profile_id=profile_id,
            profile_group=profile_group,
            proxy=self.config.get_proxy_server(),
            created_at=datetime.now().isoformat(),
            email_config=email_config,
        )

        # 6. 保存账号
        with self.accounts_lock:
            self.accounts[email] = account
        self._save_accounts()

        logger.info(f"[AccountManager] 创建账号: {email}, 军人: {account.first_name} {account.last_name}")

        # 7. 加入队列
        if async_mode:
            self._enqueue_task(account)
            return account, None
        else:
            # 同步模式：直接启动工作器
            worker_id = self._get_available_worker_slot()
            if worker_id is None:
                self._enqueue_task(account)
                return account, "已加入队列，等待执行"
            self._start_worker(worker_id, account)
            return account, None

    def batch_create_accounts(
        self,
        count: int,
        interval: float = 0,
        profile_group: str = "",
    ) -> int:
        """
        批量创建账号（后台线程）
        """
        def _batch_task():
            created = 0
            for i in range(count):
                account, error = self.create_account(
                    profile_group=profile_group,
                    async_mode=True
                )
                if account:
                    created += 1
                    logger.info(f"[Batch] 创建账号 {i+1}/{count}: {account.email}")
                else:
                    logger.warning(f"[Batch] 创建失败 {i+1}/{count}: {error}")

                if interval > 0 and i < count - 1:
                    time.sleep(interval)

            logger.info(f"[Batch] 批量创建完成: {created}/{count}")

        thread = threading.Thread(target=_batch_task, daemon=True)
        thread.start()
        return count

    # ==================== 工作器管理 ====================

    def _get_available_worker_slot(self) -> Optional[int]:
        """获取可用的工作器槽位"""
        max_workers = self.config.get_max_workers()
        with self.workers_lock:
            active_count = sum(1 for w in self.workers.values() if hasattr(w, 'is_alive') and w.is_alive())
            if active_count >= max_workers:
                return None
            for i in range(max_workers):
                if i not in self.workers or not self.workers[i].is_alive():
                    return i
        return None

    def _start_worker(self, worker_id: int, account: AccountInfo):
        """启动工作器"""
        from browser_worker import BrowserWorker, VerifyTask

        # 创建验证任务
        task = VerifyTask(
            task_id=account.account_id,
            email=account.email,
            password=account.password,
            first_name=account.first_name,
            last_name=account.last_name,
            branch=account.branch,
            birth_date=account.birth_date,
            discharge_date=account.discharge_date,
        )

        # 创建工作器
        worker = BrowserWorker(
            headless=self.config.get_headless(),
            screenshot_dir=self.config.get_debug_screenshot_dir(),
        )

        # 异步运行（需要在新线程中运行事件循环）
        def _run_worker():
            import asyncio
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                from email_manager import EmailManager
                email_manager = EmailManager(
                    account.email_config.get("worker_domain", ""),
                    account.email_config.get("email_domain", ""),
                    account.email_config.get("admin_password", ""),
                )

                success = loop.run_until_complete(
                    worker.run_verification(task, email_manager, self.veteran_data_manager)
                )

                # 更新账号状态
                with self.accounts_lock:
                    if account.email in self.accounts:
                        acc = self.accounts[account.email]
                        if success:
                            acc.status = AccountStatus.SUCCESS
                            self._on_success()
                        else:
                            acc.status = AccountStatus.FAILED
                            acc.error_message = task.error_message
                            acc.error_type = task.error_type
                            self._on_failure()
                        acc.updated_at = datetime.now().isoformat()

                self._save_accounts()
                self._on_worker_complete(worker_id, account.email, success)

            except Exception as e:
                logger.error(f"[Worker {worker_id}] 异常: {e}")
                with self.accounts_lock:
                    if account.email in self.accounts:
                        self.accounts[account.email].status = AccountStatus.FAILED
                        self.accounts[account.email].error_message = str(e)
                self._on_failure()
                self._save_accounts()

        thread = threading.Thread(target=_run_worker, daemon=True)
        with self.workers_lock:
            self.workers[worker_id] = thread
        thread.start()

    def _on_worker_complete(self, worker_id: int, email: str, success: bool):
        """工作器完成回调"""
        with self.workers_lock:
            if worker_id in self.workers:
                del self.workers[worker_id]

        logger.info(f"[Worker {worker_id}] 完成: {email}, 成功={success}")

    # ==================== 任务队列 ====================

    def _enqueue_task(self, account: AccountInfo):
        """加入任务队列"""
        self.task_queue.put(account)

    def _start_task_processor(self):
        """启动后台任务处理器"""
        def _processor():
            while True:
                try:
                    # 检查冷却
                    with self._cooldown_lock:
                        if time.time() < self._cooldown_until:
                            remaining = self._cooldown_until - time.time()
                            logger.info(f"[TaskProcessor] 冷却中，剩余 {remaining:.0f}s")
                            time.sleep(min(5, remaining))
                            continue

                    # 获取任务
                    try:
                        account = self.task_queue.get(timeout=1)
                    except queue.Empty:
                        continue

                    # 获取工作器槽位
                    worker_id = self._get_available_worker_slot()
                    if worker_id is not None:
                        self._start_worker(worker_id, account)
                    else:
                        # 放回队列
                        self.task_queue.put(account)
                        time.sleep(1)

                except Exception as e:
                    logger.error(f"[TaskProcessor] 错误: {e}")
                    time.sleep(1)

        thread = threading.Thread(target=_processor, daemon=True)
        thread.start()

    # ==================== 止损机制 ====================

    def _on_success(self):
        """成功时重置连续失败计数"""
        with self._cooldown_lock:
            self._consecutive_failures = 0

    def _on_failure(self):
        """失败时检查是否需要冷却"""
        with self._cooldown_lock:
            self._consecutive_failures += 1
            max_failures = self.config.get_max_consecutive_failures()

            if self._consecutive_failures >= max_failures:
                cooldown_min, cooldown_max = self.config.get_cooldown_range()
                cooldown = random.randint(cooldown_min, cooldown_max)
                self._cooldown_until = time.time() + cooldown
                self._consecutive_failures = 0
                logger.warning(f"[StopLoss] 连续失败 {max_failures} 次，冷却 {cooldown}s")

    # ==================== 持久化 ====================

    def _save_accounts(self, force: bool = False):
        """保存账号到磁盘"""
        if not self._persist_enabled:
            return

        debounce = float(os.getenv("SAVE_DEBOUNCE_SECONDS", "1.0"))
        now = time.time()
        if not force and (now - self._last_save_time) < debounce:
            return

        with self._save_lock:
            if not force and (now - self._last_save_time) < debounce:
                return

            try:
                path = Path(self._accounts_file)
                path.parent.mkdir(parents=True, exist_ok=True)

                with self.accounts_lock:
                    payload = {
                        "saved_at": datetime.now().isoformat(),
                        "accounts": [acc.to_storage_dict() for acc in self.accounts.values()]
                    }

                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self._last_save_time = now
                logger.debug(f"[Persist] 已保存 {len(self.accounts)} 个账号")

            except Exception as e:
                logger.error(f"[Persist] 保存失败: {e}")

    def _load_accounts(self):
        """从磁盘加载账号"""
        if not self._persist_enabled:
            return

        path = Path(self._accounts_file)
        if not path.exists():
            return

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get("accounts") if isinstance(raw, dict) else raw
            if not isinstance(items, list):
                return

            loaded = 0
            with self.accounts_lock:
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    email = item.get("email", "").strip()
                    if not email:
                        continue

                    # 获取对应的邮箱配置
                    email_config = self._get_email_config_by_domain(email)
                    account = AccountInfo.from_storage_dict(item, email_config)
                    self.accounts[email] = account
                    loaded += 1

            logger.info(f"[Persist] 已加载 {loaded} 个账号")

        except Exception as e:
            logger.error(f"[Persist] 加载失败: {e}")

    def _get_email_config_by_domain(self, email: str) -> Optional[Dict]:
        """根据邮箱域名获取配置"""
        if "@" not in email:
            return None
        domain = email.split("@")[1].lower()
        for cfg in self.config.get_email_configs():
            if cfg.get("email_domain", "").lower() == domain:
                return cfg
        return None

    # ==================== 工具方法 ====================

    @staticmethod
    def _generate_password() -> str:
        """生成随机密码（12+ 字符）"""
        import string
        chars = string.ascii_letters + string.digits + "!@#$%"
        return "".join(random.choices(chars, k=16))

    # ==================== 账号操作 ====================

    def get_accounts(
        self,
        status_filter: str = None,
        page: int = 1,
        per_page: int = 20
    ) -> Dict:
        """获取账号列表"""
        with self.accounts_lock:
            accounts_list = list(self.accounts.values())

        # 过滤
        if status_filter:
            if status_filter == "success":
                accounts_list = [a for a in accounts_list if a.status == AccountStatus.SUCCESS]
            elif status_filter == "failed":
                accounts_list = [a for a in accounts_list if a.status == AccountStatus.FAILED]
            elif status_filter == "pending":
                accounts_list = [a for a in accounts_list if a.status not in [AccountStatus.SUCCESS, AccountStatus.FAILED]]

        # 统计
        total = len(accounts_list)
        success_count = sum(1 for a in self.accounts.values() if a.status == AccountStatus.SUCCESS)
        failed_count = sum(1 for a in self.accounts.values() if a.status == AccountStatus.FAILED)
        pending_count = len(self.accounts) - success_count - failed_count

        # 分页
        start = (page - 1) * per_page
        end = start + per_page
        paginated = accounts_list[start:end]

        return {
            "accounts": [a.to_dict() for a in paginated],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page if per_page > 0 else 1,
            "stats": {
                "total": len(self.accounts),
                "success": success_count,
                "failed": failed_count,
                "pending": pending_count,
            }
        }

    def get_account(self, email: str) -> Optional[AccountInfo]:
        """获取单个账号"""
        with self.accounts_lock:
            return self.accounts.get(email)

    def delete_account(self, email: str) -> bool:
        """删除账号"""
        with self.accounts_lock:
            if email in self.accounts:
                del self.accounts[email]
                self._save_accounts(force=True)
                return True
        return False

    def retry_account(self, email: str) -> bool:
        """重试失败的账号"""
        with self.accounts_lock:
            if email not in self.accounts:
                return False
            account = self.accounts[email]
            if account.status != AccountStatus.FAILED:
                return False

            # 重置状态
            account.status = AccountStatus.PENDING
            account.error_message = ""
            account.error_type = ""

        # 加入队列
        self._enqueue_task(account)
        self._save_accounts()
        return True

    def get_status(self) -> Dict:
        """获取系统状态"""
        with self.accounts_lock:
            total = len(self.accounts)
            success = sum(1 for a in self.accounts.values() if a.status == AccountStatus.SUCCESS)
            failed = sum(1 for a in self.accounts.values() if a.status == AccountStatus.FAILED)
            pending = total - success - failed

        with self.workers_lock:
            active_workers = sum(1 for w in self.workers.values() if hasattr(w, 'is_alive') and w.is_alive())

        with self._cooldown_lock:
            cooldown_remaining = max(0, self._cooldown_until - time.time())

        return {
            "accounts": {
                "total": total,
                "success": success,
                "failed": failed,
                "pending": pending,
            },
            "workers": {
                "active": active_workers,
                "max": self.config.get_max_workers(),
            },
            "queue_size": self.task_queue.qsize(),
            "cooldown_remaining": round(cooldown_remaining),
            "consecutive_failures": self._consecutive_failures,
        }

    def stop_all(self):
        """停止所有任务"""
        # 清空队列
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
            except:
                break

        # 标记所有 pending 为失败
        with self.accounts_lock:
            for account in self.accounts.values():
                if account.status not in [AccountStatus.SUCCESS, AccountStatus.FAILED]:
                    account.status = AccountStatus.FAILED
                    account.error_message = "用户手动停止"

        self._save_accounts(force=True)
        logger.info("[AccountManager] 已停止所有任务")


# 测试
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    from config import Config
    from veteran_data import VeteranDataManager

    config = Config()
    vet_manager = VeteranDataManager()

    manager = AccountManager(config, vet_manager)

    print("\n系统状态:")
    print(json.dumps(manager.get_status(), indent=2, ensure_ascii=False))
