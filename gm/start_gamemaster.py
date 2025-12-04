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


if __name__ == "__main__":
    config = load_config()
    db_path = config.get('database', {}).get('path', 'data/game.db')
    try:
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            print("❌ 错误: 未安装 PySide6")
            print("\n请安装依赖:")
            print("  pip install PySide6")
            sys.exit(1)

        from gui.gm_window import GMWindow
        app = QApplication(sys.argv)
        window = GMWindow(db_path)
        window.show()
        exit_code = app.exec()
        sys.exit(exit_code)

    except Exception as e:
        print(f"\n\n❌ 启动失败: {e}")
        sys.exit(1)
