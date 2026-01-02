"""
Camoufox Profile 管理器

功能：
- 为每个账号创建独立的 Profile 目录
- 持久化浏览器指纹、Cookies、LocalStorage
- 避免重复登录和验证

Profile 目录结构：
    profiles/
        ├── email_hash_1/    # 账号1的 Profile
        ├── email_hash_2/    # 账号2的 Profile
        └── ...
"""
import os
import hashlib
import shutil
from pathlib import Path
from typing import Optional
import logging

from database import get_account_by_email, update_account

logger = logging.getLogger(__name__)


# Profile 根目录
PROFILES_ROOT = Path("profiles")
PROFILES_ROOT.mkdir(exist_ok=True)


def get_email_hash(email: str) -> str:
    """
    生成邮箱的哈希值（用于目录名）

    为什么不直接用邮箱？
    - 邮箱包含特殊字符（@、.），不适合做目录名
    - 哈希值固定长度，便于管理
    """
    return hashlib.md5(email.encode()).hexdigest()[:16]


def get_profile_path(email: str) -> Path:
    """获取账号的 Profile 目录路径"""
    email_hash = get_email_hash(email)
    return PROFILES_ROOT / email_hash


def create_profile(email: str) -> Path:
    """
    为账号创建 Profile 目录

    Returns:
        Profile 目录路径
    """
    profile_path = get_profile_path(email)

    if profile_path.exists():
        logger.info(f"[Profile] 已存在: {email} -> {profile_path}")
        return profile_path

    # 创建目录
    profile_path.mkdir(parents=True, exist_ok=True)

    # 保存到数据库
    update_account(email, profile_path=str(profile_path))

    logger.info(f"[Profile] 创建成功: {email} -> {profile_path}")
    return profile_path


def delete_profile(email: str) -> bool:
    """
    删除账号的 Profile 目录

    用途：
    - 账号被封禁，需要清理
    - 重置指纹，重新开始

    Returns:
        是否成功删除
    """
    profile_path = get_profile_path(email)

    if not profile_path.exists():
        logger.warning(f"[Profile] 不存在，无法删除: {email}")
        return False

    try:
        shutil.rmtree(profile_path)
        update_account(email, profile_path=None)
        logger.info(f"[Profile] 删除成功: {email} -> {profile_path}")
        return True
    except Exception as e:
        logger.error(f"[Profile] 删除失败: {e}")
        return False


def get_or_create_profile(email: str) -> Path:
    """
    获取或创建账号的 Profile 目录

    工作流程：
    1. 检查数据库是否有 profile_path
    2. 如果有且目录存在，直接返回
    3. 否则创建新 Profile
    """
    account = get_account_by_email(email)

    # 数据库有记录，检查目录是否存在
    if account and account.get('profile_path'):
        profile_path = Path(account['profile_path'])
        if profile_path.exists():
            logger.debug(f"[Profile] 使用已有: {email} -> {profile_path}")
            return profile_path
        else:
            logger.warning(f"[Profile] 数据库记录的目录不存在，重新创建")

    # 创建新 Profile
    return create_profile(email)


def list_profiles() -> list:
    """
    列出所有 Profile 目录

    Returns:
        [(email, profile_path, size_mb), ...]
    """
    from database import get_accounts

    accounts = get_accounts()
    results = []

    for acc in accounts:
        email = acc['email']
        profile_path = acc.get('profile_path')

        if profile_path:
            path = Path(profile_path)
            if path.exists():
                # 计算目录大小
                size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                size_mb = size / (1024 * 1024)
                results.append((email, str(path), round(size_mb, 2)))

    return results


def cleanup_orphaned_profiles():
    """
    清理孤立的 Profile 目录

    孤立 = Profile 目录存在，但数据库中没有对应账号
    """
    from database import get_accounts

    accounts = get_accounts()
    email_hashes = {get_email_hash(acc['email']) for acc in accounts}

    cleaned = 0
    for profile_dir in PROFILES_ROOT.iterdir():
        if profile_dir.is_dir() and profile_dir.name not in email_hashes:
            logger.info(f"[Profile] 清理孤立目录: {profile_dir}")
            shutil.rmtree(profile_dir)
            cleaned += 1

    logger.info(f"[Profile] 清理完成，删除 {cleaned} 个孤立目录")
    return cleaned


if __name__ == "__main__":
    # 测试脚本
    logging.basicConfig(level=logging.INFO)

    print("=== Profile 管理器测试 ===\n")

    # 测试邮箱
    test_email = "test@009025.xyz"

    # 1. 创建 Profile
    print(f"1. 创建 Profile: {test_email}")
    profile = create_profile(test_email)
    print(f"   路径: {profile}\n")

    # 2. 获取 Profile
    print(f"2. 获取已有 Profile")
    profile2 = get_or_create_profile(test_email)
    assert profile == profile2
    print(f"   路径相同: {profile == profile2}\n")

    # 3. 列出所有 Profile
    print("3. 列出所有 Profile:")
    for email, path, size in list_profiles():
        print(f"   {email} -> {path} ({size} MB)")
    print()

    # 4. 删除 Profile
    print(f"4. 删除 Profile")
    delete_profile(test_email)
    print(f"   已删除: {not profile.exists()}\n")
