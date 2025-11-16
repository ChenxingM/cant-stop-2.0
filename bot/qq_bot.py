# -*- coding: utf-8 -*-
"""
QQ机器人集成 (NapCat)
QQ Bot Integration with NapCat
"""

import json
import asyncio
import aiohttp
from typing import Optional, Dict, Callable
from dataclasses import dataclass
import logging

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.game_engine import GameEngine
from engine.command_parser import CommandParser, COMMAND_HANDLERS
from database.schema import init_database


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """机器人配置"""
    http_host: str = "127.0.0.1"
    http_port: int = 3000
    ws_host: str = "127.0.0.1"
    ws_port: int = 3001
    admin_qq: str = ""  # 管理员QQ号
    group_id: str = ""  # 游戏群号


class QQBot:
    """QQ机器人主类"""

    def __init__(self, config: BotConfig, db_path: str = "data/game.db"):
        self.config = config
        self.db_conn = init_database(db_path)
        self.game_engine = GameEngine(self.db_conn)
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.running = False

    async def start(self):
        """启动机器人"""
        self.session = aiohttp.ClientSession()
        self.running = True

        try:
            await self._connect_websocket()
        except Exception as e:
            logger.error(f"启动机器人失败: {e}")
            await self.stop()

    async def stop(self):
        """停止机器人"""
        self.running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

    async def _connect_websocket(self):
        """连接WebSocket"""
        ws_url = f"ws://{self.config.ws_host}:{self.config.ws_port}"
        logger.info(f"正在连接到 {ws_url}...")

        try:
            self.ws = await self.session.ws_connect(ws_url)
            logger.info("WebSocket连接成功")

            # 开始监听消息
            await self._listen_messages()

        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            raise

    async def _listen_messages(self):
        """监听消息"""
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await self._handle_message(data)
                except Exception as e:
                    logger.error(f"处理消息失败: {e}")

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket错误: {self.ws.exception()}")
                break

    async def _handle_message(self, data: Dict):
        """处理接收到的消息"""
        # 解析消息类型
        post_type = data.get('post_type')

        if post_type == 'message':
            message_type = data.get('message_type')
            if message_type == 'group':
                # 群消息
                await self._handle_group_message(data)

    async def _handle_group_message(self, data: Dict):
        """处理群消息"""
        group_id = str(data.get('group_id', ''))
        user_id = str(data.get('user_id', ''))
        message = data.get('message', '')
        sender = data.get('sender', {})
        nickname = sender.get('nickname', sender.get('card', '未知'))

        # 只处理目标群的消息
        if self.config.group_id and group_id != self.config.group_id:
            return

        logger.info(f"[群{group_id}] {nickname}({user_id}): {message}")

        # 解析纯文本消息
        text_message = self._extract_text(message)
        if not text_message:
            return

        # 清理并解析指令
        cleaned_text = CommandParser.clean_input(text_message)
        command = CommandParser.parse(cleaned_text)

        if not command:
            # 不是游戏指令，忽略
            return

        # 处理指令
        response = await self._execute_command(user_id, nickname, command)

        if response:
            # 发送回复
            await self.send_group_message(group_id, response)

    def _extract_text(self, message) -> str:
        """从消息中提取纯文本"""
        if isinstance(message, str):
            return message

        if isinstance(message, list):
            text_parts = []
            for msg_seg in message:
                if isinstance(msg_seg, dict) and msg_seg.get('type') == 'text':
                    text_parts.append(msg_seg.get('data', {}).get('text', ''))
            return ''.join(text_parts)

        return ""

    async def _execute_command(self, qq_id: str, nickname: str, command) -> Optional[str]:
        """执行游戏指令"""
        # 确保玩家已注册
        self.game_engine.register_or_get_player(qq_id, nickname)

        # 特殊处理help指令
        if command.type == 'help':
            return CommandParser.format_help()

        # 获取对应的游戏引擎方法
        handler_name = COMMAND_HANDLERS.get(command.type)
        if not handler_name:
            return "未知指令"

        # 调用游戏引擎方法
        handler = getattr(self.game_engine, handler_name, None)
        if not handler:
            return f"指令处理器未实现: {handler_name}"

        try:
            # 特殊处理claim_super
            if command.type == 'claim_super':
                command.params = {
                    'reward_type': '超常发挥',
                    'count': command.params['count'],
                    'multiplier': 1
                }

            # 调用处理器
            result = handler(qq_id, **command.params)

            return result.message

        except Exception as e:
            logger.error(f"执行指令失败: {e}", exc_info=True)
            return f"指令执行失败: {str(e)}"

    async def send_group_message(self, group_id: str, message: str):
        """发送群消息"""
        url = f"http://{self.config.http_host}:{self.config.http_port}/send_group_msg"

        data = {
            "group_id": int(group_id),
            "message": message
        }

        try:
            async with self.session.post(url, json=data) as resp:
                if resp.status == 200:
                    logger.info(f"发送消息成功: {message[:50]}...")
                else:
                    logger.error(f"发送消息失败: {resp.status}")

        except Exception as e:
            logger.error(f"发送消息异常: {e}")

    async def send_private_message(self, user_id: str, message: str):
        """发送私聊消息"""
        url = f"http://{self.config.http_host}:{self.config.http_port}/send_private_msg"

        data = {
            "user_id": int(user_id),
            "message": message
        }

        try:
            async with self.session.post(url, json=data) as resp:
                if resp.status == 200:
                    logger.info(f"发送私聊成功: {message[:50]}...")
                else:
                    logger.error(f"发送私聊失败: {resp.status}")

        except Exception as e:
            logger.error(f"发送私聊异常: {e}")


async def main():
    """主函数"""
    # 配置
    config = BotConfig(
        http_host="127.0.0.1",
        http_port=3000,
        ws_host="127.0.0.1",
        ws_port=3001,
        admin_qq="",  # 填写管理员QQ
        group_id=""   # 填写游戏群号
    )

    # 创建并启动机器人
    bot = QQBot(config)

    try:
        await bot.start()
        # 保持运行
        while bot.running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("收到停止信号")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
