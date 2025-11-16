# -*- coding: utf-8 -*-
"""
启动GM管理界面
"""

import json
from pathlib import Path
from gui.gm_window import main


def load_config():
    """加载配置"""
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    print("=" * 60)
    print("贪骰无厌 2.0 - GM管理界面")
    print("=" * 60)

    config = load_config()
    db_path = config.get('database', {}).get('path', 'data/game.db')

    print(f"\n数据库路径: {db_path}")
    print("正在启动GUI...")

    # 注意: 需要将db_path传递给GUI
    import sys
    from PySide6.QtWidgets import QApplication
    from gui.gm_window import GMWindow

    app = QApplication(sys.argv)
    window = GMWindow(db_path)
    window.show()

    sys.exit(app.exec())
