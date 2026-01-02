"""
环境变量同步工具

功能：
- 从 .env.example 读取所有参数（包含注释和说明）
- 合并到 .env 文件
- 保留 .env 中已有的配置值
- 只添加新增的参数（使用 example 中的默认值）
- 保留所有注释和格式

使用：
    python scripts/sync_env.py
"""
import os
import re
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent
ENV_EXAMPLE = ROOT_DIR / ".env.example"
ENV_FILE = ROOT_DIR / ".env"


def parse_env_file(file_path: Path) -> dict:
    """
    解析 .env 文件，提取所有 KEY=VALUE

    Returns:
        {
            'KEY1': 'value1',
            'KEY2': 'value2',
            ...
        }
    """
    if not file_path.exists():
        return {}

    env_vars = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith('#'):
                continue

            # 匹配 KEY=VALUE（支持引号）
            match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', line)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                env_vars[key] = value

    return env_vars


def merge_env_files():
    """
    合并 .env.example 和 .env

    逻辑：
    1. 读取 .env.example 的所有内容（包含注释）
    2. 读取 .env 的所有 KEY=VALUE
    3. 遍历 example，如果 KEY 在 .env 中存在，替换为 .env 的值
    4. 如果 KEY 在 .env 中不存在，使用 example 的默认值（新增参数）
    5. 写入到 .env
    """
    if not ENV_EXAMPLE.exists():
        print(f"[错误] {ENV_EXAMPLE} 不存在")
        return False

    # 1. 解析 .env（已有配置）
    existing_env = parse_env_file(ENV_FILE)
    print(f"[读取] 已有配置: {len(existing_env)} 个参数")

    # 2. 读取 .env.example 的所有行（保留注释和格式）
    with open(ENV_EXAMPLE, 'r', encoding='utf-8') as f:
        example_lines = f.readlines()

    # 3. 合并逻辑
    merged_lines = []
    added_count = 0
    updated_count = 0

    for line in example_lines:
        stripped = line.strip()

        # 注释或空行：直接保留
        if not stripped or stripped.startswith('#'):
            merged_lines.append(line)
            continue

        # KEY=VALUE 行
        match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', stripped)
        if match:
            key = match.group(1)
            example_value = match.group(2).strip()

            # 如果 .env 中已有这个 KEY，使用已有值
            if key in existing_env:
                merged_lines.append(f"{key}={existing_env[key]}\n")
                updated_count += 1
            else:
                # 新参数，使用 example 的默认值
                merged_lines.append(f"{key}={example_value}\n")
                added_count += 1
                print(f"  [+] 新增参数: {key}={example_value}")
        else:
            # 无法解析的行，直接保留
            merged_lines.append(line)

    # 4. 写入到 .env
    backup_file = ENV_FILE.with_suffix('.env.backup')
    if ENV_FILE.exists():
        # 备份原文件
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            backup_content = f.read()
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(backup_content)
        print(f"[备份] 已备份原文件到: {backup_file}")

    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.writelines(merged_lines)

    print(f"\n[完成] 同步完成!")
    print(f"   - 保留参数: {updated_count} 个")
    print(f"   - 新增参数: {added_count} 个")
    print(f"   - 输出文件: {ENV_FILE}")

    if added_count > 0:
        print(f"\n[提示] 请检查新增参数，根据需要修改默认值")

    return True


if __name__ == "__main__":
    import sys
    # 设置 UTF-8 输出（避免 Windows 编码问题）
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    print("="*60)
    print("Veterans Verify - 环境变量同步工具")
    print("="*60)
    print()

    if not ENV_EXAMPLE.exists():
        print(f"[错误] {ENV_EXAMPLE} 不存在")
        exit(1)

    if not ENV_FILE.exists():
        print(f"[提示] {ENV_FILE} 不存在，将创建新文件")
        print()

    # 确认操作
    if ENV_FILE.exists():
        print(f"[警告] 此操作会修改 {ENV_FILE}")
        print(f"       原文件将备份到 {ENV_FILE}.backup")
        confirm = input("\n是否继续？(y/n): ").strip().lower()
        if confirm != 'y':
            print("[取消] 已取消操作")
            exit(0)

    print()
    merge_env_files()
