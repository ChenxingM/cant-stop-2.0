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
from engine.command_parser import normalize_punctuation


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

    # ==================== 辅助方法 ====================

    def _match_choice(self, choice: str, available_choices: List[str]) -> Optional[str]:
        """标准化匹配选择项，不区分全角半角标点、引号、大小写

        Args:
            choice: 用户输入的选择
            available_choices: 可用的选项列表

        Returns:
            匹配到的原始选项，如果没有匹配返回 None
        """
        import re

        def strip_quotes(s: str) -> str:
            """去掉字符串两端的所有类型引号"""
            # 先去掉两端的引号字符（包括各种中英文引号）
            quote_chars = '"\'"「」『』""''＂＇'
            result = s.strip()
            while result and result[0] in quote_chars:
                result = result[1:]
            while result and result[-1] in quote_chars:
                result = result[:-1]
            return result

        normalized_choice = normalize_punctuation(choice)
        stripped_choice = strip_quotes(normalized_choice)

        for c in available_choices:
            normalized_c = normalize_punctuation(c)
            stripped_c = strip_quotes(normalized_c)

            # 精确匹配（标准化后）
            if normalized_c == normalized_choice:
                return c
            # 忽略引号匹配
            if stripped_c == stripped_choice:
                return c
            # 忽略大小写匹配
            if normalized_c.lower() == normalized_choice.lower():
                return c
            if stripped_c.lower() == stripped_choice.lower():
                return c

        return None

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
        # 检查并处理超时的限时打卡
        expired_msgs = self.check_expired_checkins(qq_id)

        # 检查是否被锁定
        lockout_result = self._check_lockout(qq_id)
        if lockout_result:
            # 如果有超时消息，附加到锁定消息后
            if expired_msgs:
                return GameResult(False, lockout_result.message + "\n\n" + "\n".join(expired_msgs))
            return lockout_result

        # 检查是否已选择阵营
        player = self.player_dao.get_player(qq_id)
        if not player.faction:
            return GameResult(False, "请选择阵营~\n使用指令：\n• 选择阵营：收养人\n• 选择阵营：Aeonreth")

        state = self.state_dao.get_state(qq_id)

        # 检查是否被强制暂停直到打卡
        if state.force_end_until_draw:
            return GameResult(False, "⚠️ 您被强制暂停，需要完成任意绘制后才能继续！\n（葡萄蔷薇紫苑效果）")

        # 检查是否需要完成绘制才能继续（婚戒陷阱）
        if state.requires_drawing:
            return GameResult(False, "⚠️ 您被困住了！需要完成婚戒相关绘制后才能继续！\n（婚戒陷阱效果）")

        if not state.can_start_new_round:
            return GameResult(False, "请先完成打卡，输入【打卡完毕】后才能开启新轮次")

        if state.current_round_active:
            return GameResult(False, "当前轮次还在进行中")

        state.current_round_active = True
        state.temp_markers_used = 0
        state.dice_history = []
        state.last_dice_result = None
        self.state_dao.update_state(state)

        # 如果有超时消息，附加到成功消息后
        if expired_msgs:
            return GameResult(True, "新轮次已开启\n\n" + "\n".join(expired_msgs))
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

        # 检查积分（黑喵效果可减少消耗）
        player = self.player_dao.get_player(qq_id)
        base_cost = 10  # 默认每回合10积分
        cost = max(0, base_cost - state.cost_reduction)  # 黑喵效果减少消耗

        # 检查免费回合
        if state.free_rounds > 0:
            state.free_rounds -= 1
            self.state_dao.update_state(state)
            cost = 0  # 免费回合不消耗积分
            print(f"[免费回合] {qq_id} 使用了1个免费回合，剩余{state.free_rounds}个")
        # 检查双倍消耗
        elif state.next_roll_double_cost:
            cost = cost * 2
            state.next_roll_double_cost = False
            self.state_dao.update_state(state)
            print(f"[双倍消耗] {qq_id} 本次投骰消耗双倍积分: {cost}")

        if cost > 0 and not self.player_dao.consume_score(qq_id, cost):
            return GameResult(False, f"积分不足，需要{cost}积分")

        # 确定骰子数量（可能被陷阱效果修改）
        dice_groups = None  # 默认为 None，让 _get_possible_sums 自动决定分组

        # 优先检查当前回合强制骰子数量（LUCKY DAY等）
        if state.current_dice_count:
            required_count = state.current_dice_count
            if dice_count != required_count:
                return GameResult(False, f"⚠️ 当前回合必须投掷 {required_count} 个骰子（.r{required_count}d6）")
            dice_count = state.current_dice_count
            dice_groups = state.current_dice_groups
            # 清除效果（使用后清除）
            state.current_dice_count = None
            state.current_dice_groups = None
            self.state_dao.update_state(state)
        elif state.next_dice_count:
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

        # 检查超级大炮效果（完全固定出目）
        if state.forced_rolls:
            results = state.forced_rolls[:6]  # 最多6个
            while len(results) < 6:
                results.append(random.randint(1, 6))  # 不足6个用随机数补足
            # 清除效果
            state.forced_rolls = None
            state.last_dice_result = results
            state.dice_history.append(results)
            self.state_dao.update_state(state)

            possible_sums = self._get_possible_sums(results)
            combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])

            message = f"💥 超级大炮！指定出目: {' '.join(map(str, results))}\n可能的组合: {combinations_str}"
            return GameResult(True, message, {
                "results": results,
                "possible_sums": possible_sums
            })

        # 检查闹Ae魔镜效果（部分固定出目）
        if state.partial_forced_rolls:
            forced_count = len(state.partial_forced_rolls)
            results = list(state.partial_forced_rolls)
            # 剩余的随机投掷
            for _ in range(6 - forced_count):
                results.append(random.randint(1, 6))
            random.shuffle(results)  # 打乱顺序
            # 清除效果
            state.partial_forced_rolls = None
            state.last_dice_result = results
            state.dice_history.append(results)
            self.state_dao.update_state(state)

            possible_sums = self._get_possible_sums(results)
            combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])

            message = f"🪞 闹Ae魔镜！部分指定出目: {' '.join(map(str, results))}\n可能的组合: {combinations_str}"
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

            # 应用变大蘑菇/缩小药水的修正效果
            modifier_msg = ""
            if state.all_dice_modifier != 0:
                original_results = results.copy()
                results = [max(1, min(6, r + state.all_dice_modifier)) for r in results]
                modifier = state.all_dice_modifier
                state.all_dice_modifier = 0  # 清除效果
                if modifier > 0:
                    modifier_msg = f"\n🍄 变大蘑菇效果：所有骰子+{modifier}\n原始结果：{' '.join(map(str, original_results))}"
                else:
                    modifier_msg = f"\n🧪 缩小药水效果：所有骰子{modifier}\n原始结果：{' '.join(map(str, original_results))}"

            # 检查沉重的巨剑效果（出1可重投）
            reroll_msg = ""
            if state.reroll_on_one and 1 in results:
                ones_count = results.count(1)
                state.reroll_on_one = False  # 清除效果
                reroll_msg = f"\n⚔️ 沉重的巨剑生效！检测到{ones_count}个1，可以输入【重投】重新投掷这些骰子"
                # 设置允许重投状态
                state.allow_reroll = True
                state.last_dice_result = results
                state.dice_history.append(results)
                self.state_dao.update_state(state)

                possible_sums = self._get_possible_sums(results, dice_groups)
                combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)]) if possible_sums else "无有效组合"
                message = f"🎲投掷结果: {' '.join(map(str, results))}{modifier_msg}{reroll_msg}\n可能的组合: {combinations_str}"
                return GameResult(True, message, {
                    "results": results,
                    "possible_sums": possible_sums,
                    "can_reroll": True,
                    "reroll_type": "ones"
                })

            # 检查女巫魔法伎俩效果（出6可重投）
            if state.reroll_on_six and 6 in results:
                sixes_count = results.count(6)
                state.reroll_on_six = False  # 清除效果
                reroll_msg = f"\n🔮 女巫魔法伎俩生效！检测到{sixes_count}个6，可以输入【重投】重新投掷这些骰子"
                # 设置允许重投状态
                state.allow_reroll = True
                state.last_dice_result = results
                state.dice_history.append(results)
                self.state_dao.update_state(state)

                possible_sums = self._get_possible_sums(results, dice_groups)
                combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)]) if possible_sums else "无有效组合"
                message = f"🎲投掷结果: {' '.join(map(str, results))}{modifier_msg}{reroll_msg}\n可能的组合: {combinations_str}"
                return GameResult(True, message, {
                    "results": results,
                    "possible_sums": possible_sums,
                    "can_reroll": True,
                    "reroll_type": "sixes"
                })

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
                    # 计算可能的组合
                    possible_sums = self._get_possible_sums(results, dice_groups)
                    combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)]) if possible_sums else "无有效组合"
                    message = (f"🎲投掷结果: {' '.join(map(str, results))}\n"
                              f"✨ 奇偶检定：奇数{odd_count}个 > 3，通过！\n"
                              f"🏆 获得成就［数学大王］\n"
                              f"额外d6: {extra_die}，可以随意加到任意组合中\n"
                              f"可能的组合: {combinations_str}")
                    # 这里暂时只返回提示，实际加值需要在记录数值时处理
                    return GameResult(True, message, {
                        "results": results,
                        "extra_die": extra_die,
                        "possible_sums": possible_sums
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
            possible_sums = self._get_possible_sums(results, dice_groups)

            # 格式化可能的组合提示
            if possible_sums:
                combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])
            else:
                combinations_str = "无有效组合"

            message = f"🎲投掷结果: {' '.join(map(str, results))}\n可能的组合: {combinations_str}"

            # 如果没有有效组合，检查是否有修改骰子的能力
            if not possible_sums:
                if state.next_dice_modify_any:
                    message += "\n\n💡 您有「修改骰子」的能力！可以修改一个骰子的数值。\n使用指令：修改骰子 位置 新值（例如：修改骰子 1 5）"
                elif state.change_one_dice_available:
                    message += "\n\n💡 您有「修改骰子」的能力！可以修改一个骰子的数值。\n使用指令：修改骰子 位置 新值（例如：修改骰子 1 5）"
                elif state.next_dice_add_3_any:
                    message += "\n\n💡 您有「骰子+3」的能力！可以让任意一个骰子的结果+3。\n使用指令：骰子加三 位置（例如：骰子加三 1）"

            return GameResult(True, message, {
                "results": results,
                "possible_sums": possible_sums
            })

    def reroll_dice(self, qq_id: str, target_value: int = None) -> GameResult:
        """重投骰子（败者尘、沉重的巨剑、女巫魔法伎俩）

        Args:
            qq_id: 玩家QQ号
            target_value: 要重投的目标值（1或6），如果为None则重投所有骰子
        """
        state = self.state_dao.get_state(qq_id)

        if not state.allow_reroll:
            return GameResult(False, "⚠️ 当前没有可重投的骰子")

        if not state.last_dice_result:
            return GameResult(False, "⚠️ 没有可重投的骰子结果")

        old_results = state.last_dice_result.copy()

        if target_value is None:
            # 败者尘：重投所有骰子
            results = [random.randint(1, 6) for _ in range(6)]
            reroll_info = "全部重投"
        else:
            # 沉重的巨剑/女巫魔法伎俩：只重投特定值的骰子
            results = []
            for r in old_results:
                if r == target_value:
                    results.append(random.randint(1, 6))
                else:
                    results.append(r)
            reroll_info = f"重投了{old_results.count(target_value)}个{target_value}"

        # 清除重投状态
        state.allow_reroll = False
        state.last_dice_result = results
        state.dice_history.append(results)
        self.state_dao.update_state(state)

        # 计算可能的组合
        possible_sums = self._get_possible_sums(results)
        combinations_str = ", ".join([f"({a}, {b})" for a, b in sorted(possible_sums)])

        message = (f"🔄 {reroll_info}\n"
                  f"原结果: {' '.join(map(str, old_results))}\n"
                  f"新结果: {' '.join(map(str, results))}\n"
                  f"可能的组合: {combinations_str}")

        return GameResult(True, message, {
            "results": results,
            "possible_sums": possible_sums
        })

    def _get_possible_sums(self, dice_results: List[int], groups: List[int] = None) -> List[Tuple[int, int]]:
        """计算所有可能的两组和

        Args:
            dice_results: 骰子结果列表
            groups: 分组方式，如 [3, 3] 表示两组各3个，[2, 2] 表示两组各2个
                    如果为 None，默认按骰子数量对半分
        """
        from itertools import combinations

        n = len(dice_results)

        # 确定分组方式
        if groups is None:
            if n == 6:
                groups = [3, 3]
            elif n == 4:
                groups = [2, 2]
            elif n == 7:
                groups = [3, 4]
            elif n == 10:
                groups = [5, 5]
            else:
                # 默认对半分
                groups = [n // 2, n - n // 2]

        group1_size = groups[0]

        possible_sums = set()
        for indices in combinations(range(n), group1_size):
            group1 = [dice_results[i] for i in indices]
            group2 = [dice_results[i] for i in range(n) if i not in indices]
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

        # 保存移动前的强制回合数（用于后续判断是否需要递减）
        forced_rounds_before_move = state.forced_remaining_rounds

        # 检查是否有待完成的遭遇选择
        if state.pending_encounters:
            return GameResult(False, "⚠️ 您还有待完成的遭遇选择，请先完成选择！\n使用指令：选择：你的选择")

        if not state.current_round_active:
            return GameResult(False, "请先开始轮次")

        # 检查是否投过骰子
        if not state.last_dice_result:
            return GameResult(False, "⚠️ 请先投掷骰子！\n使用指令：.r6d6")

        # 检查黄玫瑰效果：被标记的玩家必须重新投掷
        if state.force_reroll_next_move:
            import random
            # 强制重新投掷骰子
            new_dice = [random.randint(1, 6) for _ in range(6)]
            state.last_dice_result = new_dice
            state.force_reroll_next_move = False
            self.state_dao.update_state(state)

            new_possible_sums = self._get_possible_sums(new_dice)
            sums_str = ', '.join([f"({s[0]}, {s[1]})" for s in sorted(new_possible_sums)])

            return GameResult(False,
                f"🌹 黄玫瑰效果触发！\n"
                f"虚假的花瓣扰乱了你的骰子...\n\n"
                f"你的骰子被强制重新投掷！\n"
                f"新骰子结果：{new_dice}\n"
                f"可选数值组合：{sums_str}\n\n"
                f"请使用新的骰子结果重新记录数值")

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

        # 检查是否在冻结的列
        for val in values:
            if val in state.frozen_columns:
                return GameResult(False, f"第{val}列已被冻结，无法放置标记")

        # 检查是否在本轮禁用的列（紧闭的大门效果）
        for val in values:
            if val in state.disabled_columns_this_round:
                return GameResult(False, f"第{val}列本轮次被禁用，无法放置标记")

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

        # 移动标记
        messages = []
        content_messages = []

        for idx, val in enumerate(values):
            # 每次移动前刷新位置列表，确保处理重复值时能正确移动
            current_positions = self.position_dao.get_positions(qq_id)
            temp_positions = [p for p in current_positions if p.marker_type == 'temp']
            permanent_positions = [p for p in current_positions if p.marker_type == 'permanent']

            # 每次移动都触发所到达格子的内容（同一列走两格时两个格子都触发）
            result, content_msg = self._move_marker(qq_id, val, temp_positions, permanent_positions,
                                                   trigger_content=True)
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
        # 只有移动前就已有强制回合时才递减（避免触发陷阱的那一回合被计入）
        if forced_rounds_before_move > 0:
            state.forced_remaining_rounds -= 1

        # 清除骰子结果，要求玩家在下次记录数值前必须重新投掷骰子
        state.last_dice_result = None
        self.state_dao.update_state(state)

        # 获取更新后的位置
        current_positions = self.position_dao.get_positions(qq_id)
        temp_positions = [p for p in current_positions if p.marker_type == 'temp']
        print(f"[位置显示] {qq_id} 查询到的临时位置: {[(p.column_number, p.position) for p in temp_positions]}")

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

        # 重新获取实际位置（可能被效果修改，如回退）
        actual_positions = self.position_dao.get_positions(qq_id, 'temp')
        actual_pos = next((p for p in actual_positions if p.column_number == column), None)
        actual_position = actual_pos.position if actual_pos else 0

        # 检查是否到达列顶（使用实际位置而非效果前位置）
        if actual_position >= column_height:
            # 自动执行登顶流程
            top_result = self._auto_claim_column_top(qq_id, column)
            topped_msg = f"列{column}移动到第{actual_position}格 🎉 到达列顶！\n\n{top_result.message}"
            return GameResult(True, topped_msg), content_msg

        return GameResult(True, f"列{column}移动到第{actual_position}格"), content_msg

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
        # 花言巧语封锁：如果已在本轮生效过则清除，否则标记为已生效
        if state.sweet_talk_blocked:
            if state.sweet_talk_blocked.get('applied'):
                state.sweet_talk_blocked = None
            else:
                state.sweet_talk_blocked['applied'] = True
        state.disabled_columns_this_round = []  # 清空本轮禁用列
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

        # 检查阈限空间效果（失败可重试一次）
        if state.allow_retry_on_fail:
            state.allow_retry_on_fail = False
            state.last_dice_result = None  # 清除上次骰子结果，允许重新投骰
            self.state_dao.update_state(state)
            return GameResult(True,
                "🌀 阈限空间效果触发！\n"
                "您获得了一次重试的机会！\n"
                "本次进度回退已被取消，您可以继续投掷骰子。")

        # 检查红玫瑰效果（失败可重试）
        if state.has_red_rose:
            state.has_red_rose = False
            state.last_dice_result = None
            self.state_dao.update_state(state)
            return GameResult(True,
                "🌹 红玫瑰效果触发！\n"
                "娇艳的花瓣化为力量守护着你...\n"
                "本次进度回退已被取消，您可以继续投掷骰子。")

        # 检查蓝玫瑰效果（来自Ae的保护）
        if state.has_blue_rose_from:
            from_qq = state.has_blue_rose_from
            state.has_blue_rose_from = None
            state.last_dice_result = None
            self.state_dao.update_state(state)

            # 获取帮助者信息
            helper = self.player_dao.get_player(from_qq)
            helper_name = helper.nickname if helper else from_qq

            return GameResult(True,
                f"🌹 蓝玫瑰效果触发！\n"
                f"来自 {helper_name} 的蓝玫瑰守护了你...\n"
                f"本次进度回退已被取消，您可以继续投掷骰子。")

        # 清除所有临时标记
        self.position_dao.clear_temp_positions(qq_id)

        # 更新状态
        state.current_round_active = False
        state.temp_markers_used = 0
        # 花言巧语封锁：如果已在本轮生效过则清除，否则标记为已生效
        if state.sweet_talk_blocked:
            if state.sweet_talk_blocked.get('applied'):
                state.sweet_talk_blocked = None
            else:
                state.sweet_talk_blocked['applied'] = True
        state.disabled_columns_this_round = []  # 清空本轮禁用列
        self.state_dao.update_state(state)

        positions = self.position_dao.get_positions(qq_id, 'permanent')
        position_str = ', '.join([f"列{p.column_number}第{p.position}格" for p in positions]) if positions else "无"

        return GameResult(True, f"本轮次结束。\n当前永久棋子位置：{position_str}")

    def finish_checkin(self, qq_id: str) -> GameResult:
        """完成打卡"""
        state = self.state_dao.get_state(qq_id)
        state.can_start_new_round = True

        # 清除强制暂停状态（葡萄蔷薇紫苑效果）
        extra_msg = ""
        if state.force_end_until_draw:
            state.force_end_until_draw = False
            extra_msg = "\n✨ 强制暂停已解除！"

        # 清除婚戒陷阱效果
        if state.requires_drawing:
            state.requires_drawing = False
            extra_msg += "\n💍 婚戒束缚已解除！"

        self.state_dao.update_state(state)

        return GameResult(True, f"您可以开始新的轮次了～{extra_msg}")

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

        state = self.state_dao.get_state(qq_id)

        # 检查是否需要双倍打卡（葡萄蔷薇紫苑效果）
        extra_msg = ""
        if state.must_draw_double:
            # 需要双倍数量才能获得积分
            if count < 2:
                return GameResult(False,
                    f"⚠️ 您受到「葡萄蔷薇紫苑」效果影响，需要双倍绘制！\n"
                    f"请至少提交2张{reward_type}才能获得积分。")
            # 只给单张积分
            actual_count = count // 2
            score = reward_map[reward_type] * actual_count * multiplier
            state.must_draw_double = False
            self.state_dao.update_state(state)
            extra_msg = f"\n（双倍打卡效果已消耗，实际计算{actual_count}张）"
        else:
            score = reward_map[reward_type] * count * multiplier

        self.player_dao.add_score(qq_id, score)

        return GameResult(True, f"您的积分+{score}{extra_msg}")

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
            self.achievement_dao.add_achievement(qq_id, column, "鹤立oas群", "first_clear")

            message += (
                f"\n\n🍗 大吉大利，今晚吃鸡\n"
                f"肥美的烤鸡扑扇着翅膀飞到了你面前的盘子里，诱人的香气让你迫不及待地切开金黄外皮…不对，等一下？！\n\n"
                f"✦列全体首达奖励\n"
                f"获得成就：鹤立oas群\n"
                f"获得奖励：积分+{first_reward}\n"
                f"获得现实奖励：纪念币一枚（私信官号领取，不包邮）"
            )

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

        # 全角转半角标准化
        normalized_name = normalize_punctuation(item_name)
        item = self.shop_dao.get_item_by_name(normalized_name)

        # 如果直接匹配失败，尝试遍历商店进行标准化匹配（忽略大小写）
        if not item:
            all_items = self.shop_dao.get_all_items()
            for shop_item in all_items:
                shop_normalized = normalize_punctuation(shop_item.item_name)
                if shop_normalized.lower() == normalized_name.lower():
                    item = shop_item
                    break

        if not item:
            return GameResult(False, f"道具「{item_name}」不存在或尚未解锁")

        # 获取玩家总购买次数（使用成就系统记录）
        purchase_key = f"购买_{item.item_id}"
        achievements = self.achievement_dao.get_achievements(qq_id)
        total_purchased = sum(1 for a in achievements if a.achievement_name == purchase_key)

        can_buy, reason = item.can_buy(player, total_purchased)
        if not can_buy:
            return GameResult(False, reason)

        # 检查购物卡效果（半价）
        state = self.state_dao.get_state(qq_id)
        actual_price = item.price
        half_price_msg = ""
        if state.next_purchase_half:
            actual_price = item.price // 2
            state.next_purchase_half = False
            self.state_dao.update_state(state)
            half_price_msg = " 🎫 购物卡生效，享受半价优惠！"

        # 扣除积分
        if not self.player_dao.consume_score(qq_id, actual_price):
            return GameResult(False, "积分不足")

        # 添加道具
        self.inventory_dao.add_item(qq_id, item.item_id, item.item_name, item.item_type)

        # 更新商店库存
        self.shop_dao.purchase_item(item.item_id)

        # 记录购买历史（用于限购检查）
        self.achievement_dao.add_achievement(qq_id, 30000 + item.item_id, purchase_key, "normal")

        # 构建限购提示
        limit_msg = ""
        if item.player_limit > 0:
            remaining = item.player_limit - total_purchased - 1
            if remaining > 0:
                limit_msg = f"\n（剩余可购买次数：{remaining}）"
            else:
                limit_msg = "\n（已达到购买上限）"

        return GameResult(True, f"✅ 成功购买 {item.item_name}，消耗 {actual_price} 积分{half_price_msg}{limit_msg}")

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

    # ==================== 对决系统 ====================

    def start_duel(self, qq_id: str, target_qq: str) -> GameResult:
        """发起对决（中门对狙陷阱）

        Args:
            qq_id: 发起对决的玩家QQ号
            target_qq: 被挑战的玩家QQ号
        """
        import random

        state = self.state_dao.get_state(qq_id)

        # 检查是否有待处理的对决选择
        if not state.pending_trap_choice:
            return GameResult(False, "❌ 当前没有等待的对决陷阱")

        trap_info = state.pending_trap_choice
        extra_data = trap_info.get('extra_data', {})
        # awaiting_duel_target 可能在 trap_info 或 extra_data 中
        awaiting_duel = trap_info.get('awaiting_duel_target') or extra_data.get('awaiting_duel_target')
        if trap_info.get('trap_type') != 'duel' or not awaiting_duel:
            return GameResult(False, "❌ 当前没有等待的对决陷阱")

        # 检查不能和自己对决
        if target_qq == qq_id:
            return GameResult(False, "❌ 不能和自己对决！请选择其他玩家")

        # 检查目标玩家是否存在
        target_player = self.player_dao.get_player(target_qq)
        if not target_player:
            return GameResult(False, f"❌ 玩家 {target_qq} 不存在")

        # 发起者先投骰
        challenger_roll = random.randint(1, 6)

        # 保存对决状态到发起者的 pending_duel
        # column 可能在 trap_info 或 extra_data 中
        column = trap_info.get('column') or extra_data.get('column')
        state.pending_duel = {
            'challenger_qq': qq_id,
            'challenger_roll': challenger_roll,
            'target_qq': target_qq,
            'column': column
        }
        # 清除陷阱选择状态
        state.pending_trap_choice = None
        self.state_dao.update_state(state)

        # 同时在目标玩家的状态中记录待应战
        target_state = self.state_dao.get_state(target_qq)
        target_state.pending_duel = {
            'challenger_qq': qq_id,
            'challenger_roll': challenger_roll,
            'target_qq': target_qq,
            'awaiting_response': True
        }
        self.state_dao.update_state(target_state)

        player = self.player_dao.get_player(qq_id)
        player_name = player.nickname if player else qq_id
        target_name = target_player.nickname if target_player else target_qq

        return GameResult(True,
            f"⚔️ 中门对狙！\n\n"
            f"🎯 {player_name} 向 {target_name}({target_qq}) 发起对决！\n"
            f"🎲 {player_name} 投出了：{challenger_roll}\n\n"
            f"📢 {target_name}，请输入【应战】来接受对决！\n"
            f"（投出 .r1d6 进行对决）")

    def respond_duel(self, qq_id: str) -> GameResult:
        """响应对决

        Args:
            qq_id: 被挑战的玩家QQ号
        """
        import random

        state = self.state_dao.get_state(qq_id)

        # 检查是否有待响应的对决
        if not state.pending_duel or not state.pending_duel.get('awaiting_response'):
            return GameResult(False, "❌ 当前没有待响应的对决")

        duel_info = state.pending_duel
        challenger_qq = duel_info.get('challenger_qq')
        challenger_roll = duel_info.get('challenger_roll')

        # 响应者投骰
        responder_roll = random.randint(1, 6)

        # 获取玩家名称
        challenger = self.player_dao.get_player(challenger_qq)
        responder = self.player_dao.get_player(qq_id)
        challenger_name = challenger.nickname if challenger else challenger_qq
        responder_name = responder.nickname if responder else qq_id

        result_msg = (f"⚔️ 中门对狙结果！\n\n"
                     f"🎲 {challenger_name} 投出了：{challenger_roll}\n"
                     f"🎲 {responder_name} 投出了：{responder_roll}\n\n")

        # 判定胜负
        if challenger_roll > responder_roll:
            # 发起者胜利
            self.player_dao.add_score(challenger_qq, 5)
            challenger_state = self.state_dao.get_state(challenger_qq)
            challenger_state.pending_duel = None
            self.state_dao.update_state(challenger_state)

            # 响应者失败，停止一回合
            state.skipped_rounds += 1
            state.pending_duel = None
            self.state_dao.update_state(state)

            result_msg += (f"🏆 {challenger_name} 获胜！+5积分\n"
                          f"💀 {responder_name} 失败，停止一回合")
            print(f"[对决] {challenger_qq} vs {qq_id}: 发起者胜利")

        elif challenger_roll < responder_roll:
            # 响应者胜利
            self.player_dao.add_score(qq_id, 5)
            state.pending_duel = None
            self.state_dao.update_state(state)

            # 发起者失败，停止一回合
            challenger_state = self.state_dao.get_state(challenger_qq)
            challenger_state.skipped_rounds += 1
            challenger_state.pending_duel = None
            self.state_dao.update_state(challenger_state)

            result_msg += (f"🏆 {responder_name} 获胜！+5积分\n"
                          f"💀 {challenger_name} 失败，停止一回合")
            print(f"[对决] {challenger_qq} vs {qq_id}: 响应者胜利")

        else:
            # 平局
            state.pending_duel = None
            self.state_dao.update_state(state)

            challenger_state = self.state_dao.get_state(challenger_qq)
            challenger_state.pending_duel = None
            self.state_dao.update_state(challenger_state)

            result_msg += "🤝 平局！无事发生"
            print(f"[对决] {challenger_qq} vs {qq_id}: 平局")

        return GameResult(True, result_msg)

    def thanks_fortune(self, qq_id: str) -> GameResult:
        """玩家回复"谢谢财神"获得额外奖励

        Args:
            qq_id: 玩家QQ号
        """
        state = self.state_dao.get_state(qq_id)

        # 检查是否有待触发的财神福利
        if state.pending_bonus_trigger != 'thanks_fortune':
            return GameResult(False, "❌ 当前没有可以回复的财神福利")

        # 给予免费掷骰券
        self.inventory_dao.add_item(qq_id, 9103, "免费掷骰券", "hidden_item")

        # 清除触发状态
        state.pending_bonus_trigger = None
        self.state_dao.update_state(state)

        return GameResult(True, "\"真是有礼貌的孩子！\" 财神额外给了你一张免费掷骰券 🎟️")

    def encounter_checkin(self, qq_id: str) -> GameResult:
        """遭遇打卡，给玩家+5积分

        Args:
            qq_id: 玩家QQ号

        Returns:
            GameResult: 操作结果
        """
        # 检查玩家是否存在
        player = self.player_dao.get_player(qq_id)
        if not player:
            return GameResult(False, "⚠️ 您还未注册，请先选择阵营！")

        # 给玩家+5积分
        self.player_dao.add_score(qq_id, 5)

        # 获取更新后的积分
        player = self.player_dao.get_player(qq_id)

        return GameResult(True, f"✅ 遭遇打卡成功！获得 +5 积分\n当前积分：{player.current_score}")

    def add_timed_checkin(self, qq_id: str, encounter_name: str, success_achievement: str,
                          failure_achievement: str, days: int = 3) -> GameResult:
        """添加限时打卡任务

        Args:
            qq_id: 玩家QQ号
            encounter_name: 遭遇名称
            success_achievement: 成功时的成就名
            failure_achievement: 失败时的成就名
            days: 期限天数，默认3天
        """
        from datetime import datetime, timedelta

        state = self.state_dao.get_state(qq_id)
        deadline = (datetime.now() + timedelta(days=days)).isoformat()

        checkin_info = {
            'encounter_name': encounter_name,
            'success_achievement': success_achievement,
            'failure_achievement': failure_achievement,
            'deadline': deadline
        }

        state.pending_timed_checkins.append(checkin_info)
        self.state_dao.update_state(state)

        deadline_str = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M')
        return GameResult(True, f"⏰ 已添加限时打卡：{encounter_name}\n截止时间：{deadline_str}\n成功成就：{success_achievement}\n失败成就：{failure_achievement}")

    def check_expired_checkins(self, qq_id: str) -> List[str]:
        """检查并处理超时的打卡任务，返回超时消息列表"""
        from datetime import datetime

        state = self.state_dao.get_state(qq_id)
        if not state.pending_timed_checkins:
            return []

        now = datetime.now()
        expired_messages = []
        remaining_checkins = []

        for checkin in state.pending_timed_checkins:
            deadline = datetime.fromisoformat(checkin['deadline'])
            success_achievement = checkin['success_achievement']
            failure_achievement = checkin['failure_achievement']
            encounter_name = checkin['encounter_name']

            if now > deadline:
                # 检查是否已有成功成就
                achievements = self.achievement_dao.get_achievements(qq_id)
                has_success = any(a.achievement_name == success_achievement for a in achievements)

                if has_success:
                    # 已完成，移除打卡任务
                    expired_messages.append(f"✅ 【{encounter_name}】打卡已完成！获得成就：{success_achievement}")
                else:
                    # 超时失败，给予失败成就
                    self.achievement_dao.add_achievement(qq_id, 40000, failure_achievement, "normal")
                    expired_messages.append(f"❌ 【{encounter_name}】打卡超时！获得成就：{failure_achievement}")
            else:
                remaining_checkins.append(checkin)

        # 更新剩余的打卡任务
        if len(remaining_checkins) != len(state.pending_timed_checkins):
            state.pending_timed_checkins = remaining_checkins
            self.state_dao.update_state(state)

        return expired_messages

    def view_timed_checkins(self, qq_id: str) -> GameResult:
        """查看当前玩家的限时打卡任务"""
        from datetime import datetime

        state = self.state_dao.get_state(qq_id)

        # 先检查超时的
        expired_msgs = self.check_expired_checkins(qq_id)

        # 重新获取状态
        state = self.state_dao.get_state(qq_id)

        if not state.pending_timed_checkins and not expired_msgs:
            return GameResult(True, "📋 您当前没有待完成的限时打卡任务")

        lines = ["📋 限时打卡任务："]

        # 显示超时处理结果
        if expired_msgs:
            lines.append("\n【超时处理】")
            lines.extend(expired_msgs)

        # 显示进行中的任务
        if state.pending_timed_checkins:
            lines.append("\n【进行中】")
            now = datetime.now()
            for i, checkin in enumerate(state.pending_timed_checkins, 1):
                deadline = datetime.fromisoformat(checkin['deadline'])
                remaining = deadline - now
                hours = int(remaining.total_seconds() / 3600)
                days = hours // 24
                hours_rem = hours % 24

                if days > 0:
                    time_str = f"{days}天{hours_rem}小时"
                else:
                    time_str = f"{hours}小时"

                lines.append(f"{i}. 【{checkin['encounter_name']}】")
                lines.append(f"   成功成就：{checkin['success_achievement']}")
                lines.append(f"   剩余时间：{time_str}")

        return GameResult(True, "\n".join(lines))

    def claim_sideline(self, qq_id: str, line_id: int) -> GameResult:
        """支线积分领取，+30积分，仅限领取一次

        Args:
            qq_id: 玩家QQ号
            line_id: 支线编号

        Returns:
            GameResult: 操作结果
        """
        # 检查玩家是否存在
        player = self.player_dao.get_player(qq_id)
        if not player:
            return GameResult(False, "⚠️ 您还未注册，请先选择阵营！")

        # 使用成就系统记录是否已领取
        claim_key = f"支线{line_id}领取"
        achievements = self.achievement_dao.get_achievements(qq_id)
        existing = any(a.achievement_name == claim_key for a in achievements)
        if existing:
            return GameResult(False, f"❌ 您已经领取过「支线{line_id}」的积分奖励了！")

        # 发放积分
        self.player_dao.add_score(qq_id, 30)

        # 记录已领取（使用normal类型）
        self.achievement_dao.add_achievement(qq_id, 10000 + line_id, claim_key, "normal")

        # 获取更新后的积分
        player = self.player_dao.get_player(qq_id)

        return GameResult(True, f"✅ 支线{line_id}积分领取成功！获得 +30 积分\n当前积分：{player.current_score}")

    def claim_mainline(self, qq_id: str, line_id: int) -> GameResult:
        """主线积分领取，+50积分，仅限领取一次

        Args:
            qq_id: 玩家QQ号
            line_id: 主线编号

        Returns:
            GameResult: 操作结果
        """
        # 检查玩家是否存在
        player = self.player_dao.get_player(qq_id)
        if not player:
            return GameResult(False, "⚠️ 您还未注册，请先选择阵营！")

        # 使用成就系统记录是否已领取
        claim_key = f"主线{line_id}领取"
        achievements = self.achievement_dao.get_achievements(qq_id)
        existing = any(a.achievement_name == claim_key for a in achievements)
        if existing:
            return GameResult(False, f"❌ 您已经领取过「主线{line_id}」的积分奖励了！")

        # 发放积分
        self.player_dao.add_score(qq_id, 50)

        # 记录已领取（使用normal类型）
        self.achievement_dao.add_achievement(qq_id, 20000 + line_id, claim_key, "normal")

        # 获取更新后的积分
        player = self.player_dao.get_player(qq_id)

        return GameResult(True, f"✅ 主线{line_id}积分领取成功！获得 +50 积分\n当前积分：{player.current_score}")

    # ==================== 特殊效果使用 ====================

    def use_last_dice(self, qq_id: str, dice_values: List[int]) -> GameResult:
        """使用上轮骰子结果替换本轮骰子（时空镜过去效果）

        Args:
            qq_id: 玩家QQ号
            dice_values: 要使用的3个上轮骰子值
        """
        state = self.state_dao.get_state(qq_id)

        if not state.use_last_dice_available:
            return GameResult(False, "❌ 您当前没有「使用上轮骰子」的能力")

        if not state.current_round_active:
            return GameResult(False, "⚠️ 请先开始轮次")

        if not state.last_dice_result:
            return GameResult(False, "⚠️ 请先投掷骰子")

        if len(state.dice_history) < 2:
            return GameResult(False, "❌ 没有上轮骰子记录可用")

        if len(dice_values) != 3:
            return GameResult(False, "❌ 请指定3个骰子值")

        # 获取上一轮的骰子结果
        last_round_dice = state.dice_history[-2] if len(state.dice_history) >= 2 else None
        if not last_round_dice:
            return GameResult(False, "❌ 没有上轮骰子记录")

        # 验证指定的值是否在上轮骰子中
        last_dice_copy = list(last_round_dice)
        for val in dice_values:
            if val in last_dice_copy:
                last_dice_copy.remove(val)
            else:
                return GameResult(False, f"❌ 值 {val} 不在上轮骰子结果 {last_round_dice} 中")

        # 替换本轮骰子的3个值
        current_dice = list(state.last_dice_result)
        # 替换前3个骰子（或指定位置）
        for i, val in enumerate(dice_values):
            if i < len(current_dice):
                current_dice[i] = val

        # 更新状态
        state.last_dice_result = current_dice
        state.use_last_dice_available = False
        self.state_dao.update_state(state)

        return GameResult(True,
            f"✨ 成功使用上轮骰子！\n"
            f"上轮骰子: {last_round_dice}\n"
            f"替换值: {dice_values}\n"
            f"当前骰子: {current_dice}")

    def change_dice(self, qq_id: str, dice_index: int, new_value: int) -> GameResult:
        """修改一个骰子的值（红药丸/AI管家/面具Ae效果）

        Args:
            qq_id: 玩家QQ号
            dice_index: 骰子位置（1-6）
            new_value: 新值（1-6）
        """
        state = self.state_dao.get_state(qq_id)

        # 检查是否有修改骰子的能力
        if not state.change_one_dice_available and not state.next_dice_modify_any:
            return GameResult(False, "❌ 您当前没有「修改骰子」的能力")

        if not state.current_round_active:
            return GameResult(False, "⚠️ 请先开始轮次")

        if not state.last_dice_result:
            return GameResult(False, "⚠️ 请先投掷骰子")

        if dice_index < 1 or dice_index > len(state.last_dice_result):
            return GameResult(False, f"❌ 骰子位置无效，有效范围是 1-{len(state.last_dice_result)}")

        if new_value < 1 or new_value > 6:
            return GameResult(False, "❌ 骰子值必须在 1-6 之间")

        # 记录原值
        old_value = state.last_dice_result[dice_index - 1]

        # 修改骰子值
        current_dice = list(state.last_dice_result)
        current_dice[dice_index - 1] = new_value

        # 更新状态
        state.last_dice_result = current_dice
        # 清除对应的效果
        if state.change_one_dice_available:
            state.change_one_dice_available = False
        elif state.next_dice_modify_any:
            state.next_dice_modify_any = False
        self.state_dao.update_state(state)

        return GameResult(True,
            f"✨ 成功修改骰子！\n"
            f"第 {dice_index} 个骰子: {old_value} → {new_value}\n"
            f"当前骰子: {current_dice}")

    def add_3_dice(self, qq_id: str, dice_index: int) -> GameResult:
        """给一个骰子+3（面具收养人效果）

        Args:
            qq_id: 玩家QQ号
            dice_index: 骰子位置（1-6）
        """
        state = self.state_dao.get_state(qq_id)

        if not state.next_dice_add_3_any:
            return GameResult(False, "❌ 您当前没有「骰子+3」的能力")

        if not state.current_round_active:
            return GameResult(False, "⚠️ 请先开始轮次")

        if not state.last_dice_result:
            return GameResult(False, "⚠️ 请先投掷骰子")

        if dice_index < 1 or dice_index > len(state.last_dice_result):
            return GameResult(False, f"❌ 骰子位置无效，有效范围是 1-{len(state.last_dice_result)}")

        # 记录原值
        old_value = state.last_dice_result[dice_index - 1]
        new_value = old_value + 3

        # 修改骰子值
        current_dice = list(state.last_dice_result)
        current_dice[dice_index - 1] = new_value

        # 更新状态
        state.last_dice_result = current_dice
        state.next_dice_add_3_any = False
        self.state_dao.update_state(state)

        return GameResult(True,
            f"✨ 成功给骰子+3！\n"
            f"第 {dice_index} 个骰子: {old_value} → {new_value}\n"
            f"当前骰子: {current_dice}")

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
        # 使用标准化比较，不区分全角半角标点
        if not free_input and available_choices:
            matched_choice = self._match_choice(choice, available_choices)
            if matched_choice is None:
                choices_str = '\n'.join([f"• {c}" for c in available_choices])
                return GameResult(False,
                                f"❌ 无效的选择！请从以下选项中选择：\n{choices_str}")
            # 使用匹配到的原始选项
            choice = matched_choice

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

            # 如果遭遇/道具还需要继续输入，更新队列中的选项信息
            if result.requires_input:
                # 更新当前遭遇的选项
                state.pending_encounters[0]['choices'] = result.choices or []
                state.pending_encounters[0]['free_input'] = result.free_input
                self.state_dao.update_state(state)
                return GameResult(True, result.message)

            # 从队列中移除已处理的项目
            state.pending_encounters.pop(0)
            # 先保存 pending_encounters 的更新
            self.state_dao.update_state(state)

            # 应用效果（这会重新获取state并保存）
            extra_msg = ''
            if result.effects:
                extra_msg = self._apply_content_effects(qq_id, result.effects)

            # 组合消息
            final_message = result.message
            if extra_msg:
                final_message = f"{result.message}\n\n{extra_msg}"

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
                    return GameResult(True, final_message + additional_msg)

            return GameResult(True, final_message)

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

        # 验证选择是否有效（使用标准化比较，不区分全角半角标点）
        if available_choices:
            matched_choice = self._match_choice(choice, available_choices)
            if matched_choice is None:
                choices_str = '\n'.join([f"• {c}" for c in available_choices])
                return GameResult(False,
                                f"❌ 无效的选择！请从以下选项中选择：\n{choices_str}")
            # 使用匹配到的原始选项
            choice = matched_choice

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
        # 清理输入的道具名（全角转半角，去掉括号后缀，忽略大小写）
        normalized_name = normalize_punctuation(item_name)
        clean_name = re.sub(r'\s*[\[（(].*?[\]）)]\s*$', '', normalized_name).strip()
        for inv_item in inventory:
            # 清理背包中的道具名（也要全角转半角）
            inv_normalized = normalize_punctuation(inv_item.item_name)
            inv_clean_name = re.sub(r'\s*[\[（(].*?[\]）)]\s*$', '', inv_normalized).strip()
            # 忽略大小写比较
            if inv_normalized.lower() == normalized_name.lower() or inv_clean_name.lower() == clean_name.lower():
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
                # 记录上次使用的道具ID（用于火堆效果）
                if item.item_id != 13:  # 火堆自己不能刷新自己
                    state = self.state_dao.get_state(qq_id)
                    state.last_used_item_id = item.item_id
                    self.state_dao.update_state(state)

                # 应用效果
                extra_msg = ''
                if result.effects:
                    extra_msg = self._apply_content_effects(qq_id, result.effects)

                # 组合消息
                final_message = result.message
                if extra_msg:
                    final_message = f"{result.message}\n\n{extra_msg}"

                return GameResult(True, final_message, result.effects)
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

        # 检查陷阱免疫
        if cell_type == "T":
            state = self.state_dao.get_state(qq_id)
            # 检查直接免疫效果
            if state.immune_next_trap:
                state.immune_next_trap = False
                self.state_dao.update_state(state)
                messages.append(f"🛡️ 你免疫了陷阱【{content_name}】！")
                print(f"[陷阱免疫] {qq_id} 免疫了陷阱 {content_name}")
                return '\n\n'.join(messages) if messages else None

            # 检查绘制免疫效果（小女孩娃娃）
            if state.trap_immunity_draw and state.trap_immunity_count > 0:
                state.trap_immunity_count -= 1
                if state.trap_immunity_count <= 0:
                    state.trap_immunity_draw = False
                self.state_dao.update_state(state)
                remaining = f"（剩余{state.trap_immunity_count}次）" if state.trap_immunity_count > 0 else ""
                messages.append(f"🎨 通过绘制免疫了陷阱【{content_name}】！{remaining}")
                print(f"[绘制免疫] {qq_id} 绘制免疫了陷阱 {content_name}，剩余{state.trap_immunity_count}次")
                return '\n\n'.join(messages) if messages else None

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
                print(f"[触发内容] {qq_id} 效果字典: {result.effects}")
                extra_msg = self._apply_content_effects(qq_id, result.effects)
                if extra_msg:
                    messages.append(extra_msg)

            if result and result.message:
                messages.append(result.message)

            return '\n\n'.join(messages) if messages else None
        except Exception as e:
            print(f"[错误] 触发内容时出错: {e}")
            return f"触发内容时出错: {e}"

    def _apply_content_effects(self, qq_id: str, effects: dict) -> str:
        """应用遭遇/陷阱/道具的效果

        Args:
            qq_id: 玩家QQ号
            effects: 效果字典，可能包含各种效果

        Returns:
            str: 额外的消息（如登顶奖励等），可能为空
        """
        extra_messages = []
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
            print(f"[回退效果] {qq_id} 准备在列{column}回退 {retreat_count} 格")
            if column is not None:
                self._retreat_position(qq_id, column, retreat_count)
                print(f"[效果应用] {qq_id} 在列{column}回退 {retreat_count} 格")
            else:
                print(f"[回退效果] {qq_id} 列号为None，跳过回退")

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

            # 检查目标列是否有永久标记
            permanent_pos = next((p for p in self.position_dao.get_positions(qq_id, 'permanent')
                                if p.column_number == target_column), None)
            # 检查目标列是否已有临时标记
            temp_positions = self.position_dao.get_positions(qq_id, 'temp')
            has_temp = any(p.column_number == target_column for p in temp_positions)

            if permanent_pos and not has_temp:
                # 有永久标记且无临时标记：传送成功
                # 清除原列的临时标记
                self.position_dao.clear_temp_position_by_column(qq_id, source_column)
                # 放在永久标记+1位置
                self.position_dao.add_or_update_position(qq_id, target_column, permanent_pos.position + 1, 'temp')
                print(f"[效果应用] {qq_id} 传送到列{target_column}，位置{permanent_pos.position + 1}")
            else:
                # 无永久棋子或已有临时标记：本轮次作废，清除所有临时标记
                self.position_dao.clear_temp_positions(qq_id)
                if not permanent_pos:
                    print(f"[效果应用] {qq_id} 传送失败，目标列{target_column}无永久标记，本轮作废")
                else:
                    print(f"[效果应用] {qq_id} 传送失败，目标列{target_column}已有临时标记，本轮作废")

        # ==================== 骰子相关效果 ====================

        # 处理额外d6检查效果
        if effects.get('extra_d6_check_six'):
            state.extra_d6_check_six = True
            print(f"[效果应用] {qq_id} 下次投骰将额外投一个d6，如果是6则本回合作废")

        # 处理固定骰子效果（小小火球术）
        if 'next_dice_fixed' in effects:
            state.next_dice_fixed = effects['next_dice_fixed']
            print(f"[效果应用] {qq_id} 下回合骰子结果固定为 {state.next_dice_fixed}")

        # 处理骰子数量改变效果（下回合生效）
        if 'next_dice_count' in effects:
            state.next_dice_count = effects['next_dice_count']
            if 'next_dice_groups' in effects:
                state.next_dice_groups = effects['next_dice_groups']
            print(f"[效果应用] {qq_id} 下回合只投掷 {state.next_dice_count} 个骰子")

        # 处理当前回合骰子数量改变效果（LUCKY DAY - 立即生效）
        if 'current_dice_count' in effects:
            state.current_dice_count = effects['current_dice_count']
            if 'current_dice_groups' in effects:
                state.current_dice_groups = effects['current_dice_groups']
            print(f"[效果应用] {qq_id} 本回合只能投掷 {state.current_dice_count} 个骰子")

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
            # 设置免疫次数（默认1次，有契约加成时为2次）
            immunity_count = effects.get('trap_immunity_count', 1)
            state.trap_immunity_count = immunity_count
            print(f"[效果应用] {qq_id} 下{immunity_count}个陷阱可通过绘制免疫")

        # 处理需要完成绘制才能继续的效果（婚戒陷阱）
        if effects.get('requires_drawing'):
            state.requires_drawing = True
            print(f"[效果应用] {qq_id} 需要完成绘制才能继续")

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
            top_msg = self._direct_top_column(qq_id, column)
            if top_msg:
                extra_messages.append(top_msg)

        # ==================== 道具效果 ====================

        # 败者尘效果：清空当前回合，允许重投
        if effects.get('clear_round'):
            state.last_dice_result = None
            state.allow_reroll = True
            print(f"[效果应用] {qq_id} 清空本回合，允许重投")

        if effects.get('allow_reroll'):
            state.allow_reroll = True

        # 放飞小○! 效果：最远临时标记前进
        if 'move_farthest_temp' in effects:
            move_count = effects['move_farthest_temp']
            self._move_farthest_temp(qq_id, move_count)

        # 沉重的巨剑效果：出1可重投
        if effects.get('reroll_on_one'):
            state.reroll_on_one = True
            print(f"[效果应用] {qq_id} 下次投骰出1可重投")

        # 女巫魔法伎俩效果：出6可重投
        if effects.get('reroll_on_six'):
            state.reroll_on_six = True
            print(f"[效果应用] {qq_id} 下次投骰出6可重投")

        # 变大蘑菇效果：所有骰子+1
        if 'all_dice_plus' in effects:
            state.all_dice_modifier = effects['all_dice_plus']
            print(f"[效果应用] {qq_id} 下次投骰所有结果+{state.all_dice_modifier}")

        # 缩小药水效果：所有骰子-1
        if 'all_dice_minus' in effects:
            state.all_dice_modifier = -effects['all_dice_minus']
            print(f"[效果应用] {qq_id} 下次投骰所有结果{state.all_dice_modifier}")

        # 超级大炮效果：固定出目
        if 'forced_rolls' in effects:
            state.forced_rolls = effects['forced_rolls']
            print(f"[效果应用] {qq_id} 下次投骰固定出目: {state.forced_rolls}")

        # 闹Ae魔镜效果：部分固定出目
        if 'partial_forced_rolls' in effects:
            state.partial_forced_rolls = effects['partial_forced_rolls']
            print(f"[效果应用] {qq_id} 下次投骰部分固定: {state.partial_forced_rolls}")

        # :) 效果：临时转永久并继续轮次
        if effects.get('temp_to_permanent'):
            self.position_dao.convert_temp_to_permanent(qq_id)
            print(f"[效果应用] {qq_id} 临时标记转换为永久标记")

        if effects.get('continue_round'):
            # 保持轮次继续，不结束
            print(f"[效果应用] {qq_id} 可继续当前轮次")

        # 阈限空间效果：失败可重试
        if effects.get('allow_retry_on_fail'):
            state.allow_retry_on_fail = True
            print(f"[效果应用] {qq_id} 失败时可重试一次")

        # 购物卡效果：下次购买半价
        if effects.get('next_purchase_half'):
            state.next_purchase_half = True
            print(f"[效果应用] {qq_id} 下次购买半价")

        # 黑喵效果：永久减少回合消耗
        if 'permanent_cost_reduction' in effects:
            state.cost_reduction += effects['permanent_cost_reduction']
            print(f"[效果应用] {qq_id} 永久回合消耗减少{effects['permanent_cost_reduction']}，当前总减少: {state.cost_reduction}")

        # ==================== 玫瑰道具效果 ====================

        # 红玫瑰效果：失败可重试（类似阈限空间但有积分消耗）
        if effects.get('red_rose_active'):
            state.has_red_rose = True
            print(f"[效果应用] {qq_id} 激活红玫瑰效果")

        # 蓝玫瑰效果：给自己
        if effects.get('blue_rose_self'):
            state.has_red_rose = True  # 蓝玫瑰对自己使用时效果同红玫瑰
            print(f"[效果应用] {qq_id} 蓝玫瑰效果（对自己）")

        # 蓝玫瑰效果：给契约对象
        if 'blue_rose_target' in effects:
            target_qq = effects['blue_rose_target']
            from_qq = effects.get('blue_rose_from', qq_id)
            target_state = self.state_dao.get_state(target_qq)
            target_state.has_blue_rose_from = from_qq
            self.state_dao.update_state(target_state)
            print(f"[效果应用] {target_qq} 收到来自 {from_qq} 的蓝玫瑰保护")

        # 黄玫瑰效果：标记目标玩家
        if 'yellow_rose_target' in effects:
            target_qq = effects['yellow_rose_target']
            target_state = self.state_dao.get_state(target_qq)
            target_state.force_reroll_next_move = True
            self.state_dao.update_state(target_state)
            print(f"[效果应用] {target_qq} 被黄玫瑰标记，下次移动必须重投")

        # 五彩宝石效果：随机一半玩家扣积分
        if 'random_half_minus' in effects:
            self._apply_random_half_minus(qq_id, effects['random_half_minus'])

        # 灵魂之叶效果：永久棋子前进
        if 'move_permanent' in effects:
            column, move_count = effects['move_permanent']
            self._move_permanent_marker(qq_id, column, move_count)

        # 火堆效果：刷新上次使用的道具
        if effects.get('refresh_last_item'):
            self._refresh_last_item(qq_id)

        # ==================== 遭遇效果 ====================

        # 临时标记前进效果（你真好！/蟑螂骑乘等）
        if 'move_temp_forward' in effects:
            move_count = effects['move_temp_forward']
            column = effects.get('column')
            if column:
                self._move_temp_forward(qq_id, column, move_count)
                print(f"[效果应用] {qq_id} 在列{column}临时标记前进{move_count}格")
            else:
                # 没有指定列时，移动所有临时标记
                temp_positions = self.position_dao.get_positions(qq_id, 'temp')
                for pos in temp_positions:
                    self._move_temp_forward(qq_id, pos.column_number, move_count)
                if temp_positions:
                    cols = [str(p.column_number) for p in temp_positions]
                    print(f"[效果应用] {qq_id} 在列{','.join(cols)}的临时标记各前进{move_count}格")

        # 临时标记回退效果
        if 'temp_retreat' in effects:
            retreat_count = effects['temp_retreat']
            column = effects.get('column')
            if column:
                self._retreat_position(qq_id, column, retreat_count)
                print(f"[效果应用] {qq_id} 在列{column}临时标记回退{retreat_count}格")
            else:
                # 没有指定列时，移动所有临时标记
                temp_positions = self.position_dao.get_positions(qq_id, 'temp')
                for pos in temp_positions:
                    self._retreat_position(qq_id, pos.column_number, retreat_count)
                if temp_positions:
                    cols = [str(p.column_number) for p in temp_positions]
                    print(f"[效果应用] {qq_id} 在列{','.join(cols)}的临时标记各回退{retreat_count}格")

        # 免疫下一个陷阱效果
        if effects.get('immune_next_trap'):
            state.immune_next_trap = True
            print(f"[效果应用] {qq_id} 免疫下一个陷阱")

        # 强制结束回合效果
        if effects.get('force_end_turn'):
            state.current_round_active = False
            # 把临时标记转换为永久标记
            temp_positions = self.position_dao.get_positions(qq_id, 'temp')
            for temp_pos in temp_positions:
                self.position_dao.set_position(qq_id, temp_pos.column_number, temp_pos.position, 'permanent')
            self.position_dao.clear_temp_positions(qq_id)
            state.temp_markers_used = 0
            print(f"[效果应用] {qq_id} 被强制结束回合（临时标记已转为永久）")

        # 冥府里拉琴效果：移动自己的临时标记
        if 'move_temp' in effects:
            column, move_count = effects['move_temp']
            self._move_temp_forward(qq_id, column, move_count)
            print(f"[效果应用] {qq_id} 在列{column}临时标记移动{move_count}格")

        # 冥府里拉琴效果：移动契约对象的临时标记
        if 'move_partner_temp' in effects:
            partner_qq = effects.get('contract_partner')  # content_handler返回的键名是contract_partner
            if partner_qq:
                column, move_count = effects['move_partner_temp']
                self._move_temp_forward(partner_qq, column, move_count)
                print(f"[效果应用] {qq_id} 的契约对象 {partner_qq} 在列{column}临时标记移动{move_count}格")

        # 免费回合效果
        if 'free_round' in effects:
            state.free_rounds += effects['free_round']
            print(f"[效果应用] {qq_id} 获得{effects['free_round']}个免费回合，当前总数: {state.free_rounds}")

        # 回合作废效果
        if effects.get('invalidate_round'):
            # 清空当前骰子结果，但不结束回合
            state.last_dice_result = None
            print(f"[效果应用] {qq_id} 本回合作废，需重新投骰")

        # 使用上轮骰子效果
        if effects.get('use_last_round_dice'):
            state.use_last_dice_available = True
            print(f"[效果应用] {qq_id} 可使用上轮骰子结果")

        # 重投指定3个骰子效果
        if effects.get('reroll_selected_three'):
            # 需要玩家指定3个要重投的骰子
            state.allow_reroll = True
            print(f"[效果应用] {qq_id} 可选择重投3个骰子")

        # 更改一个骰子点数效果
        if effects.get('change_one_dice'):
            state.change_one_dice_available = True
            print(f"[效果应用] {qq_id} 可更改一个骰子点数")

        # 下次投骰双倍消耗效果
        if effects.get('next_roll_double_cost'):
            state.next_roll_double_cost = True
            print(f"[效果应用] {qq_id} 下次投骰消耗积分翻倍")

        # 冻结当前列效果
        if effects.get('freeze_current_column'):
            column = effects.get('column')
            if column and column not in state.frozen_columns:
                state.frozen_columns.append(column)
                print(f"[效果应用] {qq_id} 列{column}被冻结")

        # 禁用本轮列效果（紧闭的大门）
        if 'disable_column_this_round' in effects:
            column = effects['disable_column_this_round']
            if column not in state.disabled_columns_this_round:
                state.disabled_columns_this_round.append(column)
                print(f"[效果应用] {qq_id} 列{column}本轮次被禁用")

        # 必须双倍打卡效果（葡萄蔷薇紫苑）
        if effects.get('must_draw_double'):
            state.must_draw_double = True
            print(f"[效果应用] {qq_id} 下次打卡需双倍绘制")

        # 强制暂停直到打卡效果（葡萄蔷薇紫苑）
        if effects.get('force_end_until_draw'):
            state.force_end_until_draw = True
            state.current_round_active = False
            self.position_dao.clear_temp_positions(qq_id)
            state.temp_markers_used = 0
            print(f"[效果应用] {qq_id} 强制暂停直到完成打卡")

        # 任意修改骰子效果（面具 Ae阵营）
        if effects.get('next_dice_modify_any'):
            state.next_dice_modify_any = True
            print(f"[效果应用] {qq_id} 下回合可任意修改一个骰子")

        # 任意骰子+3效果（面具 收养人阵营）
        if effects.get('next_dice_add_3_any'):
            state.next_dice_add_3_any = True
            print(f"[效果应用] {qq_id} 下回合可任意骰子+3")

        # 特殊触发效果（财神福利等）
        if 'bonus_trigger' in effects:
            state.pending_bonus_trigger = effects['bonus_trigger']
            print(f"[效果应用] {qq_id} 可触发特殊奖励: {state.pending_bonus_trigger}")

        # 保存状态
        self.state_dao.update_state(state)

        # 返回额外消息
        return '\n\n'.join(extra_messages) if extra_messages else ''

    def _direct_top_column(self, qq_id: str, column: int) -> str:
        """直接登顶指定列（The Room徽章效果）

        Args:
            qq_id: 玩家QQ号
            column: 要登顶的列号

        Returns:
            str: 额外的消息（首达、禁止、胜利等）
        """
        import logging
        from datetime import datetime, timedelta
        from data.board_config import COLUMN_HEIGHTS

        extra_messages = []

        # 获取列高度
        column_height = COLUMN_HEIGHTS.get(column)
        if not column_height:
            logging.error(f"[直接登顶] 无效的列号: {column}")
            return ""

        # 直接在该列顶部放置永久标记
        self.position_dao.add_or_update_position(qq_id, column, column_height, 'permanent')

        # 将该列添加到topped_columns
        state = self.state_dao.get_state(qq_id)
        if column not in state.topped_columns:
            state.topped_columns.append(column)
        self.state_dao.update_state(state)

        # 清空该列所有玩家的临时标记
        self.position_dao.clear_all_temp_positions_by_column(column)

        # 给予基础登顶奖励（10积分）
        base_reward = 10
        self.player_dao.add_score(qq_id, base_reward)
        extra_messages.append(f"✦登顶奖励：积分+{base_reward}")

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
            self.achievement_dao.add_achievement(qq_id, column, "鹤立oas群", "first_clear")

            extra_messages.append(
                f"\n🍗 大吉大利，今晚吃鸡\n"
                f"✦列全体首达奖励\n"
                f"获得成就：鹤立oas群\n"
                f"获得奖励：积分+{first_reward}\n"
                f"获得现实奖励：纪念币一枚（私信官号领取，不包邮）"
            )

            # 首达后禁止新轮次12小时
            state = self.state_dao.get_state(qq_id)
            lockout_time = datetime.now() + timedelta(hours=12)
            state.lockout_until = lockout_time.isoformat()
            self.state_dao.update_state(state)

            extra_messages.append(f"\n⏰ 由于全图首次登顶，您将被禁止开启新轮次 12 小时\n解锁时间：{lockout_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 检查是否获胜（3列登顶）
        state = self.state_dao.get_state(qq_id)
        if len(state.topped_columns) >= 3:
            win_result = self._handle_game_win(qq_id)
            extra_messages.append(f"\n{win_result.message}")

        logging.info(f"[直接登顶] {qq_id} 使用The Room徽章直接登顶列{column}")

        return "\n".join(extra_messages)

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
        print(f"[回退开始] {qq_id} 列{column} 回退{retreat_count}格")
        temp_positions = self.position_dao.get_positions(qq_id, 'temp')
        print(f"[回退] 当前临时位置: {[(p.column_number, p.position) for p in temp_positions]}")
        temp_pos = next((p for p in temp_positions if p.column_number == column), None)

        if not temp_pos:
            print(f"[回退] 未找到列{column}的临时标记，跳过")
            return

        print(f"[回退] 当前位置: 列{column}第{temp_pos.position}格")
        # 计算新位置
        new_position = temp_pos.position - retreat_count
        print(f"[回退] 计算新位置: {temp_pos.position} - {retreat_count} = {new_position}")

        # 检查是否有永久标记
        permanent_positions = self.position_dao.get_positions(qq_id, 'permanent')
        permanent_pos = next((p for p in permanent_positions if p.column_number == column), None)

        if permanent_pos:
            print(f"[回退] 该列有永久标记在第{permanent_pos.position}格")
            # 如果回退后的位置<=永久标记位置，则临时标记应该在永久标记+1的位置
            if new_position <= permanent_pos.position:
                new_position = permanent_pos.position + 1
                print(f"[回退] 回退位置低于永久标记，调整为第{new_position}格")
                self.position_dao.add_or_update_position(qq_id, column, new_position, 'temp')
                # 验证数据库更新
                verify_pos = self.position_dao.get_positions(qq_id, 'temp')
                verify_current = next((p for p in verify_pos if p.column_number == column), None)
                print(f"[回退验证-永久标记] {qq_id} 列{column} 数据库当前值: {verify_current.position if verify_current else 'None'}")
                return

        # 如果回退后位置<=0，移除临时标记
        if new_position <= 0:
            self.position_dao.clear_temp_position_by_column(qq_id, column)
            print(f"[回退] {qq_id} 在列{column}的临时标记被移除（回退到起点以下）")
        else:
            self.position_dao.add_or_update_position(qq_id, column, new_position, 'temp')
            print(f"[回退完成] {qq_id} 在列{column}回退到第{new_position}格")
            # 验证数据库更新
            verify_pos = self.position_dao.get_positions(qq_id, 'temp')
            verify_current = next((p for p in verify_pos if p.column_number == column), None)
            print(f"[回退验证] {qq_id} 列{column} 数据库当前值: {verify_current.position if verify_current else 'None'}")

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
                    new_pos = pos.position - 1
                    if new_pos <= 0:
                        # 位置<=0时移除永久标记
                        cursor = self.db_conn.cursor()
                        cursor.execute(
                            "DELETE FROM player_positions WHERE qq_id = ? AND column_number = ? AND marker_type = 'permanent'",
                            (player.qq_id, column)
                        )
                        self.db_conn.commit()
                        affected_players.append(f"{player.nickname}(永久-移除)")
                        logging.info(f"[揍击派对] {player.nickname} 的永久标记在 ({column},{position}) 被移除")
                    else:
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
            self.achievement_dao.add_achievement(qq_id, column, "鹤立oas群", "first_clear")

            message += (
                f"\n\n🍗 大吉大利，今晚吃鸡\n"
                f"肥美的烤鸡扑扇着翅膀飞到了你面前的盘子里，诱人的香气让你迫不及待地切开金黄外皮…不对，等一下？！\n\n"
                f"✦列全体首达奖励\n"
                f"获得成就：鹤立oas群\n"
                f"获得奖励：积分+{first_reward}\n"
                f"获得现实奖励：纪念币一枚（私信官号领取，不包邮）"
            )

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
        cursor = self.conn.cursor()

        # 检查该玩家是否已经有排名（一个用户不能同时占有多个排名）
        cursor.execute('SELECT rank FROM game_rankings WHERE qq_id = ?', (qq_id,))
        existing_rank = cursor.fetchone()
        if existing_rank:
            # 玩家已经有排名，不重复计入
            return GameResult(True,
                            f"掌声通过隐藏音响传来，全息投影跳出\"恭喜通关\"的电子贺卡……\n\n"
                            f"🎉 再次通关！您已是第{existing_rank['rank']}个通关的玩家，继续保持！")

        # 计算新排名
        cursor.execute('SELECT COUNT(*) as count FROM game_rankings')
        row = cursor.fetchone()
        rank = row['count'] + 1

        extra_messages = []

        # 检查契约金婚成就
        from database.dao import ContractDAO
        contract_dao = ContractDAO(self.conn)
        partner_qq = contract_dao.get_contract_partner(qq_id)

        if partner_qq:
            # 检查契约对象是否也通关了
            cursor.execute('SELECT COUNT(*) as count FROM game_rankings WHERE qq_id = ?', (partner_qq,))
            partner_finished = cursor.fetchone()['count'] > 0

            if partner_finished:
                # 双方都通关，发放"产品金婚"成就
                self.achievement_dao.add_achievement(qq_id, 9901, "产品金婚", "hidden")
                self.achievement_dao.add_achievement(partner_qq, 9901, "产品金婚", "hidden")
                partner = self.player_dao.get_player(partner_qq)
                partner_name = partner.nickname if partner else partner_qq
                extra_messages.append(f"💍 您与契约对象 {partner_name} 共同通关！获得隐藏成就：产品金婚")

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

            # 根据排名生成不同的通关文案
            if rank == 1:
                result_msg = (
                    "掌声通过隐藏音响传来，全息投影跳出\"恭喜通关\"的电子贺卡……\n\n"
                    "★✦恭喜您第一通关游戏✦★\n"
                    f"获得成就：{rank_names[rank]}\n"
                    f"获得奖励：积分+{reward}\n"
                    "获得现实奖励：丑喵团子一只 纪念币一枚（私信官号领取，不包邮）"
                )
            elif rank == 2:
                result_msg = (
                    "掌声通过隐藏音响传来，全息投影跳出\"恭喜通关\"的电子贺卡……\n\n"
                    "★✦恭喜您第二通关游戏✦★\n"
                    f"获得成就：{rank_names[rank]}\n"
                    f"获得奖励：积分+{reward}\n"
                    "获得现实奖励：丑喵团子一只 纪念币一枚（私信官号领取，不包邮）"
                )
            elif rank == 3:
                result_msg = (
                    "掌声通过隐藏音响传来，全息投影跳出\"恭喜通关\"的电子贺卡……\n\n"
                    "★✦恭喜您第三通关游戏✦★\n"
                    f"获得成就：{rank_names[rank]}\n"
                    f"获得奖励：积分+{reward}\n"
                    "获得现实奖励：丑喵团子一只 纪念币一枚（私信官号领取，不包邮）"
                )
            else:  # rank == 4
                result_msg = (
                    "掌声通过隐藏音响传来，全息投影跳出\"恭喜通关\"的电子贺卡……\n\n"
                    "★✦恭喜您第四通关游戏✦★\n"
                    f"获得成就：{rank_names[rank]}\n"
                    "获得奖励：没有捏～～～"
                )

            if extra_messages:
                result_msg += "\n\n" + "\n".join(extra_messages)
            return GameResult(True, result_msg)

        # 第5名及之后
        result_msg = (
            "掌声通过隐藏音响传来，全息投影跳出\"恭喜通关\"的电子贺卡……\n\n"
            f"★✦恭喜您第{rank}个通关游戏✦★\n"
            "虽然没有排名奖励，但您成功通关了游戏！"
        )
        if extra_messages:
            result_msg += "\n\n" + "\n".join(extra_messages)
        return GameResult(True, result_msg)

    def _move_temp_forward(self, qq_id: str, column: int, move_count: int):
        """移动指定列的临时标记前进

        Args:
            qq_id: 玩家QQ号
            column: 列号
            move_count: 移动格数（正数前进，负数后退）
        """
        from data.board_config import COLUMN_HEIGHTS
        import logging

        temp_positions = self.position_dao.get_positions(qq_id, 'temp')
        target_pos = next((p for p in temp_positions if p.column_number == column), None)

        if not target_pos:
            logging.info(f"[移动临时标记] {qq_id} 列{column}没有临时标记")
            return

        column_height = COLUMN_HEIGHTS.get(column, 10)
        new_position = target_pos.position + move_count

        # 确保位置在有效范围内
        new_position = max(1, min(new_position, column_height))

        self.position_dao.add_or_update_position(qq_id, column, new_position, 'temp')
        logging.info(f"[移动临时标记] {qq_id} 列{column}从{target_pos.position}移动到{new_position}")

    def _move_farthest_temp(self, qq_id: str, move_count: int):
        """移动离终点最远的临时标记

        Args:
            qq_id: 玩家QQ号
            move_count: 移动格数
        """
        from data.board_config import COLUMN_HEIGHTS
        import logging

        temp_positions = self.position_dao.get_positions(qq_id, 'temp')
        if not temp_positions:
            logging.info(f"[放飞小○!] {qq_id} 没有临时标记")
            return

        # 计算每个临时标记离终点的距离
        farthest_pos = None
        max_distance = -1

        for pos in temp_positions:
            column_height = COLUMN_HEIGHTS.get(pos.column_number, 10)
            distance = column_height - pos.position
            if distance > max_distance:
                max_distance = distance
                farthest_pos = pos

        if farthest_pos:
            column_height = COLUMN_HEIGHTS.get(farthest_pos.column_number, 10)
            new_position = min(farthest_pos.position + move_count, column_height)
            self.position_dao.add_or_update_position(qq_id, farthest_pos.column_number, new_position, 'temp')
            logging.info(f"[放飞小○!] {qq_id} 列{farthest_pos.column_number}从{farthest_pos.position}前进到{new_position}")

    def _apply_random_half_minus(self, user_qq: str, minus_amount: int):
        """随机一半玩家扣积分（五彩宝石效果）

        Args:
            user_qq: 使用道具的玩家QQ号
            minus_amount: 扣除的积分数
        """
        import random
        import logging

        all_players = self.player_dao.get_all_players()
        if not all_players:
            return

        # 随机选择一半玩家
        half_count = max(1, len(all_players) // 2)
        selected_players = random.sample(all_players, half_count)

        for player in selected_players:
            self.player_dao.add_score(player.qq_id, -minus_amount)
            logging.info(f"[五彩宝石] {player.nickname} 积分-{minus_amount}")

    def _move_permanent_marker(self, qq_id: str, column: int, move_count: int):
        """移动永久棋子（灵魂之叶效果）

        Args:
            qq_id: 玩家QQ号
            column: 列号
            move_count: 移动格数
        """
        from data.board_config import COLUMN_HEIGHTS
        import logging

        perm_positions = self.position_dao.get_positions(qq_id, 'permanent')
        perm_pos = next((p for p in perm_positions if p.column_number == column), None)

        if not perm_pos:
            logging.info(f"[灵魂之叶] {qq_id} 在列{column}没有永久棋子")
            return

        column_height = COLUMN_HEIGHTS.get(column, 10)
        new_position = min(perm_pos.position + move_count, column_height)
        self.position_dao.add_or_update_position(qq_id, column, new_position, 'permanent')
        logging.info(f"[灵魂之叶] {qq_id} 列{column}永久棋子从{perm_pos.position}前进到{new_position}")

    def _refresh_last_item(self, qq_id: str):
        """刷新上次使用的道具（火堆效果）

        Args:
            qq_id: 玩家QQ号
        """
        import logging

        state = self.state_dao.get_state(qq_id)

        if not state.last_used_item_id:
            logging.info(f"[火堆] {qq_id} 没有上次使用的道具可刷新")
            return

        last_item_id = state.last_used_item_id

        # 获取道具信息
        shop_item = self.shop_dao.get_item(last_item_id)
        if not shop_item:
            logging.warning(f"[火堆] 道具{last_item_id}不存在")
            return

        # 将道具返还给玩家
        self.inventory_dao.add_item(qq_id, shop_item.item_id, shop_item.item_name, shop_item.item_type or 'item')

        # 清除上次使用的道具记录
        state.last_used_item_id = None
        self.state_dao.update_state(state)

        logging.info(f"[火堆] {qq_id} 刷新了道具「{shop_item.item_name}」")
