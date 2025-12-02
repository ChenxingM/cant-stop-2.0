# -*- coding: utf-8 -*-
"""
贪骰无厌 2.0 - 游戏本体启动器
启动 QQ 机器人，用于群聊游戏
"""

import sys
import asyncio
from pathlib import Path

# Windows 平台事件循环兼容性修复
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from bot.qq_bot import main


def print_banner():
    """打印启动横幅"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║           贪骰无厌 2.0 - QQ机器人游戏启动器              ║
║           Can't Stop 2.0 - QQ Bot Game Launcher           ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    print_banner()
    print("⚙️  配置文件: config.json")
    print("📂 数据库: data/game.db")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n✅ 游戏机器人已停止")
    except Exception as e:
        print(f"\n\n❌ 启动失败: {e}")
        print("\n请检查:")
        print("  1. config.json 配置是否正确")
        print("  2. OneBot 服务是否运行")
        print("  3. access_token 是否匹配")
        sys.exit(1)
