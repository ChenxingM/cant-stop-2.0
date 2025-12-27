# -*- coding: utf-8 -*-
"""
贪骰无厌 2.0 - 打包版启动器
用于 PyInstaller 打包后的启动逻辑
"""

import sys
import asyncio
import subprocess
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 获取运行目录 (打包后是 _MEIPASS，开发时是脚本目录)
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).parent

sys.path.insert(0, str(PROJECT_ROOT))

from bot.qq_bot import main


def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           Can't Stop 2.0 - QQ Bot Game Launcher           ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)


def start_gamemaster():
    """启动 GameMaster GUI (打包版)"""
    gm_exe = PROJECT_ROOT / "GameMaster" / "GameMaster.exe"
    if gm_exe.exists():
        try:
            # 在主目录运行，这样 GameMaster 能找到 data/game.db
            subprocess.Popen(
                [str(gm_exe)],
                cwd=str(PROJECT_ROOT),
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            )
            print("✅ GameMaster GUI 已启动")
        except Exception as e:
            print(f"⚠️ GameMaster 启动失败: {e}")
    else:
        print(f"⚠️ GameMaster 不存在: {gm_exe}")


if __name__ == "__main__":
    print_banner()
    print("配置文件: config.json")
    print("数据库: data/game.db")
    print()

    start_gamemaster()
    print()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✅ 游戏机器人已停止")
    except Exception as e:
        print(f"\n\n❌ 启动失败: {e}")
        sys.exit(1)
