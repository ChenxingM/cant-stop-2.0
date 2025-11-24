# -*- coding: utf-8 -*-
"""
指令解析器
Command Parser for Can't Stop Game
"""

import re
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class Command:
    """指令对象"""
    type: str  # 指令类型
    params: dict  # 参数
    raw_text: str  # 原始文本


class CommandParser:
    """指令解析器"""

    # 指令模式定义
    PATTERNS = {
        # 基础指令
        'choose_faction': r'^选择阵营[:：]\s*(收养人|Aeonreth)$',
        'help': r'^help$',

        # 游戏进行
        'start_round': r'^轮次开始$',
        'roll_dice': r'^\.r(\d+)d(\d+)$',
        'record_single': r'^(\d+)$',
        'record_double': r'^(\d+)[,，]\s*(\d+)$',
        'end_active': r'^替换永久棋子$',
        'end_passive': r'^进度回退$',
        'finish_checkin': r'^打卡完毕$',

        # 查询
        'get_progress': r'^查看当前进度$',
        'get_inventory': r'^查看背包$',
        'get_achievements': r'^成就一览$',
        'get_shop': r'^道具商店$',

        # 奖励领取
        'claim_reward': r'^领取(.+?)奖励(\d+)([*x×]\d+)?$',
        'claim_super': r'^我超级满意这张图(\d+)$',
        'claim_top': r'^数列(\d+)登顶$',

        # 道具相关
        'buy_item': r'^购买(.+)$',
        'use_item': r'^使用(.+)$',

        # 遭遇/道具选择
        'make_choice': r'^选择[:：]?\s*(.+)$',

        # 特殊功能
        'pet_cat': r'^摸摸喵$',
        'feed_cat': r'^投喂喵$',
        'squeeze_doll': r'^捏捏丑喵玩偶$',
    }

    @classmethod
    def parse(cls, text: str) -> Optional[Command]:
        """
        解析指令文本

        Args:
            text: 用户输入的文本

        Returns:
            Command对象，如果无法识别则返回None
        """
        text = text.strip()

        # 尝试匹配各种指令模式
        for cmd_type, pattern in cls.PATTERNS.items():
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                params = cls._extract_params(cmd_type, match)
                return Command(type=cmd_type, params=params, raw_text=text)

        return None

    @classmethod
    def _extract_params(cls, cmd_type: str, match: re.Match) -> dict:
        """从正则匹配中提取参数"""
        params = {}

        if cmd_type == 'choose_faction':
            params['faction'] = match.group(1)

        elif cmd_type == 'roll_dice':
            params['count'] = int(match.group(1))
            params['sides'] = int(match.group(2))

        elif cmd_type == 'record_single':
            params['values'] = [int(match.group(1))]

        elif cmd_type == 'record_double':
            params['values'] = [int(match.group(1)), int(match.group(2))]

        elif cmd_type == 'claim_reward':
            reward_type = match.group(1).strip()
            count = int(match.group(2))
            multiplier_str = match.group(3)

            # 解析倍数
            multiplier = 1
            if multiplier_str:
                multiplier = int(re.search(r'\d+', multiplier_str).group())

            params['reward_type'] = reward_type
            params['count'] = count
            params['multiplier'] = multiplier

        elif cmd_type == 'claim_super':
            params['count'] = int(match.group(1))

        elif cmd_type == 'claim_top':
            params['column'] = int(match.group(1))

        elif cmd_type == 'buy_item':
            raw_name = match.group(1).strip()
            # 移除可能的"道具"前缀
            if raw_name.startswith('道具'):
                raw_name = raw_name[2:].strip()
            # 移除阵营标签（如 [收养人专用]、[Aeonreth专用]）
            raw_name = re.sub(r'\s*\[.+?专用\]\s*$', '', raw_name)
            params['item_name'] = raw_name.strip()

        elif cmd_type == 'use_item':
            raw_input = match.group(1).strip()
            # 移除可能的"道具"前缀
            if raw_input.startswith('道具'):
                raw_input = raw_input[2:].strip()

            # 尝试分离道具名称和参数
            # 格式1: "一斤鸭梨！ 3,1,6" (骰子点数)
            # 格式2: "一斤鸭梨！ [3,1,6]"
            parts = raw_input.split(maxsplit=1)
            item_name = parts[0]

            # 移除阵营标签（如 [收养人专用]、[Aeonreth专用]）
            item_name = re.sub(r'\s*\[.+?专用\]\s*$', '', item_name)
            params['item_name'] = item_name.strip()

            # 如果有额外参数，尝试解析
            if len(parts) > 1:
                param_str = parts[1].strip()
                # 移除方括号（如果有）
                param_str = param_str.strip('[]')
                # 尝试解析为数字列表（骰子点数，用于一斤鸭梨！等道具）
                try:
                    if ',' in param_str:
                        params['reroll_values'] = [int(x.strip()) for x in param_str.split(',')]
                    else:
                        params['extra_param'] = param_str
                except ValueError:
                    params['extra_param'] = param_str

        elif cmd_type == 'make_choice':
            params['choice'] = match.group(1).strip()

        return params

    @classmethod
    def clean_input(cls, text: str) -> str:
        """
        清理输入文本
        - 移除多余空格
        """
        text = text.strip()
        return text

    @classmethod
    def format_help(cls) -> str:
        """格式化帮助信息"""
        help_text = """
=== 贪骰无厌 2.0 指令帮助 ===

📋 基础操作
• 选择阵营：收养人 / 选择阵营：Aeonreth
• help - 查看此帮助

🎮 游戏进行
• 轮次开始 - 开始新的一轮
• .r6d6 - 投掷6个骰子
• 1,2 - 记录两个数值
• 10 - 记录单个数值
• 替换永久棋子 - 主动结束轮次
• 进度回退 - 被动结束轮次
• 打卡完毕 - 完成打卡，恢复新轮次功能

🔍 查询功能
• 查看当前进度 - 查看地图位置
• 查看背包 - 查看积分和道具
• 成就一览 - 查看所有成就
• 道具商店 - 查看可购买道具

🎁 奖励领取
• 领取草图奖励1 - 领取打卡奖励
• 领取精致小图奖励1 - 领取打卡奖励
• 领取精草大图奖励1 - 领取打卡奖励
• 领取精致大图奖励1 - 领取打卡奖励
• 我超级满意这张图1 - 附加奖励（+30分/张）
• 领取草图奖励1*2 - 双倍奖励
• 数列X登顶 - 领取登顶奖励（X为列号）

🛒 道具商店
• 购买道具名称 - 购买道具
• 使用道具名称 - 使用道具
• 使用一斤鸭梨！ 3,1,6 - 重投指定点数的3个骰子
• 添加道具名称到道具商店 - 解锁道具

🎭 遭遇选择
• 选择：打歌! - 对遭遇进行选择

😺 特殊功能
• 摸摸喵 - 每天限5次
• 投喂喵 - 每天限5次
• 购买丑喵玩偶 - 购买玩偶（150积分）
• 捏捏丑喵玩偶 - 使用玩偶（每天3次）

"""
        return help_text.strip()


# 指令类型到游戏引擎方法的映射
COMMAND_HANDLERS = {
    'choose_faction': 'choose_faction',
    'help': None,  # 特殊处理
    'start_round': 'start_round',
    'roll_dice': 'roll_dice',
    'record_single': 'record_values',
    'record_double': 'record_values',
    'end_active': 'end_round_active',
    'end_passive': 'end_round_passive',
    'finish_checkin': 'finish_checkin',
    'get_progress': 'get_progress',
    'get_inventory': 'get_inventory',
    'get_achievements': 'get_achievements',
    'get_shop': 'get_shop',
    'claim_reward': 'claim_reward',
    'claim_super': 'claim_reward',  # 映射到同一个方法
    'claim_top': 'claim_column_top',
    'buy_item': 'buy_item',
    'use_item': 'use_item',
    'make_choice': 'make_choice',
    'pet_cat': 'pet_cat',
    'feed_cat': 'feed_cat',
    'squeeze_doll': 'squeeze_doll',
}


def test_parser():
    """测试解析器"""
    test_cases = [
        "选择阵营：收养人",
        "选择阵营：Aeonreth",
        "help",
        "轮次开始",
        ".r6d6",
        "7,11",
        "10",
        "替换永久棋子",
        "进度回退",
        "查看当前进度",
        "查看背包",
        "成就一览",
        "道具商店",
        "领取草图奖励1",
        "领取精致大图奖励2",
        "我超级满意这张图3",
        "领取草图奖励1*2",
        "数列7登顶",
        "购买败者○尘",
        "摸摸喵",
        "投喂喵",
        "捏捏丑喵玩偶",
    ]

    print("=== 指令解析测试 ===\n")
    for test in test_cases:
        cleaned = CommandParser.clean_input(test)
        cmd = CommandParser.parse(cleaned)
        if cmd:
            print(f"✓ '{test}'")
            print(f"  类型: {cmd.type}")
            print(f"  参数: {cmd.params}")
        else:
            print(f"✗ '{test}' - 无法识别")
        print()


if __name__ == "__main__":
    test_parser()
