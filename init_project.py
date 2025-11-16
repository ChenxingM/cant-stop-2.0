# -*- coding: utf-8 -*-
"""
项目初始化脚本
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.schema import init_database


def main():
    """初始化项目"""
    print("=" * 60)
    print("贪骰无厌 2.0 - 项目初始化")
    print("=" * 60)

    # 1. 创建数据目录
    print("\n[1/3] 创建数据目录...")
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)
    print("[OK] 数据目录已创建: data/")

    # 2. 初始化数据库
    print("\n[2/3] 初始化数据库...")
    db_path = str(data_dir / "game.db")
    conn = init_database(db_path)

    # 显示所有表
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()

    print("[OK] 数据库已创建:", db_path)
    print("\n已创建的表:")
    for table in tables:
        print(f"  - {table[0]}")

    # 3. 检查配置文件
    print("\n[3/3] 检查配置文件...")
    config_file = project_root / "config.json"
    if config_file.exists():
        print("[OK] 配置文件已存在: config.json")
        print("\n请编辑 config.json 文件，配置:")
        print("  - bot.group_id: 游戏群号")
        print("  - bot.admin_qq: 管理员QQ号")
    else:
        print("⚠ 配置文件不存在，请手动创建 config.json")

    conn.close()

    print("\n" + "=" * 60)
    print("初始化完成！")
    print("=" * 60)
    print("\n下一步:")
    print("  1. 编辑 config.json 配置文件")
    print("  2. 启动 NapCat")
    print("  3. 运行 python start_bot.py 启动机器人")
    print("  4. 运行 python start_gm.py 启动GM界面（可选）")
    print("\n详细说明请查看 README.md")


if __name__ == "__main__":
    main()
