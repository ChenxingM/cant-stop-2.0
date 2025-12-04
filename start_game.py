# -*- coding: utf-8 -*-
"""
贪骰无厌 2.0 - 游戏本体启动器
启动 QQ 机器人，用于群聊游戏
同时启动 GameMaster 管理界面
"""

import sys
import asyncio
import subprocess
from pathlib import Path

# Windows 平台事件循环兼容性修复
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.qq_bot import main


def print_banner():
    """打印启动横幅"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           Can't Stop 2.0 - QQ Bot Game Launcher           ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)


def start_gamemaster():
    """在子进程中启动 GameMaster GUI"""
    gm_script = PROJECT_ROOT / "gm" / "start_gamemaster.py"
    if gm_script.exists():
        try:
            # 使用 subprocess.Popen 启动独立进程，不等待其完成
            subprocess.Popen(
                [sys.executable, str(gm_script)],
                cwd=str(PROJECT_ROOT),
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            )
            print("✅ GameMaster GUI 已启动")
        except Exception as e:
            print(f"⚠️ GameMaster 启动失败: {e}")
    else:
        print(f"⚠️ GameMaster 脚本不存在: {gm_script}")


if __name__ == "__main__":
    print_banner()
    print("配置文件: config.json")
    print("数据库: data/game.db")
    print()

    # 启动 GameMaster GUI
    start_gamemaster()
    print()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✅ 游戏机器人已停止")
    except Exception as e:
        print(f"\n\n❌ 启动失败: {e}")
        sys.exit(1)
