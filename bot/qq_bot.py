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
    # WebSocket配置
    ws_url: str = "ws://127.0.0.1:3001"
    access_token: str = ""
    reconnect: bool = True
    reconnect_interval: int = 5
    timeout: int = 30

    # HTTP API配置
    http_host: str = "127.0.0.1"
    http_port: int = 3000

    # 机器人配置
    allowed_groups: list = None
    admin_qq: str = ""

    def __post_init__(self):
        if self.allowed_groups is None:
            self.allowed_groups = []


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
        """连接WebSocket（支持重连）"""
        while self.running:
            try:
                await self._do_connect()
                logger.info("WebSocket连接已断开")

                # 如果不需要重连，退出
                if not self.config.reconnect:
                    break

                # 等待一段时间后重连
                logger.info(f"将在 {self.config.reconnect_interval} 秒后重连...")
                await asyncio.sleep(self.config.reconnect_interval)

            except Exception as e:
                logger.error(f"WebSocket连接错误: {e}")

                if not self.config.reconnect:
                    raise

                logger.info(f"将在 {self.config.reconnect_interval} 秒后重连...")
                await asyncio.sleep(self.config.reconnect_interval)

    async def _do_connect(self):
        """执行实际的WebSocket连接"""
        logger.info(f"正在连接到 {self.config.ws_url}...")

        # 准备连接头
        headers = {}
        if self.config.access_token:
            headers['Authorization'] = f'Bearer {self.config.access_token}'

        # 连接WebSocket
        self.ws = await self.session.ws_connect(
            self.config.ws_url,
            headers=headers,
            timeout=self.config.timeout,
            heartbeat=30
        )
        logger.info("WebSocket连接成功")

        # 开始监听消息
        await self._listen_messages()

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
        group_id = data.get('group_id', 0)
        user_id = str(data.get('user_id', ''))
        message = data.get('message', '')
        sender = data.get('sender', {})
        nickname = sender.get('nickname', sender.get('card', '未知'))

        # 只处理允许的群组消息
        if self.config.allowed_groups and group_id not in self.config.allowed_groups:
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
            # 发送回复（@对应玩家）
            await self.send_group_message(str(group_id), response, at_qq=user_id)

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
            # 参数映射和特殊处理
            params = command.params.copy()

            # roll_dice 指令参数映射
            if command.type == 'roll_dice':
                params = {
                    'dice_count': params.get('count', 6)
                    # sides 参数暂时不使用，游戏固定为6面骰子
                }

            # claim_super 指令特殊处理
            elif command.type == 'claim_super':
                params = {
                    'reward_type': '超常发挥',
                    'count': params['count'],
                    'multiplier': 1
                }

            # 调用处理器
            result = handler(qq_id, **params)

            return result.message

        except Exception as e:
            logger.error(f"执行指令失败: {e}", exc_info=True)
            return f"指令执行失败: {str(e)}"

    async def send_group_message(self, group_id: str, message: str, at_qq: Optional[str] = None):
        """发送群消息（通过WebSocket）

        Args:
            group_id: 群号
            message: 消息内容
            at_qq: 要@的QQ号（可选）
        """
        if not self.ws or self.ws.closed:
            logger.error("WebSocket未连接，无法发送消息")
            return

        # 构造消息段
        message_segments = []

        # 如果需要@玩家，添加@消息段
        if at_qq:
            message_segments.append({
                "type": "at",
                "data": {"qq": str(at_qq)}
            })
            message_segments.append({
                "type": "text",
                "data": {"text": " "}  # @后面加个空格
            })

        # 添加文本消息段
        message_segments.append({
            "type": "text",
            "data": {"text": message}
        })

        # OneBot v11 WebSocket API 格式
        action_data = {
            "action": "send_group_msg",
            "params": {
                "group_id": int(group_id),
                "message": message_segments
            }
        }

        try:
            await self.ws.send_json(action_data)
            logger.info(f"发送消息成功: {message[:50]}...")
        except Exception as e:
            logger.error(f"发送消息异常: {e}")

    async def send_private_message(self, user_id: str, message: str):
        """发送私聊消息（通过WebSocket）"""
        if not self.ws or self.ws.closed:
            logger.error("WebSocket未连接，无法发送消息")
            return

        # OneBot v11 WebSocket API 格式
        action_data = {
            "action": "send_private_msg",
            "params": {
                "user_id": int(user_id),
                "message": message
            }
        }

        try:
            await self.ws.send_json(action_data)
            logger.info(f"发送私聊成功: {message[:50]}...")
        except Exception as e:
            logger.error(f"发送私聊异常: {e}")


def load_config(config_path: str = "config.json") -> BotConfig:
    """从文件加载配置"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        ws_config = config_data.get('websocket', {})
        bot_config = config_data.get('bot', {})

        return BotConfig(
            ws_url=ws_config.get('url', 'ws://127.0.0.1:3001'),
            access_token=ws_config.get('access_token', ''),
            reconnect=ws_config.get('reconnect', True),
            reconnect_interval=ws_config.get('reconnect_interval', 5),
            timeout=ws_config.get('timeout', 30),
            http_host=bot_config.get('http_host', '127.0.0.1'),
            http_port=bot_config.get('http_port', 3000),
            allowed_groups=bot_config.get('allowed_groups', []),
            admin_qq=bot_config.get('admin_qq', '')
        )
    except FileNotFoundError:
        logger.warning(f"配置文件 {config_path} 不存在，使用默认配置")
        return BotConfig()
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        return BotConfig()


async def main():
    """主函数"""
    # 从配置文件加载配置
    config = load_config("config.json")

    logger.info("=" * 60)
    logger.info("贪骰无厌 2.0 - QQ机器人")
    logger.info("=" * 60)
    logger.info(f"WebSocket URL: {config.ws_url}")
    logger.info(f"允许的群组: {config.allowed_groups}")
    logger.info(f"重连: {'启用' if config.reconnect else '禁用'}")
    logger.info("=" * 60)

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
