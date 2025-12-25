"""
Veterans Verify - 退伍军人数据管理
基于 BIRLS 数据库的真实公开信息
"""
import csv
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# SheerID 表单支持的军种选项
SHEERID_BRANCHES = [
    "Air Force",
    "Army",
    "Coast Guard",
    "Marine Corps",
    "Navy",
    "Space Force"
]

# BIRLS 数据库军种代码映射
BRANCH_MAPPING = {
    # Air Force 相关
    "AIR FORCE": "Air Force",
    "AF": "Air Force",
    "USAF": "Air Force",
    "ANG": "Air Force",  # Air National Guard
    "AIR NATIONAL GUARD": "Air Force",

    # Army 相关
    "ARMY": "Army",
    "A": "Army",
    "USA": "Army",
    "ARNG": "Army",  # Army National Guard
    "ARMY NATIONAL GUARD": "Army",
    "NG": "Army",  # National Guard (默认 Army)

    # Coast Guard
    "COAST GUARD": "Coast Guard",
    "CG": "Coast Guard",
    "USCG": "Coast Guard",

    # Marine Corps
    "MARINE CORPS": "Marine Corps",
    "MARINES": "Marine Corps",
    "M": "Marine Corps",
    "MC": "Marine Corps",
    "USMC": "Marine Corps",

    # Navy
    "NAVY": "Navy",
    "N": "Navy",
    "USN": "Navy",

    # Space Force (较新，BIRLS 可能没有)
    "SPACE FORCE": "Space Force",
    "SF": "Space Force",
    "USSF": "Space Force",
}


class VeteranDataManager:
    """退伍军人数据管理器"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        self.birls_csv = self.data_dir / "birls_update.csv"
        self.processed_json = self.data_dir / "veterans_processed.json"
        self.used_json = self.data_dir / "veterans_used.json"

        self.veterans: List[Dict] = []
        self.used_ids: set = set()

        self._load_data()

    def _load_data(self):
        """加载数据"""
        # 加载已处理的数据
        if self.processed_json.exists():
            with open(self.processed_json, 'r', encoding='utf-8') as f:
                self.veterans = json.load(f)
            logger.info(f"已加载 {len(self.veterans)} 条预处理数据")

        # 加载已使用记录
        if self.used_json.exists():
            with open(self.used_json, 'r', encoding='utf-8') as f:
                self.used_ids = set(json.load(f))
            logger.info(f"已加载 {len(self.used_ids)} 条已使用记录")

    def _save_used(self):
        """保存已使用记录"""
        with open(self.used_json, 'w', encoding='utf-8') as f:
            json.dump(list(self.used_ids), f)

    def _normalize_branch(self, branch_raw: str) -> Optional[str]:
        """将 BIRLS 军种代码映射到 SheerID 格式"""
        branch_upper = branch_raw.upper().strip()
        return BRANCH_MAPPING.get(branch_upper)

    def process_birls_csv(self, min_birth_year: int = 1980, max_birth_year: int = 2005):
        """
        处理 BIRLS CSV 文件，筛选符合条件的记录

        条件：
        1. 出生年份在 min_birth_year ~ max_birth_year 之间
        2. 有完整的姓名 (first + last)
        3. 有可识别的军种
        """
        if not self.birls_csv.exists():
            logger.error(f"BIRLS CSV 文件不存在: {self.birls_csv}")
            return 0

        logger.info(f"开始处理 BIRLS CSV: {self.birls_csv}")

        valid_records = []
        seen_keys = set()  # 去重

        with open(self.birls_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 解析出生日期
                dob = row.get('dob', '').strip()
                if not dob or '-' not in dob:
                    continue

                try:
                    birth_year = int(dob.split('-')[0])
                except ValueError:
                    continue

                if not (min_birth_year <= birth_year <= max_birth_year):
                    continue

                # 解析姓名
                first_name = row.get('first', '').strip().title()
                last_name = row.get('last', '').strip().title()

                if not first_name or not last_name:
                    continue

                # 解析军种
                branch_raw = row.get('branch_1', '').strip()
                branch = self._normalize_branch(branch_raw)

                if not branch:
                    continue

                # 创建唯一键用于去重
                unique_key = f"{first_name}_{last_name}_{dob}"
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)

                # 解析出生日期为字典格式
                dob_parts = dob.split('-')
                birth_date = {
                    "year": dob_parts[0],
                    "month": self._month_num_to_name(int(dob_parts[1])),
                    "day": str(int(dob_parts[2]))  # 去掉前导零
                }

                valid_records.append({
                    "id": unique_key,
                    "first_name": first_name,
                    "last_name": last_name,
                    "birth_date": birth_date,
                    "branch": branch,
                    "source": "BIRLS"
                })

        # 保存处理后的数据
        self.veterans = valid_records
        with open(self.processed_json, 'w', encoding='utf-8') as f:
            json.dump(valid_records, f, indent=2, ensure_ascii=False)

        logger.info(f"处理完成，共 {len(valid_records)} 条有效记录")
        return len(valid_records)

    @staticmethod
    def _month_num_to_name(month_num: int) -> str:
        """月份数字转名称"""
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        return months[month_num - 1] if 1 <= month_num <= 12 else "January"

    def get_random_veteran(self) -> Optional[Dict]:
        """
        获取一个随机的未使用的退伍军人信息

        返回格式：
        {
            "first_name": "John",
            "last_name": "Smith",
            "birth_date": {"month": "March", "day": "15", "year": "1985"},
            "branch": "Army",
            "discharge_date": {"month": "August", "day": "20", "year": "2024"}  # 随机生成
        }
        """
        if not self.veterans:
            logger.error("没有可用的退伍军人数据，请先运行 process_birls_csv()")
            return None

        # 筛选未使用的记录
        available = [v for v in self.veterans if v["id"] not in self.used_ids]

        if not available:
            logger.warning("所有记录都已使用，重置使用记录")
            self.used_ids.clear()
            self._save_used()
            available = self.veterans

        # 随机选择
        veteran = random.choice(available)

        # 标记为已使用
        self.used_ids.add(veteran["id"])
        self._save_used()

        # 生成随机退伍日期（过去 1-11 个月）
        discharge_date = self._generate_random_discharge_date()

        return {
            "first_name": veteran["first_name"],
            "last_name": veteran["last_name"],
            "birth_date": veteran["birth_date"],
            "branch": veteran["branch"],
            "discharge_date": discharge_date
        }

    def _generate_random_discharge_date(self) -> Dict[str, str]:
        """
        生成随机退伍日期（过去 1-11 个月内）

        SheerID 要求退伍日期必须在过去 12 个月内
        """
        today = datetime.now()

        # 随机 1-11 个月前
        months_ago = random.randint(1, 11)

        # 计算日期
        discharge_date = today - timedelta(days=months_ago * 30 + random.randint(0, 25))

        return {
            "month": self._month_num_to_name(discharge_date.month),
            "day": str(discharge_date.day),
            "year": str(discharge_date.year)
        }

    def get_stats(self) -> Dict:
        """获取数据统计"""
        return {
            "total": len(self.veterans),
            "used": len(self.used_ids),
            "available": len(self.veterans) - len(self.used_ids),
            "branches": self._count_by_branch()
        }

    def _count_by_branch(self) -> Dict[str, int]:
        """按军种统计"""
        counts = {}
        for v in self.veterans:
            branch = v.get("branch", "Unknown")
            counts[branch] = counts.get(branch, 0) + 1
        return counts


# 测试
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    manager = VeteranDataManager()

    # 如果没有处理过数据，先处理
    if not manager.veterans:
        print("处理 BIRLS 数据...")
        count = manager.process_birls_csv()
        print(f"处理完成: {count} 条记录")

    # 统计
    stats = manager.get_stats()
    print(f"\n数据统计:")
    print(f"  总数: {stats['total']}")
    print(f"  已用: {stats['used']}")
    print(f"  可用: {stats['available']}")
    print(f"\n按军种分布:")
    for branch, count in sorted(stats['branches'].items(), key=lambda x: -x[1]):
        print(f"  {branch}: {count}")

    # 获取随机记录
    print(f"\n随机获取 3 条记录:")
    for i in range(3):
        vet = manager.get_random_veteran()
        if vet:
            print(f"  {i+1}. {vet['first_name']} {vet['last_name']}")
            print(f"     生日: {vet['birth_date']['month']} {vet['birth_date']['day']}, {vet['birth_date']['year']}")
            print(f"     军种: {vet['branch']}")
            print(f"     退伍: {vet['discharge_date']['month']} {vet['discharge_date']['day']}, {vet['discharge_date']['year']}")
