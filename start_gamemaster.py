# -*- coding: utf-8 -*-
"""
贪骰无厌 2.0 - GameMaster 启动器
启动 GM 管理界面，用于游戏管理和数据查看
"""

import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


def load_config():
    """加载配置"""
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def print_banner():
    """打印启动横幅"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║         贪骰无厌 2.0 - GameMaster 管理界面                ║
║         Can't Stop 2.0 - GameMaster Control Panel         ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    print_banner()

    config = load_config()
    db_path = config.get('database', {}).get('path', 'data/game.db')

    print(f"📂 数据库路径: {db_path}")

    try:
        # 检查依赖
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            print("❌ 错误: 未安装 PySide6")
            print("\n请安装依赖:")
            print("  pip install PySide6")
            sys.exit(1)

        from gui.gm_window import GMWindow

        # 创建应用
        app = QApplication(sys.argv)

        # 创建主窗口
        window = GMWindow(db_path)
        window.show()

        print("✅ GM 界面已启动")
        print("   关闭窗口以退出\n")

        # 运行应用
        exit_code = app.exec()

        print("\n✅ GM 界面已关闭")
        sys.exit(exit_code)

    except Exception as e:
        print(f"\n\n❌ 启动失败: {e}")
        print("\n请检查:")
        print("  1. PySide6 是否已安装")
        print("  2. 数据库文件是否存在")
        print("  3. gui/gm_window.py 是否正确")
        sys.exit(1)
