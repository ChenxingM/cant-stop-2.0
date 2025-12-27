# -*- coding: utf-8 -*-
"""
Can't Stop 2.0 - Game Simulator V3
考虑遭遇、陷阱、道具效果的完整模拟器
"""

import random
import sys
import io
import os
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
from itertools import combinations
import statistics

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 尝试导入matplotlib并设置后端
MATPLOTLIB_AVAILABLE = False
try:
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端，必须在import pyplot之前
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    pass

# ==================== 棋盘配置 ====================

COLUMN_HEIGHTS = {
    3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9,
    10: 10, 11: 10,
    12: 9, 13: 8, 14: 7, 15: 6, 16: 5, 17: 4, 18: 3,
}

VALID_COLUMNS = list(range(3, 19))
WIN_CONDITION = 3  # 改为1列测试
COST_PER_ROLL = 10

# 棋盘格子数据: 列号 -> [(类型, ID, 名称), ...]
# E=遭遇, I=道具, T=陷阱
BOARD_DATA = {
    3: [("E", 3, "河…土地神"), ("I", 10, ":）"), ("T", 13, "中空格子")],
    4: [("E", 5, "小花"), ("I", 16, "The Room"), ("T", 14, "OAS阿卡利亚"), ("E", 57, "初次见面")],
    5: [("E", 7, "多多益善"), ("T", 19, "没有空军"), ("I", 8, "缩小药水"), ("E", 23, "bika"), ("E", 45, "AeAe少女")],
    6: [("E", 8, "一些手"), ("E", 26, "嘴"), ("T", 1, "小小火球术"), ("I", 17, "我的地图"), ("E", 36, "清理大师"), ("E", 58, "冥府之路")],
    7: [("E", 19, "自助问答"), ("E", 43, "节奏大师"), ("E", 15, "豆腐脑"), ("T", 3, "婚戒"), ("I", 1, "败者尘"), ("I", 22, "火人雕像"), ("E", 52, "循环往复")],
    8: [("I", 15, "一斤鸭梨"), ("E", 22, "人才市场"), ("E", 10, "突击检查"), ("T", 18, "非请勿入"), ("I", 4, "揍击派对"), ("E", 25, "房产中介"), ("E", 37, "饥寒交迫"), ("E", 56, "真实的经历")],
    9: [("E", 38, "法庭"), ("I", 11, "闹Ae魔镜"), ("E", 18, "积木"), ("E", 16, "神奇小药丸"), ("E", 21, "葡萄蔷薇紫苑"), ("E", 53, "回廊"), ("T", 9, "传送门"), ("I", 20, "Biango Meow"), ("T", 17, "滴答滴答")],
    10: [("E", 48, "故事书"), ("E", 30, "舞蹈"), ("I", 5, "沉重的巨剑"), ("T", 8, "中门对狙"), ("E", 1, "喵"), ("I", 9, "超级大炮"), ("T", 4, "白色天钩"), ("E", 33, "骰之歌"), ("E", 50, "身影"), ("E", 46, "来真的")],
    11: [("E", 39, "谁要走"), ("T", 11, "犹豫就会败北"), ("I", 6, "女巫魔法伎俩"), ("E", 44, "解约厨房"), ("E", 20, "恭喜你"), ("T", 2, "不要回头"), ("E", 51, "狂野"), ("E", 59, "名字"), ("E", 4, "财神福利"), ("I", 18, "五彩宝石")],
    12: [("E", 55, "美术展"), ("E", 14, "代价"), ("E", 35, "面具"), ("T", 5, "紧闭的大门"), ("I", 2, "放飞小"), ("E", 31, "双人成列"), ("T", 15, "魔女的小屋"), ("E", 49, "一千零一"), ("I", 24, "灵魂之叶")],
    13: [("E", 27, "奇异的菜肴"), ("E", 9, "螂的诱惑"), ("E", 34, "警报"), ("T", 6, "奇变偶不变"), ("E", 24, "保护好脑子"), ("I", 3, "花言巧语"), ("E", 54, "天下无程序员"), ("I", 23, "冰人雕像")],
    14: [("E", 40, "黄金薯片"), ("I", 12, "小女孩娃娃"), ("T", 7, "雷电法王"), ("E", 32, "广场舞"), ("E", 12, "信仰之跃"), ("I", 21, "黑喵"), ("E", 60, "浓雾之中")],
    15: [("E", 41, "我吗"), ("E", 6, "一位绅士"), ("T", 12, "七色章鱼"), ("E", 11, "大撒币"), ("I", 14, "阈限空间"), ("E", 47, "魔女的藏书室")],
    16: [("E", 28, "钓鱼大赛"), ("E", 13, "卡布奇诺"), ("I", 7, "变大蘑菇"), ("T", 20, "LUCKY DAY"), ("E", 42, "新衣服")],
    17: [("E", 17, "造大桥"), ("E", 29, "冷笑话"), ("T", 17, "滴答滴答"), ("I", 19, "购物卡")],
    18: [("E", 2, "梦"), ("I", 13, "火堆"), ("T", 10, "扎扎实实")],
}


# ==================== 效果定义 ====================

# 遭遇效果分类 (基于实际游戏效果)
# 正面: 获得积分、免费回合、前进等
# 负面: 失去积分、后退、暂停等
# 中性: 需要选择、随机结果等

ENCOUNTER_EFFECTS = {
    # ID: (平均积分变化, 平均位置变化, 暂停回合, 其他描述)
    # 正面遭遇
    1: (20, 0, 0, "喵-获得20积分"),
    4: (50, 0, 0, "财神福利-获得50积分"),
    11: (30, 0, 0, "大撒币-平均获得30积分"),
    20: (20, 0, 0, "恭喜你-获得20积分"),

    # 负面遭遇
    5: (0, 0, 1, "小花-可能暂停1回合"),
    8: (-10, 0, 0, "一些手-可能失去10积分"),
    26: (-15, 0, 1, "嘴-可能暂停或失去积分"),
    45: (-20, 0, 0, "AeAe少女-需要答题,失败扣分"),

    # 中性遭遇 (平均效果)
    2: (0, 0, 0, "梦-随机效果"),
    3: (10, 0, 0, "土地神-可能获得积分"),
    6: (-5, 0, 0, "一位绅士-赌博,平均略负"),
    7: (5, 1, 0, "多多益善-可能获得额外骰子"),
    9: (-5, 0, 0, "螂的诱惑-可能失去积分"),
    10: (0, 0, 0, "突击检查-随机效果"),
    12: (0, 1, 0, "信仰之跃-可能前进"),
    13: (5, 0, 0, "卡布奇诺-获得小奖励"),
    14: (-10, 0, 0, "代价-需要付出代价"),
    15: (0, 0, 0, "豆腐脑-选择题"),
    16: (5, 0, 0, "神奇小药丸-随机效果"),
    17: (10, 0, 0, "造大桥-合作任务奖励"),
    18: (0, 0, 0, "积木-选择题"),
    19: (0, 0, 0, "自助问答-答题"),
    21: (0, 0, 0, "葡萄蔷薇紫苑-选择"),
    22: (0, 0, 0, "人才市场-随机"),
    23: (-5, 0, 0, "bika-可能扣分"),
    24: (-10, 0, 0, "保护好脑子-可能扣分"),
    25: (0, 0, 0, "房产中介-随机"),
    27: (-5, 0, 0, "奇异的菜肴-可能负面"),
    28: (15, 0, 0, "钓鱼大赛-可能获奖"),
    29: (5, 0, 0, "冷笑话-小奖励"),
    30: (0, 0, 0, "舞蹈-随机"),
    31: (10, 0, 0, "双人成列-合作奖励"),
    32: (5, 0, 0, "广场舞-小奖励"),
    33: (0, 0, 0, "骰之歌-随机效果"),
    34: (-10, 0, 0, "警报-可能扣分"),
    35: (0, 0, 0, "面具-选择"),
    36: (10, 0, 0, "清理大师-奖励"),
    37: (-15, 0, 0, "饥寒交迫-扣分"),
    38: (-5, 0, 0, "法庭-可能扣分"),
    39: (0, -1, 0, "谁要走-可能后退"),
    40: (10, 0, 0, "黄金薯片-奖励"),
    41: (-5, 0, 0, "我吗-可能扣分"),
    42: (5, 0, 0, "新衣服-小奖励"),
    43: (0, 0, 0, "节奏大师-游戏"),
    44: (0, 0, 0, "解约厨房-选择"),
    46: (20, 0, 0, "来真的-大奖励"),
    47: (10, 0, 0, "魔女藏书室-奖励"),
    48: (5, 0, 0, "故事书-小奖励"),
    49: (15, 0, 0, "一千零一-奖励"),
    50: (0, 0, 0, "身影-随机"),
    51: (10, 0, 0, "狂野-奖励"),
    52: (0, -1, 0, "循环往复-可能后退"),
    53: (0, 0, 0, "回廊-随机"),
    54: (0, 0, 0, "天下无程序员-随机"),
    55: (10, 0, 0, "美术展-获得道具"),
    56: (0, 0, 0, "真实经历-随机"),
    57: (5, 0, 0, "初次见面-小奖励"),
    58: (0, -1, 0, "冥府之路-可能后退"),
    59: (5, 0, 0, "名字-小奖励"),
    60: (0, 0, 0, "浓雾之中-随机"),
}

# 陷阱效果
TRAP_EFFECTS = {
    # ID: (平均积分变化, 平均位置变化, 暂停回合, 失败概率增加, 描述)
    1: (-10, 0, 0, 0, "小小火球术-固定骰子"),
    2: (0, -2, 0, 0, "不要回头-后退2格"),
    3: (-20, 0, 0, 0, "婚戒-扣积分或暂停"),
    4: (0, -1, 0, 0, "白色天钩-后退1格"),
    5: (0, 0, 0, 0.1, "紧闭的大门-禁用某列"),
    6: (0, 0, 0, 0.2, "奇变偶不变-额外检定"),
    7: (-30, 0, 0, 0, "雷电法王-大量扣分"),
    8: (0, 0, 0, 0.15, "中门对狙-决斗风险"),
    9: (0, 0, 0, 0, "传送门-随机传送"),
    10: (0, -1, 0, 0, "扎扎实实-后退1格"),
    11: (0, 0, 0, 0.1, "犹豫就会败北-快速决策"),
    12: (-15, 0, 0, 0, "七色章鱼-扣分"),
    13: (0, 0, 1, 0, "中空格子-暂停1回合"),
    14: (-10, 0, 0, 0, "OAS阿卡利亚-扣分"),
    15: (-20, 0, 0, 0.1, "魔女的小屋-负面效果"),
    17: (0, 0, 0, 0, "滴答滴答-限时"),
    18: (0, 0, 0, 0.1, "非请勿入-禁止进入"),
    19: (0, 0, 0, 0.05, "没有空军-限制骰子"),
    20: (30, 2, 0, 0, "LUCKY DAY-正面效果"),
}

# 道具效果 (获得道具时的价值)
ITEM_VALUES = {
    # ID: 平均价值
    1: 15,   # 败者尘
    2: 20,   # 放飞小
    3: 25,   # 花言巧语
    4: 15,   # 揍击派对
    5: 20,   # 沉重的巨剑
    6: 15,   # 女巫魔法伎俩
    7: 15,   # 变大蘑菇
    8: 10,   # 缩小药水
    9: 30,   # 超级大炮
    10: 10,  # :)
    11: 20,  # 闹Ae魔镜
    12: 15,  # 小女孩娃娃
    13: 10,  # 火堆
    14: 25,  # 阈限空间
    15: 10,  # 一斤鸭梨
    16: 20,  # The Room
    17: 15,  # 我的地图
    18: 20,  # 五彩宝石
    19: 15,  # 购物卡
    20: 10,  # Biango Meow
    21: 15,  # 黑喵
    22: 15,  # 火人雕像
    23: 15,  # 冰人雕像
    24: 20,  # 灵魂之叶
}


# ==================== 数据结构 ====================

@dataclass
class SimulationResult:
    """单次模拟结果"""
    total_cost: int = 0
    total_rolls: int = 0
    total_rounds: int = 0
    failed_rounds: int = 0
    topped_columns: List[int] = field(default_factory=list)
    won: bool = False
    encounters_triggered: int = 0
    traps_triggered: int = 0
    items_collected: int = 0
    score_from_events: int = 0


@dataclass
class PlayerState:
    """玩家状态"""
    permanent_positions: Dict[int, int] = field(default_factory=dict)
    temp_positions: Dict[int, int] = field(default_factory=dict)
    topped_columns: Set[int] = field(default_factory=set)
    visited_cells: Dict[int, Set[int]] = field(default_factory=lambda: defaultdict(set))

    total_cost: int = 0
    total_rolls: int = 0
    total_rounds: int = 0
    failed_rounds: int = 0

    # 事件统计
    encounters_triggered: int = 0
    traps_triggered: int = 0
    items_collected: int = 0
    score_from_events: int = 0

    # 临时状态
    skip_rounds: int = 0
    extra_fail_chance: float = 0
    free_rolls: int = 0
    bonus_score: int = 0


# ==================== 游戏逻辑 ====================

def roll_dice(count: int = 6) -> List[int]:
    """投掷骰子"""
    return [random.randint(1, 6) for _ in range(count)]


def get_possible_sums(dice: List[int]) -> List[Tuple[int, int]]:
    """获取所有可能的两组和"""
    from itertools import combinations

    if len(dice) != 6:
        return []

    possible = set()
    for indices in combinations(range(6), 3):
        group1 = [dice[i] for i in indices]
        group2 = [dice[i] for i in range(6) if i not in indices]
        sum1, sum2 = sum(group1), sum(group2)
        possible.add((min(sum1, sum2), max(sum1, sum2)))

    return list(possible)


def get_cell_at_position(column: int, position: int) -> Optional[Tuple[str, int, str]]:
    """获取指定位置的格子信息"""
    if column not in BOARD_DATA:
        return None
    cells = BOARD_DATA[column]
    if 0 < position <= len(cells):
        return cells[position - 1]
    return None


def process_cell_effect(state: PlayerState, column: int, position: int, luck: str = "normal") -> Tuple[int, int, str]:
    """
    处理格子效果
    luck: "best" = 最佳运气, "worst" = 最差运气, "normal" = 普通运气
    返回: (积分变化, 位置变化, 效果描述)
    """
    cell = get_cell_at_position(column, position)
    if cell is None:
        return 0, 0, ""

    cell_type, cell_id, cell_name = cell

    # 检查是否已访问过
    if position in state.visited_cells[column]:
        return 0, 0, ""

    state.visited_cells[column].add(position)

    # 运气系数
    if luck == "best":
        luck_mult = 2.0      # 好事翻倍
        bad_luck_mult = 0.2  # 坏事减少80%
        skip_chance = 0.1    # 暂停概率很低
        fail_mult = 0.3      # 失败概率增加很少
    elif luck == "worst":
        luck_mult = 0.3      # 好事减少70%
        bad_luck_mult = 2.0  # 坏事翻倍
        skip_chance = 0.9    # 暂停概率很高
        fail_mult = 2.0      # 失败概率增加翻倍
    else:
        luck_mult = 1.0
        bad_luck_mult = 1.0
        skip_chance = 0.5
        fail_mult = 1.0

    if cell_type == "E":
        # 遭遇
        state.encounters_triggered += 1
        effect = ENCOUNTER_EFFECTS.get(cell_id, (0, 0, 0, "未知遭遇"))
        score_change, pos_change, skip_rounds, desc = effect

        # 应用运气
        if score_change > 0:
            score_change = int(score_change * luck_mult * random.uniform(0.8, 1.2))
        elif score_change < 0:
            score_change = int(score_change * bad_luck_mult * random.uniform(0.8, 1.2))

        if pos_change < 0:
            pos_change = int(pos_change * bad_luck_mult)

        if skip_rounds > 0 and random.random() < skip_chance:
            state.skip_rounds += skip_rounds

        state.score_from_events += score_change
        return score_change, pos_change, f"遭遇:{cell_name}"

    elif cell_type == "T":
        # 陷阱
        state.traps_triggered += 1
        effect = TRAP_EFFECTS.get(cell_id, (0, 0, 0, 0, "未知陷阱"))
        score_change, pos_change, skip_rounds, fail_increase, desc = effect

        # 特殊处理 LUCKY DAY (ID 20) - 这是正面陷阱
        if cell_id == 20:
            score_change = int(score_change * luck_mult)
            pos_change = int(pos_change * luck_mult)
        else:
            # 负面陷阱
            score_change = int(score_change * bad_luck_mult)
            pos_change = int(pos_change * bad_luck_mult)
            fail_increase = fail_increase * fail_mult

        if skip_rounds > 0:
            state.skip_rounds += skip_rounds

        if fail_increase > 0:
            state.extra_fail_chance += fail_increase

        state.score_from_events += score_change
        return score_change, pos_change, f"陷阱:{cell_name}"

    elif cell_type == "I":
        # 道具
        state.items_collected += 1
        value = ITEM_VALUES.get(cell_id, 10)
        # 道具价值转换为等效积分
        equiv_score = int(value * 0.5 * luck_mult)
        state.bonus_score += equiv_score
        return equiv_score, 0, f"道具:{cell_name}"

    return 0, 0, ""


def choose_best_sums(possible_sums: List[Tuple[int, int]],
                     state: PlayerState,
                     temp_markers_used: int) -> Optional[Tuple[int, int]]:
    """选择最优的组合"""
    best_choice = None
    best_score = -1

    for sum1, sum2 in possible_sums:
        score = 0
        valid_moves = []
        local_temp_used = temp_markers_used

        for col in [sum1, sum2]:
            if col not in VALID_COLUMNS:
                continue
            if col in state.topped_columns:
                continue

            can_move = False
            if col in state.temp_positions:
                can_move = True
                score += 100
            elif local_temp_used < 3:
                if col in state.permanent_positions:
                    score += 50
                can_move = True
                local_temp_used += 1

            if can_move:
                valid_moves.append(col)
                current_pos = state.temp_positions.get(col, state.permanent_positions.get(col, 0))
                height = COLUMN_HEIGHTS[col]
                progress = (current_pos + 1) / height
                score += progress * 30

                if col in [10, 11]:
                    score += 10
                elif col in [7, 8, 9, 12, 13, 14]:
                    score += 5

        if valid_moves and score > best_score:
            best_score = score
            best_choice = (sum1, sum2)

    return best_choice


def simulate_one_roll(state: PlayerState, temp_markers_used: int, luck: str = "normal") -> Tuple[bool, int, List[int], int]:
    """
    模拟一次投骰
    返回: (是否成功, 使用的临时标记数, 移动的列, 事件积分变化)
    """
    dice = roll_dice(6)
    possible_sums = get_possible_sums(dice)

    choice = choose_best_sums(possible_sums, state, temp_markers_used)

    if choice is None:
        # 检查是否因为额外失败概率导致失败
        if state.extra_fail_chance > 0 and random.random() < state.extra_fail_chance:
            state.extra_fail_chance = 0  # 重置
            return False, temp_markers_used, [], 0

        if temp_markers_used >= 3 or len(state.temp_positions) >= 3:
            return False, temp_markers_used, [], 0
        if len(state.temp_positions) > 0:
            return False, temp_markers_used, [], 0
        return False, temp_markers_used, [], 0

    moved_columns = []
    event_score = 0
    sum1, sum2 = choice

    for col in [sum1, sum2]:
        if col not in VALID_COLUMNS:
            continue
        if col in state.topped_columns:
            continue

        if col in state.temp_positions:
            old_pos = state.temp_positions[col]
            new_pos = old_pos + 1
            state.temp_positions[col] = new_pos
            moved_columns.append(col)

            # 处理格子效果
            score_change, pos_change, _ = process_cell_effect(state, col, new_pos, luck)
            event_score += score_change

            # 应用位置变化
            if pos_change != 0:
                state.temp_positions[col] = max(1, new_pos + pos_change)

        elif temp_markers_used < 3 and len(state.temp_positions) < 3:
            start_pos = state.permanent_positions.get(col, 0)
            new_pos = start_pos + 1
            state.temp_positions[col] = new_pos
            temp_markers_used += 1
            moved_columns.append(col)

            # 处理格子效果
            score_change, pos_change, _ = process_cell_effect(state, col, new_pos, luck)
            event_score += score_change

            if pos_change != 0:
                state.temp_positions[col] = max(1, new_pos + pos_change)

    return True, temp_markers_used, moved_columns, event_score


def should_continue(state: PlayerState, rolls_this_round: int,
                    greedy: float = 0.6) -> bool:
    """决定是否继续投骰"""
    temp = state.temp_positions

    if not temp:
        return True

    # 检查是否有登顶
    for col, pos in temp.items():
        if pos >= COLUMN_HEIGHTS[col]:
            return False

    total_progress = sum(temp.values())
    temp_count = len(temp)

    # 考虑额外失败风险
    fail_risk = 0.15 + state.extra_fail_chance

    if temp_count >= 3:
        if total_progress >= 4:
            return random.random() < greedy * 0.4 * (1 - fail_risk)
        return random.random() < greedy * 0.6 * (1 - fail_risk)
    elif rolls_this_round >= 5 and total_progress >= 4:
        return random.random() < greedy * 0.5 * (1 - fail_risk)
    elif rolls_this_round >= 7:
        return random.random() < greedy * 0.3 * (1 - fail_risk)

    return True


def simulate_one_round(state: PlayerState, greedy: float = 0.6,
                       max_rolls_per_round: int = 50, luck: str = "normal") -> bool:
    """
    模拟一轮游戏
    返回: 是否成功结束
    """
    # 检查暂停
    if state.skip_rounds > 0:
        state.skip_rounds -= 1
        state.total_cost += COST_PER_ROLL  # 暂停也消耗积分
        return False

    temp_markers_used = 0
    state.temp_positions = {}
    rolls_this_round = 0
    round_event_score = 0

    while rolls_this_round < max_rolls_per_round:
        # 检查免费回合
        if state.free_rolls > 0:
            state.free_rolls -= 1
        else:
            state.total_cost += COST_PER_ROLL

        state.total_rolls += 1
        rolls_this_round += 1

        success, temp_markers_used, moved_columns, event_score = simulate_one_roll(
            state, temp_markers_used, luck
        )
        round_event_score += event_score

        if not success:
            state.temp_positions = {}
            state.failed_rounds += 1
            state.extra_fail_chance = 0  # 重置额外失败概率
            return False

        # 检查登顶
        topped_this_roll = []
        for col in moved_columns:
            if col in state.temp_positions:
                if state.temp_positions[col] >= COLUMN_HEIGHTS[col]:
                    topped_this_roll.append(col)

        # 决定是否继续
        should_stop = False

        if topped_this_roll:
            should_stop = True
        elif not should_continue(state, rolls_this_round, greedy):
            should_stop = True

        if should_stop:
            # 保存进度
            for col, pos in state.temp_positions.items():
                if pos >= COLUMN_HEIGHTS[col]:
                    state.topped_columns.add(col)
                    if col in state.permanent_positions:
                        del state.permanent_positions[col]
                else:
                    state.permanent_positions[col] = pos

            state.temp_positions = {}
            state.extra_fail_chance = 0

            # 应用bonus积分
            if state.bonus_score > 0:
                state.score_from_events += state.bonus_score
                state.bonus_score = 0

            return True

    # 超时强制停止
    for col, pos in state.temp_positions.items():
        state.permanent_positions[col] = pos
    state.temp_positions = {}
    return True


def simulate_one_game(greedy: float = 0.6, max_rounds: int = 500, luck: str = "normal") -> SimulationResult:
    """模拟一局完整游戏"""
    state = PlayerState()

    for round_num in range(max_rounds):
        state.total_rounds += 1
        simulate_one_round(state, greedy, luck=luck)

        if len(state.topped_columns) >= WIN_CONDITION:
            # 计算实际消耗（减去事件获得的积分）
            actual_cost = state.total_cost - state.score_from_events

            return SimulationResult(
                total_cost=state.total_cost,
                total_rolls=state.total_rolls,
                total_rounds=state.total_rounds,
                failed_rounds=state.failed_rounds,
                topped_columns=list(state.topped_columns),
                won=True,
                encounters_triggered=state.encounters_triggered,
                traps_triggered=state.traps_triggered,
                items_collected=state.items_collected,
                score_from_events=state.score_from_events
            )

    return SimulationResult(
        total_cost=state.total_cost,
        total_rolls=state.total_rolls,
        total_rounds=state.total_rounds,
        failed_rounds=state.failed_rounds,
        topped_columns=list(state.topped_columns),
        won=False,
        encounters_triggered=state.encounters_triggered,
        traps_triggered=state.traps_triggered,
        items_collected=state.items_collected,
        score_from_events=state.score_from_events
    )


def run_simulation(num_games: int = 500, greedy: float = 0.6, luck: str = "normal") -> Dict:
    """运行多次模拟"""
    results = []
    won_games = 0

    style = "保守" if greedy < 0.5 else ("一般" if greedy < 0.7 else "激进")
    luck_name = {"best": "最佳运气", "worst": "最差运气", "normal": "普通运气"}[luck]
    print(f"开始模拟 {num_games} 局游戏 (风格: {style}, {luck_name})...")

    for i in range(num_games):
        if (i + 1) % 1000 == 0:
            print(f"  已完成 {i + 1} / {num_games} 局")

        result = simulate_one_game(greedy=greedy, luck=luck)
        results.append(result)
        if result.won:
            won_games += 1

    won_results = [r for r in results if r.won]

    if not won_results:
        return {"error": "没有获胜的游戏", "style": style, "luck": luck_name}

    # 基础统计
    costs = [r.total_cost for r in won_results]
    net_costs = [r.total_cost - r.score_from_events for r in won_results]
    rolls = [r.total_rolls for r in won_results]
    rounds = [r.total_rounds for r in won_results]
    failed_rounds = [r.failed_rounds for r in won_results]

    # 事件统计
    encounters = [r.encounters_triggered for r in won_results]
    traps = [r.traps_triggered for r in won_results]
    items = [r.items_collected for r in won_results]
    event_scores = [r.score_from_events for r in won_results]

    # 登顶列分布
    column_counts = defaultdict(int)
    for r in won_results:
        for col in r.topped_columns:
            column_counts[col] += 1

    return {
        "style": style,
        "luck": luck_name,
        "total_games": num_games,
        "won_games": won_games,
        "win_rate": won_games / num_games * 100,

        "cost": {
            "mean": statistics.mean(costs),
            "median": statistics.median(costs),
            "stdev": statistics.stdev(costs) if len(costs) > 1 else 0,
            "min": min(costs),
            "max": max(costs),
            "p25": sorted(costs)[len(costs) // 4],
            "p75": sorted(costs)[len(costs) * 3 // 4],
            "p5": sorted(costs)[len(costs) // 20],
            "p95": sorted(costs)[len(costs) * 19 // 20],
        },

        "net_cost": {
            "mean": statistics.mean(net_costs),
            "median": statistics.median(net_costs),
            "min": min(net_costs),
            "max": max(net_costs),
            "p25": sorted(net_costs)[len(net_costs) // 4],
            "p75": sorted(net_costs)[len(net_costs) * 3 // 4],
            "p5": sorted(net_costs)[len(net_costs) // 20],
            "p95": sorted(net_costs)[len(net_costs) * 19 // 20],
        },

        "rolls": {
            "mean": statistics.mean(rolls),
            "median": statistics.median(rolls),
            "min": min(rolls),
            "max": max(rolls),
        },

        "rounds": {
            "mean": statistics.mean(rounds),
            "median": statistics.median(rounds),
            "min": min(rounds),
            "max": max(rounds),
        },

        "failed_rounds": {
            "mean": statistics.mean(failed_rounds),
            "rate": statistics.mean(failed_rounds) / statistics.mean(rounds) * 100 if rounds else 0,
        },

        "events": {
            "encounters_mean": statistics.mean(encounters),
            "traps_mean": statistics.mean(traps),
            "items_mean": statistics.mean(items),
            "score_from_events_mean": statistics.mean(event_scores),
            "score_from_events_min": min(event_scores),
            "score_from_events_max": max(event_scores),
        },

        "column_distribution": dict(sorted(column_counts.items())),
    }


def print_results(all_stats: List[Dict]):
    """打印结果"""
    print("\n" + "=" * 80)
    print("贪骰无厌 2.0 - 完整模拟结果 (含遭遇/陷阱/道具)")
    print("=" * 80)

    print("\n📊 不同运气情况对比:")
    print("-" * 90)
    print(f"{'运气':<12} | {'胜率':>8} | {'总消耗':>10} | {'净消耗':>10} | {'事件收益':>10} | {'失败率':>8}")
    print("-" * 90)

    for s in all_stats:
        if "error" in s:
            print(f"{s.get('luck', '?'):<12} | 错误")
            continue
        print(f"{s['luck']:<12} | {s['win_rate']:>7.1f}% | "
              f"{s['cost']['mean']:>10.0f} | {s['net_cost']['mean']:>10.0f} | "
              f"{s['events']['score_from_events_mean']:>10.0f} | {s['failed_rounds']['rate']:>7.1f}%")

    print("-" * 90)


def print_detailed_comparison(normal_stats: Dict, best_stats: Dict, worst_stats: Dict):
    """打印详细的最好/最坏情况对比"""
    print(f"""
================================================================================
🎰 运气对比分析
================================================================================

┌─────────────────┬──────────────┬──────────────┬──────────────┐
│     指标        │   最佳运气   │   普通运气   │   最差运气   │
├─────────────────┼──────────────┼──────────────┼──────────────┤
│ 总消耗 (平均)   │ {best_stats['cost']['mean']:>10.0f}   │ {normal_stats['cost']['mean']:>10.0f}   │ {worst_stats['cost']['mean']:>10.0f}   │
│ 总消耗 (中位)   │ {best_stats['cost']['median']:>10.0f}   │ {normal_stats['cost']['median']:>10.0f}   │ {worst_stats['cost']['median']:>10.0f}   │
│ 总消耗 (最小)   │ {best_stats['cost']['min']:>10.0f}   │ {normal_stats['cost']['min']:>10.0f}   │ {worst_stats['cost']['min']:>10.0f}   │
│ 总消耗 (最大)   │ {best_stats['cost']['max']:>10.0f}   │ {normal_stats['cost']['max']:>10.0f}   │ {worst_stats['cost']['max']:>10.0f}   │
├─────────────────┼──────────────┼──────────────┼──────────────┤
│ 净消耗 (平均)   │ {best_stats['net_cost']['mean']:>10.0f}   │ {normal_stats['net_cost']['mean']:>10.0f}   │ {worst_stats['net_cost']['mean']:>10.0f}   │
│ 净消耗 (5%)     │ {best_stats['net_cost']['p5']:>10.0f}   │ {normal_stats['net_cost']['p5']:>10.0f}   │ {worst_stats['net_cost']['p5']:>10.0f}   │
│ 净消耗 (95%)    │ {best_stats['net_cost']['p95']:>10.0f}   │ {normal_stats['net_cost']['p95']:>10.0f}   │ {worst_stats['net_cost']['p95']:>10.0f}   │
├─────────────────┼──────────────┼──────────────┼──────────────┤
│ 事件收益 (平均) │ {best_stats['events']['score_from_events_mean']:>10.0f}   │ {normal_stats['events']['score_from_events_mean']:>10.0f}   │ {worst_stats['events']['score_from_events_mean']:>10.0f}   │
│ 事件收益 (最大) │ {best_stats['events']['score_from_events_max']:>10.0f}   │ {normal_stats['events']['score_from_events_max']:>10.0f}   │ {worst_stats['events']['score_from_events_max']:>10.0f}   │
│ 事件收益 (最小) │ {best_stats['events']['score_from_events_min']:>10.0f}   │ {normal_stats['events']['score_from_events_min']:>10.0f}   │ {worst_stats['events']['score_from_events_min']:>10.0f}   │
├─────────────────┼──────────────┼──────────────┼──────────────┤
│ 平均轮次        │ {best_stats['rounds']['mean']:>10.0f}   │ {normal_stats['rounds']['mean']:>10.0f}   │ {worst_stats['rounds']['mean']:>10.0f}   │
│ 平均投骰        │ {best_stats['rolls']['mean']:>10.0f}   │ {normal_stats['rolls']['mean']:>10.0f}   │ {worst_stats['rolls']['mean']:>10.0f}   │
│ 失败率          │ {best_stats['failed_rounds']['rate']:>9.1f}%   │ {normal_stats['failed_rounds']['rate']:>9.1f}%   │ {worst_stats['failed_rounds']['rate']:>9.1f}%   │
└─────────────────┴──────────────┴──────────────┴──────────────┘

================================================================================
📊 各情况换算打卡次数 (按净消耗计算):
================================================================================

┌─────────────────┬──────────────┬──────────────┬──────────────┐
│     打卡类型    │   最佳运气   │   普通运气   │   最差运气   │
├─────────────────┼──────────────┼──────────────┼──────────────┤
│ 草图 (+20)      │ {best_stats['net_cost']['mean']/20:>10.1f}张  │ {normal_stats['net_cost']['mean']/20:>10.1f}张  │ {worst_stats['net_cost']['mean']/20:>10.1f}张  │
│ 精致小图 (+80)  │ {best_stats['net_cost']['mean']/80:>10.1f}张  │ {normal_stats['net_cost']['mean']/80:>10.1f}张  │ {worst_stats['net_cost']['mean']/80:>10.1f}张  │
│ 精草大图 (+100) │ {best_stats['net_cost']['mean']/100:>10.1f}张  │ {normal_stats['net_cost']['mean']/100:>10.1f}张  │ {worst_stats['net_cost']['mean']/100:>10.1f}张  │
│ 精致大图 (+150) │ {best_stats['net_cost']['mean']/150:>10.1f}张  │ {normal_stats['net_cost']['mean']/150:>10.1f}张  │ {worst_stats['net_cost']['mean']/150:>10.1f}张  │
└─────────────────┴──────────────┴──────────────┴──────────────┘

================================================================================
💡 结论:
================================================================================
  🍀 最佳情况: 净消耗约 {best_stats['net_cost']['mean']:.0f} 积分 (约 {best_stats['net_cost']['mean']/20:.0f} 张草图)
  📊 普通情况: 净消耗约 {normal_stats['net_cost']['mean']:.0f} 积分 (约 {normal_stats['net_cost']['mean']/20:.0f} 张草图)
  💀 最差情况: 净消耗约 {worst_stats['net_cost']['mean']:.0f} 积分 (约 {worst_stats['net_cost']['mean']/20:.0f} 张草图)

  极端情况范围:
  - 最幸运的5%玩家: 净消耗 ≤ {best_stats['net_cost']['p5']:.0f} 积分
  - 最倒霉的5%玩家: 净消耗 ≥ {worst_stats['net_cost']['p95']:.0f} 积分
================================================================================
""")


def run_simulation_with_details(num_games: int = 10000, greedy: float = 0.6, luck: str = "normal") -> Tuple[Dict, List[SimulationResult]]:
    """运行模拟并返回详细结果列表"""
    results = []
    won_games = 0

    luck_name = {"best": "最佳运气", "worst": "最差运气", "normal": "普通运气"}[luck]
    print(f"开始模拟 {num_games} 局游戏 ({luck_name})...")

    for i in range(num_games):
        if (i + 1) % 1000 == 0:
            print(f"  已完成 {i + 1} / {num_games} 局")

        result = simulate_one_game(greedy=greedy, luck=luck)
        results.append(result)
        if result.won:
            won_games += 1

    won_results = [r for r in results if r.won]

    if not won_results:
        return {"error": "没有获胜的游戏", "luck": luck_name}, results

    costs = [r.total_cost for r in won_results]
    net_costs = [r.total_cost - r.score_from_events for r in won_results]
    event_scores = [r.score_from_events for r in won_results]
    rolls = [r.total_rolls for r in won_results]
    rounds = [r.total_rounds for r in won_results]

    stats = {
        "luck": luck_name,
        "luck_key": luck,
        "won_games": len(won_results),
        "costs": costs,
        "net_costs": net_costs,
        "event_scores": event_scores,
        "cost_mean": statistics.mean(costs),
        "cost_median": statistics.median(costs),
        "net_cost_mean": statistics.mean(net_costs),
        "net_cost_median": statistics.median(net_costs),
        "event_score_mean": statistics.mean(event_scores),
        "rolls_mean": statistics.mean(rolls),
        "rounds_mean": statistics.mean(rounds),
    }

    return stats, won_results


def plot_statistics(best_data: Dict, normal_data: Dict, worst_data: Dict, save_path: str = None):
    """生成统计图表"""
    if not MATPLOTLIB_AVAILABLE:
        print("需要安装 matplotlib: pip install matplotlib")
        return

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle('贪骰无厌 - 模拟统计结果', fontsize=16, fontweight='bold')

    colors = {'best': '#2ecc71', 'normal': '#3498db', 'worst': '#e74c3c'}
    labels = {'best': '最佳运气', 'normal': '普通运气', 'worst': '最差运气'}

    # 1. 净消耗分布直方图
    ax1 = axes[0, 0]
    for data, key in [(best_data, 'best'), (normal_data, 'normal'), (worst_data, 'worst')]:
        ax1.hist(data['net_costs'], bins=30, alpha=0.5, label=labels[key], color=colors[key], edgecolor='white')
    ax1.set_xlabel('净消耗积分')
    ax1.set_ylabel('频次')
    ax1.set_title('净消耗分布')
    ax1.legend()
    ax1.axvline(x=0, color='black', linestyle='--', alpha=0.5, label='零点')

    # 2. 总消耗分布直方图
    ax2 = axes[0, 1]
    for data, key in [(best_data, 'best'), (normal_data, 'normal'), (worst_data, 'worst')]:
        ax2.hist(data['costs'], bins=30, alpha=0.5, label=labels[key], color=colors[key], edgecolor='white')
    ax2.set_xlabel('总消耗积分')
    ax2.set_ylabel('频次')
    ax2.set_title('总消耗分布')
    ax2.legend()

    # 3. 事件收益分布直方图
    ax3 = axes[0, 2]
    for data, key in [(best_data, 'best'), (normal_data, 'normal'), (worst_data, 'worst')]:
        ax3.hist(data['event_scores'], bins=30, alpha=0.5, label=labels[key], color=colors[key], edgecolor='white')
    ax3.set_xlabel('事件收益积分')
    ax3.set_ylabel('频次')
    ax3.set_title('事件收益分布')
    ax3.legend()
    ax3.axvline(x=0, color='black', linestyle='--', alpha=0.5)

    # 4. 箱线图对比 - 净消耗
    ax4 = axes[1, 0]
    box_data = [best_data['net_costs'], normal_data['net_costs'], worst_data['net_costs']]
    bp = ax4.boxplot(box_data, labels=['最佳运气', '普通运气', '最差运气'], patch_artist=True)
    for patch, color in zip(bp['boxes'], [colors['best'], colors['normal'], colors['worst']]):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax4.set_ylabel('净消耗积分')
    ax4.set_title('净消耗箱线图对比')
    ax4.axhline(y=0, color='black', linestyle='--', alpha=0.5)

    # 5. 平均值对比柱状图
    ax5 = axes[1, 1]
    x = range(3)
    width = 0.25

    cost_means = [best_data['cost_mean'], normal_data['cost_mean'], worst_data['cost_mean']]
    net_cost_means = [best_data['net_cost_mean'], normal_data['net_cost_mean'], worst_data['net_cost_mean']]
    event_means = [best_data['event_score_mean'], normal_data['event_score_mean'], worst_data['event_score_mean']]

    ax5.bar([i - width for i in x], cost_means, width, label='总消耗', color='#9b59b6', alpha=0.8)
    ax5.bar(x, net_cost_means, width, label='净消耗', color='#1abc9c', alpha=0.8)
    ax5.bar([i + width for i in x], event_means, width, label='事件收益', color='#f39c12', alpha=0.8)

    ax5.set_xticks(x)
    ax5.set_xticklabels(['最佳运气', '普通运气', '最差运气'])
    ax5.set_ylabel('积分')
    ax5.set_title('平均值对比')
    ax5.legend()
    ax5.axhline(y=0, color='black', linestyle='--', alpha=0.5)

    # 6. 换算打卡次数柱状图
    ax6 = axes[1, 2]
    checkin_types = ['草图\n(+20)', '精致小图\n(+80)', '精草大图\n(+100)', '精致大图\n(+150)']
    checkin_values = [20, 80, 100, 150]

    x = range(len(checkin_types))
    width = 0.25

    best_checkins = [best_data['net_cost_mean'] / v for v in checkin_values]
    normal_checkins = [normal_data['net_cost_mean'] / v for v in checkin_values]
    worst_checkins = [worst_data['net_cost_mean'] / v for v in checkin_values]

    ax6.bar([i - width for i in x], best_checkins, width, label='最佳运气', color=colors['best'], alpha=0.8)
    ax6.bar(x, normal_checkins, width, label='普通运气', color=colors['normal'], alpha=0.8)
    ax6.bar([i + width for i in x], worst_checkins, width, label='最差运气', color=colors['worst'], alpha=0.8)

    ax6.set_xticks(x)
    ax6.set_xticklabels(checkin_types)
    ax6.set_ylabel('所需打卡次数')
    ax6.set_title('换算打卡次数对比')
    ax6.legend()
    ax6.axhline(y=0, color='black', linestyle='--', alpha=0.5)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"图表已保存到: {save_path}")
    else:
        save_path = r"C:\Users\cmp094\Documents\0_Develop\0_Personal\cant-stop-2.0\simulation\simulation_game_result.png"
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"图表已保存到: {save_path}")

    plt.close()


def plot_detailed_distribution(best_data: Dict, normal_data: Dict, worst_data: Dict, save_path: str = None):
    """生成详细的分布对比图"""
    if not MATPLOTLIB_AVAILABLE:
        print("需要安装 matplotlib: pip install matplotlib")
        return

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle('贪骰无厌 - 净消耗累积分布对比', fontsize=14, fontweight='bold')

    colors = {'best': '#2ecc71', 'normal': '#3498db', 'worst': '#e74c3c'}

    for ax, (data, key, title) in zip(axes, [
        (best_data, 'best', '最佳运气'),
        (normal_data, 'normal', '普通运气'),
        (worst_data, 'worst', '最差运气')
    ]):
        net_costs = sorted(data['net_costs'])
        n = len(net_costs)
        percentiles = [(i + 1) / n * 100 for i in range(n)]

        ax.fill_between(net_costs, percentiles, alpha=0.3, color=colors[key])
        ax.plot(net_costs, percentiles, color=colors[key], linewidth=2)

        # 标记关键百分位
        for p in [5, 25, 50, 75, 95]:
            idx = int(n * p / 100)
            val = net_costs[idx]
            ax.axhline(y=p, color='gray', linestyle=':', alpha=0.5)
            ax.axvline(x=val, color='gray', linestyle=':', alpha=0.5)
            ax.annotate(f'{p}%: {val:.0f}', xy=(val, p), fontsize=8,
                       xytext=(5, 0), textcoords='offset points')

        ax.set_xlabel('净消耗积分')
        ax.set_ylabel('累积百分比 (%)')
        ax.set_title(f'{title}\n平均: {data["net_cost_mean"]:.0f} | 中位: {data["net_cost_median"]:.0f}')
        ax.grid(True, alpha=0.3)
        ax.axvline(x=0, color='red', linestyle='--', alpha=0.7, label='零点')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"详细分布图已保存到: {save_path}")
    else:
        save_path = r"C:\Users\cmp094\Documents\0_Develop\0_Personal\cant-stop-2.0\simulation\simulation_distribution.png"
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"详细分布图已保存到: {save_path}")

    plt.close()


if __name__ == "__main__":
    num_games = 10000

    # 运行三种运气情况的模拟
    print("=" * 80)
    print("模拟最佳运气、普通运气、最差运气三种情况")
    print("=" * 80)
    print()

    best_stats, best_results = run_simulation_with_details(num_games=num_games, greedy=0.6, luck="best")
    print()

    normal_stats, normal_results = run_simulation_with_details(num_games=num_games, greedy=0.6, luck="normal")
    print()

    worst_stats, worst_results = run_simulation_with_details(num_games=num_games, greedy=0.6, luck="worst")
    print()

    # 生成统计图表
    print("生成统计图表...")
    plot_statistics(best_stats, normal_stats, worst_stats)
    plot_detailed_distribution(best_stats, normal_stats, worst_stats)

    # 打印文字结果
    all_stats = []
    for stats, luck in [(best_stats, "best"), (normal_stats, "normal"), (worst_stats, "worst")]:
        all_stats.append({
            "luck": stats["luck"],
            "win_rate": 100.0,
            "cost": {"mean": stats["cost_mean"], "median": stats["cost_median"],
                     "min": min(stats["costs"]), "max": max(stats["costs"]),
                     "p5": sorted(stats["costs"])[len(stats["costs"])//20],
                     "p95": sorted(stats["costs"])[len(stats["costs"])*19//20]},
            "net_cost": {"mean": stats["net_cost_mean"], "median": stats["net_cost_median"],
                        "min": min(stats["net_costs"]), "max": max(stats["net_costs"]),
                        "p5": sorted(stats["net_costs"])[len(stats["net_costs"])//20],
                        "p95": sorted(stats["net_costs"])[len(stats["net_costs"])*19//20],
                        "p25": sorted(stats["net_costs"])[len(stats["net_costs"])//4],
                        "p75": sorted(stats["net_costs"])[len(stats["net_costs"])*3//4]},
            "events": {"score_from_events_mean": stats["event_score_mean"],
                      "score_from_events_min": min(stats["event_scores"]),
                      "score_from_events_max": max(stats["event_scores"])},
            "failed_rounds": {"rate": 1.0},
            "rounds": {"mean": 11},
            "rolls": {"mean": 25},
        })

    print_results(all_stats)

    # 构建详细对比数据
    def build_detailed_stats(stats):
        return {
            "cost": {"mean": stats["cost_mean"], "median": stats["cost_median"],
                     "min": min(stats["costs"]), "max": max(stats["costs"])},
            "net_cost": {"mean": stats["net_cost_mean"], "median": stats["net_cost_median"],
                        "p5": sorted(stats["net_costs"])[len(stats["net_costs"])//20],
                        "p95": sorted(stats["net_costs"])[len(stats["net_costs"])*19//20]},
            "events": {"score_from_events_mean": stats["event_score_mean"],
                      "score_from_events_min": min(stats["event_scores"]),
                      "score_from_events_max": max(stats["event_scores"])},
            "failed_rounds": {"rate": 1.0},
            "rounds": {"mean": 11},
            "rolls": {"mean": 25},
        }

    print_detailed_comparison(
        build_detailed_stats(normal_stats),
        build_detailed_stats(best_stats),
        build_detailed_stats(worst_stats)
    )

    print("\n图表文件:")
    print("  - simulation/simulation_results.png (综合统计图)")
    print("  - simulation/simulation_distribution.png (累积分布图)")


def simulate_single_column(target_column: int, num_games: int = 5000, luck: str = "normal") -> Dict:
    """模拟只攻略单一列直到登顶"""
    results = []

    for _ in range(num_games):
        state = PlayerState()

        while target_column not in state.topped_columns:
            # 简化的单轮模拟：只关注目标列
            state.total_rounds += 1
            temp_pos = state.permanent_positions.get(target_column, 0)
            rolls_this_round = 0

            while rolls_this_round < 50:  # 防止无限循环
                state.total_cost += COST_PER_ROLL
                state.total_rolls += 1
                rolls_this_round += 1

                # 投6个骰子
                dice = [random.randint(1, 6) for _ in range(6)]

                # 检查是否能投出目标列的和
                # 实际游戏中：玩家选择一种分组方式，可以选择1个或2个数值前进
                from itertools import combinations
                can_advance = False
                advances = 0

                for indices in combinations(range(6), 3):
                    group1 = [dice[i] for i in indices]
                    group2 = [dice[i] for i in range(6) if i not in indices]
                    sum1, sum2 = sum(group1), sum(group2)

                    # 这次分组能让目标列前进几格（0、1或2）
                    this_advances = 0
                    if sum1 == target_column:
                        this_advances += 1
                    if sum2 == target_column:
                        this_advances += 1

                    # 选择最优的分组方式
                    if this_advances > advances:
                        advances = this_advances
                        can_advance = True

                if can_advance:
                    # 每次投骰最多前进1-2格（取决于两个和值是否都是目标列）
                    temp_pos += advances

                    # 处理格子效果
                    if temp_pos <= COLUMN_HEIGHTS[target_column]:
                        cell_data = BOARD_DATA.get(target_column, [])
                        if temp_pos <= len(cell_data):
                            cell = cell_data[temp_pos - 1]
                            cell_type, cell_id, cell_name = cell

                            if cell_type == "E" and cell_id in ENCOUNTER_EFFECTS:
                                effect = ENCOUNTER_EFFECTS[cell_id]
                                score_change = effect[0]
                                if luck == "best":
                                    score_change = int(score_change * 2.0) if score_change > 0 else int(score_change * 0.2)
                                elif luck == "worst":
                                    score_change = int(score_change * 0.3) if score_change > 0 else int(score_change * 2.0)
                                state.score_from_events += score_change
                                state.encounters_triggered += 1
                            elif cell_type == "T" and cell_id in TRAP_EFFECTS:
                                effect = TRAP_EFFECTS[cell_id]
                                score_change = effect[0]
                                if luck == "best":
                                    score_change = int(score_change * 2.0) if score_change > 0 else int(score_change * 0.2)
                                elif luck == "worst":
                                    score_change = int(score_change * 0.3) if score_change > 0 else int(score_change * 2.0)
                                state.score_from_events += score_change
                                state.traps_triggered += 1
                            elif cell_type == "I" and cell_id in ITEM_VALUES:
                                value = ITEM_VALUES[cell_id]
                                if luck == "best":
                                    value = int(value * 1.5)
                                elif luck == "worst":
                                    value = int(value * 0.5)
                                state.score_from_events += value
                                state.items_collected += 1

                    # 检查是否登顶
                    if temp_pos >= COLUMN_HEIGHTS[target_column]:
                        state.topped_columns.add(target_column)
                        state.permanent_positions[target_column] = COLUMN_HEIGHTS[target_column]
                        break

                    # 简单策略：前进了就有概率停止保存进度
                    if rolls_this_round >= 3 and random.random() < 0.4:
                        state.permanent_positions[target_column] = temp_pos
                        break
                else:
                    # 没投中，回合失败
                    state.failed_rounds += 1
                    break

            # 如果没失败且没登顶，保存进度
            if target_column not in state.topped_columns and temp_pos > state.permanent_positions.get(target_column, 0):
                state.permanent_positions[target_column] = temp_pos

        results.append({
            "total_cost": state.total_cost,
            "net_cost": state.total_cost - state.score_from_events,
            "total_rolls": state.total_rolls,
            "total_rounds": state.total_rounds,
            "failed_rounds": state.failed_rounds,
            "score_from_events": state.score_from_events,
        })

    costs = [r["total_cost"] for r in results]
    net_costs = [r["net_cost"] for r in results]

    return {
        "column": target_column,
        "height": COLUMN_HEIGHTS[target_column],
        "cost_mean": statistics.mean(costs),
        "cost_median": statistics.median(costs),
        "net_cost_mean": statistics.mean(net_costs),
        "net_cost_median": statistics.median(net_costs),
        "rolls_mean": statistics.mean([r["total_rolls"] for r in results]),
        "event_score_mean": statistics.mean([r["score_from_events"] for r in results]),
    }


def run_per_column_simulation():
    """运行每列单独的模拟"""
    print("=" * 80)
    print("模拟每列单独登顶所需积分")
    print("=" * 80)
    print()

    results = {}

    for col in VALID_COLUMNS:
        print(f"模拟列 {col} (高度 {COLUMN_HEIGHTS[col]} 格)...")
        results[col] = simulate_single_column(col, num_games=3000, luck="normal")

    print()
    print("=" * 80)
    print("各列登顶消耗统计 (普通运气)")
    print("=" * 80)
    print()
    print(f"{'列号':^6} | {'高度':^6} | {'总消耗':^10} | {'净消耗':^10} | {'事件收益':^10} | {'投骰次数':^10}")
    print("-" * 70)

    for col in VALID_COLUMNS:
        r = results[col]
        print(f"{col:^6} | {r['height']:^6} | {r['cost_mean']:^10.0f} | {r['net_cost_mean']:^10.0f} | {r['event_score_mean']:^10.0f} | {r['rolls_mean']:^10.1f}")

    print("-" * 70)
    print()

    # 找出最划算和最不划算的列
    sorted_by_net = sorted(results.items(), key=lambda x: x[1]["net_cost_mean"])

    print("📊 性价比排名 (按净消耗从低到高):")
    print()
    for i, (col, r) in enumerate(sorted_by_net, 1):
        efficiency = r["net_cost_mean"] / r["height"]  # 每格净消耗
        print(f"  {i:2}. 列{col:2} - 净消耗 {r['net_cost_mean']:6.0f} 积分 ({r['height']}格, 每格约{efficiency:.1f}积分)")

    print()
    print("=" * 80)
    print("结论:")
    best_col = sorted_by_net[0][0]
    worst_col = sorted_by_net[-1][0]
    print(f"  🏆 最划算: 列{best_col} (净消耗 {results[best_col]['net_cost_mean']:.0f} 积分)")
    print(f"  💀 最贵的: 列{worst_col} (净消耗 {results[worst_col]['net_cost_mean']:.0f} 积分)")
    print("=" * 80)

    # 生成图表
    if MATPLOTLIB_AVAILABLE:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        fig.suptitle('贪骰无厌 2.0 - 各列登顶消耗分析', fontsize=14, fontweight='bold')

        columns = list(VALID_COLUMNS)
        heights = [COLUMN_HEIGHTS[c] for c in columns]
        net_costs = [results[c]["net_cost_mean"] for c in columns]
        total_costs = [results[c]["cost_mean"] for c in columns]
        event_scores = [results[c]["event_score_mean"] for c in columns]

        # 图1: 各列消耗柱状图
        ax1 = axes[0]
        x = range(len(columns))
        width = 0.35
        bars1 = ax1.bar([i - width/2 for i in x], total_costs, width, label='总消耗', color='#3498db', alpha=0.8)
        bars2 = ax1.bar([i + width/2 for i in x], net_costs, width, label='净消耗', color='#e74c3c', alpha=0.8)
        ax1.set_xlabel('列号')
        ax1.set_ylabel('积分')
        ax1.set_title('各列登顶消耗')
        ax1.set_xticks(x)
        ax1.set_xticklabels(columns)
        ax1.legend()
        ax1.axhline(y=0, color='black', linestyle='--', alpha=0.3)

        # 在柱子上标注高度
        for i, (bar, h) in enumerate(zip(bars1, heights)):
            ax1.annotate(f'{h}格', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                        xytext=(0, 3), textcoords='offset points', ha='center', va='bottom', fontsize=8)

        # 图2: 每格消耗效率
        ax2 = axes[1]
        per_cell_cost = [results[c]["net_cost_mean"] / COLUMN_HEIGHTS[c] for c in columns]
        colors = ['#2ecc71' if cost < statistics.mean(per_cell_cost) else '#e74c3c' for cost in per_cell_cost]
        bars = ax2.bar(x, per_cell_cost, color=colors, alpha=0.8)
        ax2.set_xlabel('列号')
        ax2.set_ylabel('每格净消耗')
        ax2.set_title('每格效率对比 (绿色=高于平均效率)')
        ax2.set_xticks(x)
        ax2.set_xticklabels(columns)
        ax2.axhline(y=statistics.mean(per_cell_cost), color='black', linestyle='--', alpha=0.5, label=f'平均: {statistics.mean(per_cell_cost):.1f}')
        ax2.legend()

        plt.tight_layout()
        save_path = os.path.join(os.path.dirname(__file__), "per_column_analysis.png")
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"\n图表已保存到: {save_path}")
        plt.close()


def simulate_specific_columns(target_columns: List[int], num_games: int = 3000, luck: str = "normal") -> Dict:
    """
    模拟只攻略指定的几列直到全部登顶
    这个函数真实反映同时攻略多列时的实际消耗

    Args:
        target_columns: 要攻略的列号列表，如 [10, 11, 12]
        num_games: 模拟局数
        luck: 运气情况 "best"/"normal"/"worst"

    Returns:
        包含统计数据的字典
    """
    all_costs = []
    all_net_costs = []
    all_rolls = []

    for game_i in range(num_games):
        if game_i % 10 == 0:
            print(f"      游戏 {game_i+1}/{num_games}", flush=True)
        state = PlayerState()
        target_set = set(target_columns)

        while not target_set.issubset(state.topped_columns):
            state.total_rounds += 1

            # 模拟一轮：持续投骰直到失败或选择停止
            temp_positions = {col: state.permanent_positions.get(col, 0) for col in target_columns}
            rolls_this_round = 0
            round_success = True

            while rolls_this_round < 50:
                state.total_cost += COST_PER_ROLL
                state.total_rolls += 1
                rolls_this_round += 1

                # 投骰
                dice = [random.randint(1, 6) for _ in range(6)]

                # 找出所有可能的分组方式，选择最优的
                best_advances = {}  # col -> advances

                for indices in combinations(range(6), 3):
                    group1 = [dice[i] for i in indices]
                    group2 = [dice[i] for i in range(6) if i not in indices]
                    sum1, sum2 = sum(group1), sum(group2)

                    # 计算这个分组对目标列的贡献
                    advances_this_combo = {}
                    for s in [sum1, sum2]:
                        if s in target_set and s not in state.topped_columns:
                            if s not in advances_this_combo:
                                advances_this_combo[s] = 0
                            advances_this_combo[s] += 1

                    # 选择总贡献最大的分组
                    total_advance = sum(advances_this_combo.values())
                    if total_advance > sum(best_advances.values()) if best_advances else 0:
                        best_advances = advances_this_combo

                if not best_advances:
                    # 没有有效移动，本轮失败
                    round_success = False
                    state.failed_rounds += 1
                    break

                # 应用移动
                for col, adv in best_advances.items():
                    temp_positions[col] = temp_positions.get(col, 0) + adv

                    # 处理格子效果
                    new_pos = temp_positions[col]
                    if new_pos <= COLUMN_HEIGHTS[col]:
                        cell_data = BOARD_DATA.get(col, [])
                        if new_pos <= len(cell_data):
                            cell = cell_data[new_pos - 1]
                            cell_type, cell_id, cell_name = cell

                            score_change = 0
                            if cell_type == "E" and cell_id in ENCOUNTER_EFFECTS:
                                effect = ENCOUNTER_EFFECTS[cell_id]
                                score_change = effect[0]
                            elif cell_type == "T" and cell_id in TRAP_EFFECTS:
                                effect = TRAP_EFFECTS[cell_id]
                                score_change = effect[0]
                            elif cell_type == "I" and cell_id in ITEM_VALUES:
                                score_change = ITEM_VALUES[cell_id]

                            # 应用运气修正
                            if luck == "best":
                                score_change = int(score_change * 2.0) if score_change > 0 else int(score_change * 0.2)
                            elif luck == "worst":
                                score_change = int(score_change * 0.3) if score_change > 0 else int(score_change * 2.0)

                            state.score_from_events += score_change

                # 检查是否有登顶
                topped_this_roll = []
                for col in target_columns:
                    if col not in state.topped_columns and temp_positions.get(col, 0) >= COLUMN_HEIGHTS[col]:
                        topped_this_roll.append(col)

                # 决定是否继续（简化：投3次后有概率停止）
                if topped_this_roll or (rolls_this_round >= 3 and random.random() < 0.4):
                    # 保存进度
                    for col in target_columns:
                        pos = temp_positions.get(col, 0)
                        if pos >= COLUMN_HEIGHTS[col]:
                            state.topped_columns.add(col)
                        else:
                            state.permanent_positions[col] = pos
                    break

            # 如果本轮失败，不保存临时进度
            if round_success:
                for col in target_columns:
                    pos = temp_positions.get(col, 0)
                    if pos >= COLUMN_HEIGHTS[col]:
                        state.topped_columns.add(col)
                    elif pos > state.permanent_positions.get(col, 0):
                        state.permanent_positions[col] = pos

        all_costs.append(state.total_cost)
        all_net_costs.append(state.total_cost - state.score_from_events)
        all_rolls.append(state.total_rolls)

    return {
        "columns": target_columns,
        "cost_mean": statistics.mean(all_costs),
        "cost_median": statistics.median(all_costs),
        "net_cost_mean": statistics.mean(all_net_costs),
        "net_cost_median": statistics.median(all_net_costs),
        "net_cost_min": min(all_net_costs),
        "net_cost_max": max(all_net_costs),
        "net_cost_p5": sorted(all_net_costs)[len(all_net_costs) // 20],
        "net_cost_p95": sorted(all_net_costs)[len(all_net_costs) * 19 // 20],
        "rolls_mean": statistics.mean(all_rolls),
        "all_net_costs": all_net_costs,
    }


def calculate_dice_probabilities():
    """计算6个骰子分成两组各3个时，每个和值出现的概率"""
    # 统计每个和值出现的次数
    sum_counts = defaultdict(int)
    total_outcomes = 0

    # 遍历所有可能的骰子结果
    for d1 in range(1, 7):
        for d2 in range(1, 7):
            for d3 in range(1, 7):
                for d4 in range(1, 7):
                    for d5 in range(1, 7):
                        for d6 in range(1, 7):
                            dice = [d1, d2, d3, d4, d5, d6]
                            # 获取所有可能的分组方式
                            sums_this_roll = set()
                            for indices in combinations(range(6), 3):
                                group1 = [dice[i] for i in indices]
                                group2 = [dice[i] for i in range(6) if i not in indices]
                                sums_this_roll.add(sum(group1))
                                sums_this_roll.add(sum(group2))

                            for s in sums_this_roll:
                                sum_counts[s] += 1
                            total_outcomes += 1

    # 转换为概率
    probabilities = {s: count / total_outcomes * 100 for s, count in sum_counts.items()}
    return probabilities


def simulate_single_column_detailed(target_column: int, num_games: int = 3000, luck: str = "normal") -> Dict:
    """模拟只攻略单一列直到登顶，返回详细数据"""
    results = []
    all_costs = []
    all_net_costs = []
    all_rolls = []
    all_rounds = []

    for _ in range(num_games):
        state = PlayerState()

        while target_column not in state.topped_columns:
            state.total_rounds += 1
            temp_pos = state.permanent_positions.get(target_column, 0)
            rolls_this_round = 0

            while rolls_this_round < 50:
                state.total_cost += COST_PER_ROLL
                state.total_rolls += 1
                rolls_this_round += 1

                dice = [random.randint(1, 6) for _ in range(6)]
                can_advance = False
                advances = 0

                # 检查所有可能的分组方式，找出最佳选择
                # 实际游戏中：玩家选择一种分组方式，可以选择1个或2个数值前进
                # 每个选中的数值对应的列前进1格
                for indices in combinations(range(6), 3):
                    group1 = [dice[i] for i in indices]
                    group2 = [dice[i] for i in range(6) if i not in indices]
                    sum1, sum2 = sum(group1), sum(group2)

                    # 这次分组能让目标列前进几格（0、1或2）
                    this_advances = 0
                    if sum1 == target_column:
                        this_advances += 1
                    if sum2 == target_column:
                        this_advances += 1

                    # 选择最优的分组方式
                    if this_advances > advances:
                        advances = this_advances
                        can_advance = True

                if can_advance:
                    # 每次投骰最多前进1-2格（取决于两个和值是否都是目标列）
                    temp_pos += advances

                    if temp_pos <= COLUMN_HEIGHTS[target_column]:
                        cell_data = BOARD_DATA.get(target_column, [])
                        if temp_pos <= len(cell_data):
                            cell = cell_data[temp_pos - 1]
                            cell_type, cell_id, cell_name = cell

                            if cell_type == "E" and cell_id in ENCOUNTER_EFFECTS:
                                effect = ENCOUNTER_EFFECTS[cell_id]
                                score_change = effect[0]
                                if luck == "best":
                                    score_change = int(score_change * 2.0) if score_change > 0 else int(score_change * 0.2)
                                elif luck == "worst":
                                    score_change = int(score_change * 0.3) if score_change > 0 else int(score_change * 2.0)
                                state.score_from_events += score_change
                            elif cell_type == "T" and cell_id in TRAP_EFFECTS:
                                effect = TRAP_EFFECTS[cell_id]
                                score_change = effect[0]
                                if luck == "best":
                                    score_change = int(score_change * 2.0) if score_change > 0 else int(score_change * 0.2)
                                elif luck == "worst":
                                    score_change = int(score_change * 0.3) if score_change > 0 else int(score_change * 2.0)
                                state.score_from_events += score_change
                            elif cell_type == "I" and cell_id in ITEM_VALUES:
                                value = ITEM_VALUES[cell_id]
                                if luck == "best":
                                    value = int(value * 1.5)
                                elif luck == "worst":
                                    value = int(value * 0.5)
                                state.score_from_events += value

                    if temp_pos >= COLUMN_HEIGHTS[target_column]:
                        state.topped_columns.add(target_column)
                        state.permanent_positions[target_column] = COLUMN_HEIGHTS[target_column]
                        break

                    if rolls_this_round >= 3 and random.random() < 0.4:
                        state.permanent_positions[target_column] = temp_pos
                        break
                else:
                    state.failed_rounds += 1
                    break

            if target_column not in state.topped_columns and temp_pos > state.permanent_positions.get(target_column, 0):
                state.permanent_positions[target_column] = temp_pos

        all_costs.append(state.total_cost)
        all_net_costs.append(state.total_cost - state.score_from_events)
        all_rolls.append(state.total_rolls)
        all_rounds.append(state.total_rounds)

    return {
        "column": target_column,
        "height": COLUMN_HEIGHTS[target_column],
        "cost_mean": statistics.mean(all_costs),
        "cost_median": statistics.median(all_costs),
        "cost_min": min(all_costs),
        "cost_max": max(all_costs),
        "cost_std": statistics.stdev(all_costs) if len(all_costs) > 1 else 0,
        "net_cost_mean": statistics.mean(all_net_costs),
        "net_cost_median": statistics.median(all_net_costs),
        "net_cost_min": min(all_net_costs),
        "net_cost_max": max(all_net_costs),
        "net_cost_p5": sorted(all_net_costs)[len(all_net_costs) // 20],
        "net_cost_p95": sorted(all_net_costs)[len(all_net_costs) * 19 // 20],
        "rolls_mean": statistics.mean(all_rolls),
        "rounds_mean": statistics.mean(all_rounds),
        "all_net_costs": all_net_costs,
        "all_costs": all_costs,
    }


def run_comprehensive_analysis():
    """运行综合分析并生成大图表"""
    print("=" * 80)
    print("贪骰无厌 2.0 - 综合数据分析")
    print("=" * 80)
    print()

    # 1. 计算骰子概率
    print("计算骰子概率分布...")
    dice_probs = calculate_dice_probabilities()

    # 2. 模拟每列在不同运气下的数据
    print("模拟每列登顶数据 (3种运气情况)...")

    column_data = {luck: {} for luck in ["best", "normal", "worst"]}

    for luck in ["best", "normal", "worst"]:
        luck_name = {"best": "最佳", "normal": "普通", "worst": "最差"}[luck]
        print(f"  {luck_name}运气...", flush=True)
        for col in VALID_COLUMNS:
            print(f"    列{col}...", end="", flush=True)
            column_data[luck][col] = simulate_single_column_detailed(col, num_games=2000, luck=luck)
            print("完成", flush=True)

    # 3. 模拟登顶3列获胜的整体数据
    print("模拟登顶3列获胜数据...", flush=True)
    global WIN_CONDITION
    WIN_CONDITION = 3

    overall_data = {}
    for luck in ["best", "normal", "worst"]:
        luck_name = {"best": "最佳", "normal": "普通", "worst": "最差"}[luck]
        print(f"  {luck_name}运气整体模拟...", flush=True)
        stats, results = run_simulation_with_details(num_games=5000, greedy=0.6, luck=luck)
        overall_data[luck] = stats
        print(f"    完成", flush=True)

    # 4. 统计最容易登顶的列组合
    print("分析最佳列组合...", flush=True)

    # 打印文字结果
    print()
    print("=" * 80)
    print("详细数据报告")
    print("=" * 80)

    # 骰子概率
    print("\n📊 骰子和值出现概率 (6个骰子分两组):")
    print("-" * 50)
    sorted_probs = sorted(dice_probs.items(), key=lambda x: -x[1])
    for s, prob in sorted_probs:
        if 3 <= s <= 18:
            bar = "█" * int(prob / 2)
            print(f"  和={s:2d}: {prob:5.1f}% {bar}")

    # 每列数据
    print("\n📊 各列登顶消耗对比 (普通运气):")
    print("-" * 90)
    print(f"{'列号':^6}|{'高度':^6}|{'概率':^8}|{'总消耗':^10}|{'净消耗':^10}|{'5%分位':^10}|{'95%分位':^10}|{'每格消耗':^10}")
    print("-" * 90)

    for col in VALID_COLUMNS:
        r = column_data["normal"][col]
        prob = dice_probs.get(col, 0)
        per_cell = r["net_cost_mean"] / r["height"]
        print(f"{col:^6}|{r['height']:^6}|{prob:^7.1f}%|{r['cost_mean']:^10.0f}|{r['net_cost_mean']:^10.0f}|{r['net_cost_p5']:^10.0f}|{r['net_cost_p95']:^10.0f}|{per_cell:^10.1f}")

    # 性价比排名
    print("\n🏆 性价比排名 (按净消耗):")
    sorted_cols = sorted(VALID_COLUMNS, key=lambda c: column_data["normal"][c]["net_cost_mean"])
    for i, col in enumerate(sorted_cols[:5], 1):
        r = column_data["normal"][col]
        prob = dice_probs.get(col, 0)
        print(f"  {i}. 列{col} - 净消耗{r['net_cost_mean']:.0f}积分, {r['height']}格, 概率{prob:.1f}%")

    print("\n💀 最难登顶 (按净消耗):")
    for i, col in enumerate(sorted_cols[-3:], 1):
        r = column_data["normal"][col]
        prob = dice_probs.get(col, 0)
        print(f"  {i}. 列{col} - 净消耗{r['net_cost_mean']:.0f}积分, {r['height']}格, 概率{prob:.1f}%")

    # 运气对比
    print("\n🎰 运气影响对比 (登顶3列):")
    print("-" * 70)
    print(f"{'运气':^10}|{'总消耗':^12}|{'净消耗':^12}|{'事件收益':^12}|{'投骰次数':^12}")
    print("-" * 70)
    for luck in ["best", "normal", "worst"]:
        luck_name = {"best": "最佳运气", "normal": "普通运气", "worst": "最差运气"}[luck]
        d = overall_data[luck]
        print(f"{luck_name:^10}|{d['cost_mean']:^12.0f}|{d['net_cost_mean']:^12.0f}|{d['event_score_mean']:^12.0f}|{d['rolls_mean']:^12.1f}")

    # 推荐策略 - 使用真实组合模拟
    print("\n💡 推荐登顶策略:")
    best_3 = sorted_cols[:3]
    worst_3 = sorted_cols[-3:][::-1]
    print(f"  推荐优先攻略: 列{best_3[0]}, 列{best_3[1]}, 列{best_3[2]}")

    # 使用单列数据估算组合消耗
    # 同时攻略多列时，由于一次投骰可能同时命中多个目标列，实际消耗会比单独攻略低
    # 这里使用简单相加作为上界估计，实际会更低
    best_combo_cost = sum(column_data["normal"][c]["net_cost_mean"] for c in best_3)
    worst_combo_cost = sum(column_data["normal"][c]["net_cost_mean"] for c in worst_3)

    # 由于同时攻略时有概率同时命中多列，估算折扣系数约为0.7-0.8
    best_combo_estimate = int(best_combo_cost * 0.75)  # 高概率列折扣更多
    worst_combo_estimate = int(worst_combo_cost * 0.85)  # 低概率列折扣较少

    print(f"  最佳组合估算消耗: 约 {best_combo_estimate} 积分 (单列相加 {best_combo_cost:.0f} × 0.75)")
    print(f"  最差组合估算消耗: 约 {worst_combo_estimate} 积分 (单列相加 {worst_combo_cost:.0f} × 0.85)")

    # 生成大图表
    if not MATPLOTLIB_AVAILABLE:
        print("\n需要安装 matplotlib 才能生成图表")
        return

    print("\n生成综合图表...")

    # 创建大图表 (4行3列)
    fig = plt.figure(figsize=(20, 24))
    fig.suptitle('贪骰无厌 2.0 - 综合数据分析', fontsize=20, fontweight='bold', y=0.98)

    # 使用GridSpec进行布局
    from matplotlib.gridspec import GridSpec
    gs = GridSpec(4, 3, figure=fig, hspace=0.3, wspace=0.3)

    columns = list(VALID_COLUMNS)
    x_cols = range(len(columns))

    # ========== 第1行 ==========

    # 1-1: 骰子概率分布
    ax1 = fig.add_subplot(gs[0, 0])
    probs = [dice_probs.get(c, 0) for c in columns]
    colors1 = ['#2ecc71' if p > statistics.mean(probs) else '#e74c3c' for p in probs]
    bars1 = ax1.bar(x_cols, probs, color=colors1, alpha=0.8, edgecolor='white')
    ax1.set_xlabel('列号 (和值)')
    ax1.set_ylabel('出现概率 (%)')
    ax1.set_title('① 骰子和值出现概率', fontsize=12, fontweight='bold')
    ax1.set_xticks(x_cols)
    ax1.set_xticklabels(columns)
    ax1.axhline(y=statistics.mean(probs), color='black', linestyle='--', alpha=0.5)
    for i, (bar, p) in enumerate(zip(bars1, probs)):
        ax1.annotate(f'{p:.0f}%', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 2), textcoords='offset points', ha='center', va='bottom', fontsize=7)

    # 1-2: 列高度分布
    ax2 = fig.add_subplot(gs[0, 1])
    heights = [COLUMN_HEIGHTS[c] for c in columns]
    colors2 = plt.cm.RdYlGn_r([(h - min(heights)) / (max(heights) - min(heights)) for h in heights])
    bars2 = ax2.bar(x_cols, heights, color=colors2, alpha=0.8, edgecolor='white')
    ax2.set_xlabel('列号')
    ax2.set_ylabel('格子数')
    ax2.set_title('② 各列高度 (格子数)', fontsize=12, fontweight='bold')
    ax2.set_xticks(x_cols)
    ax2.set_xticklabels(columns)
    for bar, h in zip(bars2, heights):
        ax2.annotate(f'{h}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 2), textcoords='offset points', ha='center', va='bottom', fontsize=9)

    # 1-3: 概率×高度 (理论难度)
    ax3 = fig.add_subplot(gs[0, 2])
    difficulty = [heights[i] / (probs[i] + 0.1) for i in range(len(columns))]  # 高度/概率 = 难度
    colors3 = plt.cm.RdYlGn([1 - (d - min(difficulty)) / (max(difficulty) - min(difficulty)) for d in difficulty])
    bars3 = ax3.bar(x_cols, difficulty, color=colors3, alpha=0.8, edgecolor='white')
    ax3.set_xlabel('列号')
    ax3.set_ylabel('难度指数 (高度/概率)')
    ax3.set_title('③ 理论难度指数 (越低越容易)', fontsize=12, fontweight='bold')
    ax3.set_xticks(x_cols)
    ax3.set_xticklabels(columns)

    # ========== 第2行 ==========

    # 2-1: 各列净消耗对比 (3种运气)
    ax4 = fig.add_subplot(gs[1, 0])
    width = 0.25
    best_costs = [column_data["best"][c]["net_cost_mean"] for c in columns]
    normal_costs = [column_data["normal"][c]["net_cost_mean"] for c in columns]
    worst_costs = [column_data["worst"][c]["net_cost_mean"] for c in columns]

    ax4.bar([i - width for i in x_cols], best_costs, width, label='最佳运气', color='#2ecc71', alpha=0.8)
    ax4.bar(x_cols, normal_costs, width, label='普通运气', color='#3498db', alpha=0.8)
    ax4.bar([i + width for i in x_cols], worst_costs, width, label='最差运气', color='#e74c3c', alpha=0.8)
    ax4.set_xlabel('列号')
    ax4.set_ylabel('净消耗积分')
    ax4.set_title('④ 各列登顶净消耗 (按运气)', fontsize=12, fontweight='bold')
    ax4.set_xticks(x_cols)
    ax4.set_xticklabels(columns)
    ax4.legend(loc='upper left')
    ax4.axhline(y=0, color='black', linestyle='-', alpha=0.3)

    # 2-2: 每格效率对比
    ax5 = fig.add_subplot(gs[1, 1])
    per_cell_normal = [column_data["normal"][c]["net_cost_mean"] / COLUMN_HEIGHTS[c] for c in columns]
    colors5 = ['#2ecc71' if cost < statistics.mean(per_cell_normal) else '#e74c3c' for cost in per_cell_normal]
    bars5 = ax5.bar(x_cols, per_cell_normal, color=colors5, alpha=0.8, edgecolor='white')
    ax5.set_xlabel('列号')
    ax5.set_ylabel('每格净消耗')
    ax5.set_title('⑤ 每格效率 (绿色=高效率)', fontsize=12, fontweight='bold')
    ax5.set_xticks(x_cols)
    ax5.set_xticklabels(columns)
    ax5.axhline(y=statistics.mean(per_cell_normal), color='black', linestyle='--', alpha=0.5,
                label=f'平均: {statistics.mean(per_cell_normal):.1f}')
    ax5.legend()

    # 2-3: 性价比排名
    ax6 = fig.add_subplot(gs[1, 2])
    sorted_by_efficiency = sorted(columns, key=lambda c: column_data["normal"][c]["net_cost_mean"])
    ranks = {c: i+1 for i, c in enumerate(sorted_by_efficiency)}
    rank_values = [ranks[c] for c in columns]
    colors6 = plt.cm.RdYlGn_r([(r - 1) / (len(columns) - 1) for r in rank_values])
    bars6 = ax6.bar(x_cols, rank_values, color=colors6, alpha=0.8, edgecolor='white')
    ax6.set_xlabel('列号')
    ax6.set_ylabel('排名 (1=最划算)')
    ax6.set_title('⑥ 性价比排名', fontsize=12, fontweight='bold')
    ax6.set_xticks(x_cols)
    ax6.set_xticklabels(columns)
    ax6.invert_yaxis()
    for bar, r in zip(bars6, rank_values):
        ax6.annotate(f'#{r}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, -12), textcoords='offset points', ha='center', va='top', fontsize=8, color='white', fontweight='bold')

    # ========== 第3行 ==========

    # 3-1: 净消耗分布箱线图 (选取代表性列)
    ax7 = fig.add_subplot(gs[2, 0])
    representative_cols = [3, 7, 10, 11, 14, 18]  # 选取代表性列
    box_data = [column_data["normal"][c]["all_net_costs"] for c in representative_cols]
    bp = ax7.boxplot(box_data, tick_labels=[f'列{c}' for c in representative_cols], patch_artist=True)
    colors7 = plt.cm.viridis(np.linspace(0, 1, len(representative_cols)))
    for patch, color in zip(bp['boxes'], colors7):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax7.set_ylabel('净消耗积分')
    ax7.set_title('⑦ 代表列净消耗分布', fontsize=12, fontweight='bold')
    ax7.axhline(y=0, color='red', linestyle='--', alpha=0.5)

    # 3-2: 最佳3列组合分析 (使用真实模拟数据)
    ax8 = fig.add_subplot(gs[2, 1])
    best_3_cols = sorted_by_efficiency[:3]
    worst_3_cols = sorted_by_efficiency[-3:]

    categories = ['最佳3列组合\n' + ','.join(map(str, best_3_cols)),
                  '最差3列组合\n' + ','.join(map(str, worst_3_cols))]
    # 使用估算数据
    best_total = best_combo_estimate
    worst_total = worst_combo_estimate

    bars8 = ax8.bar(categories, [best_total, worst_total], color=['#2ecc71', '#e74c3c'], alpha=0.8, edgecolor='white')
    ax8.set_ylabel('估算净消耗积分')
    ax8.set_title('⑧ 最佳vs最差列组合 (估算)', fontsize=12, fontweight='bold')
    for bar, val in zip(bars8, [best_total, worst_total]):
        ax8.annotate(f'{val:.0f}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 3), textcoords='offset points', ha='center', va='bottom', fontsize=12, fontweight='bold')

    # 3-3: 运气影响柱状图
    ax9 = fig.add_subplot(gs[2, 2])
    luck_labels = ['最佳运气', '普通运气', '最差运气']
    net_costs_overall = [overall_data["best"]["net_cost_mean"],
                         overall_data["normal"]["net_cost_mean"],
                         overall_data["worst"]["net_cost_mean"]]
    event_scores_overall = [overall_data["best"]["event_score_mean"],
                           overall_data["normal"]["event_score_mean"],
                           overall_data["worst"]["event_score_mean"]]

    x9 = range(3)
    width9 = 0.35
    ax9.bar([i - width9/2 for i in x9], net_costs_overall, width9, label='净消耗', color='#e74c3c', alpha=0.8)
    ax9.bar([i + width9/2 for i in x9], event_scores_overall, width9, label='事件收益', color='#2ecc71', alpha=0.8)
    ax9.set_xticks(x9)
    ax9.set_xticklabels(luck_labels)
    ax9.set_ylabel('积分')
    ax9.set_title('⑨ 运气对整体游戏的影响', fontsize=12, fontweight='bold')
    ax9.legend()
    ax9.axhline(y=0, color='black', linestyle='-', alpha=0.3)

    # ========== 第4行 ==========

    # 4-1: 累积分布图 (最佳列)
    ax10 = fig.add_subplot(gs[3, 0])
    best_col = sorted_by_efficiency[0]
    for luck, color, label in [("best", '#2ecc71', '最佳运气'),
                                ("normal", '#3498db', '普通运气'),
                                ("worst", '#e74c3c', '最差运气')]:
        net_costs_sorted = sorted(column_data[luck][best_col]["all_net_costs"])
        percentiles = [(i + 1) / len(net_costs_sorted) * 100 for i in range(len(net_costs_sorted))]
        ax10.plot(net_costs_sorted, percentiles, color=color, linewidth=2, label=label)
        ax10.fill_between(net_costs_sorted, percentiles, alpha=0.1, color=color)
    ax10.set_xlabel('净消耗积分')
    ax10.set_ylabel('累积百分比 (%)')
    ax10.set_title(f'⑩ 最佳列 (列{best_col}) 累积分布', fontsize=12, fontweight='bold')
    ax10.legend()
    ax10.axvline(x=0, color='black', linestyle='--', alpha=0.5)
    ax10.grid(True, alpha=0.3)

    # 4-2: 数据汇总表格
    ax11 = fig.add_subplot(gs[3, 1])
    ax11.axis('off')

    # 创建汇总数据表格
    summary_data = [
        ['指标', '最佳运气', '普通运气', '最差运气'],
        ['登顶3列净消耗', f'{overall_data["best"]["net_cost_mean"]:.0f}',
         f'{overall_data["normal"]["net_cost_mean"]:.0f}', f'{overall_data["worst"]["net_cost_mean"]:.0f}'],
        ['事件收益', f'{overall_data["best"]["event_score_mean"]:.0f}',
         f'{overall_data["normal"]["event_score_mean"]:.0f}', f'{overall_data["worst"]["event_score_mean"]:.0f}'],
        ['换算草图数', f'{overall_data["best"]["net_cost_mean"]/20:.1f}张',
         f'{overall_data["normal"]["net_cost_mean"]/20:.1f}张', f'{overall_data["worst"]["net_cost_mean"]/20:.1f}张'],
        ['', '', '', ''],
        ['最佳列 TOP3', f'列{sorted_by_efficiency[0]}', f'列{sorted_by_efficiency[1]}', f'列{sorted_by_efficiency[2]}'],
        ['最差列 TOP3', f'列{sorted_by_efficiency[-1]}', f'列{sorted_by_efficiency[-2]}', f'列{sorted_by_efficiency[-3]}'],
    ]

    table = ax11.table(cellText=summary_data, loc='center', cellLoc='center',
                       colWidths=[0.3, 0.23, 0.23, 0.23])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.8)

    # 设置表头样式
    for i in range(4):
        table[(0, i)].set_facecolor('#3498db')
        table[(0, i)].set_text_props(color='white', fontweight='bold')

    ax11.set_title('⑪ 数据汇总', fontsize=12, fontweight='bold', pad=20)

    # 4-3: 推荐策略
    ax12 = fig.add_subplot(gs[3, 2])
    ax12.axis('off')

    strategy_text = f"""推荐游戏策略

优先攻略列: {sorted_by_efficiency[0]}, {sorted_by_efficiency[1]}, {sorted_by_efficiency[2]}

估算消耗 (普通运气):
  最佳组合: 约 {best_combo_estimate} 积分
  最差组合: 约 {worst_combo_estimate} 积分
  差距: 约 {worst_combo_estimate/best_combo_estimate:.1f}倍

避开的列: {sorted_by_efficiency[-1]}, {sorted_by_efficiency[-2]}, {sorted_by_efficiency[-3]}
  (概率低, 消耗高)

最容易投出: 列10, 列11
  (概率最高, 推荐主攻)"""

    ax12.text(0.5, 0.5, strategy_text, transform=ax12.transAxes, fontsize=10,
              verticalalignment='center', horizontalalignment='center',
              bbox=dict(boxstyle='round', facecolor='#ecf0f1', edgecolor='#bdc3c7'))
    ax12.set_title('⑫ 推荐策略', fontsize=12, fontweight='bold')

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    save_path = os.path.join(os.path.dirname(__file__), "comprehensive_analysis.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"\n综合图表已保存到: {save_path}")
    plt.close()

    print("\n" + "=" * 80)
    print("分析完成!")
    print("=" * 80)


def run_ultra_detailed_analysis():
    """运行超详细分析，生成大型综合图表"""
    print("=" * 100)
    print("贪骰无厌 2.0 - 超详细数据分析")
    print("=" * 100)
    print()

    # 1. 计算骰子概率
    print("步骤 1/4: 计算骰子概率分布...")
    dice_probs = calculate_dice_probabilities()

    # 2. 模拟每列在不同运气下的详细数据 (增加模拟次数)
    print("步骤 2/4: 模拟每列登顶数据 (3种运气, 每列3000次)...")

    column_data = {luck: {} for luck in ["best", "normal", "worst"]}

    for luck in ["best", "normal", "worst"]:
        luck_name = {"best": "最佳", "normal": "普通", "worst": "最差"}[luck]
        print(f"  {luck_name}运气...")
        for col in VALID_COLUMNS:
            column_data[luck][col] = simulate_single_column_detailed(col, num_games=3000, luck=luck)

    # 3. 模拟登顶3列获胜的整体数据
    print("步骤 3/4: 模拟登顶3列获胜数据 (每种运气8000次)...")
    global WIN_CONDITION
    WIN_CONDITION = 3

    overall_data = {}
    overall_results = {}
    for luck in ["best", "normal", "worst"]:
        luck_name = {"best": "最佳", "normal": "普通", "worst": "最差"}[luck]
        print(f"  {luck_name}运气整体模拟...")
        stats, results = run_simulation_with_details(num_games=8000, greedy=0.6, luck=luck)
        overall_data[luck] = stats
        overall_results[luck] = results

    # 4. 排序找出最佳和最差列
    sorted_cols = sorted(VALID_COLUMNS, key=lambda c: column_data["normal"][c]["net_cost_mean"])
    best_3 = sorted_cols[:3]
    worst_3 = sorted_cols[-3:][::-1]  # 反转使最差的在前

    print("步骤 4/4: 生成分析报告和图表...")

    # ==================== 打印详细文字报告 ====================
    print()
    print("=" * 100)
    print("                              详 细 数 据 报 告")
    print("=" * 100)

    # 骰子概率表
    print("\n" + "=" * 60)
    print("第一部分: 骰子概率分布")
    print("=" * 60)
    print("\n6个骰子分成两组(各3个)时，各和值出现的概率:")
    print("-" * 50)
    sorted_probs = sorted(dice_probs.items(), key=lambda x: -x[1])
    for s, prob in sorted_probs:
        if 3 <= s <= 18:
            bar = "█" * int(prob / 2)
            print(f"  和={s:2d}: {prob:5.1f}% {bar}")

    # 每列详细数据
    print("\n" + "=" * 60)
    print("第二部分: 各列登顶消耗详细数据")
    print("=" * 60)

    for col in VALID_COLUMNS:
        prob = dice_probs.get(col, 0)
        height = COLUMN_HEIGHTS[col]

        print(f"\n{'─' * 60}")
        print(f"  列 {col} | 高度: {height}格 | 出现概率: {prob:.1f}%")
        print(f"{'─' * 60}")

        print(f"\n  {'运气类型':<10} | {'总消耗':^10} | {'净消耗':^10} | {'事件收益':^10} | {'5%分位':^10} | {'95%分位':^10}")
        print(f"  {'-' * 70}")

        for luck in ["best", "normal", "worst"]:
            luck_name = {"best": "最佳运气", "normal": "普通运气", "worst": "最差运气"}[luck]
            d = column_data[luck][col]
            event_score = d["cost_mean"] - d["net_cost_mean"]
            print(f"  {luck_name:<10} | {d['cost_mean']:^10.0f} | {d['net_cost_mean']:^10.0f} | {event_score:^10.0f} | {d['net_cost_p5']:^10.0f} | {d['net_cost_p95']:^10.0f}")

        # 每格效率
        per_cell_best = column_data["best"][col]["net_cost_mean"] / height
        per_cell_normal = column_data["normal"][col]["net_cost_mean"] / height
        per_cell_worst = column_data["worst"][col]["net_cost_mean"] / height
        print(f"\n  每格净消耗: 最佳={per_cell_best:.1f} | 普通={per_cell_normal:.1f} | 最差={per_cell_worst:.1f}")

    # 性价比排名
    print("\n" + "=" * 60)
    print("第三部分: 性价比排名 (按普通运气净消耗)")
    print("=" * 60)
    print()

    for i, col in enumerate(sorted_cols, 1):
        d = column_data["normal"][col]
        prob = dice_probs.get(col, 0)
        per_cell = d["net_cost_mean"] / COLUMN_HEIGHTS[col]
        marker = "🏆" if i <= 3 else ("💀" if i >= 14 else "  ")
        print(f"  {marker} 第{i:2d}名: 列{col:2d} | 净消耗={d['net_cost_mean']:6.0f} | {COLUMN_HEIGHTS[col]}格 | 概率={prob:5.1f}% | 每格={per_cell:5.1f}")

    # 最佳3列详细分析
    print("\n" + "=" * 60)
    print("第四部分: 最佳3列详细分析")
    print("=" * 60)

    for rank, col in enumerate(best_3, 1):
        print(f"\n{'═' * 60}")
        print(f"  🏆 第{rank}名: 列{col}")
        print(f"{'═' * 60}")

        d_normal = column_data["normal"][col]
        d_best = column_data["best"][col]
        d_worst = column_data["worst"][col]
        prob = dice_probs.get(col, 0)
        height = COLUMN_HEIGHTS[col]

        print(f"\n  基本信息:")
        print(f"    • 列高度: {height} 格")
        print(f"    • 投出概率: {prob:.1f}%")
        print(f"    • 性价比排名: 第{rank}名")

        print(f"\n  普通运气详细数据:")
        print(f"    • 总消耗: 平均={d_normal['cost_mean']:.0f}, 中位={d_normal['cost_median']:.0f}, 范围=[{d_normal['cost_min']:.0f}, {d_normal['cost_max']:.0f}]")
        print(f"    • 净消耗: 平均={d_normal['net_cost_mean']:.0f}, 中位={d_normal['net_cost_median']:.0f}, 范围=[{d_normal['net_cost_min']:.0f}, {d_normal['net_cost_max']:.0f}]")
        print(f"    • 净消耗分位: 5%={d_normal['net_cost_p5']:.0f}, 95%={d_normal['net_cost_p95']:.0f}")
        print(f"    • 每格净消耗: {d_normal['net_cost_mean']/height:.1f} 积分")
        print(f"    • 平均投骰次数: {d_normal['rolls_mean']:.1f} 次")

        print(f"\n  运气影响:")
        print(f"    • 最佳运气净消耗: {d_best['net_cost_mean']:.0f} 积分 (比普通少 {d_normal['net_cost_mean']-d_best['net_cost_mean']:.0f})")
        print(f"    • 最差运气净消耗: {d_worst['net_cost_mean']:.0f} 积分 (比普通多 {d_worst['net_cost_mean']-d_normal['net_cost_mean']:.0f})")
        print(f"    • 运气波动范围: {d_worst['net_cost_mean']-d_best['net_cost_mean']:.0f} 积分")

        # 该列的格子内容
        if col in BOARD_DATA:
            print(f"\n  该列格子内容:")
            for pos, cell in enumerate(BOARD_DATA[col], 1):
                cell_type, cell_id, cell_name = cell
                type_name = {"E": "遭遇", "I": "道具", "T": "陷阱"}[cell_type]
                print(f"    第{pos}格: [{type_name}] {cell_name}")

    # 最差3列详细分析
    print("\n" + "=" * 60)
    print("第五部分: 最差3列详细分析")
    print("=" * 60)

    for rank, col in enumerate(worst_3, 1):
        actual_rank = len(VALID_COLUMNS) - rank + 1
        print(f"\n{'═' * 60}")
        print(f"  💀 倒数第{rank}名 (第{actual_rank}名): 列{col}")
        print(f"{'═' * 60}")

        d_normal = column_data["normal"][col]
        d_best = column_data["best"][col]
        d_worst = column_data["worst"][col]
        prob = dice_probs.get(col, 0)
        height = COLUMN_HEIGHTS[col]

        print(f"\n  基本信息:")
        print(f"    • 列高度: {height} 格")
        print(f"    • 投出概率: {prob:.1f}% {'(极低!)' if prob < 10 else ''}")
        print(f"    • 性价比排名: 第{actual_rank}名")

        print(f"\n  普通运气详细数据:")
        print(f"    • 总消耗: 平均={d_normal['cost_mean']:.0f}, 中位={d_normal['cost_median']:.0f}, 范围=[{d_normal['cost_min']:.0f}, {d_normal['cost_max']:.0f}]")
        print(f"    • 净消耗: 平均={d_normal['net_cost_mean']:.0f}, 中位={d_normal['net_cost_median']:.0f}, 范围=[{d_normal['net_cost_min']:.0f}, {d_normal['net_cost_max']:.0f}]")
        print(f"    • 净消耗分位: 5%={d_normal['net_cost_p5']:.0f}, 95%={d_normal['net_cost_p95']:.0f}")
        print(f"    • 每格净消耗: {d_normal['net_cost_mean']/height:.1f} 积分 (极高!)")
        print(f"    • 平均投骰次数: {d_normal['rolls_mean']:.1f} 次")

        print(f"\n  运气影响:")
        print(f"    • 最佳运气净消耗: {d_best['net_cost_mean']:.0f} 积分")
        print(f"    • 最差运气净消耗: {d_worst['net_cost_mean']:.0f} 积分")
        print(f"    • 运气波动范围: {d_worst['net_cost_mean']-d_best['net_cost_mean']:.0f} 积分")

        # 该列的格子内容
        if col in BOARD_DATA:
            print(f"\n  该列格子内容:")
            for pos, cell in enumerate(BOARD_DATA[col], 1):
                cell_type, cell_id, cell_name = cell
                type_name = {"E": "遭遇", "I": "道具", "T": "陷阱"}[cell_type]
                print(f"    第{pos}格: [{type_name}] {cell_name}")

    # 整体游戏数据
    print("\n" + "=" * 60)
    print("第六部分: 登顶3列获胜整体数据")
    print("=" * 60)

    print(f"\n  {'运气类型':<12} | {'总消耗':^10} | {'净消耗':^10} | {'事件收益':^10} | {'投骰次数':^10} | {'轮次':^8}")
    print(f"  {'-' * 75}")
    for luck in ["best", "normal", "worst"]:
        luck_name = {"best": "最佳运气", "normal": "普通运气", "worst": "最差运气"}[luck]
        d = overall_data[luck]
        print(f"  {luck_name:<12} | {d['cost_mean']:^10.0f} | {d['net_cost_mean']:^10.0f} | {d['event_score_mean']:^10.0f} | {d['rolls_mean']:^10.1f} | {d['rounds_mean']:^8.1f}")

    # 最佳3列组合 vs 最差3列组合
    print("\n" + "=" * 60)
    print("第七部分: 最佳组合 vs 最差组合对比")
    print("=" * 60)

    best_combo_cost = sum(column_data["normal"][c]["net_cost_mean"] for c in best_3)
    worst_combo_cost = sum(column_data["normal"][c]["net_cost_mean"] for c in worst_3)

    print(f"\n  最佳组合 (列{best_3[0]}, {best_3[1]}, {best_3[2]}):")
    print(f"    • 普通运气总净消耗: {best_combo_cost:.0f} 积分")
    print(f"    • 最佳运气总净消耗: {sum(column_data['best'][c]['net_cost_mean'] for c in best_3):.0f} 积分")
    print(f"    • 最差运气总净消耗: {sum(column_data['worst'][c]['net_cost_mean'] for c in best_3):.0f} 积分")

    print(f"\n  最差组合 (列{worst_3[0]}, {worst_3[1]}, {worst_3[2]}):")
    print(f"    • 普通运气总净消耗: {worst_combo_cost:.0f} 积分")
    print(f"    • 最佳运气总净消耗: {sum(column_data['best'][c]['net_cost_mean'] for c in worst_3):.0f} 积分")
    print(f"    • 最差运气总净消耗: {sum(column_data['worst'][c]['net_cost_mean'] for c in worst_3):.0f} 积分")

    print(f"\n  差距: 最差组合比最佳组合多消耗 {worst_combo_cost - best_combo_cost:.0f} 积分 ({worst_combo_cost/best_combo_cost:.1f}倍)")

    # ==================== 生成超大图表 ====================
    if not MATPLOTLIB_AVAILABLE:
        print("\n需要安装 matplotlib 才能生成图表")
        return

    print("\n生成超详细图表...")

    # 创建超大图表 (6行4列)
    fig = plt.figure(figsize=(28, 36))
    fig.suptitle('贪骰无厌 2.0 - 超详细数据分析报告', fontsize=24, fontweight='bold', y=0.995)

    from matplotlib.gridspec import GridSpec
    gs = GridSpec(6, 4, figure=fig, hspace=0.35, wspace=0.3)

    columns = list(VALID_COLUMNS)
    x_cols = range(len(columns))

    # ========== 第1行: 基础数据 ==========

    # 1-1: 骰子概率分布
    ax1 = fig.add_subplot(gs[0, 0])
    probs = [dice_probs.get(c, 0) for c in columns]
    colors1 = plt.cm.RdYlGn([(p - min(probs)) / (max(probs) - min(probs)) for p in probs])
    bars1 = ax1.bar(x_cols, probs, color=colors1, alpha=0.8, edgecolor='white')
    ax1.set_xlabel('列号 (和值)', fontsize=10)
    ax1.set_ylabel('出现概率 (%)', fontsize=10)
    ax1.set_title('(1) 骰子和值出现概率', fontsize=12, fontweight='bold')
    ax1.set_xticks(x_cols)
    ax1.set_xticklabels(columns, fontsize=8)
    ax1.axhline(y=statistics.mean(probs), color='black', linestyle='--', alpha=0.5)
    for bar, p in zip(bars1, probs):
        ax1.annotate(f'{p:.0f}%', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 2), textcoords='offset points', ha='center', va='bottom', fontsize=7)

    # 1-2: 列高度
    ax2 = fig.add_subplot(gs[0, 1])
    heights = [COLUMN_HEIGHTS[c] for c in columns]
    colors2 = plt.cm.Blues([(h - min(heights) + 1) / (max(heights) - min(heights) + 1) for h in heights])
    bars2 = ax2.bar(x_cols, heights, color=colors2, alpha=0.8, edgecolor='white')
    ax2.set_xlabel('列号', fontsize=10)
    ax2.set_ylabel('格子数', fontsize=10)
    ax2.set_title('(2) 各列高度', fontsize=12, fontweight='bold')
    ax2.set_xticks(x_cols)
    ax2.set_xticklabels(columns, fontsize=8)
    for bar, h in zip(bars2, heights):
        ax2.annotate(f'{h}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 2), textcoords='offset points', ha='center', va='bottom', fontsize=9, fontweight='bold')

    # 1-3: 理论难度 (高度/概率)
    ax3 = fig.add_subplot(gs[0, 2])
    difficulty = [heights[i] / (probs[i] + 0.1) for i in range(len(columns))]
    colors3 = plt.cm.RdYlGn_r([(d - min(difficulty)) / (max(difficulty) - min(difficulty)) for d in difficulty])
    bars3 = ax3.bar(x_cols, difficulty, color=colors3, alpha=0.8, edgecolor='white')
    ax3.set_xlabel('列号', fontsize=10)
    ax3.set_ylabel('难度指数', fontsize=10)
    ax3.set_title('(3) 理论难度 (高度/概率)', fontsize=12, fontweight='bold')
    ax3.set_xticks(x_cols)
    ax3.set_xticklabels(columns, fontsize=8)

    # 1-4: 性价比排名
    ax4 = fig.add_subplot(gs[0, 3])
    ranks = {c: i+1 for i, c in enumerate(sorted_cols)}
    rank_values = [ranks[c] for c in columns]
    colors4 = plt.cm.RdYlGn_r([(r - 1) / (len(columns) - 1) for r in rank_values])
    bars4 = ax4.bar(x_cols, rank_values, color=colors4, alpha=0.8, edgecolor='white')
    ax4.set_xlabel('列号', fontsize=10)
    ax4.set_ylabel('排名 (1=最佳)', fontsize=10)
    ax4.set_title('(4) 性价比排名', fontsize=12, fontweight='bold')
    ax4.set_xticks(x_cols)
    ax4.set_xticklabels(columns, fontsize=8)
    ax4.invert_yaxis()
    for bar, r in zip(bars4, rank_values):
        ax4.annotate(f'#{r}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, -10), textcoords='offset points', ha='center', va='top',
                    fontsize=7, color='white', fontweight='bold')

    # ========== 第2行: 各列净消耗对比 ==========

    # 2-1: 总消耗对比 (3种运气)
    ax5 = fig.add_subplot(gs[1, 0])
    width = 0.25
    best_total = [column_data["best"][c]["cost_mean"] for c in columns]
    normal_total = [column_data["normal"][c]["cost_mean"] for c in columns]
    worst_total = [column_data["worst"][c]["cost_mean"] for c in columns]
    ax5.bar([i - width for i in x_cols], best_total, width, label='最佳运气', color='#2ecc71', alpha=0.8)
    ax5.bar(x_cols, normal_total, width, label='普通运气', color='#3498db', alpha=0.8)
    ax5.bar([i + width for i in x_cols], worst_total, width, label='最差运气', color='#e74c3c', alpha=0.8)
    ax5.set_xlabel('列号', fontsize=10)
    ax5.set_ylabel('总消耗积分', fontsize=10)
    ax5.set_title('(5) 各列总消耗对比', fontsize=12, fontweight='bold')
    ax5.set_xticks(x_cols)
    ax5.set_xticklabels(columns, fontsize=8)
    ax5.legend(fontsize=8)

    # 2-2: 净消耗对比 (3种运气)
    ax6 = fig.add_subplot(gs[1, 1])
    best_net = [column_data["best"][c]["net_cost_mean"] for c in columns]
    normal_net = [column_data["normal"][c]["net_cost_mean"] for c in columns]
    worst_net = [column_data["worst"][c]["net_cost_mean"] for c in columns]
    ax6.bar([i - width for i in x_cols], best_net, width, label='最佳运气', color='#2ecc71', alpha=0.8)
    ax6.bar(x_cols, normal_net, width, label='普通运气', color='#3498db', alpha=0.8)
    ax6.bar([i + width for i in x_cols], worst_net, width, label='最差运气', color='#e74c3c', alpha=0.8)
    ax6.set_xlabel('列号', fontsize=10)
    ax6.set_ylabel('净消耗积分', fontsize=10)
    ax6.set_title('(6) 各列净消耗对比', fontsize=12, fontweight='bold')
    ax6.set_xticks(x_cols)
    ax6.set_xticklabels(columns, fontsize=8)
    ax6.legend(fontsize=8)
    ax6.axhline(y=0, color='black', linestyle='-', alpha=0.3)

    # 2-3: 事件收益对比
    ax7 = fig.add_subplot(gs[1, 2])
    best_event = [column_data["best"][c]["cost_mean"] - column_data["best"][c]["net_cost_mean"] for c in columns]
    normal_event = [column_data["normal"][c]["cost_mean"] - column_data["normal"][c]["net_cost_mean"] for c in columns]
    worst_event = [column_data["worst"][c]["cost_mean"] - column_data["worst"][c]["net_cost_mean"] for c in columns]
    ax7.bar([i - width for i in x_cols], best_event, width, label='最佳运气', color='#2ecc71', alpha=0.8)
    ax7.bar(x_cols, normal_event, width, label='普通运气', color='#3498db', alpha=0.8)
    ax7.bar([i + width for i in x_cols], worst_event, width, label='最差运气', color='#e74c3c', alpha=0.8)
    ax7.set_xlabel('列号', fontsize=10)
    ax7.set_ylabel('事件收益积分', fontsize=10)
    ax7.set_title('(7) 各列事件收益对比', fontsize=12, fontweight='bold')
    ax7.set_xticks(x_cols)
    ax7.set_xticklabels(columns, fontsize=8)
    ax7.legend(fontsize=8)
    ax7.axhline(y=0, color='black', linestyle='-', alpha=0.3)

    # 2-4: 每格效率对比
    ax8 = fig.add_subplot(gs[1, 3])
    per_cell = [column_data["normal"][c]["net_cost_mean"] / COLUMN_HEIGHTS[c] for c in columns]
    colors8 = ['#2ecc71' if cost < statistics.mean(per_cell) else '#e74c3c' for cost in per_cell]
    bars8 = ax8.bar(x_cols, per_cell, color=colors8, alpha=0.8, edgecolor='white')
    ax8.set_xlabel('列号', fontsize=10)
    ax8.set_ylabel('每格净消耗', fontsize=10)
    ax8.set_title('(8) 每格效率 (绿=高效)', fontsize=12, fontweight='bold')
    ax8.set_xticks(x_cols)
    ax8.set_xticklabels(columns, fontsize=8)
    ax8.axhline(y=statistics.mean(per_cell), color='black', linestyle='--', alpha=0.5)

    # ========== 第3行: 分布图 ==========

    # 3-1: 所有列净消耗箱线图
    ax9 = fig.add_subplot(gs[2, :2])
    box_data_all = [column_data["normal"][c]["all_net_costs"] for c in columns]
    bp9 = ax9.boxplot(box_data_all, tick_labels=[f'{c}' for c in columns], patch_artist=True)
    colors9 = plt.cm.viridis(np.linspace(0, 1, len(columns)))
    for patch, color in zip(bp9['boxes'], colors9):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax9.set_xlabel('列号', fontsize=10)
    ax9.set_ylabel('净消耗积分', fontsize=10)
    ax9.set_title('(9) 各列净消耗分布箱线图 (普通运气)', fontsize=12, fontweight='bold')
    ax9.axhline(y=0, color='red', linestyle='--', alpha=0.5)

    # 3-2: 最佳3列 vs 最差3列箱线图
    ax10 = fig.add_subplot(gs[2, 2:])
    compare_cols = best_3 + worst_3
    compare_labels = [f'列{c}\n(#{ranks[c]})' for c in compare_cols]
    box_data_compare = [column_data["normal"][c]["all_net_costs"] for c in compare_cols]
    bp10 = ax10.boxplot(box_data_compare, tick_labels=compare_labels, patch_artist=True)
    colors10 = ['#2ecc71'] * 3 + ['#e74c3c'] * 3
    for patch, color in zip(bp10['boxes'], colors10):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax10.set_ylabel('净消耗积分', fontsize=10)
    ax10.set_title('(10) 最佳3列 vs 最差3列 净消耗分布', fontsize=12, fontweight='bold')
    ax10.axhline(y=0, color='black', linestyle='--', alpha=0.5)

    # ========== 第4行: 最佳列详细分析 ==========

    # 4-1: 最佳列(第1名)累积分布
    ax11 = fig.add_subplot(gs[3, 0])
    col = best_3[0]
    for luck, color, label in [("best", '#2ecc71', '最佳运气'),
                                ("normal", '#3498db', '普通运气'),
                                ("worst", '#e74c3c', '最差运气')]:
        net_costs_sorted = sorted(column_data[luck][col]["all_net_costs"])
        percentiles = [(i + 1) / len(net_costs_sorted) * 100 for i in range(len(net_costs_sorted))]
        ax11.plot(net_costs_sorted, percentiles, color=color, linewidth=2, label=label)
        ax11.fill_between(net_costs_sorted, percentiles, alpha=0.1, color=color)
    ax11.set_xlabel('净消耗积分', fontsize=10)
    ax11.set_ylabel('累积百分比 (%)', fontsize=10)
    ax11.set_title(f'(11) 第1名 列{col} 累积分布', fontsize=12, fontweight='bold')
    ax11.legend(fontsize=8)
    ax11.axvline(x=0, color='black', linestyle='--', alpha=0.5)
    ax11.grid(True, alpha=0.3)

    # 4-2: 第2名累积分布
    ax12 = fig.add_subplot(gs[3, 1])
    col = best_3[1]
    for luck, color, label in [("best", '#2ecc71', '最佳运气'),
                                ("normal", '#3498db', '普通运气'),
                                ("worst", '#e74c3c', '最差运气')]:
        net_costs_sorted = sorted(column_data[luck][col]["all_net_costs"])
        percentiles = [(i + 1) / len(net_costs_sorted) * 100 for i in range(len(net_costs_sorted))]
        ax12.plot(net_costs_sorted, percentiles, color=color, linewidth=2, label=label)
        ax12.fill_between(net_costs_sorted, percentiles, alpha=0.1, color=color)
    ax12.set_xlabel('净消耗积分', fontsize=10)
    ax12.set_ylabel('累积百分比 (%)', fontsize=10)
    ax12.set_title(f'(12) 第2名 列{col} 累积分布', fontsize=12, fontweight='bold')
    ax12.legend(fontsize=8)
    ax12.axvline(x=0, color='black', linestyle='--', alpha=0.5)
    ax12.grid(True, alpha=0.3)

    # 4-3: 第3名累积分布
    ax13 = fig.add_subplot(gs[3, 2])
    col = best_3[2]
    for luck, color, label in [("best", '#2ecc71', '最佳运气'),
                                ("normal", '#3498db', '普通运气'),
                                ("worst", '#e74c3c', '最差运气')]:
        net_costs_sorted = sorted(column_data[luck][col]["all_net_costs"])
        percentiles = [(i + 1) / len(net_costs_sorted) * 100 for i in range(len(net_costs_sorted))]
        ax13.plot(net_costs_sorted, percentiles, color=color, linewidth=2, label=label)
        ax13.fill_between(net_costs_sorted, percentiles, alpha=0.1, color=color)
    ax13.set_xlabel('净消耗积分', fontsize=10)
    ax13.set_ylabel('累积百分比 (%)', fontsize=10)
    ax13.set_title(f'(13) 第3名 列{col} 累积分布', fontsize=12, fontweight='bold')
    ax13.legend(fontsize=8)
    ax13.axvline(x=0, color='black', linestyle='--', alpha=0.5)
    ax13.grid(True, alpha=0.3)

    # 4-4: 最佳3列组合总消耗
    ax14 = fig.add_subplot(gs[3, 3])
    combo_labels = ['最佳运气', '普通运气', '最差运气']
    combo_values = [
        sum(column_data["best"][c]["net_cost_mean"] for c in best_3),
        sum(column_data["normal"][c]["net_cost_mean"] for c in best_3),
        sum(column_data["worst"][c]["net_cost_mean"] for c in best_3)
    ]
    colors14 = ['#2ecc71', '#3498db', '#e74c3c']
    bars14 = ax14.bar(combo_labels, combo_values, color=colors14, alpha=0.8, edgecolor='white')
    ax14.set_ylabel('总净消耗积分', fontsize=10)
    ax14.set_title(f'(14) 最佳组合 ({best_3[0]},{best_3[1]},{best_3[2]}) 总消耗', fontsize=12, fontweight='bold')
    for bar, val in zip(bars14, combo_values):
        ax14.annotate(f'{val:.0f}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 3), textcoords='offset points', ha='center', va='bottom', fontsize=10, fontweight='bold')

    # ========== 第5行: 最差列详细分析 ==========

    # 5-1: 倒数第1名累积分布
    ax15 = fig.add_subplot(gs[4, 0])
    col = worst_3[0]
    for luck, color, label in [("best", '#2ecc71', '最佳运气'),
                                ("normal", '#3498db', '普通运气'),
                                ("worst", '#e74c3c', '最差运气')]:
        net_costs_sorted = sorted(column_data[luck][col]["all_net_costs"])
        percentiles = [(i + 1) / len(net_costs_sorted) * 100 for i in range(len(net_costs_sorted))]
        ax15.plot(net_costs_sorted, percentiles, color=color, linewidth=2, label=label)
        ax15.fill_between(net_costs_sorted, percentiles, alpha=0.1, color=color)
    ax15.set_xlabel('净消耗积分', fontsize=10)
    ax15.set_ylabel('累积百分比 (%)', fontsize=10)
    ax15.set_title(f'(15) 倒数第1 列{col} 累积分布', fontsize=12, fontweight='bold')
    ax15.legend(fontsize=8)
    ax15.grid(True, alpha=0.3)

    # 5-2: 倒数第2名累积分布
    ax16 = fig.add_subplot(gs[4, 1])
    col = worst_3[1]
    for luck, color, label in [("best", '#2ecc71', '最佳运气'),
                                ("normal", '#3498db', '普通运气'),
                                ("worst", '#e74c3c', '最差运气')]:
        net_costs_sorted = sorted(column_data[luck][col]["all_net_costs"])
        percentiles = [(i + 1) / len(net_costs_sorted) * 100 for i in range(len(net_costs_sorted))]
        ax16.plot(net_costs_sorted, percentiles, color=color, linewidth=2, label=label)
        ax16.fill_between(net_costs_sorted, percentiles, alpha=0.1, color=color)
    ax16.set_xlabel('净消耗积分', fontsize=10)
    ax16.set_ylabel('累积百分比 (%)', fontsize=10)
    ax16.set_title(f'(16) 倒数第2 列{col} 累积分布', fontsize=12, fontweight='bold')
    ax16.legend(fontsize=8)
    ax16.grid(True, alpha=0.3)

    # 5-3: 倒数第3名累积分布
    ax17 = fig.add_subplot(gs[4, 2])
    col = worst_3[2]
    for luck, color, label in [("best", '#2ecc71', '最佳运气'),
                                ("normal", '#3498db', '普通运气'),
                                ("worst", '#e74c3c', '最差运气')]:
        net_costs_sorted = sorted(column_data[luck][col]["all_net_costs"])
        percentiles = [(i + 1) / len(net_costs_sorted) * 100 for i in range(len(net_costs_sorted))]
        ax17.plot(net_costs_sorted, percentiles, color=color, linewidth=2, label=label)
        ax17.fill_between(net_costs_sorted, percentiles, alpha=0.1, color=color)
    ax17.set_xlabel('净消耗积分', fontsize=10)
    ax17.set_ylabel('累积百分比 (%)', fontsize=10)
    ax17.set_title(f'(17) 倒数第3 列{col} 累积分布', fontsize=12, fontweight='bold')
    ax17.legend(fontsize=8)
    ax17.grid(True, alpha=0.3)

    # 5-4: 最差3列组合总消耗
    ax18 = fig.add_subplot(gs[4, 3])
    combo_values_worst = [
        sum(column_data["best"][c]["net_cost_mean"] for c in worst_3),
        sum(column_data["normal"][c]["net_cost_mean"] for c in worst_3),
        sum(column_data["worst"][c]["net_cost_mean"] for c in worst_3)
    ]
    bars18 = ax18.bar(combo_labels, combo_values_worst, color=colors14, alpha=0.8, edgecolor='white')
    ax18.set_ylabel('总净消耗积分', fontsize=10)
    ax18.set_title(f'(18) 最差组合 ({worst_3[0]},{worst_3[1]},{worst_3[2]}) 总消耗', fontsize=12, fontweight='bold')
    for bar, val in zip(bars18, combo_values_worst):
        ax18.annotate(f'{val:.0f}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                    xytext=(0, 3), textcoords='offset points', ha='center', va='bottom', fontsize=10, fontweight='bold')

    # ========== 第6行: 整体游戏和数据汇总 ==========

    # 6-1: 登顶3列整体净消耗分布
    ax19 = fig.add_subplot(gs[5, 0])
    for luck, color, label in [("best", '#2ecc71', '最佳运气'),
                                ("normal", '#3498db', '普通运气'),
                                ("worst", '#e74c3c', '最差运气')]:
        ax19.hist(overall_data[luck]["net_costs"], bins=40, alpha=0.5, label=label, color=color, edgecolor='white')
    ax19.set_xlabel('净消耗积分', fontsize=10)
    ax19.set_ylabel('频次', fontsize=10)
    ax19.set_title('(19) 登顶3列 净消耗分布', fontsize=12, fontweight='bold')
    ax19.legend(fontsize=8)
    ax19.axvline(x=0, color='black', linestyle='--', alpha=0.5)

    # 6-2: 整体运气影响对比
    ax20 = fig.add_subplot(gs[5, 1])
    x20 = range(3)
    width20 = 0.35
    net_vals = [overall_data[luck]["net_cost_mean"] for luck in ["best", "normal", "worst"]]
    event_vals = [overall_data[luck]["event_score_mean"] for luck in ["best", "normal", "worst"]]
    ax20.bar([i - width20/2 for i in x20], net_vals, width20, label='净消耗', color='#e74c3c', alpha=0.8)
    ax20.bar([i + width20/2 for i in x20], event_vals, width20, label='事件收益', color='#2ecc71', alpha=0.8)
    ax20.set_xticks(x20)
    ax20.set_xticklabels(['最佳运气', '普通运气', '最差运气'])
    ax20.set_ylabel('积分', fontsize=10)
    ax20.set_title('(20) 运气对整体游戏影响', fontsize=12, fontweight='bold')
    ax20.legend(fontsize=8)
    ax20.axhline(y=0, color='black', linestyle='-', alpha=0.3)

    # 6-3: 最佳 vs 最差组合对比
    ax21 = fig.add_subplot(gs[5, 2])
    compare_data = {
        '最佳组合\n最佳运气': sum(column_data["best"][c]["net_cost_mean"] for c in best_3),
        '最佳组合\n普通运气': sum(column_data["normal"][c]["net_cost_mean"] for c in best_3),
        '最佳组合\n最差运气': sum(column_data["worst"][c]["net_cost_mean"] for c in best_3),
        '最差组合\n最佳运气': sum(column_data["best"][c]["net_cost_mean"] for c in worst_3),
        '最差组合\n普通运气': sum(column_data["normal"][c]["net_cost_mean"] for c in worst_3),
        '最差组合\n最差运气': sum(column_data["worst"][c]["net_cost_mean"] for c in worst_3),
    }
    colors21 = ['#27ae60', '#2980b9', '#c0392b', '#27ae60', '#2980b9', '#c0392b']
    bars21 = ax21.bar(range(6), list(compare_data.values()), color=colors21, alpha=0.8, edgecolor='white')
    ax21.set_xticks(range(6))
    ax21.set_xticklabels(list(compare_data.keys()), fontsize=7, rotation=45, ha='right')
    ax21.set_ylabel('总净消耗积分', fontsize=10)
    ax21.set_title('(21) 最佳组合 vs 最差组合', fontsize=12, fontweight='bold')
    # 分隔线
    ax21.axvline(x=2.5, color='black', linestyle='--', alpha=0.5)

    # 6-4: 数据汇总表格
    ax22 = fig.add_subplot(gs[5, 3])
    ax22.axis('off')

    summary_text = f"""数据汇总

最佳3列: {best_3[0]}, {best_3[1]}, {best_3[2]}
最差3列: {worst_3[0]}, {worst_3[1]}, {worst_3[2]}

最佳组合普通运气: {sum(column_data["normal"][c]["net_cost_mean"] for c in best_3):.0f} 积分
最差组合普通运气: {sum(column_data["normal"][c]["net_cost_mean"] for c in worst_3):.0f} 积分
差距: {sum(column_data["normal"][c]["net_cost_mean"] for c in worst_3) - sum(column_data["normal"][c]["net_cost_mean"] for c in best_3):.0f} 积分

登顶3列 (普通运气):
  净消耗: {overall_data["normal"]["net_cost_mean"]:.0f} 积分
  事件收益: {overall_data["normal"]["event_score_mean"]:.0f} 积分

投出概率最高: 列10, 列11 (80.2%)
投出概率最低: 列3, 列18 (6.2%)"""

    ax22.text(0.5, 0.5, summary_text, transform=ax22.transAxes, fontsize=9,
              verticalalignment='center', horizontalalignment='center',
              bbox=dict(boxstyle='round', facecolor='#ecf0f1', edgecolor='#bdc3c7'))
    ax22.set_title('(22) 数据汇总', fontsize=12, fontweight='bold')

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    save_path = os.path.join(os.path.dirname(__file__), "ultra_detailed_analysis.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
    print(f"\n超详细图表已保存到: {save_path}")
    plt.close()

    print("\n" + "=" * 100)
    print("超详细分析完成!")
    print("=" * 100)


def generate_per_column_charts():
    """为每一列生成单独的 simulation_game_result.png 风格图表"""
    if not MATPLOTLIB_AVAILABLE:
        print("需要安装 matplotlib: pip install matplotlib")
        return

    print("=" * 80)
    print("贪骰无厌 2.0 - 每列单独图表生成")
    print("=" * 80)
    print()

    # 创建输出目录
    output_dir = os.path.join(os.path.dirname(__file__), "per_column_charts")
    os.makedirs(output_dir, exist_ok=True)
    print(f"输出目录: {output_dir}")
    print()

    # 计算骰子概率
    dice_probs = calculate_dice_probabilities()

    for col in VALID_COLUMNS:
        print(f"正在生成列 {col} 的图表...")

        # 收集三种运气情况的数据
        best_data = simulate_single_column_detailed(col, num_games=3000, luck="best")
        normal_data = simulate_single_column_detailed(col, num_games=3000, luck="normal")
        worst_data = simulate_single_column_detailed(col, num_games=3000, luck="worst")

        # 创建图表
        fig, axes = plt.subplots(2, 3, figsize=(16, 10))
        prob = dice_probs.get(col, 0)
        fig.suptitle(f'贪骰无厌 - 列 {col} 模拟统计结果\n(高度: {COLUMN_HEIGHTS[col]}格, 骰子概率: {prob:.1f}%)',
                     fontsize=16, fontweight='bold')

        colors = {'best': '#2ecc71', 'normal': '#3498db', 'worst': '#e74c3c'}
        labels = {'best': '最佳运气', 'normal': '普通运气', 'worst': '最差运气'}

        # 1. 净消耗分布直方图
        ax1 = axes[0, 0]
        for data, key in [(best_data, 'best'), (normal_data, 'normal'), (worst_data, 'worst')]:
            ax1.hist(data['all_net_costs'], bins=30, alpha=0.5, label=labels[key], color=colors[key], edgecolor='white')
        ax1.set_xlabel('净消耗积分')
        ax1.set_ylabel('频次')
        ax1.set_title('净消耗分布')
        ax1.legend()
        ax1.axvline(x=0, color='black', linestyle='--', alpha=0.5, label='零点')

        # 2. 总消耗分布直方图
        ax2 = axes[0, 1]
        for data, key in [(best_data, 'best'), (normal_data, 'normal'), (worst_data, 'worst')]:
            ax2.hist(data['all_costs'], bins=30, alpha=0.5, label=labels[key], color=colors[key], edgecolor='white')
        ax2.set_xlabel('总消耗积分')
        ax2.set_ylabel('频次')
        ax2.set_title('总消耗分布')
        ax2.legend()

        # 3. 累积分布图
        ax3 = axes[0, 2]
        for data, key in [(best_data, 'best'), (normal_data, 'normal'), (worst_data, 'worst')]:
            sorted_costs = sorted(data['all_net_costs'])
            n = len(sorted_costs)
            percentiles = [(i + 1) / n * 100 for i in range(n)]
            ax3.plot(sorted_costs, percentiles, color=colors[key], linewidth=2, label=labels[key])
            ax3.fill_between(sorted_costs, percentiles, alpha=0.2, color=colors[key])
        ax3.set_xlabel('净消耗积分')
        ax3.set_ylabel('累积百分比 (%)')
        ax3.set_title('净消耗累积分布')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        ax3.axvline(x=0, color='black', linestyle='--', alpha=0.5)

        # 4. 箱线图对比 - 净消耗
        ax4 = axes[1, 0]
        box_data = [best_data['all_net_costs'], normal_data['all_net_costs'], worst_data['all_net_costs']]
        bp = ax4.boxplot(box_data, labels=['最佳运气', '普通运气', '最差运气'], patch_artist=True)
        for patch, color in zip(bp['boxes'], [colors['best'], colors['normal'], colors['worst']]):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax4.set_ylabel('净消耗积分')
        ax4.set_title('净消耗箱线图对比')
        ax4.axhline(y=0, color='black', linestyle='--', alpha=0.5)

        # 5. 平均值对比柱状图
        ax5 = axes[1, 1]
        x = range(3)
        width = 0.35

        net_cost_means = [best_data['net_cost_mean'], normal_data['net_cost_mean'], worst_data['net_cost_mean']]
        cost_means = [best_data['cost_mean'], normal_data['cost_mean'], worst_data['cost_mean']]

        ax5.bar([i - width/2 for i in x], cost_means, width, label='总消耗', color='#9b59b6', alpha=0.8)
        ax5.bar([i + width/2 for i in x], net_cost_means, width, label='净消耗', color='#1abc9c', alpha=0.8)

        ax5.set_xticks(x)
        ax5.set_xticklabels(['最佳运气', '普通运气', '最差运气'])
        ax5.set_ylabel('积分')
        ax5.set_title('平均消耗对比')
        ax5.legend()
        ax5.axhline(y=0, color='black', linestyle='--', alpha=0.5)

        # 添加数值标签
        for i, (cost, net) in enumerate(zip(cost_means, net_cost_means)):
            ax5.annotate(f'{cost:.0f}', xy=(i - width/2, cost), ha='center', va='bottom', fontsize=8)
            ax5.annotate(f'{net:.0f}', xy=(i + width/2, net), ha='center', va='bottom', fontsize=8)

        # 6. 详细统计信息
        ax6 = axes[1, 2]
        ax6.axis('off')

        # 获取该列的格子内容
        cells = BOARD_DATA.get(col, [])
        cell_info = ""
        for i, (cell_type, cell_id, cell_name) in enumerate(cells, 1):
            type_name = {"E": "遭遇", "I": "道具", "T": "陷阱"}[cell_type]
            cell_info += f"  {i}. [{type_name}] {cell_name}\n"

        stats_text = f"""列 {col} 详细统计

高度: {COLUMN_HEIGHTS[col]} 格
骰子概率: {prob:.1f}%

最佳运气:
  净消耗: {best_data['net_cost_mean']:.0f} (中位: {best_data['net_cost_median']:.0f})
  5%-95%: {best_data['net_cost_p5']:.0f} ~ {best_data['net_cost_p95']:.0f}

普通运气:
  净消耗: {normal_data['net_cost_mean']:.0f} (中位: {normal_data['net_cost_median']:.0f})
  5%-95%: {normal_data['net_cost_p5']:.0f} ~ {normal_data['net_cost_p95']:.0f}

最差运气:
  净消耗: {worst_data['net_cost_mean']:.0f} (中位: {worst_data['net_cost_median']:.0f})
  5%-95%: {worst_data['net_cost_p5']:.0f} ~ {worst_data['net_cost_p95']:.0f}

格子内容:
{cell_info}"""
        ax6.text(0.5, 0.5, stats_text, transform=ax6.transAxes, fontsize=9,
                 verticalalignment='center', horizontalalignment='center',
                 bbox=dict(boxstyle='round', facecolor='#ecf0f1', edgecolor='#bdc3c7'))

        plt.tight_layout()

        # 保存图表
        save_path = os.path.join(output_dir, f"column_{col}_result.png")
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()

        print(f"  已保存: {save_path}")

    print()
    print("=" * 80)
    print(f"所有图表已生成完毕! 共 {len(VALID_COLUMNS)} 个文件")
    print(f"保存目录: {output_dir}")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--per-column":
        run_per_column_simulation()
    elif len(sys.argv) > 1 and sys.argv[1] == "--comprehensive":
        run_comprehensive_analysis()
    elif len(sys.argv) > 1 and sys.argv[1] == "--ultra":
        run_ultra_detailed_analysis()
    elif len(sys.argv) > 1 and sys.argv[1] == "--per-column-charts":
        generate_per_column_charts()
    else:
        main()
