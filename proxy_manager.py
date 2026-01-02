"""
代理池管理器 - 支持 HTTP/HTTPS/SOCKS5 代理轮换
"""
import threading
import time
import logging
import random
from typing import List, Optional, Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ProxyManager:
    """代理池管理器"""

    def __init__(
        self,
        proxy_list: List[str],
        strategy: str = "round_robin",  # round_robin | random
        bad_proxy_ttl: int = 900,  # 失败代理的冷却时间（秒）
    ):
        """
        初始化代理池

        Args:
            proxy_list: 代理列表，格式：
                - http://ip:port
                - http://user:pass@ip:port
                - socks5://ip:port
            strategy: 分配策略
                - round_robin: 轮询
                - random: 随机
            bad_proxy_ttl: 失败代理的冷却时间（秒）
        """
        self._lock = threading.Lock()

        # 验证并存储代理列表
        self._all_proxies = [p.strip() for p in proxy_list if p.strip()]
        self._validate_proxies()

        # 可用代理列表
        self._available_proxies = self._all_proxies.copy()

        # 失败代理记录 {proxy: failed_timestamp}
        self._bad_proxies: Dict[str, float] = {}

        self.strategy = strategy
        self.bad_proxy_ttl = bad_proxy_ttl

        # 轮询索引
        self._round_robin_index = 0

        logger.info(f"[ProxyManager] 初始化完成，共 {len(self._all_proxies)} 个代理")
        logger.info(f"[ProxyManager] 策略: {strategy}, 失败冷却: {bad_proxy_ttl}s")

    def _validate_proxies(self):
        """验证代理格式"""
        valid_proxies = []
        for proxy in self._all_proxies:
            if self._is_valid_proxy(proxy):
                valid_proxies.append(proxy)
            else:
                logger.warning(f"[ProxyManager] 无效代理格式: {proxy}")

        self._all_proxies = valid_proxies

        if not self._all_proxies:
            logger.error("[ProxyManager] 没有有效的代理！")

    def _is_valid_proxy(self, proxy: str) -> bool:
        """检查代理格式是否有效"""
        try:
            parsed = urlparse(proxy)

            # 检查协议
            if parsed.scheme not in ['http', 'https', 'socks5', 'socks4']:
                return False

            # 检查主机和端口
            if not parsed.hostname or not parsed.port:
                return False

            return True
        except Exception:
            return False

    def get_proxy(self) -> Optional[str]:
        """
        获取一个可用代理

        Returns:
            代理字符串，如果没有可用代理则返回 None
        """
        with self._lock:
            # 先恢复冷却完成的代理
            self._recover_bad_proxies()

            if not self._available_proxies:
                logger.warning("[ProxyManager] 没有可用代理！")
                return None

            if self.strategy == "round_robin":
                proxy = self._get_round_robin()
            else:  # random
                proxy = random.choice(self._available_proxies)

            logger.info(f"[ProxyManager] 分配代理: {self._mask_proxy(proxy)}")
            return proxy

    def _get_round_robin(self) -> str:
        """轮询获取代理"""
        proxy = self._available_proxies[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(self._available_proxies)
        return proxy

    def _recover_bad_proxies(self):
        """恢复冷却完成的代理"""
        current_time = time.time()
        recovered = []

        for proxy, failed_time in list(self._bad_proxies.items()):
            if current_time - failed_time >= self.bad_proxy_ttl:
                # 恢复代理
                if proxy not in self._available_proxies:
                    self._available_proxies.append(proxy)
                del self._bad_proxies[proxy]
                recovered.append(proxy)

        if recovered:
            logger.info(f"[ProxyManager] 恢复 {len(recovered)} 个代理")

    def mark_bad(self, proxy: str):
        """
        标记代理为失败

        Args:
            proxy: 失败的代理
        """
        with self._lock:
            if proxy not in self._all_proxies:
                return

            # 记录失败时间
            self._bad_proxies[proxy] = time.time()

            # 从可用列表中移除
            if proxy in self._available_proxies:
                self._available_proxies.remove(proxy)

            logger.warning(f"[ProxyManager] 标记失败代理: {self._mask_proxy(proxy)}")
            logger.info(f"[ProxyManager] 剩余可用代理: {len(self._available_proxies)}/{len(self._all_proxies)}")

    def mark_success(self, proxy: str):
        """
        标记代理为成功（从失败列表移除）

        Args:
            proxy: 成功的代理
        """
        with self._lock:
            if proxy in self._bad_proxies:
                del self._bad_proxies[proxy]
                if proxy not in self._available_proxies:
                    self._available_proxies.append(proxy)
                logger.info(f"[ProxyManager] 代理恢复成功: {self._mask_proxy(proxy)}")

    def get_stats(self) -> Dict:
        """获取代理池统计信息"""
        with self._lock:
            return {
                "total": len(self._all_proxies),
                "available": len(self._available_proxies),
                "bad": len(self._bad_proxies),
                "strategy": self.strategy,
                "proxies": [self._mask_proxy(p) for p in self._available_proxies],
            }

    def _mask_proxy(self, proxy: str) -> str:
        """隐藏代理中的密码"""
        try:
            parsed = urlparse(proxy)
            if parsed.username and parsed.password:
                # 隐藏密码
                return f"{parsed.scheme}://{parsed.username}:***@{parsed.hostname}:{parsed.port}"
            return proxy
        except Exception:
            return proxy


def parse_proxy_format(line: str, default_protocol: str = 'http') -> Optional[str]:
    """
    智能解析代理格式并转换为标准格式

    支持格式：
        - ip:port → http://ip:port
        - ip:port:user:pass → http://user:pass@ip:port
        - user:pass@ip:port → http://user:pass@ip:port
        - http://ip:port (原样)
        - socks5://user:pass@ip:port (原样)

    Args:
        line: 代理字符串
        default_protocol: 默认协议（http/socks5）

    Returns:
        标准格式代理，解析失败返回 None
    """
    line = line.strip()
    if not line:
        return None

    # 已经是标准格式
    if line.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
        return line

    # 提取协议（如果指定）
    protocol = default_protocol
    if line.startswith('socks5:'):
        protocol = 'socks5'
        line = line[7:]  # 移除 "socks5:"
    elif line.startswith('http:'):
        protocol = 'http'
        line = line[5:]  # 移除 "http:"

    # 移除可能的 //
    line = line.lstrip('/')

    # 格式 1: user:pass@ip:port
    if '@' in line:
        auth, host_port = line.rsplit('@', 1)
        if ':' in host_port:
            return f"{protocol}://{auth}@{host_port}"

    # 格式 2: ip:port:user:pass
    parts = line.split(':')
    if len(parts) == 4:
        ip, port, user, password = parts
        return f"{protocol}://{user}:{password}@{ip}:{port}"

    # 格式 3: ip:port
    if len(parts) == 2:
        ip, port = parts
        return f"{protocol}://{ip}:{port}"

    # 无法解析
    logger.warning(f"[ProxyManager] 无法解析代理格式: {line}")
    return None


def load_proxies_from_file(file_path: str, default_protocol: str = 'http') -> List[str]:
    """
    从文件加载代理列表（支持多种格式自动转换）

    文件格式（每行一个代理）：
        ip:port
        ip:port:user:pass
        user:pass@ip:port
        http://ip:port
        socks5://user:pass@ip:port

    Args:
        file_path: 代理列表文件路径
        default_protocol: 默认协议（http/socks5）

    Returns:
        代理列表（标准格式）
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        proxies = []
        for line in lines:
            proxy = parse_proxy_format(line, default_protocol)
            if proxy:
                proxies.append(proxy)

        logger.info(f"[ProxyManager] 从文件加载了 {len(proxies)}/{len(lines)} 个代理: {file_path}")
        return proxies
    except FileNotFoundError:
        logger.error(f"[ProxyManager] 代理文件不存在: {file_path}")
        return []
    except Exception as e:
        logger.error(f"[ProxyManager] 加载代理文件失败: {e}")
        return []


def load_proxies_from_env(env_value: str, default_protocol: str = 'http') -> List[str]:
    """
    从环境变量加载代理列表（支持多种格式自动转换）

    格式（分号或换行分隔）：
        ip1:port;ip2:port
        http://ip1:port;socks5://ip2:port

    Args:
        env_value: 环境变量值
        default_protocol: 默认协议（http/socks5）

    Returns:
        代理列表（标准格式）
    """
    if not env_value:
        return []

    # 支持分号或换行分隔
    if ';' in env_value:
        lines = [p.strip() for p in env_value.split(';') if p.strip()]
    else:
        lines = [p.strip() for p in env_value.split('\n') if p.strip()]

    proxies = []
    for line in lines:
        proxy = parse_proxy_format(line, default_protocol)
        if proxy:
            proxies.append(proxy)

    logger.info(f"[ProxyManager] 从环境变量加载了 {len(proxies)}/{len(lines)} 个代理")
    return proxies
