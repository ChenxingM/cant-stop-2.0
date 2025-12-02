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

    # ==================== 通用检查 ====================

    def _check_lockout(self, qq_id: str) -> Optional[GameResult]:
        """检查玩家是否被锁定

        Returns:
            如果被锁定返回 GameResult 错误消息，否则返回 None
        """
        from datetime import datetime
        state = self.state_dao.get_state(qq_id)

        if not state or not state.lockout_until:
            return None

        try:
            lockout_time = datetime.fromisoformat(state.lockout_until)
            now = datetime.now()

            if now < lockout_time:
                remaining = lockout_time - now
                total_seconds = remaining.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                return GameResult(False,
                    f"⏰ 您当前被禁止进行游戏\n"
                    f"剩余时间：{hours}小时{minutes}分钟\n"
                    f"解锁时间：{lockout_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                # 锁定已过期，清除
                state.lockout_until = None
                self.state_dao.update_state(state)
                return None
        except ValueError:
            # 时间格式错误，清除
            state.lockout_until = None
            self.state_dao.update_state(state)
            return None

    # ==================== 玩家管理 ====================

    def register_or_get_player(self, qq_id: str, nickname: str) -> tuple[Player, bool]:
        """注册或获取玩家

        Returns:
            tuple: (player, is_new) - 玩家对象和是否是新注册的玩家
        """
        player = self.player_dao.get_player(qq_id)
        is_new = False
        if not player:
            player = self.player_dao.create_player(qq_id, nickname)
            is_new = True
        return player, is_new

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
        # 检查是否被锁定
        lockout_result = self._check_lockout(qq_id)
        if lockout_result:
            return lockout_result

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
        # 检查是否被锁定
        lockout_result = self._check_lockout(qq_id)
        if lockout_result:
            return lockout_result

        # 检查是否已选择阵营
        player = self.player_dao.get_player(qq_id)
        if not player.faction:
            return GameResult(False, "⚠️ 请先选择阵营！\n使用指令：\n• 选择阵营：收养人\n• 选择阵营：Aeonreth")

        state = self.state_dao.get_state(qq_id)

        # 检查是否是花言巧语抵抗骰（.r1d6）
        if dice_count == 1 and state.sweet_talk_blocked:
            result = random.randint(1, 6)
            blocked_columns = state.sweet_talk_blocked.get('blocked_columns', [])
            blocked_columns_str = ', '.join([f"列{c}" for c in blocked_columns])

            if result == 6:
                # 抵抗成功，清除封锁
                state.sweet_talk_blocked = None
                self.state_dao.update_state(state)
                return GameResult(True,
                    f"🎲 抵抗骰结果: {result}\n"
                    f"✨ 抵抗成功！花言巧语的封锁已解除！\n"
                    f"您可以正常在 {blocked_columns_str} 行进了")
            else:
                # 抵抗失败
                return GameResult(False,
                    f"🎲 抵抗骰结果: {result}\n"
                    f"❌ 抵抗失败...需要投出6才能解除封锁\n"
                    f"本轮次您无法在 {blocked_columns_str} 行进")

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
                    # 通过检定，获得额外d6，发放成就［数学大王］
                    extra_die = random.randint(1, 6)
                    self.state_dao.update_state(state)
                    self.achievement_dao.add_achievement(qq_id, 0, "数学大王", "hidden")
                    message = (f"🎲投掷结果: {' '.join(map(str, results))}\n"
                              f"✨ 奇偶检定：奇数{odd_count}个 > 3，通过！\n"
                              f"🏆 获得成就［数学大王］\n"
                              f"额外d6: {extra_die}，可以随意加到任意组合中")
                    # 这里暂时只返回提示，实际加值需要在记录数值时处理
                    return GameResult(True, message, {
                        "results": results,
                        "extra_die": extra_die
                    })
                else:
                    # 未通过检定，本回合作废，发放成就［数学0蛋］
                    # 回退本回合所有临时标记移动的1格
                    temp_positions = self.position_dao.get_positions(qq_id, 'temp')
                    retreat_msgs = []
                    for pos in temp_positions:
                        self._retreat_position(qq_id, pos.column_number, 1)
                        retreat_msgs.append(f"列{pos.column_number}")

                    state.last_dice_result = None
                    self.state_dao.update_state(state)
                    self.achievement_dao.add_achievement(qq_id, 0, "数学0蛋", "hidden")

                    retreat_info = f"\n⬅️ 临时标记回退：{', '.join(retreat_msgs)}" if retreat_msgs else ""
                    return GameResult(False,
                                   f"🎲投掷结果: {' '.join(map(str, results))}\n"
                                   f"❌ 奇偶检定：奇数{odd_count}个 ≤ 3，未通过！本回合作废{retreat_info}\n"
                                   f"🏆 获得成就［数学0蛋］")

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
                    # 通过检定，发放成就［进去吧你！］
                    self.achievement_dao.add_achievement(qq_id, 0, "进去吧你！", "hidden")
                    combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])
                    message = (f"🎲投掷结果: {' '.join(map(str, results))}\n"
                              f"✨ 数学检定：可得到{unique_count}种不同数字 ≥ 8，通过！\n"
                              f"🏆 获得成就［进去吧你！］\n"
                              f"可能的组合: {combinations_str}")
                    return GameResult(True, message, {
                        "results": results,
                        "possible_sums": possible_sums
                    })
                else:
                    # 未通过检定，本回合作废，发放成就［哭哭做题家］
                    # 回退本回合所有临时标记移动的1格
                    temp_positions = self.position_dao.get_positions(qq_id, 'temp')
                    retreat_msgs = []
                    for pos in temp_positions:
                        self._retreat_position(qq_id, pos.column_number, 1)
                        retreat_msgs.append(f"列{pos.column_number}")

                    state.last_dice_result = None
                    self.state_dao.update_state(state)
                    self.achievement_dao.add_achievement(qq_id, 0, "哭哭做题家", "hidden")

                    retreat_info = f"\n⬅️ 临时标记回退：{', '.join(retreat_msgs)}" if retreat_msgs else ""
                    return GameResult(False,
                                   f"🎲投掷结果: {' '.join(map(str, results))}\n"
                                   f"❌ 数学检定：可得到{unique_count}种不同数字 < 8，未通过！本回合作废{retreat_info}\n"
                                   f"🏆 获得成就［哭哭做题家］")

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

        print(f"[record_values] {qq_id}: 当前临时列={temp_columns}, 新列={new_columns}, 总数={len(temp_columns) + len(new_columns)}")

        if len(temp_columns) + len(new_columns) > 3:
            return GameResult(False, f"最多只能在3列上放置临时标记\n当前已有列：{list(temp_columns)}")

        # 检查是否在已登顶的列
        for val in values:
            if val in state.topped_columns:
                return GameResult(False, f"第{val}列您已经登顶，无法再次放置标记")

        # 检查花言巧语封锁
        if state.sweet_talk_blocked:
            blocked_columns = state.sweet_talk_blocked.get('blocked_columns', [])
            from_qq = state.sweet_talk_blocked.get('from_qq', '')
            for val in values:
                if val in blocked_columns:
                    blocked_str = ', '.join([f"列{c}" for c in blocked_columns])
                    # 获取施放者昵称
                    from_player = self.player_dao.get_player(from_qq)
                    from_name = from_player.nickname if from_player else from_qq
                    return GameResult(False,
                        f"🗣️ 您被 {from_name} 施加了花言巧语！\n"
                        f"{blocked_str} 被封锁，本轮次无法在这些列上行进\n"
                        f"💡 可输入 .r1d6 投掷抵抗骰，出目6可解除封锁")

        # 检查「魔女的小屋」逃跑效果：下次必须移动指定列
        if state.pending_trap_choice and state.pending_trap_choice.get('trap_type') == 'witch_house_escape':
            must_move_column = state.pending_trap_choice.get('must_move_column')
            if must_move_column and must_move_column not in values:
                # 没有移动指定列，清除该列的临时标记
                self.position_dao.clear_temp_position_by_column(qq_id, must_move_column)
                # 清除效果
                state.pending_trap_choice = None
                self.state_dao.update_state(state)
                return GameResult(False,
                    f"⚠️ 魔女的厨刀追上了你！\n"
                    f"你未能移动列{must_move_column}的标记，该列的临时标记已被清除！")
            else:
                # 成功移动了指定列，清除效果
                state.pending_trap_choice = None
                self.state_dao.update_state(state)

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

        # 检查是否有登顶提示
        topped_msgs = [msg for msg in messages if "到达列顶" in msg]

        # 组合消息：位置信息 + 登顶提示 + 内容触发
        base_msg = f"玩家选择记录数值：{values}\n当前位置：{position_str}\n剩余可放置标记：{remaining}"

        # 添加登顶提示
        if topped_msgs:
            base_msg += "\n\n" + "\n".join(topped_msgs)

        if content_messages:
            full_msg = base_msg + "\n\n" + "\n\n".join(content_messages)
        else:
            full_msg = base_msg

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

        # 获取列高度
        column_height = COLUMN_HEIGHTS[column]

        # 检查是否已经到达列顶（临时标记已在顶部）
        if temp_pos and temp_pos.position >= column_height:
            return GameResult(False, f"列{column}已到达列顶，无法继续前进"), None

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
        if new_position > column_height:
            return GameResult(False, f"列{column}已到达列顶，无法继续前进"), None

        # 更新位置
        self.position_dao.add_or_update_position(qq_id, column, new_position, 'temp')

        # 只在最终位置触发地图内容
        content_msg = None
        if trigger_content:
            content_msg = self._trigger_cell_content(qq_id, column, new_position)

        # 检查是否到达列顶
        if new_position >= column_height:
            # 自动执行登顶流程
            top_result = self._auto_claim_column_top(qq_id, column)
            topped_msg = f"列{column}移动到第{new_position}格 🎉 到达列顶！\n\n{top_result.message}"
            return GameResult(True, topped_msg), content_msg

        return GameResult(True, f"列{column}移动到第{new_position}格"), content_msg

    def end_round_active(self, qq_id: str) -> GameResult:
        """主动结束轮次（替换永久棋子）"""
        # 检查是否被锁定
        lockout_result = self._check_lockout(qq_id)
        if lockout_result:
            return lockout_result

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
        new_topped_columns = []  # 本次新登顶的列
        for pos in positions:
            if pos.position >= COLUMN_HEIGHTS[pos.column_number]:
                # 登顶
                if pos.column_number not in state.topped_columns:
                    state.topped_columns.append(pos.column_number)
                    new_topped_columns.append(pos.column_number)

        # 检查是否获胜（3列登顶）
        if len(state.topped_columns) >= 3:
            return self._handle_game_win(qq_id)

        # 更新状态
        state.current_round_active = False
        state.can_start_new_round = False  # 需要打卡后才能开启新轮次
        state.sweet_talk_blocked = None  # 清除花言巧语封锁
        self.state_dao.update_state(state)

        position_str = ', '.join([f"列{p.column_number}第{p.position}格" for p in positions])

        # 生成登顶提示
        topped_msg = ""
        if new_topped_columns:
            topped_str = ', '.join([f"列{c}" for c in new_topped_columns])
            topped_msg = f"\n🎉 恭喜！您在 {topped_str} 登顶！\n请输入【数列X登顶】领取登顶奖励（X为列号）"

        return GameResult(True, f"本轮次结束。\n当前永久棋子位置：{position_str}{topped_msg}\n进度已锁定，请打卡后输入【打卡完毕】恢复开启新轮次功能")

    def end_round_passive(self, qq_id: str) -> GameResult:
        """被动结束轮次（进度回退）"""
        # 检查是否被锁定
        lockout_result = self._check_lockout(qq_id)
        if lockout_result:
            return lockout_result

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
        state.sweet_talk_blocked = None  # 清除花言巧语封锁
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

        # 清空该列所有玩家的临时标记
        self.position_dao.clear_all_temp_positions_by_column(column)

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

            # 首达后禁止新轮次12小时
            from datetime import datetime, timedelta
            state = self.state_dao.get_state(qq_id)
            lockout_time = datetime.now() + timedelta(hours=12)
            state.lockout_until = lockout_time.isoformat()
            self.state_dao.update_state(state)

            message += f"\n\n⏰ 由于全图首次登顶，您将被禁止开启新轮次 12 小时\n解锁时间：{lockout_time.strftime('%Y-%m-%d %H:%M:%S')}"

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

            # 显示道具描述
            if item.description:
                item_line += f"\n   📝 {item.description}"

            # 如果不可购买，显示原因
            if not can_buy and reason != "可以购买":
                item_line += f"\n   ❌ {reason}"

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
        # 检查是否被锁定
        lockout_result = self._check_lockout(qq_id)
        if lockout_result:
            return lockout_result

        player = self.player_dao.get_player(qq_id)
        item = self.shop_dao.get_item_by_name(item_name)

        if not item:
            return GameResult(False, f"道具「{item_name}」不存在或尚未解锁")

        # 获取玩家当前拥有该道具的数量
        current_owned = self.inventory_dao.get_item_count(qq_id, item.item_id, item.item_type)

        can_buy, reason = item.can_buy(player, current_owned)
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

    # ==================== 契约系统 ====================

    def bind_contract(self, qq_id: str, target_qq: str) -> GameResult:
        """绑定契约对象

        Args:
            qq_id: 发起绑定的玩家QQ号
            target_qq: 目标契约对象QQ号
        """
        from database.dao import ContractDAO
        contract_dao = ContractDAO(self.conn)

        # 不能与自己建立契约
        if qq_id == target_qq:
            return GameResult(False, "❌ 不能与自己建立契约")

        # 检查双方是否都是注册玩家
        player = self.player_dao.get_player(qq_id)
        target = self.player_dao.get_player(target_qq)

        if not player:
            return GameResult(False, "❌ 您还未注册，请先进行游戏操作")
        if not target:
            return GameResult(False, f"❌ 目标玩家 {target_qq} 还未注册游戏")

        # 尝试建立契约
        success, message = contract_dao.create_contract(qq_id, target_qq)

        if success:
            return GameResult(True, f"💕 契约建立成功！\n您与 {target.nickname}({target_qq}) 已成为契约对象\n在某些遭遇和道具中，你们可以互相获得加成效果")
        else:
            return GameResult(False, f"❌ {message}")

    def view_contract(self, qq_id: str) -> GameResult:
        """查看契约关系"""
        from database.dao import ContractDAO
        contract_dao = ContractDAO(self.conn)

        partner_qq = contract_dao.get_contract_partner(qq_id)

        if not partner_qq:
            return GameResult(True, "💔 您当前没有契约对象\n使用「绑定契约对象@QQ号」与其他玩家建立契约")

        partner = self.player_dao.get_player(partner_qq)
        partner_name = partner.nickname if partner else "未知"
        partner_faction = partner.faction if partner else "未选择"

        return GameResult(True, f"💕 您的契约对象：\n👤 {partner_name}({partner_qq})\n🏰 阵营：{partner_faction}")

    def remove_contract(self, qq_id: str) -> GameResult:
        """解除契约关系"""
        from database.dao import ContractDAO
        contract_dao = ContractDAO(self.conn)

        partner_qq = contract_dao.get_contract_partner(qq_id)

        if not partner_qq:
            return GameResult(False, "❌ 您当前没有契约对象")

        partner = self.player_dao.get_player(partner_qq)
        partner_name = partner.nickname if partner else "未知"

        success = contract_dao.remove_contract(qq_id)

        if success:
            return GameResult(True, f"💔 您与 {partner_name}({partner_qq}) 的契约已解除")
        else:
            return GameResult(False, "❌ 解除契约失败")

    # ==================== 遭遇选择 ====================

    def make_choice(self, qq_id: str, choice: str) -> GameResult:
        """对等待选择的遭遇/道具进行选择

        Args:
            qq_id: 玩家QQ号
            choice: 玩家的选择
        """
        # 检查是否被锁定
        lockout_result = self._check_lockout(qq_id)
        if lockout_result:
            return lockout_result

        state = self.state_dao.get_state(qq_id)

        if not state.pending_encounters:
            return GameResult(False, "当前没有等待选择的遭遇或道具")

        # 获取队列中第一个等待选择的信息
        pending_info = state.pending_encounters[0]
        item_id = pending_info['encounter_id']  # 对于道具，这是item_id
        item_name = pending_info['encounter_name']
        available_choices = pending_info.get('choices', [])
        is_item = pending_info.get('is_item', False)
        free_input = pending_info.get('free_input', False)  # 是否自由输入

        # 验证选择是否有效（自由输入模式跳过验证）
        if not free_input and available_choices and choice not in available_choices:
            choices_str = '\n'.join([f"• {c}" for c in available_choices])
            return GameResult(False,
                            f"❌ 无效的选择！请从以下选项中选择：\n{choices_str}")

        # 调用content_handler处理选择
        try:
            if is_item:
                # 道具选择
                result = self.content_handler.use_item(qq_id, item_id, item_name, choice=choice)
                # 如果道具使用成功且不再需要输入，从背包移除
                if result.success and not result.requires_input:
                    self.inventory_dao.remove_item(qq_id, item_id, 'item')
            else:
                # 遭遇选择
                result = self.content_handler._handle_encounter(
                    qq_id, item_id, item_name, is_first=True, choice=choice
                )

            # 从队列中移除已处理的项目
            state.pending_encounters.pop(0)
            # 先保存 pending_encounters 的更新
            self.state_dao.update_state(state)

            # 应用效果（这会重新获取state并保存）
            if result.effects:
                self._apply_content_effects(qq_id, result.effects)

            # 重新获取更新后的state
            state = self.state_dao.get_state(qq_id)

            # 检查是否还有待处理的遭遇/道具
            if state.pending_encounters:
                next_item = state.pending_encounters[0]
                next_choices = next_item.get('choices', [])
                next_is_item = next_item.get('is_item', False)
                type_name = "道具" if next_is_item else "遭遇"
                if next_choices:
                    choices_str = '\n'.join([f"• {c}" for c in next_choices])
                    additional_msg = (f"\n\n⚠️ 您还有待处理的{type_name}：{next_item['encounter_name']}\n"
                                    f"请选择：\n{choices_str}\n\n"
                                    f"💡 使用「选择：你的选择」来进行选择")
                    return GameResult(True, result.message + additional_msg)

            return GameResult(True, result.message)

        except Exception as e:
            return GameResult(False, f"处理选择时出错: {e}")

    def make_trap_choice(self, qq_id: str, choice: str) -> GameResult:
        """处理陷阱选择

        Args:
            qq_id: 玩家QQ号
            choice: 玩家的选择
        """
        state = self.state_dao.get_state(qq_id)

        if not state.pending_trap_choice:
            return GameResult(False, "当前没有等待选择的陷阱")

        trap_info = state.pending_trap_choice
        trap_type = trap_info.get('trap_type')
        available_choices = trap_info.get('choices', [])
        extra_data = trap_info.get('extra_data', {})

        # 验证选择是否有效
        if available_choices and choice not in available_choices:
            choices_str = '\n'.join([f"• {c}" for c in available_choices])
            return GameResult(False,
                            f"❌ 无效的选择！请从以下选项中选择：\n{choices_str}")

        # 根据陷阱类型处理选择
        try:
            if trap_type == 'closed_door':
                result = self._handle_closed_door_choice(qq_id, choice, extra_data)
            elif trap_type == 'witch_house':
                result = self._handle_witch_house_choice(qq_id, choice, extra_data)
            elif trap_type == 'duel':
                result = self._handle_duel_choice(qq_id, choice, extra_data)
            else:
                return GameResult(False, f"未知的陷阱类型: {trap_type}")

            # 清除待处理的陷阱选择
            state.pending_trap_choice = None
            self.state_dao.update_state(state)

            return result

        except Exception as e:
            return GameResult(False, f"处理陷阱选择时出错: {e}")

    def _handle_closed_door_choice(self, qq_id: str, choice: str, extra_data: dict) -> GameResult:
        """处理「紧闭的大门」陷阱的选择

        效果：将当前列的临时标记移动到选择的相邻列
        """
        available_columns = extra_data.get('available_columns', [])
        source_column = extra_data.get('source_column')

        # 解析选择的目标列
        target_column = None
        for col in available_columns:
            if f"移动到列{col}" == choice:
                target_column = col
                break

        if target_column is None:
            return GameResult(False, "无效的列选择")

        # 获取源列的临时标记位置
        temp_positions = self.position_dao.get_positions(qq_id, 'temp')
        source_temp = next((p for p in temp_positions if p.column_number == source_column), None)

        if not source_temp:
            return GameResult(False, "源列没有临时标记")

        # 清除源列的临时标记
        self.position_dao.clear_temp_position_by_column(qq_id, source_column)

        # 在目标列放置临时标记
        # 检查目标列是否有永久标记
        permanent_positions = self.position_dao.get_positions(qq_id, 'permanent')
        target_permanent = next((p for p in permanent_positions if p.column_number == target_column), None)

        if target_permanent:
            # 有永久标记，放在永久标记+1的位置
            new_position = target_permanent.position + 1
        else:
            # 没有永久标记，从第1格开始
            new_position = 1

        self.position_dao.add_or_update_position(qq_id, target_column, new_position, 'temp')

        print(f"[陷阱选择] {qq_id} 紧闭的大门：从列{source_column}移动到列{target_column}第{new_position}格")

        return GameResult(True,
                         f"✅ 你穿过大门来到了相邻的列\n"
                         f"从列{source_column}移动到列{target_column}第{new_position}格")

    def _handle_duel_choice(self, qq_id: str, choice: str, extra_data: dict) -> GameResult:
        """处理「中门对狙」陷阱的选择

        效果：与神秘对手进行d6对决
        - 点数大：+5积分
        - 点数小：停止一回合
        - 点数相同：无事发生
        """
        import random

        # 玩家和对手各投一个d6
        player_roll = random.randint(1, 6)
        opponent_roll = random.randint(1, 6)

        result_msg = f"🎲 中门对狙！\n\n你投出了：{player_roll}\n神秘对手投出了：{opponent_roll}\n\n"

        if player_roll > opponent_roll:
            # 玩家胜利
            self.player_dao.add_score(qq_id, 5)
            result_msg += "🏆 你赢了！获得5积分！\n成就：［狙神］"
            print(f"[陷阱选择] {qq_id} 中门对狙：胜利，+5积分")
        elif player_roll < opponent_roll:
            # 玩家失败
            state = self.state_dao.get_state(qq_id)
            state.skipped_rounds += 1
            self.state_dao.update_state(state)
            result_msg += "💀 你输了...停止一回合\n成就：［尸体］"
            print(f"[陷阱选择] {qq_id} 中门对狙：失败，停止一回合")
        else:
            # 平局
            result_msg += "🤝 平局！无事发生\n成就：［虚晃一枪］"
            print(f"[陷阱选择] {qq_id} 中门对狙：平局")

        return GameResult(True, result_msg)

    def _handle_witch_house_choice(self, qq_id: str, choice: str, extra_data: dict) -> GameResult:
        """处理「魔女的小屋」陷阱的选择

        选择：
        - 帮忙：当前纵列的临时标记被清除
        - 离开：下次移动标记时必须移动该纵列的临时标记，否则清除当前纵列的临时标记
        """
        column = extra_data.get('column')

        if choice == "帮忙":
            # 清除当前列的临时标记
            self.position_dao.clear_temp_position_by_column(qq_id, column)
            result_msg = ("\"太好了...感谢你的帮助，我正需要人手呢...\"\n\n"
                         "随后，你的手臂被一股无形的力量死死按在了砧板上，厨刀落下——\n\n"
                         f"⚠️ 列{column}的临时标记已被清除\n"
                         "成就：［留了一手］")
            print(f"[陷阱选择] {qq_id} 魔女的小屋：选择帮忙，清除列{column}临时标记")
        else:  # 离开
            # 设置状态：下次必须移动该列
            state = self.state_dao.get_state(qq_id)
            # 使用 pending_trap_choice 来存储这个状态
            state.pending_trap_choice = {
                'trap_type': 'witch_house_escape',
                'must_move_column': column
            }
            self.state_dao.update_state(state)
            result_msg = ("你转身离开了厨房，但随后厨房中就传来了刺耳的哭嚎声，"
                         "锋利的厨刀和餐叉朝着你的背后飞来...请立刻逃走！\n\n"
                         f"⚠️ 下次移动标记时，必须移动列{column}的临时标记，否则将清除该列的临时标记！\n"
                         "成就：［冷漠无情］")
            print(f"[陷阱选择] {qq_id} 魔女的小屋：选择离开，下次必须移动列{column}")

        return GameResult(True, result_msg)

    # ==================== 道具使用 ====================

    def use_item(self, qq_id: str, item_name: str, **kwargs) -> GameResult:
        """使用道具

        Args:
            qq_id: 玩家QQ号
            item_name: 道具名称
            **kwargs: 额外参数 (new_column, new_position, reroll_values等)
        """
        # 检查是否被锁定
        lockout_result = self._check_lockout(qq_id)
        if lockout_result:
            return lockout_result

        # 从玩家背包中查找该道具（支持模糊匹配，去掉括号后缀）
        import re
        inventory = self.inventory_dao.get_inventory(qq_id)
        item = None
        # 清理输入的道具名（去掉括号后缀）
        clean_name = re.sub(r'\s*[\[（].*?[\]）]\s*$', '', item_name).strip()
        for inv_item in inventory:
            # 清理背包中的道具名
            inv_clean_name = re.sub(r'\s*[\[（].*?[\]）]\s*$', '', inv_item.item_name).strip()
            if inv_item.item_name == item_name or inv_clean_name == clean_name:
                item = inv_item
                break

        if not item:
            return GameResult(False, f"❌ 您没有道具「{item_name}」\n请使用「查看背包」查看您拥有的道具")

        # 统一参数名称：new_column/new_position -> column/position
        if 'new_column' in kwargs:
            kwargs['column'] = kwargs.pop('new_column')
        if 'new_position' in kwargs:
            kwargs['position'] = kwargs.pop('new_position')

        try:
            result = self.content_handler.use_item(qq_id, item.item_id, item.item_name, **kwargs)

            # 如果道具需要玩家选择，保存到待处理队列
            if result.success and result.requires_input:
                state = self.state_dao.get_state(qq_id)
                item_choice_info = {
                    'column': 0,  # 道具使用不关联位置
                    'position': 0,
                    'encounter_id': item.item_id,  # 复用encounter_id存储item_id
                    'encounter_name': item.item_name,
                    'choices': result.choices,
                    'is_item': True  # 标记这是道具选择
                }
                state.pending_encounters.append(item_choice_info)
                self.state_dao.update_state(state)

                # 返回选择提示
                choices_str = '\n'.join([f"• {choice}" for choice in result.choices])
                return GameResult(True,
                    f"🎒 使用道具：{item_name}\n\n{result.message}\n\n"
                    f"请选择：\n{choices_str}\n\n"
                    f"💡 使用「选择：你的选择」来进行选择")

            if result.success:
                return GameResult(True, result.message, result.effects)
            else:
                return GameResult(False, result.message)
        except Exception as e:
            return GameResult(False, f"使用道具时出错: {e}")

    # ==================== 内部辅助方法 ====================

    def _check_gem_pool_at_position(self, qq_id: str, column: int, position: int) -> Optional[str]:
        """检查指定位置是否有宝石或池沼，并触发效果

        返回触发消息，如果没有宝石/池沼则返回None
        """
        from database.dao import GemPoolDAO
        gem_dao = GemPoolDAO(self.conn)

        gems_at_pos = gem_dao.get_gem_at_position(column, position)
        if not gems_at_pos:
            return None

        messages = []
        player = self.player_dao.get_player(qq_id)

        for gem in gems_at_pos:
            gem_type = gem['gem_type']
            owner_qq = gem['owner_qq']

            # 根据宝石/池沼类型处理效果
            if gem_type == 'red_gem':
                # 红色宝石：+100积分（给触发者，不是owner）
                self.player_dao.add_score(qq_id, 100)
                gem_dao.deactivate_gem(gem['id'])
                messages.append(f"💎🔴 发现红色宝石！\n获得 +100 积分！")
                print(f"[宝石触发] {qq_id} 在 ({column},{position}) 获得红色宝石 +100积分")

            elif gem_type == 'blue_gem':
                # 蓝色宝石：+100积分
                self.player_dao.add_score(qq_id, 100)
                gem_dao.deactivate_gem(gem['id'])
                messages.append(f"💎🔵 发现蓝色宝石！\n获得 +100 积分！")
                print(f"[宝石触发] {qq_id} 在 ({column},{position}) 获得蓝色宝石 +100积分")

            elif gem_type == 'red_pool':
                # 红色池沼：-10积分，并使对应蓝色宝石消失
                self.player_dao.add_score(qq_id, -10)
                gem_dao.deactivate_gem(gem['id'])
                # 使该玩家的蓝色宝石消失
                gem_dao.deactivate_player_gems(owner_qq, 'blue_gem')
                messages.append(f"🌊🔴 踏入红色池沼！\n-10 积分，并且蓝色宝石消失了...")
                print(f"[池沼触发] {qq_id} 在 ({column},{position}) 踏入红色池沼 -10积分")

            elif gem_type == 'blue_pool':
                # 蓝色池沼：-10积分，并使对应红色宝石消失
                self.player_dao.add_score(qq_id, -10)
                gem_dao.deactivate_gem(gem['id'])
                # 使该玩家的红色宝石消失
                gem_dao.deactivate_player_gems(owner_qq, 'red_gem')
                messages.append(f"🌊🔵 踏入蓝色池沼！\n-10 积分，并且红色宝石消失了...")
                print(f"[池沼触发] {qq_id} 在 ({column},{position}) 踏入蓝色池沼 -10积分")

        return '\n\n'.join(messages) if messages else None

    def _trigger_cell_content(self, qq_id: str, column: int, position: int) -> Optional[str]:
        """触发地图格子内容，返回触发消息"""
        messages = []

        # 检查是否有宝石或池沼在该位置
        gem_msg = self._check_gem_pool_at_position(qq_id, column, position)
        if gem_msg:
            messages.append(gem_msg)

        # 从棋盘配置获取该格子的内容
        if column not in BOARD_DATA:
            return '\n\n'.join(messages) if messages else None

        cells = BOARD_DATA[column]
        if position < 1 or position > len(cells):
            return '\n\n'.join(messages) if messages else None

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
                    'choices': result.choices,
                    'free_input': result.free_input  # 是否自由输入
                }
                state.pending_encounters.append(encounter_info)
                self.state_dao.update_state(state)

                # 构建返回消息
                msg = result.message
                # 如果不是自由输入，显示选项
                if result.choices and not result.free_input:
                    choices_str = '\n'.join([f"• {choice}" for choice in result.choices])
                    msg = f"{result.message}\n\n请选择：\n{choices_str}\n\n💡 使用「选择：你的选择」来进行选择"

                # 如果有图片，附加图片路径标记
                if result.image_path:
                    msg = f"[IMAGE:{result.image_path}]\n{msg}"

                # 组合宝石消息和遭遇消息
                if messages:
                    return '\n\n'.join(messages) + '\n\n' + msg
                return msg

            # 如果陷阱需要玩家选择，保存陷阱选择信息
            if result and result.effects and result.effects.get('requires_trap_choice'):
                state = self.state_dao.get_state(qq_id)
                trap_choice_info = {
                    'column': column,
                    'position': position,
                    'trap_id': content_id,
                    'trap_name': content_name,
                    'trap_type': result.effects.get('trap_type'),
                    'choices': result.effects.get('choices', []),
                    'extra_data': {k: v for k, v in result.effects.items()
                                 if k not in ['requires_trap_choice', 'trap_type', 'choices']}
                }
                state.pending_trap_choice = trap_choice_info
                self.state_dao.update_state(state)

                # 添加选择提示到消息
                choices = result.effects.get('choices', [])
                if choices:
                    choices_str = '\n'.join([f"• {choice}" for choice in choices])
                    trap_msg = f"{result.message}\n\n请选择：\n{choices_str}\n\n💡 使用「陷阱选择：你的选择」来进行选择"
                    if messages:
                        return '\n\n'.join(messages) + '\n\n' + trap_msg
                    return trap_msg
                if messages:
                    return '\n\n'.join(messages) + '\n\n' + result.message
                return result.message

            # 处理返回的effects
            if result and result.effects:
                self._apply_content_effects(qq_id, result.effects)

            if result and result.message:
                messages.append(result.message)

            return '\n\n'.join(messages) if messages else None
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
            import logging
            logging.info(f"[效果应用] {qq_id} 被锁定 {lockout_hours} 小时，直到 {lockout_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 处理需要选择的陷阱（魔女的小屋）
        if effects.get('requires_choice') and 'choices' in effects:
            # 这个由 game_engine 中的 _trigger_cell_content 处理
            pass

        # 处理陷阱免疫效果（小女孩娃娃）
        if 'trap_immunity_cost' in effects:
            state.trap_immunity_cost = effects['trap_immunity_cost']
            print(f"[效果应用] {qq_id} 下个陷阱可消耗{state.trap_immunity_cost}积分免疫")

        if effects.get('trap_immunity_draw'):
            state.trap_immunity_draw = True
            print(f"[效果应用] {qq_id} 下个陷阱可通过绘制免疫")

        # 处理揍击派对效果（锤击指定位置的其他玩家标记）
        if 'hammer_position' in effects:
            target_column, target_position = effects['hammer_position']
            self._apply_hammer_effect(qq_id, target_column, target_position)

        # 处理花言巧语效果（封锁目标玩家的当前列）
        if 'block_target' in effects:
            target_qq = effects['block_target']
            self._apply_sweet_talk_effect(qq_id, target_qq)

        # 处理直接登顶效果（The Room徽章）
        if 'direct_top_column' in effects:
            column = effects['direct_top_column']
            self._direct_top_column(qq_id, column)

        # 保存状态
        self.state_dao.update_state(state)

    def _direct_top_column(self, qq_id: str, column: int):
        """直接登顶指定列（The Room徽章效果）

        Args:
            qq_id: 玩家QQ号
            column: 要登顶的列号
        """
        import logging
        from data.board_config import COLUMN_HEIGHTS

        # 获取列高度
        column_height = COLUMN_HEIGHTS.get(column)
        if not column_height:
            logging.error(f"[直接登顶] 无效的列号: {column}")
            return

        # 直接在该列顶部放置永久标记
        self.position_dao.add_or_update_position(qq_id, column, column_height, 'permanent')

        # 将该列添加到topped_columns
        state = self.state_dao.get_state(qq_id)
        if column not in state.topped_columns:
            state.topped_columns.append(column)
        self.state_dao.update_state(state)

        # 清空该列所有玩家的临时标记
        self.position_dao.clear_all_temp_positions_by_column(column)

        logging.info(f"[直接登顶] {qq_id} 使用The Room徽章直接登顶列{column}")

    def _apply_sweet_talk_effect(self, from_qq: str, target_qq: str):
        """应用花言巧语效果 - 封锁目标玩家当前轮次的列

        Args:
            from_qq: 使用道具的玩家QQ号
            target_qq: 目标玩家QQ号
        """
        import logging

        # 获取目标玩家当前的临时标记列
        target_temp_positions = self.position_dao.get_positions(target_qq, 'temp')
        blocked_columns = [p.column_number for p in target_temp_positions]

        if not blocked_columns:
            logging.info(f"[花言巧语] 目标 {target_qq} 没有临时标记，无法封锁")
            return

        # 设置目标玩家的封锁状态
        target_state = self.state_dao.get_state(target_qq)
        target_state.sweet_talk_blocked = {
            'blocked_columns': blocked_columns,
            'from_qq': from_qq
        }
        self.state_dao.update_state(target_state)

        blocked_str = ', '.join([f"列{c}" for c in blocked_columns])
        logging.info(f"[花言巧语] {from_qq} 对 {target_qq} 使用花言巧语，封锁了 {blocked_str}")

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

    def _apply_hammer_effect(self, user_qq: str, column: int, position: int):
        """应用揍击派对效果 - 锤击指定位置所有玩家的标记（包括自己）

        Args:
            user_qq: 使用道具的玩家QQ号
            column: 目标列号
            position: 目标位置
        """
        import logging
        affected_players = []

        # 获取所有玩家
        all_players = self.player_dao.get_all_players()

        for player in all_players:
            # 检查临时标记
            temp_positions = self.position_dao.get_positions(player.qq_id, 'temp')
            for pos in temp_positions:
                if pos.column_number == column and pos.position == position:
                    # 回退1格
                    self._retreat_position(player.qq_id, column, 1)
                    affected_players.append(f"{player.nickname}(临时)")
                    logging.info(f"[揍击派对] {player.nickname} 的临时标记在 ({column},{position}) 被锤退1格")
                    break

            # 检查永久标记
            perm_positions = self.position_dao.get_positions(player.qq_id, 'permanent')
            for pos in perm_positions:
                if pos.column_number == column and pos.position == position:
                    # 永久标记回退1格
                    new_pos = max(1, pos.position - 1)
                    self.position_dao.add_or_update_position(player.qq_id, column, new_pos, 'permanent')
                    affected_players.append(f"{player.nickname}(永久)")
                    logging.info(f"[揍击派对] {player.nickname} 的永久标记在 ({column},{position}) 被锤退1格")
                    break

        if affected_players:
            logging.info(f"[揍击派对] 在({column},{position})共影响: {', '.join(affected_players)}")
        else:
            logging.info(f"[揍击派对] 在({column},{position})没有玩家的标记")

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

    def _auto_claim_column_top(self, qq_id: str, column: int) -> GameResult:
        """自动执行登顶流程（当临时标记到达列顶时）

        Args:
            qq_id: 玩家QQ号
            column: 登顶的列号

        Returns:
            GameResult: 包含登顶奖励信息的结果
        """
        from datetime import datetime, timedelta

        # 1. 将临时标记转换为永久标记
        self.position_dao.convert_temp_to_permanent_by_column(qq_id, column)

        # 2. 将该列添加到topped_columns
        state = self.state_dao.get_state(qq_id)
        if column not in state.topped_columns:
            state.topped_columns.append(column)
        self.state_dao.update_state(state)

        # 3. 清空该列所有玩家的临时标记
        self.position_dao.clear_all_temp_positions_by_column(column)

        # 4. 给予基础登顶奖励（10积分）
        base_reward = 10
        self.player_dao.add_score(qq_id, base_reward)

        message = (f"恭喜您在【{column}】列登顶～\n"
                  f"已清空该列场上所有临时标记。\n"
                  f"✦登顶奖励\n"
                  f"恭喜您获得 {base_reward} 积分")

        # 5. 检查是否是首达
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

            # 6. 首达后禁止新轮次12小时
            state = self.state_dao.get_state(qq_id)
            lockout_time = datetime.now() + timedelta(hours=12)
            state.lockout_until = lockout_time.isoformat()
            self.state_dao.update_state(state)

            message += f"\n\n⏰ 由于全图首次登顶，您将被禁止开启新轮次 12 小时\n解锁时间：{lockout_time.strftime('%Y-%m-%d %H:%M:%S')}"

        # 7. 检查是否获胜（3列登顶）
        state = self.state_dao.get_state(qq_id)
        if len(state.topped_columns) >= 3:
            win_result = self._handle_game_win(qq_id)
            message += f"\n\n{win_result.message}"

        return GameResult(True, message)

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
