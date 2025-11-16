# -*- coding: utf-8 -*-
"""
游戏核心逻辑引擎
Can't Stop Game Engine
"""

import random
import sqlite3
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.dao import (
    PlayerDAO, PositionDAO, InventoryDAO, GameStateDAO,
    ShopDAO, AchievementDAO, DailyLimitDAO
)
from database.models import Player, Position, DAILY_LIMITS, ACHIEVEMENTS
from data.board_config import BOARD_DATA, COLUMN_HEIGHTS, VALID_COLUMNS
from engine.content_handler import ContentHandler


@dataclass
class GameResult:
    """游戏操作结果"""
    success: bool
    message: str
    data: Optional[Dict] = None


class GameEngine:
    """游戏引擎主类"""

    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn
        self.player_dao = PlayerDAO(db_conn)
        self.position_dao = PositionDAO(db_conn)
        self.inventory_dao = InventoryDAO(db_conn)
        self.state_dao = GameStateDAO(db_conn)
        self.shop_dao = ShopDAO(db_conn)
        self.achievement_dao = AchievementDAO(db_conn)
        self.daily_dao = DailyLimitDAO(db_conn)
        self.content_handler = ContentHandler(
            self.player_dao, self.inventory_dao, self.achievement_dao,
            self.position_dao, self.shop_dao, db_conn
        )

    # ==================== 玩家管理 ====================

    def register_or_get_player(self, qq_id: str, nickname: str) -> Player:
        """注册或获取玩家"""
        player = self.player_dao.get_player(qq_id)
        if not player:
            player = self.player_dao.create_player(qq_id, nickname)
        return player

    def choose_faction(self, qq_id: str, faction: str) -> GameResult:
        """选择阵营"""
        if faction not in ['收养人', 'Aeonreth']:
            return GameResult(False, "阵营选择错误，请选择：收养人 或 Aeonreth")

        player = self.player_dao.get_player(qq_id)
        if not player:
            return GameResult(False, "玩家不存在")

        if player.faction:
            return GameResult(False, f"您已经选择了阵营：{player.faction}，无法更改")

        self.player_dao.update_faction(qq_id, faction)
        return GameResult(True, f"您已选择阵营：{faction}，祝您玩得开心～")

    # ==================== 轮次管理 ====================

    def start_round(self, qq_id: str) -> GameResult:
        """开始新轮次"""
        state = self.state_dao.get_state(qq_id)

        if not state.can_start_new_round:
            return GameResult(False, "请先完成打卡，输入【打卡完毕】后才能开启新轮次")

        if state.current_round_active:
            return GameResult(False, "当前轮次还在进行中")

        state.current_round_active = True
        state.temp_markers_used = 0
        state.dice_history = []
        state.last_dice_result = None
        self.state_dao.update_state(state)

        return GameResult(True, "新轮次已开启")

    def roll_dice(self, qq_id: str, dice_count: int = 6) -> GameResult:
        """投掷骰子"""
        state = self.state_dao.get_state(qq_id)

        if not state.current_round_active:
            return GameResult(False, "请先输入【轮次开始】")

        # 检查积分
        player = self.player_dao.get_player(qq_id)
        cost = 10  # 默认每回合10积分
        if not self.player_dao.consume_score(qq_id, cost):
            return GameResult(False, f"积分不足，需要{cost}积分")

        # 投掷骰子
        results = [random.randint(1, 6) for _ in range(dice_count)]
        state.last_dice_result = results
        state.dice_history.append(results)
        self.state_dao.update_state(state)

        # 检查特殊成就
        self._check_dice_achievements(qq_id, results)

        return GameResult(True, f"投掷结果: {' '.join(map(str, results))}", {
            "results": results,
            "possible_sums": self._get_possible_sums(results)
        })

    def _get_possible_sums(self, dice_results: List[int]) -> List[Tuple[int, int]]:
        """计算所有可能的两组和"""
        from itertools import combinations

        if len(dice_results) != 6:
            return []

        possible_sums = set()
        for indices in combinations(range(6), 3):
            group1 = [dice_results[i] for i in indices]
            group2 = [dice_results[i] for i in range(6) if i not in indices]
            sum1, sum2 = sum(group1), sum(group2)
            possible_sums.add(tuple(sorted([sum1, sum2])))

        return list(possible_sums)

    def record_values(self, qq_id: str, values: List[int]) -> GameResult:
        """记录数值并移动标记"""
        # 验证数值
        for val in values:
            if val not in VALID_COLUMNS:
                return GameResult(False, f"数值 {val} 无效，有效范围是 3-18")

        # 检查是否在当前轮次
        state = self.state_dao.get_state(qq_id)
        if not state.current_round_active:
            return GameResult(False, "请先开始轮次")

        # 检查是否投过骰子
        if not state.last_dice_result:
            return GameResult(False, "请先投掷骰子")

        # 验证数值是否可以由骰子结果组成
        possible_sums = self._get_possible_sums(state.last_dice_result)
        values_tuple = tuple(sorted(values))
        if values_tuple not in possible_sums:
            return GameResult(False, f"数值 {values} 无法由骰子结果 {state.last_dice_result} 组成")

        # 获取当前位置
        current_positions = self.position_dao.get_positions(qq_id)
        temp_positions = [p for p in current_positions if p.marker_type == 'temp']
        permanent_positions = [p for p in current_positions if p.marker_type == 'permanent']

        # 检查临时标记数量限制
        temp_columns = set(p.column_number for p in temp_positions)
        new_columns = [v for v in values if v not in temp_columns]

        if len(temp_columns) + len(new_columns) > 3:
            return GameResult(False, "最多只能在3列上放置临时标记")

        # 检查是否在已登顶的列
        for val in values:
            if val in state.topped_columns:
                return GameResult(False, f"第{val}列您已经登顶，无法再次放置标记")

        # 移动标记
        messages = []
        for val in values:
            result = self._move_marker(qq_id, val, temp_positions, permanent_positions)
            messages.append(result.message)
            if not result.success:
                return result

        # 更新临时标记使用数量
        state.temp_markers_used = len(set(p.column_number for p in self.position_dao.get_positions(qq_id, 'temp')))
        self.state_dao.update_state(state)

        # 获取更新后的位置
        current_positions = self.position_dao.get_positions(qq_id)
        temp_positions = [p for p in current_positions if p.marker_type == 'temp']

        position_str = ', '.join([f"列{p.column_number}第{p.position}格" for p in temp_positions])
        remaining = 3 - len(set(p.column_number for p in temp_positions))

        return GameResult(True, f"玩家选择记录数值：{values}\n当前位置：{position_str}\n剩余可放置标记：{remaining}")

    def _move_marker(self, qq_id: str, column: int, temp_positions: List[Position],
                     permanent_positions: List[Position]) -> GameResult:
        """移动单个标记"""
        # 查找该列的临时位置
        temp_pos = next((p for p in temp_positions if p.column_number == column), None)
        permanent_pos = next((p for p in permanent_positions if p.column_number == column), None)

        if temp_pos:
            # 已有临时标记，向前移动1格
            new_position = temp_pos.position + 1
        elif permanent_pos:
            # 有永久标记，从永久标记位置+1开始
            new_position = permanent_pos.position + 1
        else:
            # 新列，从第1格开始
            new_position = 1

        # 检查是否超出列高度
        column_height = COLUMN_HEIGHTS[column]
        if new_position > column_height:
            return GameResult(False, f"列{column}最多只有{column_height}格，无法移动到第{new_position}格")

        # 更新位置
        self.position_dao.add_or_update_position(qq_id, column, new_position, 'temp')

        # 触发地图内容
        self._trigger_cell_content(qq_id, column, new_position)

        return GameResult(True, f"列{column}移动到第{new_position}格")

    def end_round_active(self, qq_id: str) -> GameResult:
        """主动结束轮次（替换永久棋子）"""
        state = self.state_dao.get_state(qq_id)

        if not state.current_round_active:
            return GameResult(False, "当前没有进行中的轮次")

        # 将临时标记转换为永久标记
        self.position_dao.convert_temp_to_permanent(qq_id)

        # 检查登顶
        positions = self.position_dao.get_positions(qq_id, 'permanent')
        for pos in positions:
            if pos.position >= COLUMN_HEIGHTS[pos.column_number]:
                # 登顶
                if pos.column_number not in state.topped_columns:
                    state.topped_columns.append(pos.column_number)

        # 检查是否获胜（3列登顶）
        if len(state.topped_columns) >= 3:
            return self._handle_game_win(qq_id)

        # 更新状态
        state.current_round_active = False
        state.can_start_new_round = False  # 需要打卡后才能开启新轮次
        self.state_dao.update_state(state)

        position_str = ', '.join([f"列{p.column_number}第{p.position}格" for p in positions])

        return GameResult(True, f"本轮次结束。\n当前永久棋子位置：{position_str}\n进度已锁定，请打卡后输入【打卡完毕】恢复开启新轮次功能")

    def end_round_passive(self, qq_id: str) -> GameResult:
        """被动结束轮次（进度回退）"""
        state = self.state_dao.get_state(qq_id)

        if not state.current_round_active:
            return GameResult(False, "当前没有进行中的轮次")

        # 清除所有临时标记
        self.position_dao.clear_temp_positions(qq_id)

        # 更新状态
        state.current_round_active = False
        state.temp_markers_used = 0
        self.state_dao.update_state(state)

        positions = self.position_dao.get_positions(qq_id, 'permanent')
        position_str = ', '.join([f"列{p.column_number}第{p.position}格" for p in positions]) if positions else "无"

        return GameResult(True, f"本轮次结束。\n当前永久棋子位置：{position_str}")

    def finish_checkin(self, qq_id: str) -> GameResult:
        """完成打卡"""
        state = self.state_dao.get_state(qq_id)
        state.can_start_new_round = True
        self.state_dao.update_state(state)

        return GameResult(True, "您可以开始新的轮次了～")

    # ==================== 查询功能 ====================

    def get_progress(self, qq_id: str) -> GameResult:
        """查看当前进度"""
        positions = self.position_dao.get_positions(qq_id)
        temp_positions = [p for p in positions if p.marker_type == 'temp']
        permanent_positions = [p for p in positions if p.marker_type == 'permanent']

        state = self.state_dao.get_state(qq_id)

        temp_str = ', '.join([f"列{p.column_number}第{p.position}格" for p in temp_positions]) if temp_positions else "无"
        perm_str = ', '.join([f"列{p.column_number}第{p.position}格" for p in permanent_positions]) if permanent_positions else "无"
        remaining = 3 - len(set(p.column_number for p in temp_positions))

        message = f"当前临时位置：{temp_str}\n剩余可放置标记：{remaining}\n" \
                  f"当前永久棋子位置：{perm_str}\n已登顶棋子数：{len(state.topped_columns)}"

        return GameResult(True, message, {
            "temp_positions": temp_positions,
            "permanent_positions": permanent_positions,
            "topped_count": len(state.topped_columns)
        })

    def get_inventory(self, qq_id: str) -> GameResult:
        """查看背包"""
        player = self.player_dao.get_player(qq_id)
        inventory = self.inventory_dao.get_inventory(qq_id)

        items = [item for item in inventory if item.item_type == 'item']
        hidden_items = [item for item in inventory if item.item_type in ['hidden_item', 'special']]

        items_str = ', '.join([f"{item.item_name} x{item.quantity}" for item in items]) if items else "无"
        hidden_str = ', '.join([f"{item.item_name} x{item.quantity}" for item in hidden_items]) if hidden_items else "无"

        message = f"当前积分：{player.current_score}\n历史获得积分：{player.total_score}\n" \
                  f"当前道具：{items_str}\n当前隐藏道具/物品：{hidden_str}"

        return GameResult(True, message, {
            "score": player.current_score,
            "total_score": player.total_score,
            "items": items,
            "hidden_items": hidden_items
        })

    def get_achievements(self, qq_id: str) -> GameResult:
        """查看成就"""
        achievements = self.achievement_dao.get_achievements(qq_id)

        if not achievements:
            return GameResult(True, "您还没有获得任何成就")

        message = "您的成就列表：\n" + '\n'.join([
            f"- {ach.achievement_name} ({ach.achievement_type})"
            for ach in achievements
        ])

        return GameResult(True, message, {"achievements": achievements})

    # ==================== 奖励系统 ====================

    def claim_reward(self, qq_id: str, reward_type: str, count: int = 1, multiplier: int = 1) -> GameResult:
        """领取打卡奖励"""
        reward_map = {
            "草图": 20,
            "精致小图": 80,
            "精草大图": 100,
            "精致大图": 150,
            "超常发挥": 30,
        }

        if reward_type not in reward_map:
            return GameResult(False, f"未知的奖励类型：{reward_type}")

        score = reward_map[reward_type] * count * multiplier
        self.player_dao.add_score(qq_id, score)

        return GameResult(True, f"您的积分+{score}")

    def claim_column_top(self, qq_id: str, column: int) -> GameResult:
        """领取登顶奖励"""
        if column not in VALID_COLUMNS:
            return GameResult(False, f"无效的列号：{column}")

        # 检查是否真的登顶了
        positions = self.position_dao.get_positions(qq_id, 'permanent')
        column_pos = next((p for p in positions if p.column_number == column), None)

        if not column_pos or column_pos.position < COLUMN_HEIGHTS[column]:
            return GameResult(False, f"您还没有在第{column}列登顶")

        # 基础登顶奖励
        base_reward = 10
        self.player_dao.add_score(qq_id, base_reward)

        message = f"恭喜您在【{column}】列登顶～\n已清空该列场上所有临时标记。\n✦登顶奖励\n恭喜您获得 {base_reward} 积分"

        # 检查是否是首达
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM first_achievements WHERE column_number = ?', (column,))
        first_record = cursor.fetchone()

        if not first_record:
            # 首达奖励
            cursor.execute('INSERT INTO first_achievements (column_number, first_qq_id) VALUES (?, ?)', (column, qq_id))
            self.conn.commit()

            first_reward = 20
            self.player_dao.add_score(qq_id, first_reward)
            self.achievement_dao.add_achievement(qq_id, column, f"第{column}列首达", "first_clear")

            message += f"\n✦首达奖励\n恭喜您在该列首次登顶，获得 {first_reward} 积分"

        return GameResult(True, message)

    # ==================== 商店系统 ====================

    def get_shop(self, qq_id: str) -> GameResult:
        """查看道具商店"""
        player = self.player_dao.get_player(qq_id)
        items = self.shop_dao.get_all_items(unlocked_only=True)

        available_items = []
        for item in items:
            can_buy, reason = item.can_buy(player)
            available_items.append({
                "item": item,
                "can_buy": can_buy,
                "reason": reason
            })

        return GameResult(True, "道具商店", {"items": available_items, "player_score": player.current_score})

    def buy_item(self, qq_id: str, item_id: int) -> GameResult:
        """购买道具"""
        player = self.player_dao.get_player(qq_id)
        item = self.shop_dao.get_item(item_id)

        if not item:
            return GameResult(False, "道具不存在")

        can_buy, reason = item.can_buy(player)
        if not can_buy:
            return GameResult(False, reason)

        # 扣除积分
        if not self.player_dao.consume_score(qq_id, item.price):
            return GameResult(False, "积分不足")

        # 添加道具
        self.inventory_dao.add_item(qq_id, item.item_id, item.item_name, item.item_type)

        # 更新商店库存
        self.shop_dao.purchase_item(item_id)

        return GameResult(True, f"成功购买 {item.item_name}，消耗 {item.price} 积分")

    # ==================== 特殊功能 ====================

    def pet_cat(self, qq_id: str) -> GameResult:
        """摸摸喵"""
        can_do, remaining = self.daily_dao.can_do(qq_id, "摸摸喵", DAILY_LIMITS["摸摸喵"])
        if not can_do:
            return GameResult(False, f"今天已经摸够了，明天再来吧~ (今日剩余次数: {remaining})")

        self.daily_dao.increment(qq_id, "摸摸喵")

        responses = [
            "喵向你露出肚皮",
            "喵抖抖耳朵",
            "喵呼噜呼噜",
            "喵不给你摸并跑开了",
            "喵突然发出奇怪的声响，不一会儿，你的积分显示+1"
        ]

        result = random.choice(responses)
        if "+1" in result:
            self.player_dao.add_score(qq_id, 1)

        return GameResult(True, f"{result}\n(今日剩余次数: {remaining - 1})")

    def feed_cat(self, qq_id: str) -> GameResult:
        """投喂喵"""
        can_do, remaining = self.daily_dao.can_do(qq_id, "投喂喵", DAILY_LIMITS["投喂喵"])
        if not can_do:
            return GameResult(False, f"今天已经投喂够了，明天再来吧~ (今日剩余次数: {remaining})")

        self.daily_dao.increment(qq_id, "投喂喵")

        responses = [
            "喵大快朵颐，吃得很开心",
            "喵上前舔了舔",
            "喵露出嫌弃的表情并跑开了",
            "喵突然发出奇怪的声响，不一会儿，你的积分显示+1"
        ]

        result = random.choice(responses)
        if "+1" in result:
            self.player_dao.add_score(qq_id, 1)

        return GameResult(True, f"{result}\n(今日剩余次数: {remaining - 1})")

    def squeeze_doll(self, qq_id: str) -> GameResult:
        """捏捏丑喵玩偶"""
        # 检查是否拥有玩偶
        if not self.inventory_dao.has_item(qq_id, 999, 'special'):
            return GameResult(False, "您还没有丑喵玩偶，请先购买")

        can_do, remaining = self.daily_dao.can_do(qq_id, "捏捏丑喵玩偶", DAILY_LIMITS["捏捏丑喵玩偶"])
        if not can_do:
            return GameResult(False, f"今天已经捏够了，明天再来吧~ (今日剩余次数: {remaining})")

        self.daily_dao.increment(qq_id, "捏捏丑喵玩偶")

        # 70%概率失败，30%概率成功
        if random.random() < 0.7:
            return GameResult(True, f"玩偶发出了吱吱的响声，并从你手中滑了出去\n(今日剩余次数: {remaining - 1})")
        else:
            score = sum([random.randint(1, 6) for _ in range(3)])
            self.player_dao.add_score(qq_id, score)
            return GameResult(True, f"玩偶发出了呼噜呼噜的响声，似乎很高兴，你获得{score}积分\n(今日剩余次数: {remaining - 1})")

    # ==================== 道具使用 ====================

    def use_item(self, qq_id: str, item_id: int, item_name: str, **kwargs) -> GameResult:
        """使用道具"""
        try:
            result = self.content_handler.use_item(qq_id, item_id, item_name, **kwargs)
            if result.success:
                return GameResult(True, result.message, result.effects)
            else:
                return GameResult(False, result.message)
        except Exception as e:
            return GameResult(False, f"使用道具时出错: {e}")

    # ==================== 内部辅助方法 ====================

    def _trigger_cell_content(self, qq_id: str, column: int, position: int):
        """触发地图格子内容"""
        # 从棋盘配置获取该格子的内容
        if column not in BOARD_DATA:
            return

        cells = BOARD_DATA[column]
        if position < 1 or position > len(cells):
            return

        cell_type, content_id, content_name = cells[position - 1]

        # 触发内容（遭遇、道具、陷阱）
        try:
            result = self.content_handler.trigger_content(
                qq_id, column, position, cell_type, content_id, content_name
            )
            # 内容触发结果会返回给玩家，由命令处理器处理
            # 这里仅记录日志
            print(f"[触发内容] {qq_id} 在 ({column},{position}) 触发 {cell_type}:{content_name}")
        except Exception as e:
            print(f"[错误] 触发内容时出错: {e}")

    def _check_dice_achievements(self, qq_id: str, results: List[int]):
        """检查骰子相关成就"""
        # 检查全1
        if all(r == 1 for r in results):
            if not self.achievement_dao.has_achievement(qq_id, 5, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 5, "一鸣惊人", "hidden")

        # 检查全6
        if all(r == 6 for r in results):
            if not self.achievement_dao.has_achievement(qq_id, 6, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 6, "六六大顺", "hidden")

    def _handle_game_win(self, qq_id: str) -> GameResult:
        """处理游戏胜利"""
        # 检查排名
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM game_rankings')
        row = cursor.fetchone()
        rank = row['count'] + 1

        if rank <= 4:
            # 记录排名
            cursor.execute('INSERT INTO game_rankings (rank, qq_id) VALUES (?, ?)', (rank, qq_id))
            self.conn.commit()

            # 发放排名奖励
            rank_rewards = {1: 100, 2: 80, 3: 50, 4: 0}
            reward = rank_rewards.get(rank, 0)
            if reward > 0:
                self.player_dao.add_score(qq_id, reward)

            rank_names = {1: "OAS游戏王", 2: "银闪闪", 3: "吉祥三宝", 4: "一步之遥"}
            self.achievement_dao.add_achievement(qq_id, rank, rank_names[rank], "first_clear")

            return GameResult(True, f"🎉🎉🎉 恭喜您第{rank}个通关游戏！🎉🎉🎉\n获得成就：{rank_names[rank]}\n奖励积分：{reward}")

        return GameResult(True, "🎉 恭喜您通关游戏！")
