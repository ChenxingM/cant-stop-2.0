# -*- coding: utf-8 -*-
"""
贪骰无厌 2.0 - GameMaster 打包版启动器
"""

import sys
import json
from pathlib import Path

# 获取运行目录 (打包后使用 exe 所在目录的父目录，因为会在主目录 cwd 运行)
if getattr(sys, 'frozen', False):
    # 打包后，cwd 会被设置为主目录
    PROJECT_ROOT = Path.cwd()
else:
    PROJECT_ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(PROJECT_ROOT))


def load_config():
    """加载配置"""
    config_file = PROJECT_ROOT / "config.json"
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


if __name__ == "__main__":
    config = load_config()
    db_path = config.get('database', {}).get('path', 'data/game.db')

    try:
        from PySide6.QtWidgets import QApplication
        from gui.gm_window import GMWindow

        app = QApplication(sys.argv)
        window = GMWindow(db_path)
        window.show()
        exit_code = app.exec()
        sys.exit(exit_code)

    except ImportError as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 启动失败: {e}")
        sys.exit(1)
