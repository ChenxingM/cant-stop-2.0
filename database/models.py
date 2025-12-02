# -*- coding: utf-8 -*-
"""
数据模型层
Data Models for Can't Stop Game
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
import json


@dataclass
class Player:
    """玩家数据模型"""
    qq_id: str
    nickname: str
    faction: Optional[str] = None  # '收养人' or 'Aeonreth'
    total_score: int = 0
    current_score: int = 0
    created_at: Optional[datetime] = None
    last_active: Optional[datetime] = None


@dataclass
class Position:
    """位置标记模型"""
    column_number: int
    position: int
    marker_type: str  # 'temp' or 'permanent'


@dataclass
class InventoryItem:
    """背包物品模型"""
    item_id: int
    item_name: str
    item_type: str  # 'item', 'hidden_item', 'special'
    quantity: int = 1
    obtained_at: Optional[datetime] = None


@dataclass
class Achievement:
    """成就模型"""
    achievement_id: int
    achievement_name: str
    achievement_type: str  # 'normal', 'hidden', 'first_clear'
    obtained_at: Optional[datetime] = None


@dataclass
class PlayerGameState:
    """玩家游戏状态"""
    qq_id: str
    current_round_active: bool = False
    can_start_new_round: bool = True
    temp_markers_used: int = 0
    dice_history: List[List[int]] = field(default_factory=list)
    last_dice_result: Optional[List[int]] = None
    topped_columns: List[int] = field(default_factory=list)
    skipped_rounds: int = 0  # 被暂停的回合数
    pending_encounter: Optional[Dict] = None  # 等待选择的遭遇信息 {column, position, encounter_id, encounter_name} (已废弃，保留兼容)
    pending_encounters: List[Dict] = field(default_factory=list)  # 等待选择的遭遇队列
    extra_d6_check_six: bool = False  # 下次投骰额外投一个d6，如果是6则本回合作废

    # 陷阱效果相关状态
    next_dice_fixed: Optional[List[int]] = None  # 下回合固定骰子结果
    next_dice_count: Optional[int] = None  # 下回合骰子数量
    next_dice_groups: Optional[List[int]] = None  # 下回合骰子分组方式
    forced_remaining_rounds: int = 0  # 强制进行的剩余回合数
    odd_even_check_active: bool = False  # 奇偶检定激活
    math_check_active: bool = False  # 数学检定激活
    lockout_until: Optional[str] = None  # 锁定到的时间（ISO格式字符串）
    pending_trap_choice: Optional[Dict] = None  # 等待处理的陷阱选择

    # 陷阱免疫状态
    trap_immunity_cost: Optional[int] = None  # 下个陷阱可消耗积分免疫（小女孩娃娃-戳脸蛋）
    trap_immunity_draw: bool = False  # 下个陷阱可通过绘制免疫（小女孩娃娃-戳手）

    # 花言巧语封锁状态
    sweet_talk_blocked: Optional[Dict] = None  # {blocked_columns: [列号], from_qq: 施放者QQ}

    def to_dict(self) -> dict:
        """转换为字典（用于存储）"""
        return {
            'current_round_active': int(self.current_round_active),
            'can_start_new_round': int(self.can_start_new_round),
            'temp_markers_used': self.temp_markers_used,
            'dice_history': json.dumps(self.dice_history),
            'last_dice_result': json.dumps(self.last_dice_result) if self.last_dice_result else None,
            'topped_columns': json.dumps(self.topped_columns),
            'skipped_rounds': self.skipped_rounds,
            'pending_encounter': json.dumps(self.pending_encounter) if self.pending_encounter else None,
            'pending_encounters': json.dumps(self.pending_encounters),
            'extra_d6_check_six': int(self.extra_d6_check_six),
            'next_dice_fixed': json.dumps(self.next_dice_fixed) if self.next_dice_fixed else None,
            'next_dice_count': self.next_dice_count,
            'next_dice_groups': json.dumps(self.next_dice_groups) if self.next_dice_groups else None,
            'forced_remaining_rounds': self.forced_remaining_rounds,
            'odd_even_check_active': int(self.odd_even_check_active),
            'math_check_active': int(self.math_check_active),
            'lockout_until': self.lockout_until,
            'pending_trap_choice': json.dumps(self.pending_trap_choice) if self.pending_trap_choice else None,
            'trap_immunity_cost': self.trap_immunity_cost,
            'trap_immunity_draw': int(self.trap_immunity_draw),
            'sweet_talk_blocked': json.dumps(self.sweet_talk_blocked) if self.sweet_talk_blocked else None
        }

    @staticmethod
    def from_dict(qq_id: str, data: dict) -> 'PlayerGameState':
        """从字典创建（用于读取）"""
        # 处理可能为 NULL 的 JSON 字段
        dice_history_raw = data.get('dice_history')
        dice_history = json.loads(dice_history_raw) if dice_history_raw else []

        last_dice_raw = data.get('last_dice_result')
        last_dice_result = json.loads(last_dice_raw) if last_dice_raw else None

        topped_columns_raw = data.get('topped_columns')
        topped_columns = json.loads(topped_columns_raw) if topped_columns_raw else []

        pending_encounter_raw = data.get('pending_encounter')
        pending_encounter = json.loads(pending_encounter_raw) if pending_encounter_raw else None

        pending_encounters_raw = data.get('pending_encounters')
        pending_encounters = json.loads(pending_encounters_raw) if pending_encounters_raw else []

        next_dice_fixed_raw = data.get('next_dice_fixed')
        next_dice_fixed = json.loads(next_dice_fixed_raw) if next_dice_fixed_raw else None

        next_dice_groups_raw = data.get('next_dice_groups')
        next_dice_groups = json.loads(next_dice_groups_raw) if next_dice_groups_raw else None

        pending_trap_choice_raw = data.get('pending_trap_choice')
        pending_trap_choice = json.loads(pending_trap_choice_raw) if pending_trap_choice_raw else None

        sweet_talk_blocked_raw = data.get('sweet_talk_blocked')
        sweet_talk_blocked = json.loads(sweet_talk_blocked_raw) if sweet_talk_blocked_raw else None

        return PlayerGameState(
            qq_id=qq_id,
            current_round_active=bool(data.get('current_round_active', 0)),
            can_start_new_round=bool(data.get('can_start_new_round', 1)),
            temp_markers_used=data.get('temp_markers_used', 0),
            dice_history=dice_history,
            last_dice_result=last_dice_result,
            topped_columns=topped_columns,
            skipped_rounds=data.get('skipped_rounds', 0),
            pending_encounter=pending_encounter,
            pending_encounters=pending_encounters,
            extra_d6_check_six=bool(data.get('extra_d6_check_six', 0)),
            next_dice_fixed=next_dice_fixed,
            next_dice_count=data.get('next_dice_count'),
            next_dice_groups=next_dice_groups,
            forced_remaining_rounds=data.get('forced_remaining_rounds', 0),
            odd_even_check_active=bool(data.get('odd_even_check_active', 0)),
            math_check_active=bool(data.get('math_check_active', 0)),
            lockout_until=data.get('lockout_until'),
            pending_trap_choice=pending_trap_choice,
            trap_immunity_cost=data.get('trap_immunity_cost'),
            trap_immunity_draw=bool(data.get('trap_immunity_draw', 0)),
            sweet_talk_blocked=sweet_talk_blocked
        )


@dataclass
class ShopItem:
    """商店道具模型"""
    item_id: int
    item_name: str
    item_type: str
    price: int
    faction_limit: Optional[str]  # '通用', '收养人', 'Aeonreth'
    global_limit: int = -1  # -1表示无限制
    global_sold: int = 0
    unlocked: bool = False
    description: Optional[str] = None
    player_limit: int = -1  # 每人限购数量，-1表示无限制

    def can_buy(self, player: Player, current_owned: int = 0) -> tuple[bool, str]:
        """检查玩家是否可以购买

        Args:
            player: 玩家对象
            current_owned: 玩家当前拥有该道具的数量
        """
        # 检查是否解锁
        if not self.unlocked and self.item_type != 'special':
            return False, "该道具尚未解锁"

        # 检查阵营限制
        if self.faction_limit and self.faction_limit != '通用':
            if not player.faction:
                return False, "请先选择阵营"
            if player.faction != self.faction_limit:
                return False, f"该道具仅限{self.faction_limit}使用"

        # 检查积分
        if player.current_score < self.price:
            return False, f"积分不足，需要{self.price}积分"

        # 检查全局限制
        if self.global_limit > 0 and self.global_sold >= self.global_limit:
            return False, "该道具已售罄"

        # 检查每人限购
        if self.player_limit > 0 and current_owned >= self.player_limit:
            return False, f"该道具每人限购{self.player_limit}个，您已拥有{current_owned}个"

        return True, "可以购买"


@dataclass
class DiceRoll:
    """骰子投掷结果"""
    results: List[int]
    timestamp: datetime = field(default_factory=datetime.now)

    def get_possible_sums(self) -> List[tuple[int, int]]:
        """获取所有可能的两组和"""
        from itertools import combinations

        if len(self.results) != 6:
            return []

        possible_sums = []
        # 遍历所有可能的3+3分组
        for indices in combinations(range(6), 3):
            group1 = [self.results[i] for i in indices]
            group2 = [self.results[i] for i in range(6) if i not in indices]
            sum1, sum2 = sum(group1), sum(group2)
            possible_sums.append((sum1, sum2))

        return list(set(possible_sums))  # 去重


@dataclass
class ContentTrigger:
    """地图内容触发记录"""
    column_number: int
    position: int
    content_type: str  # 'encounter', 'item', 'trap'
    content_id: int
    first_trigger_qq: Optional[str] = None
    first_trigger_time: Optional[datetime] = None
    trigger_count: int = 0


@dataclass
class GameRanking:
    """游戏通关排名"""
    rank: int
    qq_id: str
    nickname: str
    finished_at: datetime


# ==================== 成就定义 ====================

ACHIEVEMENTS = {
    # 首达成就
    "first_clear_1": {"name": "OAS游戏王", "desc": "第一个通关游戏", "reward_score": 100},
    "first_clear_2": {"name": "银闪闪", "desc": "第二个通关游戏", "reward_score": 80},
    "first_clear_3": {"name": "吉祥三宝", "desc": "第三个通关游戏", "reward_score": 50},
    "first_clear_4": {"name": "一步之遥", "desc": "第四个通关游戏", "reward_score": 0},
    "first_column": {"name": "鹤立oas群", "desc": "首次在某列登顶", "reward_score": 20},

    # 隐藏成就
    "territory": {"name": "领地意识", "desc": "在当前列回家三次", "reward": "修改液"},
    "bad_luck": {"name": "出门没看黄历", "desc": "遭遇三次首达陷阱", "reward": "风水罗盘"},
    "one_shot": {"name": "看我一命通关！", "desc": "一轮次内从起点到达列终点", "reward": "奇妙的变身器"},
    "collector": {"name": "收集癖", "desc": "解锁全部地图及可购买道具", "reward": "自定义头衔"},
    "all_ones": {"name": "一鸣惊人", "desc": "掷骰结果均为1", "reward": "一本很火的同人画集"},
    "all_sixes": {"name": "六六大顺", "desc": "掷骰结果均为6", "reward": "恶魔的祝福"},
    "self_damage": {"name": "自巡航", "desc": "使用道具时触发陷阱", "reward": "婴儿般的睡眠"},
    "lucky_save": {"name": "雪中送炭", "desc": "遭遇陷阱后触发奖励", "reward": "欧皇王冠"},
    "peaceful": {"name": "平平淡淡才是真", "desc": "三次遭遇选择无事发生", "reward": "老头款大背心"},
    "special_effect": {"name": "善恶有报", "desc": "三次遭遇触发特殊效果", "reward": "游戏机打折券"},
    "meta": {"name": "天机算不尽", "desc": "解锁3个隐藏成就", "reward": "套娃"},
    "host_doubt": {"name": "主持人的猜忌", "desc": "2次遭遇陷阱后触发奖励", "reward": "黄牌警告"},

    # 陷阱检定成就
    "math_king": {"name": "数学大王", "desc": "奇偶检定通过（奇数>3个）", "reward_score": 10},
    "math_zero": {"name": "数学0蛋", "desc": "奇偶检定失败（奇数≤3个）", "reward_score": 0},
    "crying_student": {"name": "哭哭做题家", "desc": "数学检定失败（组合<8种）", "reward_score": 0},
    "pass_through": {"name": "进去吧你！", "desc": "数学检定通过（组合≥8种）", "reward_score": 10},
}


# ==================== 每日限制配置 ====================

DAILY_LIMITS = {
    "摸摸喵": 5,
    "投喂喵": 5,
    "捏捏丑喵玩偶": 3,
}
