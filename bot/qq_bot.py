# -*- coding: utf-8 -*-
"""
QQ机器人集成 (NapCat)
QQ Bot Integration with NapCat
"""

import json
import asyncio
import aiohttp
import platform
import socket
from typing import Optional, Dict, Callable
from dataclasses import dataclass
import logging
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.game_engine import GameEngine
from engine.command_parser import CommandParser, COMMAND_HANDLERS
from database.schema import init_database

# 版本信息
try:
    from version import VERSION, AUTHOR, PROJECT_NAME
except ImportError:
    VERSION = "dev"
    AUTHOR = "Unknown"
    PROJECT_NAME = "贪骰无厌 2.0"


def get_base_path():
    """获取项目根目录（兼容打包后环境）"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent

def setup_logging():
    """配置日志系统：控制台完整输出 + 文件记录"""
    # 确保logs目录存在
    log_dir = get_base_path() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 生成日志文件名（按启动时间）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"bot_{timestamp}.log"

    # 创建根日志记录器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # 清除已有的处理器
    logger.handlers.clear()

    # 日志格式（完整格式，不省略）
    formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logging.getLogger(__name__), log_file


logger, current_log_file = setup_logging()


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
        self.db_path = db_path
        self.db_conn = init_database(db_path)
        self.game_engine = GameEngine(self.db_conn)
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.running = False
        self.backup_task = None

    async def start(self):
        """启动机器人"""
        self.session = aiohttp.ClientSession()
        self.running = True

        # 启动数据库自动备份任务
        self.backup_task = asyncio.create_task(self._auto_backup_database())

        try:
            await self._connect_websocket()
        except Exception as e:
            logger.error(f"启动机器人失败: {e}")
            await self.stop()

    async def stop(self):
        """停止机器人"""
        self.running = False
        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

    async def _auto_backup_database(self):
        """每10秒自动备份数据库，保留最近24小时的备份"""
        import sqlite3
        import time

        backup_dir = get_base_path() / "data" / "db_backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"数据库自动备份已启动，备份目录: {backup_dir}")

        last_timestamped_backup = 0
        backup_interval = 60  # 每60秒创建一个带时间戳的备份
        retention_seconds = 24 * 60 * 60  # 保留24小时

        while self.running:
            try:
                await asyncio.sleep(60)

                if not self.running:
                    break

                now = time.time()

                # 每10秒更新最新备份
                latest_file = backup_dir / "game_latest.db"
                backup_conn = sqlite3.connect(str(latest_file))
                self.db_conn.backup(backup_conn)
                backup_conn.close()

                # 每分钟创建带时间戳的备份
                if now - last_timestamped_backup >= backup_interval:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    timestamped_file = backup_dir / f"game_{timestamp}.db"
                    backup_conn = sqlite3.connect(str(timestamped_file))
                    self.db_conn.backup(backup_conn)
                    backup_conn.close()
                    last_timestamped_backup = now

                    # 清理超过24小时的旧备份
                    for old_file in backup_dir.glob("game_*.db"):
                        if old_file.name == "game_latest.db":
                            continue
                        try:
                            file_age = now - old_file.stat().st_mtime
                            if file_age > retention_seconds:
                                old_file.unlink()
                        except Exception:
                            pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"数据库备份失败: {e}")

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

        logger.info(f"[收到群消息] 群{group_id} | {nickname}({user_id})\n{message}")

        # 解析纯文本消息
        text_message = self._extract_text(message)
        if not text_message:
            return

        # 管理员专用：SQL 调试命令
        if text_message.strip().upper().startswith('SQL:'):
            response = await self._handle_admin_sql(user_id, text_message.strip())
            if response:
                await self.send_group_message(str(group_id), response, at_qq=user_id)
            return

        # 管理员专用：Python 调试命令
        if text_message.strip().upper().startswith('PY:'):
            response = await self._handle_admin_py(user_id, text_message.strip())
            if response:
                await self.send_group_message(str(group_id), response, at_qq=user_id)
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
        """从消息中提取纯文本，将 at 消息段转换为 @QQ号 格式"""
        if isinstance(message, str):
            return message

        if isinstance(message, list):
            text_parts = []
            for msg_seg in message:
                if isinstance(msg_seg, dict):
                    msg_type = msg_seg.get('type')
                    if msg_type == 'text':
                        text_parts.append(msg_seg.get('data', {}).get('text', ''))
                    elif msg_type == 'at':
                        # 将 at 消息段转换为 @QQ号 格式
                        qq = msg_seg.get('data', {}).get('qq', '')
                        if qq:
                            text_parts.append(f'@{qq}')
            return ''.join(text_parts)

        return ""

    async def _execute_command(self, qq_id: str, nickname: str, command) -> Optional[str]:
        """执行游戏指令"""
        # 确保玩家已注册
        player, is_new = self.game_engine.register_or_get_player(qq_id, nickname)

        # 新玩家注册提示
        welcome_msg = ""
        if is_new:
            welcome_msg = f"🎉 欢迎 {nickname} 加入贪骰无厌！\n请先选择阵营才能开始游戏：\n• 选择阵营：收养人\n• 选择阵营：Aeonreth\n\n"

        # 特殊处理help指令
        if command.type == 'help':
            return welcome_msg + CommandParser.format_help()

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

            return welcome_msg + result.message

        except Exception as e:
            logger.error(f"执行指令失败: {e}", exc_info=True)
            return f"指令执行失败: {str(e)}"

    async def _handle_admin_sql(self, user_id: str, text: str) -> Optional[str]:
        """处理管理员 SQL 调试命令

        格式: SQL:SELECT * FROM players
        仅限 admin_qq 使用
        """
        # 检查是否是管理员
        if not self.config.admin_qq or user_id != self.config.admin_qq:
            return "❌ 权限不足：此命令仅限管理员使用"

        # 提取 SQL 语句
        sql = text[4:].strip()  # 去掉 "SQL:" 前缀
        if not sql:
            return "❌ 请输入 SQL 语句\n格式: SQL:SELECT * FROM players"

        logger.warning(f"[管理员SQL] {user_id} 执行: {sql}")

        try:
            cursor = self.db_conn.cursor()
            cursor.execute(sql)

            # 判断是查询还是修改操作
            if sql.strip().upper().startswith('SELECT'):
                rows = cursor.fetchall()
                if not rows:
                    return "✅ 查询成功，无结果"

                # 获取列名
                col_names = [desc[0] for desc in cursor.description]

                # 格式化输出（限制行数避免消息过长）
                max_rows = 10
                result_lines = [f"📊 查询结果 ({len(rows)} 行):"]
                result_lines.append(" | ".join(col_names))
                result_lines.append("-" * 40)

                for i, row in enumerate(rows[:max_rows]):
                    result_lines.append(" | ".join(str(v) for v in row))

                if len(rows) > max_rows:
                    result_lines.append(f"... 还有 {len(rows) - max_rows} 行未显示")

                return "\n".join(result_lines)
            else:
                # INSERT/UPDATE/DELETE 等修改操作
                self.db_conn.commit()
                return f"✅ 执行成功，影响 {cursor.rowcount} 行"

        except Exception as e:
            self.db_conn.rollback()
            return f"❌ SQL 执行失败: {str(e)}"

    async def _handle_admin_py(self, user_id: str, text: str) -> Optional[str]:
        """处理管理员 Python 调试命令

        格式: PY:engine.player_dao.get_player('123456')
        仅限 admin_qq 使用

        可用变量:
        - engine: GameEngine 实例
        - db: 数据库连接
        - player_dao, position_dao, inventory_dao, state_dao, shop_dao 等
        """
        # 检查是否是管理员
        if not self.config.admin_qq or user_id != self.config.admin_qq:
            return "❌ 权限不足：此命令仅限管理员使用"

        # 提取 Python 代码
        code = text[3:].strip()  # 去掉 "PY:" 前缀
        if not code:
            return ("❌ 请输入 Python 代码\n"
                    "格式: PY:表达式\n\n"
                    "可用变量:\n"
                    "• engine - GameEngine实例\n"
                    "• db - 数据库连接\n"
                    "• player_dao, position_dao, state_dao 等")

        logger.warning(f"[管理员PY] {user_id} 执行: {code}")

        try:
            import io
            import sys
            from contextlib import redirect_stdout, redirect_stderr

            # 准备执行环境
            local_vars = {
                'engine': self.engine,
                'db': self.db_conn,
                'player_dao': self.engine.player_dao,
                'position_dao': self.engine.position_dao,
                'inventory_dao': self.engine.inventory_dao,
                'state_dao': self.engine.state_dao,
                'shop_dao': self.engine.shop_dao,
                'achievement_dao': self.engine.achievement_dao,
                'settings_dao': self.engine.settings_dao,
                'contract_dao': getattr(self.engine, 'contract_dao', None),
            }

            # 捕获输出
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # 尝试作为表达式求值
                try:
                    result = eval(code, {"__builtins__": __builtins__}, local_vars)
                    if result is not None:
                        print(repr(result))
                except SyntaxError:
                    # 如果不是表达式，作为语句执行
                    exec(code, {"__builtins__": __builtins__}, local_vars)

            # 获取输出
            stdout_output = stdout_capture.getvalue()
            stderr_output = stderr_capture.getvalue()

            output_parts = []
            if stdout_output:
                output_parts.append(stdout_output.strip())
            if stderr_output:
                output_parts.append(f"[stderr] {stderr_output.strip()}")

            if output_parts:
                result_text = "\n".join(output_parts)
                # 限制输出长度
                if len(result_text) > 1000:
                    result_text = result_text[:1000] + "\n... (输出已截断)"
                return f"✅ 执行结果:\n{result_text}"
            else:
                return "✅ 执行成功 (无输出)"

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            # 限制错误信息长度
            if len(tb) > 500:
                tb = tb[:500] + "\n..."
            return f"❌ 执行失败:\n{tb}"

    async def send_group_message(self, group_id: str, message: str, at_qq: Optional[str] = None):
        """发送群消息（通过WebSocket）

        Args:
            group_id: 群号
            message: 消息内容（支持 [IMAGE:path] 标记嵌入图片）
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

        # 检查消息中是否有图片标记 [IMAGE:path]
        import re
        from pathlib import Path

        image_pattern = r'\[IMAGE:([^\]]+)\]'
        parts = re.split(image_pattern, message)

        for i, part in enumerate(parts):
            if i % 2 == 0:
                # 文本部分
                if part.strip():
                    message_segments.append({
                        "type": "text",
                        "data": {"text": part}
                    })
            else:
                # 图片路径部分
                image_path = Path(part)
                if not image_path.is_absolute():
                    # 相对路径转绝对路径
                    image_path = get_base_path() / part

                if image_path.exists():
                    # 使用 file:// 协议发送本地图片
                    message_segments.append({
                        "type": "image",
                        "data": {"file": f"file:///{image_path.resolve()}"}
                    })
                    logger.info(f"添加图片: {image_path}")
                else:
                    logger.warning(f"图片文件不存在: {image_path}")
                    message_segments.append({
                        "type": "text",
                        "data": {"text": f"[图片加载失败: {part}]"}
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
            # 完整输出消息内容，图片路径替换为[图片]标记
            text_full = re.sub(image_pattern, '[图片]', message)
            logger.info(f"[发送群消息] 群{group_id}\n{text_full}")
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
            logger.info(f"[发送私聊] 用户{user_id}\n{message}")
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


def get_local_ip():
    """获取本机局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "未知"

async def main():
    """主函数"""
    # 从配置文件加载配置
    config = load_config("config.json")

    # 系统信息
    logger.info("=" * 60)
    logger.info(f"{PROJECT_NAME}")
    logger.info(f"版本: {VERSION}  作者: {AUTHOR}")
    logger.info("=" * 60)
    logger.info("[系统信息]")
    logger.info(f"  操作系统: {platform.system()} {platform.release()}")
    logger.info(f"  系统版本: {platform.version()}")
    logger.info(f"  主机名: {platform.node()}")
    logger.info(f"  本机IP: {get_local_ip()}")
    logger.info(f"  Python: {platform.python_version()}")
    logger.info(f"  架构: {platform.machine()}")
    logger.info("-" * 60)
    logger.info("[运行配置]")
    logger.info(f"  日志文件: {current_log_file}")
    logger.info(f"  WebSocket: {config.ws_url}")
    logger.info(f"  允许群组: {config.allowed_groups}")
    logger.info(f"  自动重连: {'启用' if config.reconnect else '禁用'}")
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
