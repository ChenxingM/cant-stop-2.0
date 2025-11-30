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

        # 允许更改阵营
        if player.faction and player.faction != faction:
            self.player_dao.update_faction(qq_id, faction)
            return GameResult(True, f"您已将阵营更改为：{faction}")
        elif player.faction == faction:
            return GameResult(False, f"您已经是{faction}阵营了")

        self.player_dao.update_faction(qq_id, faction)
        return GameResult(True, f"您已选择阵营：{faction}，祝您玩得开心～")

    # ==================== 轮次管理 ====================

    def start_round(self, qq_id: str) -> GameResult:
        """开始新轮次"""
        # 检查是否已选择阵营
        player = self.player_dao.get_player(qq_id)
        if not player.faction:
            return GameResult(False, "请选择阵营~\n使用指令：\n• 选择阵营：收养人\n• 选择阵营：Aeonreth")

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
        # 检查是否已选择阵营
        player = self.player_dao.get_player(qq_id)
        if not player.faction:
            return GameResult(False, "⚠️ 请先选择阵营！\n使用指令：\n• 选择阵营：收养人\n• 选择阵营：Aeonreth")

        state = self.state_dao.get_state(qq_id)

        # 检查是否有待完成的遭遇选择
        if state.pending_encounters:
            return GameResult(False, "⚠️ 您还有待完成的遭遇选择，请先完成选择！\n使用指令：选择：你的选择")

        if not state.current_round_active:
            return GameResult(False, "请先输入【轮次开始】")

        # 检查玩家是否被暂停
        if state.skipped_rounds > 0:
            # 暂停状态：扣除积分但不能投掷骰子
            player = self.player_dao.get_player(qq_id)
            cost = 10  # 默认每回合10积分
            if not self.player_dao.consume_score(qq_id, cost):
                return GameResult(False, f"积分不足，需要{cost}积分")

            # 减少暂停回合数
            state.skipped_rounds -= 1
            self.state_dao.update_state(state)

            remaining_msg = f"，还需暂停{state.skipped_rounds}回合" if state.skipped_rounds > 0 else ""
            return GameResult(False, f"⏸️ 您当前处于暂停状态，本回合无法投掷骰子\n已消耗{cost}积分{remaining_msg}")

        # 检查积分
        player = self.player_dao.get_player(qq_id)
        cost = 10  # 默认每回合10积分
        if not self.player_dao.consume_score(qq_id, cost):
            return GameResult(False, f"积分不足，需要{cost}积分")

        # 确定骰子数量（可能被陷阱效果修改）
        if state.next_dice_count:
            dice_count = state.next_dice_count
            dice_groups = state.next_dice_groups
            # 清除效果
            state.next_dice_count = None
            state.next_dice_groups = None
            self.state_dao.update_state(state)

        # 检查是否有固定骰子效果（小小火球术）
        if state.next_dice_fixed:
            results = state.next_dice_fixed
            # 清除效果
            state.next_dice_fixed = None
            state.last_dice_result = results
            state.dice_history.append(results)
            self.state_dao.update_state(state)

            # 计算可能的组合
            possible_sums = self._get_possible_sums(results)
            combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])

            message = f"🎲固定骰子结果: {' '.join(map(str, results))}\n可能的组合: {combinations_str}"
            return GameResult(True, message, {
                "results": results,
                "possible_sums": possible_sums
            })

        # 检查是否有额外d6检查效果
        if state.extra_d6_check_six:
            # 投掷7个骰子（6个正常+1个额外）
            results = [random.randint(1, 6) for _ in range(dice_count)]
            extra_die = random.randint(1, 6)

            # 清除效果标记
            state.extra_d6_check_six = False

            if extra_die == 6:
                # 额外骰子是6，本回合作废
                state.dice_history.append(results)
                state.last_dice_result = None  # 不保存结果
                self.state_dao.update_state(state)

                return GameResult(False,
                               f"🎲投掷结果: {' '.join(map(str, results))}\n"
                               f"💥 额外d6结果: {extra_die}\n\n"
                               f"你用力过猛，将所有骰子掷碎了！本回合作废。")
            else:
                # 额外骰子不是6，正常继续
                state.last_dice_result = results
                state.dice_history.append(results)
                self.state_dao.update_state(state)

                # 检查特殊成就
                self._check_dice_achievements(qq_id, results)

                # 计算可能的组合
                possible_sums = self._get_possible_sums(results)
                combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])

                message = (f"🎲投掷结果: {' '.join(map(str, results))}\n"
                          f"✨ 额外d6结果: {extra_die}（未触发，继续游戏）\n"
                          f"可能的组合: {combinations_str}")

                return GameResult(True, message, {
                    "results": results,
                    "possible_sums": possible_sums
                })
        else:
            # 正常投掷骰子
            results = [random.randint(1, 6) for _ in range(dice_count)]
            state.last_dice_result = results
            state.dice_history.append(results)

            # 检查奇偶检定（陷阱6: 奇变偶不变）
            if state.odd_even_check_active:
                state.odd_even_check_active = False
                odd_count = sum(1 for r in results if r % 2 == 1)
                if odd_count > 3:
                    # 通过检定，获得额外d6
                    extra_die = random.randint(1, 6)
                    self.state_dao.update_state(state)
                    message = (f"🎲投掷结果: {' '.join(map(str, results))}\n"
                              f"✨ 奇偶检定：奇数{odd_count}个 > 3，通过！\n"
                              f"额外d6: {extra_die}，可以随意加到任意组合中")
                    # 这里暂时只返回提示，实际加值需要在记录数值时处理
                    return GameResult(True, message, {
                        "results": results,
                        "extra_die": extra_die
                    })
                else:
                    # 未通过检定，本回合作废
                    state.last_dice_result = None
                    self.state_dao.update_state(state)
                    return GameResult(False,
                                   f"🎲投掷结果: {' '.join(map(str, results))}\n"
                                   f"❌ 奇偶检定：奇数{odd_count}个 ≤ 3，未通过！本回合作废")

            # 检查数学检定（陷阱7: 雷电法王）
            if state.math_check_active:
                state.math_check_active = False
                possible_sums = self._get_possible_sums(results)
                unique_values = set()
                for sum1, sum2 in possible_sums:
                    unique_values.add(sum1)
                    unique_values.add(sum2)
                unique_count = len(unique_values)
                self.state_dao.update_state(state)

                if unique_count >= 8:
                    # 通过检定
                    combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])
                    message = (f"🎲投掷结果: {' '.join(map(str, results))}\n"
                              f"✨ 数学检定：可得到{unique_count}种不同数字 ≥ 8，通过！\n"
                              f"可能的组合: {combinations_str}")
                    return GameResult(True, message, {
                        "results": results,
                        "possible_sums": possible_sums
                    })
                else:
                    # 未通过检定，本回合作废
                    state.last_dice_result = None
                    self.state_dao.update_state(state)
                    return GameResult(False,
                                   f"🎲投掷结果: {' '.join(map(str, results))}\n"
                                   f"❌ 数学检定：可得到{unique_count}种不同数字 < 8，未通过！本回合作废")

            self.state_dao.update_state(state)

            # 检查特殊成就
            self._check_dice_achievements(qq_id, results)

            # 计算可能的组合
            possible_sums = self._get_possible_sums(results)

            # 格式化可能的组合提示
            combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])

            message = f"🎲投掷结果: {' '.join(map(str, results))}\n可能的组合: {combinations_str}"

            return GameResult(True, message, {
                "results": results,
                "possible_sums": possible_sums
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
        # 检查是否已选择阵营
        player = self.player_dao.get_player(qq_id)
        if not player.faction:
            return GameResult(False, "⚠️ 请先选择阵营！\n使用指令：\n• 选择阵营：收养人\n• 选择阵营：Aeonreth")

        # 验证数值
        for val in values:
            if val not in VALID_COLUMNS:
                return GameResult(False, f"数值 {val} 无效，有效范围是 3-18")

        # 检查是否在当前轮次
        state = self.state_dao.get_state(qq_id)

        # 检查是否有待完成的遭遇选择
        if state.pending_encounters:
            return GameResult(False, "⚠️ 您还有待完成的遭遇选择，请先完成选择！\n使用指令：选择：你的选择")

        if not state.current_round_active:
            return GameResult(False, "请先开始轮次")

        # 检查是否投过骰子
        if not state.last_dice_result:
            return GameResult(False, "⚠️ 请先投掷骰子！\n使用指令：.r6d6")

        # 验证数值是否可以由骰子结果组成
        possible_sums = self._get_possible_sums(state.last_dice_result)

        # 如果用户输入1个数值，检查是否存在包含该数值的组合
        if len(values) == 1:
            target_value = values[0]
            valid = any(target_value in combo for combo in possible_sums)
            if not valid:
                return GameResult(False, f"数值 {values[0]} 无法由骰子结果 {state.last_dice_result} 组成")
        # 如果用户输入2个数值，检查这个组合是否存在
        elif len(values) == 2:
            values_tuple = tuple(sorted(values))
            if values_tuple not in possible_sums:
                return GameResult(False, f"数值组合 {values} 无法由骰子结果 {state.last_dice_result} 组成")
        else:
            return GameResult(False, "每次只能记录1个或2个数值")

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

        # 找出每个数值最后一次出现的索引（用于只在最后一次移动时触发遭遇）
        last_occurrence = {}
        for idx, val in enumerate(values):
            last_occurrence[val] = idx

        # 移动标记
        messages = []
        content_messages = []

        for idx, val in enumerate(values):
            # 每次移动前刷新位置列表，确保处理重复值时能正确移动
            current_positions = self.position_dao.get_positions(qq_id)
            temp_positions = [p for p in current_positions if p.marker_type == 'temp']
            permanent_positions = [p for p in current_positions if p.marker_type == 'permanent']

            # 只在该数值最后一次出现时触发遭遇
            should_trigger = (idx == last_occurrence[val])

            result, content_msg = self._move_marker(qq_id, val, temp_positions, permanent_positions,
                                                   trigger_content=should_trigger)
            messages.append(result.message)
            if content_msg:
                content_messages.append(content_msg)
            if not result.success:
                return result

        # 重新获取状态，因为在 _trigger_cell_content 中可能已经更新了 pending_encounter
        state = self.state_dao.get_state(qq_id)

        # 更新临时标记使用数量
        state.temp_markers_used = len(set(p.column_number for p in self.position_dao.get_positions(qq_id, 'temp')))

        # 处理强制回合效果（犹豫就会败北）
        if state.forced_remaining_rounds > 0:
            state.forced_remaining_rounds -= 1

        # 清除骰子结果，要求玩家在下次记录数值前必须重新投掷骰子
        state.last_dice_result = None
        self.state_dao.update_state(state)

        # 获取更新后的位置
        current_positions = self.position_dao.get_positions(qq_id)
        temp_positions = [p for p in current_positions if p.marker_type == 'temp']

        position_str = ', '.join([f"列{p.column_number}第{p.position}格" for p in temp_positions])
        remaining = 3 - len(set(p.column_number for p in temp_positions))

        # 组合消息：位置信息 + 内容触发
        base_msg = f"玩家选择记录数值：{values}\n当前位置：{position_str}\n剩余可放置标记：{remaining}"

        if content_messages:
            full_msg = base_msg + "\n\n" + "\n\n".join(content_messages)
        else:
            full_msg = base_msg + "\n\n没有触发道具和遭遇"

        return GameResult(True, full_msg)

    def _move_marker(self, qq_id: str, column: int, temp_positions: List[Position],
                     permanent_positions: List[Position], trigger_content: bool = True) -> tuple[GameResult, Optional[str]]:
        """移动单个标记，返回(结果, 内容触发消息)

        Args:
            qq_id: 玩家QQ号
            column: 列号
            temp_positions: 临时位置列表
            permanent_positions: 永久位置列表
            trigger_content: 是否触发地图内容（默认True）
        """
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
            return GameResult(False, f"列{column}最多只有{column_height}格，无法移动到第{new_position}格"), None

        # 更新位置
        self.position_dao.add_or_update_position(qq_id, column, new_position, 'temp')

        # 只在最终位置触发地图内容
        content_msg = None
        if trigger_content:
            content_msg = self._trigger_cell_content(qq_id, column, new_position)

        return GameResult(True, f"列{column}移动到第{new_position}格"), content_msg

    def end_round_active(self, qq_id: str) -> GameResult:
        """主动结束轮次（替换永久棋子）"""
        state = self.state_dao.get_state(qq_id)

        # 检查是否有待完成的遭遇选择
        if state.pending_encounters:
            return GameResult(False, "⚠️ 您还有待完成的遭遇选择，请先完成选择！\n使用指令：选择：你的选择")

        if not state.current_round_active:
            return GameResult(False, "当前没有进行中的轮次")

        # 检查是否有强制轮次效果（犹豫就会败北）
        if state.forced_remaining_rounds > 0:
            return GameResult(False, f"⚠️ 您还需要再进行 {state.forced_remaining_rounds} 回合才能结束轮次！\n（陷阱效果：犹豫就会败北）")

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

        # 检查是否有待完成的遭遇选择
        if state.pending_encounters:
            return GameResult(False, "⚠️ 您还有待完成的遭遇选择，请先完成选择！\n使用指令：选择：你的选择")

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

        if not items:
            return GameResult(True, "道具商店暂无已解锁的道具")

        # 格式化商店列表
        message_lines = [
            "🛒 道具商店",
            f"当前积分：{player.current_score}",
            "",
            "已解锁道具："
        ]

        available_items = []
        for idx, item in enumerate(items, 1):
            can_buy, reason = item.can_buy(player)
            available_items.append({
                "item": item,
                "can_buy": can_buy,
                "reason": reason
            })

            # 构造道具信息
            faction_tag = ""
            if item.faction_limit and item.faction_limit != '通用':
                faction_tag = f"[{item.faction_limit}专用]"

            status = "✓" if can_buy else "✗"
            price_str = f"{item.price}积分" if item.price > 0 else "不可购买"

            item_line = f"{idx}. {status} {item.item_name} {faction_tag} - {price_str}"

            # 如果有全局限制，显示库存
            if item.global_limit > 0:
                remaining = item.global_limit - item.global_sold
                item_line += f" [剩余{remaining}件]"

            # 如果不可购买，显示原因
            if not can_buy and reason != "可以购买":
                item_line += f"\n   ({reason})"

            message_lines.append(item_line)

        message_lines.append("")
        message_lines.append("💡 使用「购买道具名称」来购买道具")

        message = '\n'.join(message_lines)

        return GameResult(True, message, {"items": available_items, "player_score": player.current_score})

    def buy_item(self, qq_id: str, item_name: str) -> GameResult:
        """购买道具

        Args:
            qq_id: 玩家QQ号
            item_name: 道具名称
        """
        player = self.player_dao.get_player(qq_id)
        item = self.shop_dao.get_item_by_name(item_name)

        if not item:
            return GameResult(False, f"道具「{item_name}」不存在或尚未解锁")

        can_buy, reason = item.can_buy(player)
        if not can_buy:
            return GameResult(False, reason)

        # 扣除积分
        if not self.player_dao.consume_score(qq_id, item.price):
            return GameResult(False, "积分不足")

        # 添加道具
        self.inventory_dao.add_item(qq_id, item.item_id, item.item_name, item.item_type)

        # 更新商店库存
        self.shop_dao.purchase_item(item.item_id)

        return GameResult(True, f"✅ 成功购买 {item.item_name}，消耗 {item.price} 积分")

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

    # ==================== 遭遇选择 ====================

    def make_choice(self, qq_id: str, choice: str) -> GameResult:
        """对等待选择的遭遇/道具进行选择

        Args:
            qq_id: 玩家QQ号
            choice: 玩家的选择
        """
        state = self.state_dao.get_state(qq_id)

        if not state.pending_encounters:
            return GameResult(False, "当前没有等待选择的遭遇或道具")

        # 获取队列中第一个等待选择的遭遇信息
        encounter_info = state.pending_encounters[0]
        column = encounter_info['column']
        position = encounter_info['position']
        encounter_id = encounter_info['encounter_id']
        encounter_name = encounter_info['encounter_name']
        available_choices = encounter_info.get('choices', [])

        # 验证选择是否有效
        if available_choices and choice not in available_choices:
            choices_str = '\n'.join([f"• {c}" for c in available_choices])
            return GameResult(False,
                            f"❌ 无效的选择！请从以下选项中选择：\n{choices_str}")

        # 调用content_handler处理选择
        try:
            result = self.content_handler._handle_encounter(
                qq_id, encounter_id, encounter_name, is_first=True, choice=choice
            )

            # 从队列中移除已处理的遭遇
            state.pending_encounters.pop(0)

            # 应用效果
            if result.effects:
                self._apply_content_effects(qq_id, result.effects)

            # 检查是否还有待处理的遭遇
            if state.pending_encounters:
                next_encounter = state.pending_encounters[0]
                next_choices = next_encounter.get('choices', [])
                if next_choices:
                    choices_str = '\n'.join([f"• {c}" for c in next_choices])
                    additional_msg = (f"\n\n⚠️ 您还有待处理的遭遇：{next_encounter['encounter_name']}\n"
                                    f"请选择：\n{choices_str}\n\n"
                                    f"💡 使用「选择：你的选择」来进行选择")
                    self.state_dao.update_state(state)
                    return GameResult(True, result.message + additional_msg)

            self.state_dao.update_state(state)
            return GameResult(True, result.message)

        except Exception as e:
            return GameResult(False, f"处理选择时出错: {e}")

    # ==================== 道具使用 ====================

    def use_item(self, qq_id: str, item_name: str, **kwargs) -> GameResult:
        """使用道具

        Args:
            qq_id: 玩家QQ号
            item_name: 道具名称
            **kwargs: 额外参数
        """
        # 从玩家背包中查找该道具
        inventory = self.inventory_dao.get_inventory(qq_id)
        item = None
        for inv_item in inventory:
            if inv_item.item_name == item_name:
                item = inv_item
                break

        if not item:
            return GameResult(False, f"❌ 您没有道具「{item_name}」\n请使用「查看背包」查看您拥有的道具")

        try:
            result = self.content_handler.use_item(qq_id, item.item_id, item.item_name, **kwargs)
            if result.success:
                return GameResult(True, result.message, result.effects)
            else:
                return GameResult(False, result.message)
        except Exception as e:
            return GameResult(False, f"使用道具时出错: {e}")

    # ==================== 内部辅助方法 ====================

    def _trigger_cell_content(self, qq_id: str, column: int, position: int) -> Optional[str]:
        """触发地图格子内容，返回触发消息"""
        # 从棋盘配置获取该格子的内容
        if column not in BOARD_DATA:
            return None

        cells = BOARD_DATA[column]
        if position < 1 or position > len(cells):
            return None

        cell_type, content_id, content_name = cells[position - 1]

        # 触发内容（遭遇、道具、陷阱）
        try:
            result = self.content_handler.trigger_content(
                qq_id, column, position, cell_type, content_id, content_name
            )
            print(f"[触发内容] {qq_id} 在 ({column},{position}) 触发 {cell_type}:{content_name}")

            # 如果遭遇需要玩家选择，保存遭遇信息
            if result and result.requires_input and cell_type == "E":
                state = self.state_dao.get_state(qq_id)
                # 添加到待处理队列（而不是覆盖）
                encounter_info = {
                    'column': column,
                    'position': position,
                    'encounter_id': content_id,
                    'encounter_name': content_name,
                    'choices': result.choices
                }
                state.pending_encounters.append(encounter_info)
                self.state_dao.update_state(state)

                # 添加选择提示到消息
                if result.choices:
                    choices_str = '\n'.join([f"• {choice}" for choice in result.choices])
                    return f"{result.message}\n\n请选择：\n{choices_str}\n\n💡 使用「选择：你的选择」来进行选择"
                return result.message

            # 处理返回的effects
            if result and result.effects:
                self._apply_content_effects(qq_id, result.effects)

            return result.message if result else None
        except Exception as e:
            print(f"[错误] 触发内容时出错: {e}")
            return f"触发内容时出错: {e}"

    def _apply_content_effects(self, qq_id: str, effects: dict):
        """应用遭遇/陷阱/道具的效果

        Args:
            qq_id: 玩家QQ号
            effects: 效果字典，可能包含各种效果
        """
        state = self.state_dao.get_state(qq_id)

        # ==================== 回合控制效果 ====================

        # 处理暂停回合效果
        if 'skip_rounds' in effects:
            skip_count = effects['skip_rounds']
            state.skipped_rounds += skip_count
            print(f"[效果应用] {qq_id} 被暂停 {skip_count} 回合，当前总暂停回合数: {state.skipped_rounds}")

        # 处理强制结束轮次效果
        if effects.get('force_end_round'):
            state.current_round_active = False
            # 清空临时标记
            self.position_dao.clear_temp_positions(qq_id)
            state.temp_markers_used = 0
            print(f"[效果应用] {qq_id} 被强制结束轮次")

        # 处理强制轮次效果（犹豫就会败北）
        if 'force_rounds' in effects:
            state.forced_remaining_rounds = effects['force_rounds']
            print(f"[效果应用] {qq_id} 必须再进行 {state.forced_remaining_rounds} 回合才能结束轮次")

        # ==================== 位置相关效果 ====================

        # 处理清空当前列进度效果
        if effects.get('clear_current_column') and 'column' in effects:
            column = effects['column']
            self.position_dao.clear_temp_position_by_column(qq_id, column)
            print(f"[效果应用] {qq_id} 清空列{column}的临时进度")

        # 处理回退效果（白色天○钩）
        if 'retreat' in effects and 'column' in effects:
            retreat_count = effects['retreat']
            column = effects['column']
            self._retreat_position(qq_id, column, retreat_count)
            print(f"[效果应用] {qq_id} 在列{column}回退 {retreat_count} 格")

        # 处理所有列回退效果（七色章鱼）
        if 'retreat_all' in effects:
            retreat_count = effects['retreat_all']
            positions = self.position_dao.get_positions(qq_id, 'temp')
            for pos in positions:
                self._retreat_position(qq_id, pos.column_number, retreat_count)
            print(f"[效果应用] {qq_id} 所有临时标记回退 {retreat_count} 格")

        # 处理随机回退效果（没有空军）
        if 'random_retreat' in effects:
            retreat_count = effects['random_retreat']
            positions = self.position_dao.get_positions(qq_id, 'temp')
            if positions:
                import random
                random_pos = random.choice(positions)
                self._retreat_position(qq_id, random_pos.column_number, retreat_count)
                print(f"[效果应用] {qq_id} 随机回退列{random_pos.column_number} {retreat_count} 格")

        # 处理传送效果（传送门）
        if 'teleport_to' in effects and 'column' in effects:
            target_column = effects['teleport_to']
            source_column = effects['column']
            # 清除原列的临时标记
            self.position_dao.clear_temp_position_by_column(qq_id, source_column)
            # 在目标列设置标记
            permanent_pos = next((p for p in self.position_dao.get_positions(qq_id, 'permanent')
                                if p.column_number == target_column), None)
            if permanent_pos:
                # 有永久标记，放在永久标记+1位置
                self.position_dao.add_or_update_position(qq_id, target_column, permanent_pos.position + 1, 'temp')
                print(f"[效果应用] {qq_id} 传送到列{target_column}，位置{permanent_pos.position + 1}")
            else:
                # 检查该列是否已有临时标记
                temp_positions = self.position_dao.get_positions(qq_id, 'temp')
                has_temp = any(p.column_number == target_column for p in temp_positions)
                if not has_temp:
                    # 没有标记，放在第1格
                    self.position_dao.add_or_update_position(qq_id, target_column, 1, 'temp')
                    print(f"[效果应用] {qq_id} 传送到列{target_column}，位置1")
                else:
                    print(f"[效果应用] {qq_id} 传送失败，目标列{target_column}已有临时标记")

        # ==================== 骰子相关效果 ====================

        # 处理额外d6检查效果
        if effects.get('extra_d6_check_six'):
            state.extra_d6_check_six = True
            print(f"[效果应用] {qq_id} 下次投骰将额外投一个d6，如果是6则本回合作废")

        # 处理固定骰子效果（小小火球术）
        if 'next_dice_fixed' in effects:
            state.next_dice_fixed = effects['next_dice_fixed']
            print(f"[效果应用] {qq_id} 下回合骰子结果固定为 {state.next_dice_fixed}")

        # 处理骰子数量改变效果（LUCKY DAY）
        if 'next_dice_count' in effects:
            state.next_dice_count = effects['next_dice_count']
            if 'next_dice_groups' in effects:
                state.next_dice_groups = effects['next_dice_groups']
            print(f"[效果应用] {qq_id} 下回合只投掷 {state.next_dice_count} 个骰子")

        # 处理奇偶检定效果
        if effects.get('odd_even_check'):
            state.odd_even_check_active = True
            print(f"[效果应用] {qq_id} 下回合将进行奇偶检定")

        # 处理数学检定效果
        if effects.get('math_check'):
            state.math_check_active = True
            print(f"[效果应用] {qq_id} 下回合将进行数学检定")

        # ==================== 特殊效果 ====================

        # 处理锁定时间效果（非请勿入）
        if 'lockout_hours' in effects:
            from datetime import datetime, timedelta
            lockout_hours = effects['lockout_hours']
            lockout_time = datetime.now() + timedelta(hours=lockout_hours)
            state.lockout_until = lockout_time.isoformat()
            print(f"[效果应用] {qq_id} 被锁定 {lockout_hours} 小时，直到 {lockout_time}")

        # 处理需要选择的陷阱（魔女的小屋）
        if effects.get('requires_choice') and 'choices' in effects:
            # 这个由 game_engine 中的 _trigger_cell_content 处理
            pass

        # 保存状态
        self.state_dao.update_state(state)

    def _retreat_position(self, qq_id: str, column: int, retreat_count: int):
        """回退指定列的位置

        Args:
            qq_id: 玩家QQ号
            column: 列号
            retreat_count: 回退格数
        """
        temp_positions = self.position_dao.get_positions(qq_id, 'temp')
        temp_pos = next((p for p in temp_positions if p.column_number == column), None)

        if not temp_pos:
            return

        # 计算新位置
        new_position = max(1, temp_pos.position - retreat_count)

        # 检查是否有永久标记
        permanent_positions = self.position_dao.get_positions(qq_id, 'permanent')
        permanent_pos = next((p for p in permanent_positions if p.column_number == column), None)

        if permanent_pos:
            # 如果回退后的位置<=永久标记位置，则临时标记应该在永久标记+1的位置
            if new_position <= permanent_pos.position:
                new_position = permanent_pos.position + 1

        # 更新位置
        self.position_dao.add_or_update_position(qq_id, column, new_position, 'temp')

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
