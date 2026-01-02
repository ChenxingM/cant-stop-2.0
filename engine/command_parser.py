# -*- coding: utf-8 -*-
"""
指令解析器
Command Parser for Can't Stop Game
"""

import re
from typing import Optional, Tuple, List
from dataclasses import dataclass


# 全角标点到半角标点的映射表
FULLWIDTH_TO_HALFWIDTH = {
    '，': ',',  # 逗号
    '：': ':',  # 冒号
    '；': ';',  # 分号
    '！': '!',  # 感叹号
    '？': '?',  # 问号
    '（': '(',  # 左括号
    '）': ')',  # 右括号
    '【': '[',  # 左方括号
    '】': ']',  # 右方括号
    '「': '"',  # 左角括号 -> 引号
    '」': '"',  # 右角括号 -> 引号
    '『': '"',  # 左双角括号 -> 引号
    '』': '"',  # 右双角括号 -> 引号
    '"': '"',   # 左双引号
    '"': '"',   # 右双引号
    ''': "'",   # 左单引号
    ''': "'",   # 右单引号
    '＂': '"',  # 全角双引号
    '＇': "'",  # 全角单引号
    '～': '~',  # 波浪号
    '＋': '+',  # 加号
    '－': '-',  # 减号
    '＊': '*',  # 星号
    '／': '/',  # 斜杠
    '．': '.',  # 句点
    '　': ' ',  # 全角空格
}


def normalize_punctuation(text: str) -> str:
    """
    将全角标点符号转换为半角标点符号

    Args:
        text: 输入文本

    Returns:
        转换后的文本
    """
    for fullwidth, halfwidth in FULLWIDTH_TO_HALFWIDTH.items():
        text = text.replace(fullwidth, halfwidth)
    return text


@dataclass
class Command:
    """指令对象"""
    type: str  # 指令类型
    params: dict  # 参数
    raw_text: str  # 原始文本


class CommandParser:
    """指令解析器"""

    # 自定义口令关键词列表（精确匹配）
    custom_commands: List[str] = []

    @classmethod
    def set_custom_commands(cls, keywords: List[str]):
        """设置自定义口令关键词列表"""
        cls.custom_commands = keywords

    @classmethod
    def add_custom_command(cls, keyword: str):
        """添加单个自定义口令关键词"""
        if keyword not in cls.custom_commands:
            cls.custom_commands.append(keyword)

    @classmethod
    def remove_custom_command(cls, keyword: str):
        """移除单个自定义口令关键词"""
        if keyword in cls.custom_commands:
            cls.custom_commands.remove(keyword)

    # 指令模式定义
    PATTERNS = {
        # 基础指令
        'choose_faction': r'^选择阵营:\s*(收养人|Aeonreth)$',
        'help': r'^help$',

        # 游戏进行
        'start_round': r'^轮次开始$',
        'roll_dice': r'^\.r(\d+)d(\d+)$',
        'reroll': r'^重投$',
        'record_single': r'^(\d+)$',
        'record_double': r'^(\d+),\s*(\d+)$',
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

        # 特殊效果使用（需要在use_item之前，因为更特定）
        'use_last_dice': r'^使用上轮骰子:?\s*(\d+),(\d+),(\d+)$',  # 使用上轮骰子:3,4,5
        'change_dice': r'^修改骰子:?\s*(\d+),(\d+)$',  # 修改骰子:位置,新值
        'add_3_dice': r'^骰子加3:?\s*(\d+)$',  # 骰子加3:位置

        # 道具相关
        'buy_item': r'^购买(.+)$',
        'use_item': r'^使用(.+)$',

        # 遭遇/道具选择
        'make_choice': r'^选择:?\s*(.+)$',

        # 陷阱选择
        'make_trap_choice': r'^陷阱选择:?\s*(.+)$',

        # 对决系统
        'start_duel': r'^对决\s*@?(\d+)$',  # 对决@QQ号
        'respond_duel': r'^应战$',  # 被@的玩家应战

        # Poke骰对决（玩家主动发起）
        'start_poke_duel': r'^poke骰对决\s*@?(\d+)$',  # poke骰对决@QQ号
        'accept_poke_duel': r'^接受挑战\s*@?(\d+)$',  # 接受挑战@QQ号
        'claim_poke_victory': r'^对战胜利$',  # 对战胜利

        # 特殊功能
        'pet_cat': r'^摸摸喵$',
        'feed_cat': r'^投喂喵$',
        'squeeze_doll': r'^捏捏丑喵玩偶$',

        # 契约系统
        'bind_contract': r'^绑定契约对象\s*@?(\d+)$',
        'view_contract': r'^查看契约$',
        'remove_contract': r'^解除契约$',

        # 特殊触发
        'thanks_fortune': r'^谢谢财神$',

        # 遭遇打卡
        'encounter_checkin': r'^遭遇打卡$',

        # 支线/主线积分领取
        'claim_sideline': r'^支线(\d+)领取$',
        'claim_mainline': r'^主线(\d+)领取$',

        # GM指令：限时打卡
        # 格式：添加限时打卡 遭遇名 成功成就 失败成就 [天数]
        'add_timed_checkin': r'^添加限时打卡\s+(.+?)\s+(.+?)\s+(.+?)(?:\s+(\d+))?$',
        # 查看待完成的限时打卡
        'view_timed_checkins': r'^查看限时打卡$',

        # 支线系统
        'branch_join_solo': r'^支线(\d+)单人$',  # 支线1单人
        'branch_join_duo': r'^支线(\d+)双人\s*@?(\d+)$',  # 支线1双人@QQ号
        'branch_record_points': r'^支线点数总计(\d+)$',  # 支线点数总计200
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
        # 统一全角标点为半角标点
        text = normalize_punctuation(text)

        # 优先检查自定义口令（精确匹配）
        if text in cls.custom_commands:
            return Command(type='custom_command', params={'keyword': text}, raw_text=text)

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
            # 支持的格式:
            # 1. "揍击派对（通用）14,6" - 括号结尾 + 数字坐标
            # 2. "揍击派对（通用） 14,6" - 括号结尾 + 空格 + 数字坐标
            # 3. "揍击派对（通用）（14,6）" - 括号结尾 + 括号包裹的数字
            # 4. "揍击派对 14,6" - 空格分隔 + 坐标
            # 5. "一斤鸭梨！ 3,1,6" - 多个数字
            # 6. "花言巧语（通用）906081155" - 括号结尾 + 单个数字（QQ号）
            # 7. "花言巧语（通用） 906081155" - 括号结尾 + 空格 + 单个数字

            # 先尝试匹配括号包裹的坐标：(14,6)
            bracket_coord_match = re.match(r'^(.+?)\s*\((\d+)\s*,\s*(\d+)\)$', raw_input)
            if bracket_coord_match:
                item_name = bracket_coord_match.group(1).strip()
                param_str = f"{bracket_coord_match.group(2)},{bracket_coord_match.group(3)}"
            else:
                # 匹配：括号结尾 + 可选空格 + 数字参数（坐标格式，带逗号）
                coord_match = re.match(r'^(.+?[\)\]])\s*(\d+\s*,\s*[\d,\s]+)$', raw_input)
                if not coord_match:
                    # 或者：任意内容 + 必须空格 + 数字参数（坐标格式，带逗号）
                    coord_match = re.match(r'^(.+?)\s+(\d+\s*,\s*[\d,\s]+)$', raw_input)
                if coord_match:
                    item_name = coord_match.group(1).strip()
                    param_str = coord_match.group(2).strip()
                else:
                    # 尝试匹配单个数字（如QQ号）：括号结尾 + 可选空格 + 纯数字
                    single_num_match = re.match(r'^(.+?[\)\]])\s*(\d+)$', raw_input)
                    if not single_num_match:
                        # 或者：任意内容 + 空格 + 纯数字
                        single_num_match = re.match(r'^(.+?)\s+(\d+)$', raw_input)
                    if single_num_match:
                        item_name = single_num_match.group(1).strip()
                        param_str = single_num_match.group(2).strip()
                    else:
                        # 没有数字参数，整个输入就是道具名
                        item_name = raw_input
                        param_str = None

            # 移除阵营标签（如 [收养人专用]、[Aeonreth专用]、(通用) 等）
            item_name = re.sub(r'\s*[\[(].*?[\])]\s*$', '', item_name)
            params['item_name'] = item_name.strip()

            # 如果有额外参数，尝试解析
            if param_str:
                # 移除各种括号（如果有）
                param_str = re.sub(r'^[\(\[]+', '', param_str)
                param_str = re.sub(r'[\)\]]+$', '', param_str)
                # 尝试解析为数字列表
                try:
                    if ',' in param_str:
                        numbers = [int(x.strip()) for x in param_str.split(',')]
                        # 如果是2个数字，可能是坐标（用于我的地图等道具）
                        if len(numbers) == 2:
                            params['new_column'] = numbers[0]
                            params['new_position'] = numbers[1]
                        else:
                            # 否则是骰子点数（用于一斤鸭梨！等道具）
                            params['reroll_values'] = numbers
                    else:
                        # 单个数字，可能是QQ号（用于花言巧语等道具）
                        params['target_qq'] = param_str
                except ValueError:
                    params['extra_param'] = param_str

        elif cmd_type == 'make_choice':
            params['choice'] = match.group(1).strip()

        elif cmd_type == 'make_trap_choice':
            params['choice'] = match.group(1).strip()

        elif cmd_type == 'bind_contract':
            params['target_qq'] = match.group(1).strip()

        elif cmd_type == 'start_duel':
            params['target_qq'] = match.group(1).strip()

        elif cmd_type == 'start_poke_duel':
            params['target_qq'] = match.group(1).strip()

        elif cmd_type == 'accept_poke_duel':
            params['challenger_qq'] = match.group(1).strip()

        elif cmd_type == 'use_last_dice':
            params['dice_values'] = [int(match.group(1)), int(match.group(2)), int(match.group(3))]

        elif cmd_type == 'change_dice':
            params['dice_index'] = int(match.group(1))  # 骰子位置（1-6）
            params['new_value'] = int(match.group(2))   # 新值（1-6）

        elif cmd_type == 'add_3_dice':
            params['dice_index'] = int(match.group(1))  # 骰子位置（1-6）

        elif cmd_type == 'claim_sideline':
            params['line_id'] = int(match.group(1))  # 支线编号

        elif cmd_type == 'claim_mainline':
            params['line_id'] = int(match.group(1))  # 主线编号

        elif cmd_type == 'add_timed_checkin':
            params['encounter_name'] = match.group(1)
            params['success_achievement'] = match.group(2)
            params['failure_achievement'] = match.group(3)
            params['days'] = int(match.group(4)) if match.group(4) else 3

        elif cmd_type == 'branch_join_solo':
            params['event_id'] = int(match.group(1))

        elif cmd_type == 'branch_join_duo':
            params['event_id'] = int(match.group(1))
            params['partner_qq'] = match.group(2).strip()

        elif cmd_type == 'branch_record_points':
            params['points'] = int(match.group(1))

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

🛒 道具商店
• 购买道具名称 - 购买道具
• 使用道具名称 - 使用道具
• 使用一斤鸭梨！ 3,1,6 - 重投指定点数的3个骰子
• 使用我的地图 7,5 - 移动陷阱到第7列第5格
• 添加道具名称到道具商店 - 解锁道具

🎭 遭遇/陷阱选择
• 选择：打歌! - 对遭遇进行选择
• 陷阱选择：移动到列11 - 对陷阱进行选择

😺 特殊功能
• 购买丑喵玩偶 - 购买玩偶（150积分）
• 捏捏丑喵玩偶 - 使用玩偶（每天3次）

💕 契约系统
• 绑定契约对象@QQ号 - 与指定玩家建立契约
• 查看契约 - 查看当前契约关系
• 解除契约 - 解除现有契约关系

✨ 特殊效果
• 使用上轮骰子：3,4,5 - 用上轮骰子值替换本轮（时空镜效果）
• 修改骰子：2,6 - 把第2个骰子改成6（红药丸/AI管家/面具Ae效果）
• 骰子加3：2 - 把第2个骰子+3（面具收养人效果）

"""
        return help_text.strip()


# 指令类型到游戏引擎方法的映射
COMMAND_HANDLERS = {
    'choose_faction': 'choose_faction',
    'help': None,  # 特殊处理
    'start_round': 'start_round',
    'roll_dice': 'roll_dice',
    'reroll': 'reroll_dice',
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
    'make_trap_choice': 'make_trap_choice',
    'pet_cat': 'pet_cat',
    'feed_cat': 'feed_cat',
    'squeeze_doll': 'squeeze_doll',
    'bind_contract': 'bind_contract',
    'view_contract': 'view_contract',
    'remove_contract': 'remove_contract',
    'use_last_dice': 'use_last_dice',
    'change_dice': 'change_dice',
    'add_3_dice': 'add_3_dice',
    'start_duel': 'start_duel',
    'respond_duel': 'respond_duel',
    'start_poke_duel': 'start_poke_duel',
    'accept_poke_duel': 'accept_poke_duel',
    'claim_poke_victory': 'claim_poke_victory',
    'thanks_fortune': 'thanks_fortune',
    'encounter_checkin': 'encounter_checkin',
    'claim_sideline': 'claim_sideline',
    'claim_mainline': 'claim_mainline',
    'add_timed_checkin': 'add_timed_checkin',
    'view_timed_checkins': 'view_timed_checkins',
    'custom_command': 'handle_custom_command',
    # 支线系统
    'branch_join_solo': 'branch_join_solo',
    'branch_join_duo': 'branch_join_duo',
    'branch_record_points': 'branch_record_points',
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
