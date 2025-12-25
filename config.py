"""
Veterans Verify - 配置管理
完整版本，包含所有环境变量配置
"""
import os
import random
import threading
from typing import List, Dict, Optional, Tuple
import logging

def setup_logging():
    """配置日志"""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_file = os.getenv('LOG_FILE', '')

    handlers = [logging.StreamHandler()]

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        from logging.handlers import RotatingFileHandler
        max_size = int(os.getenv('LOG_MAX_SIZE', '10485760'))
        backup_count = int(os.getenv('LOG_BACKUP_COUNT', '5'))
        handlers.append(RotatingFileHandler(
            log_file, maxBytes=max_size, backupCount=backup_count
        ))

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )

logger = logging.getLogger(__name__)


class Config:
    """配置管理器"""

    def __init__(self):
        self._lock = threading.Lock()

        # Basic
        self._port = 7870
        self._debug = False
        self._secret_key = ''

        # Auth
        self._admin_username = 'admin'
        self._admin_password = ''
        self._admin_token = ''

        # Browser & concurrency
        self._max_workers = 1
        self._headless = True
        self._proxy_server = ''
        self._debug_screenshot_dir = ''

        # Email configs
        self._email_configs = []

        # Human behavior
        self._human_delay_min = 50
        self._human_delay_max = 150
        self._request_interval_min = 30
        self._request_interval_max = 120
        self._field_delay_min = 0.3
        self._field_delay_max = 0.8

        # Stop-loss
        self._max_consecutive_failures = 3
        self._cooldown_min = 180
        self._cooldown_max = 480
        self._single_failure_cooldown = 900
        self._captcha_cooldown = 600

        # Fingerprint
        self._window_size = '1920x1080'
        self._timezone = 'America/Los_Angeles'
        self._locale = 'en-US'
        self._geo_latitude = None
        self._geo_longitude = None

        # Profile
        self._profile_config_path = './data/profiles.json'
        self._profile_assign_strategy = 'round_robin'
        self._profile_default_group = ''
        self._profile_bad_ttl = 900

        # Auto-recover
        self._auto_recover_max_retries = 2
        self._auto_recover_backoff = 30

        # Verification
        self._sheerid_verify_url = 'https://services.sheerid.com/verify/690415d58971e73ca187d8c9/'
        self._email_code_max_retries = 20
        self._email_code_check_interval = 3.0
        self._page_load_timeout = 30
        self._submit_timeout = 60

        # Persistence
        self._persist_data = False
        self._data_dir = './data'
        self._tasks_file = './data/tasks.json'
        self._results_file = './data/results.json'
        self._save_debounce = 1.0

        # IPQS
        self._ipqs_api_key = ''
        self._ipqs_max_fraud_score = 75

        # Rate limiting
        self._rate_limit_max_requests = 3
        self._rate_limit_window_ms = 600000

        # Faker
        self._faker_locale = 'en_US'
        self._birth_year_min = 1950
        self._birth_year_max = 1995
        self._discharge_year_min = 1975
        self._discharge_year_max = 2024

        # Camoufox
        self._humanize_cursor = True
        self._geoip_enabled = True
        self._firefox_profile_dir = ''

        self._load_from_env()

    def _load_from_env(self):
        """从环境变量加载配置"""
        # Basic
        self._port = int(os.getenv('PORT', '7870'))
        self._debug = os.getenv('DEBUG', 'false').lower() == 'true'
        self._secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

        # Auth
        self._admin_username = os.getenv('ADMIN_USERNAME', 'admin')
        self._admin_password = os.getenv('ADMIN_PASSWORD', '')
        self._admin_token = os.getenv('ADMIN_TOKEN', '')

        # Browser & concurrency
        self._max_workers = int(os.getenv('MAX_WORKERS', '1'))
        self._headless = os.getenv('HEADLESS', 'true').lower() == 'true'
        self._proxy_server = os.getenv('PROXY_SERVER', '')
        self._debug_screenshot_dir = os.getenv('DEBUG_SCREENSHOT_DIR', '')

        # Human behavior
        self._human_delay_min = int(os.getenv('HUMAN_DELAY_MIN', '50'))
        self._human_delay_max = int(os.getenv('HUMAN_DELAY_MAX', '150'))
        self._request_interval_min = int(os.getenv('REQUEST_INTERVAL_MIN', '30'))
        self._request_interval_max = int(os.getenv('REQUEST_INTERVAL_MAX', '120'))
        self._field_delay_min = float(os.getenv('FIELD_DELAY_MIN', '0.3'))
        self._field_delay_max = float(os.getenv('FIELD_DELAY_MAX', '0.8'))

        # Stop-loss
        self._max_consecutive_failures = int(os.getenv('MAX_CONSECUTIVE_FAILURES', '3'))
        self._cooldown_min = int(os.getenv('COOLDOWN_MIN_SECONDS', '180'))
        self._cooldown_max = int(os.getenv('COOLDOWN_MAX_SECONDS', '480'))
        self._single_failure_cooldown = int(os.getenv('SINGLE_FAILURE_COOLDOWN_SECONDS', '900'))
        self._captcha_cooldown = int(os.getenv('CAPTCHA_COOLDOWN_SECONDS', '600'))

        # Fingerprint
        self._window_size = os.getenv('WINDOW_SIZE', '1920x1080')
        self._timezone = os.getenv('TIMEZONE', 'America/Los_Angeles')
        self._locale = os.getenv('LOCALE', 'en-US')
        lat = os.getenv('GEO_LATITUDE', '')
        lng = os.getenv('GEO_LONGITUDE', '')
        self._geo_latitude = float(lat) if lat else None
        self._geo_longitude = float(lng) if lng else None

        # Profile
        self._profile_config_path = os.getenv('PROFILE_CONFIG_PATH', './data/profiles.json')
        self._profile_assign_strategy = os.getenv('PROFILE_ASSIGN_STRATEGY', 'round_robin')
        self._profile_default_group = os.getenv('PROFILE_DEFAULT_GROUP', '')
        self._profile_bad_ttl = int(os.getenv('PROFILE_BAD_TTL_SECONDS', '900'))

        # Auto-recover
        self._auto_recover_max_retries = int(os.getenv('AUTO_RECOVER_MAX_RETRIES', '2'))
        self._auto_recover_backoff = int(os.getenv('AUTO_RECOVER_BACKOFF_SECONDS', '30'))

        # Verification
        self._sheerid_verify_url = os.getenv('SHEERID_VERIFY_URL',
            'https://services.sheerid.com/verify/690415d58971e73ca187d8c9/')
        self._email_code_max_retries = int(os.getenv('EMAIL_CODE_MAX_RETRIES', '20'))
        self._email_code_check_interval = float(os.getenv('EMAIL_CODE_CHECK_INTERVAL', '3.0'))
        self._page_load_timeout = int(os.getenv('PAGE_LOAD_TIMEOUT', '30'))
        self._submit_timeout = int(os.getenv('SUBMIT_TIMEOUT', '60'))

        # Persistence
        self._persist_data = os.getenv('PERSIST_DATA', 'false').lower() == 'true'
        self._data_dir = os.getenv('DATA_DIR', './data')
        self._tasks_file = os.getenv('TASKS_FILE', './data/tasks.json')
        self._results_file = os.getenv('RESULTS_FILE', './data/results.json')
        self._save_debounce = float(os.getenv('SAVE_DEBOUNCE_SECONDS', '1.0'))

        # IPQS
        self._ipqs_api_key = os.getenv('IPQS_API_KEY', '')
        self._ipqs_max_fraud_score = int(os.getenv('IPQS_MAX_FRAUD_SCORE', '75'))

        # Rate limiting
        self._rate_limit_max_requests = int(os.getenv('RATE_LIMIT_MAX_REQUESTS', '3'))
        self._rate_limit_window_ms = int(os.getenv('RATE_LIMIT_WINDOW_MS', '600000'))

        # Faker
        self._faker_locale = os.getenv('FAKER_LOCALE', 'en_US')
        self._birth_year_min = int(os.getenv('BIRTH_YEAR_MIN', '1950'))
        self._birth_year_max = int(os.getenv('BIRTH_YEAR_MAX', '1995'))
        self._discharge_year_min = int(os.getenv('DISCHARGE_YEAR_MIN', '1975'))
        self._discharge_year_max = int(os.getenv('DISCHARGE_YEAR_MAX', '2024'))

        # Camoufox
        self._humanize_cursor = os.getenv('HUMANIZE_CURSOR', 'true').lower() == 'true'
        self._geoip_enabled = os.getenv('GEOIP_ENABLED', 'true').lower() == 'true'
        self._firefox_profile_dir = os.getenv('FIREFOX_PROFILE_DIR', '')

        # 邮箱配置（支持多个，用分号分隔）
        self._load_email_configs()

        logger.info(f"[Config] 配置加载完成")
        logger.info(f"[Config] - Port: {self._port}")
        logger.info(f"[Config] - Max Workers: {self._max_workers}")
        logger.info(f"[Config] - Headless: {self._headless}")
        logger.info(f"[Config] - Email Configs: {len(self._email_configs)}")

    def _load_email_configs(self):
        """加载邮箱配置"""
        self._email_configs = []

        worker_domains = os.getenv('WORKER_DOMAINS', '').split(';')
        email_domains = os.getenv('EMAIL_DOMAINS', '').split(';')
        admin_passwords = os.getenv('ADMIN_PASSWORDS', '').split(';')

        max_len = max(len(worker_domains), len(email_domains), len(admin_passwords))

        for i in range(max_len):
            worker = worker_domains[i].strip() if i < len(worker_domains) else ''
            email = email_domains[i].strip() if i < len(email_domains) else ''
            password = admin_passwords[i].strip() if i < len(admin_passwords) else ''

            if worker and email and password:
                self._email_configs.append({
                    'worker_domain': worker,
                    'email_domain': email,
                    'admin_password': password
                })

        if not self._email_configs:
            logger.warning("[Config] 警告: 未配置邮箱服务！")

    # ==================== Getters ====================

    def get_port(self) -> int:
        return self._port

    def get_debug(self) -> bool:
        return self._debug

    def get_secret_key(self) -> str:
        return self._secret_key

    def get_admin_username(self) -> str:
        return self._admin_username

    def get_admin_password(self) -> str:
        return self._admin_password

    def get_admin_token(self) -> str:
        return self._admin_token

    def get_max_workers(self) -> int:
        with self._lock:
            return self._max_workers

    def get_headless(self) -> bool:
        with self._lock:
            return self._headless

    def get_proxy_server(self) -> str:
        return self._proxy_server

    def get_debug_screenshot_dir(self) -> str:
        return self._debug_screenshot_dir

    def get_human_delay(self) -> Tuple[int, int]:
        """获取人类输入延迟范围 (min_ms, max_ms)"""
        with self._lock:
            return (self._human_delay_min, self._human_delay_max)

    def get_request_interval(self) -> Tuple[int, int]:
        """获取请求间隔范围 (min_s, max_s)"""
        with self._lock:
            return (self._request_interval_min, self._request_interval_max)

    def get_field_delay(self) -> Tuple[float, float]:
        """获取字段输入延迟范围 (min_s, max_s)"""
        with self._lock:
            return (self._field_delay_min, self._field_delay_max)

    def get_cooldown_range(self) -> Tuple[int, int]:
        """获取冷却时间范围 (min_s, max_s)"""
        with self._lock:
            return (self._cooldown_min, self._cooldown_max)

    def get_max_consecutive_failures(self) -> int:
        with self._lock:
            return self._max_consecutive_failures

    def get_single_failure_cooldown(self) -> int:
        return self._single_failure_cooldown

    def get_captcha_cooldown(self) -> int:
        return self._captcha_cooldown

    def get_email_configs(self) -> List[Dict]:
        with self._lock:
            return self._email_configs.copy()

    def get_random_email_config(self) -> Optional[Dict]:
        with self._lock:
            if self._email_configs:
                return random.choice(self._email_configs)
            return None

    def get_fingerprint(self) -> Dict:
        """获取指纹配置"""
        return {
            'window_size': self._window_size,
            'timezone': self._timezone,
            'locale': self._locale,
            'geo_latitude': self._geo_latitude,
            'geo_longitude': self._geo_longitude,
        }

    def get_profile_config(self) -> Dict:
        """获取 Profile 配置"""
        return {
            'config_path': self._profile_config_path,
            'assign_strategy': self._profile_assign_strategy,
            'default_group': self._profile_default_group,
            'bad_ttl': self._profile_bad_ttl,
        }

    def get_auto_recover_config(self) -> Dict:
        """获取自动恢复配置"""
        return {
            'max_retries': self._auto_recover_max_retries,
            'backoff_seconds': self._auto_recover_backoff,
        }

    def get_verification_config(self) -> Dict:
        """获取验证配置"""
        return {
            'sheerid_url': self._sheerid_verify_url,
            'email_code_max_retries': self._email_code_max_retries,
            'email_code_check_interval': self._email_code_check_interval,
            'page_load_timeout': self._page_load_timeout,
            'submit_timeout': self._submit_timeout,
        }

    def get_persistence_config(self) -> Dict:
        """获取持久化配置"""
        return {
            'enabled': self._persist_data,
            'data_dir': self._data_dir,
            'tasks_file': self._tasks_file,
            'results_file': self._results_file,
            'save_debounce': self._save_debounce,
        }

    def get_ipqs_config(self) -> Dict:
        """获取 IPQS 配置"""
        return {
            'api_key': self._ipqs_api_key,
            'max_fraud_score': self._ipqs_max_fraud_score,
        }

    def get_rate_limit_config(self) -> Dict:
        """获取限流配置"""
        return {
            'max_requests': self._rate_limit_max_requests,
            'window_ms': self._rate_limit_window_ms,
        }

    def get_faker_config(self) -> Dict:
        """获取 Faker 配置"""
        return {
            'locale': self._faker_locale,
            'birth_year_min': self._birth_year_min,
            'birth_year_max': self._birth_year_max,
            'discharge_year_min': self._discharge_year_min,
            'discharge_year_max': self._discharge_year_max,
        }

    def get_camoufox_config(self) -> Dict:
        """获取 Camoufox 配置"""
        return {
            'humanize_cursor': self._humanize_cursor,
            'geoip_enabled': self._geoip_enabled,
            'firefox_profile_dir': self._firefox_profile_dir,
            'headless': self._headless,
            'proxy': self._proxy_server,
            'locale': self._locale,
        }


# 全局配置实例
config = Config()
