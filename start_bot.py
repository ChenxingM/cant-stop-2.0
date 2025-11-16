# -*- coding: utf-8 -*-
"""
启动QQ机器人
"""

import asyncio
import json
from pathlib import Path

from bot.qq_bot import QQBot, BotConfig


def load_config():
    """加载配置"""
    config_file = Path(__file__).parent / "config.json"
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


async def main():
    """主函数"""
    print("=" * 60)
    print("贪骰无厌 2.0 - QQ机器人")
    print("=" * 60)

    # 加载配置
    config_data = load_config()
    bot_config = config_data.get('bot', {})

    config = BotConfig(
        http_host=bot_config.get('http_host', '127.0.0.1'),
        http_port=bot_config.get('http_port', 3000),
        ws_host=bot_config.get('ws_host', '127.0.0.1'),
        ws_port=bot_config.get('ws_port', 3001),
        admin_qq=bot_config.get('admin_qq', ''),
        group_id=bot_config.get('group_id', '')
    )

    print(f"\n配置信息:")
    print(f"  HTTP: {config.http_host}:{config.http_port}")
    print(f"  WebSocket: {config.ws_host}:{config.ws_port}")
    print(f"  游戏群号: {config.group_id or '未配置（将处理所有群消息）'}")
    print()

    # 创建并启动机器人
    bot = QQBot(config, db_path=config_data.get('database', {}).get('path', 'data/game.db'))

    try:
        print("正在启动机器人...")
        await bot.start()

        # 保持运行
        print("机器人已启动，按 Ctrl+C 停止")
        while bot.running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n正在停止机器人...")
    except Exception as e:
        print(f"错误: {e}")
    finally:
        await bot.stop()
        print("机器人已停止")


if __name__ == "__main__":
    asyncio.run(main())
