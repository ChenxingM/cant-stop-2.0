# -*- coding: utf-8 -*-
"""
地图内容处理器
Content Handler for Map Cells (Encounters, Items, Traps)
"""

import random
from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.dao import (
    PlayerDAO, InventoryDAO, AchievementDAO, PositionDAO, ShopDAO
)
from database.models import Player


@dataclass
class ContentResult:
    """内容触发结果"""
    success: bool
    message: str
    effects: Dict = None  # 效果字典
    requires_input: bool = False  # 是否需要玩家输入选择
    choices: List[str] = None  # 可选项列表


class ContentHandler:
    """地图内容处理器"""

    def __init__(self, player_dao, inventory_dao, achievement_dao, position_dao, shop_dao, conn):
        self.player_dao = player_dao
        self.inventory_dao = inventory_dao
        self.achievement_dao = achievement_dao
        self.position_dao = position_dao
        self.shop_dao = shop_dao
        self.conn = conn

    # ==================== 内容触发主入口 ====================

    def trigger_content(self, qq_id: str, column: int, position: int,
                       cell_type: str, content_id: int, content_name: str) -> ContentResult:
        """
        触发地图格子内容

        Args:
            qq_id: 玩家QQ号
            column: 列号
            position: 位置
            cell_type: 内容类型 (E/I/T)
            content_id: 内容ID
            content_name: 内容名称

        Returns:
            ContentResult对象
        """
        # 映射内容类型
        type_map = {'E': 'encounter', 'I': 'item', 'T': 'trap'}
        full_type = type_map.get(cell_type, 'encounter')

        # 检查是否首次触发
        is_first = self._check_first_trigger(column, position, qq_id, full_type, content_id)

        if cell_type == "E":
            return self._handle_encounter(qq_id, content_id, content_name, is_first)
        elif cell_type == "I":
            return self._handle_item(qq_id, content_id, content_name, is_first)
        elif cell_type == "T":
            return self._handle_trap(qq_id, content_id, content_name, is_first, column, position)

        return ContentResult(False, "未知的内容类型")

    def _check_first_trigger(self, column: int, position: int, qq_id: str,
                            content_type: str, content_id: int) -> bool:
        """检查是否首次触发"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT first_trigger_qq FROM content_triggers
            WHERE column_number = ? AND position = ?
        ''', (column, position))

        row = cursor.fetchone()

        if not row:
            # 首次触发，记录
            cursor.execute('''
                INSERT INTO content_triggers
                (column_number, position, content_type, content_id, first_trigger_qq, trigger_count)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (column, position, content_type, content_id, qq_id))
            self.conn.commit()
            return True
        else:
            # 增加触发计数
            cursor.execute('''
                UPDATE content_triggers
                SET trigger_count = trigger_count + 1
                WHERE column_number = ? AND position = ?
            ''', (column, position))
            self.conn.commit()
            return False

    # ==================== 道具处理 ====================

    def _handle_item(self, qq_id: str, item_id: int, item_name: str, is_first: bool) -> ContentResult:
        """处理道具获取"""
        if is_first:
            # 检查阵营限制
            player = self.player_dao.get_player(qq_id)
            shop_item = self.shop_dao.get_item(item_id)

            # 检查玩家阵营是否符合道具限制
            if shop_item and shop_item.faction_limit and shop_item.faction_limit != '通用':
                if not player.faction:
                    # 玩家没有阵营，无法获得限制道具
                    return ContentResult(True, f"❌ 发现道具：{item_name}\n该道具仅限{shop_item.faction_limit}阵营使用，您无法获得")
                elif player.faction != shop_item.faction_limit:
                    # 玩家阵营不匹配
                    return ContentResult(True, f"❌ 发现道具：{item_name}\n该道具仅限{shop_item.faction_limit}阵营使用，您的阵营是{player.faction}，无法获得")

            # 首次获得道具
            self.inventory_dao.add_item(qq_id, item_id, item_name, 'item')

            # 解锁道具到商店
            self.shop_dao.unlock_item(item_id)

            message = f"🎁 获得道具：{item_name}\n该道具已解锁到商店，其他玩家可购买"

            # 记录隐藏成就计数
            self._increment_achievement_counter(qq_id, 'items_collected')

            return ContentResult(True, message)
        else:
            # 非首次，获得积分
            self.player_dao.add_score(qq_id, 10)
            return ContentResult(True, f"道具已被拾取，获得积分奖励：+10")

    # ==================== 陷阱处理 ====================

    def _handle_trap(self, qq_id: str, trap_id: int, trap_name: str, is_first: bool, column: int = None, position: int = None) -> ContentResult:
        """处理陷阱触发"""
        player = self.player_dao.get_player(qq_id)

        if is_first:
            # 首次触发，执行特殊惩罚
            message, effects = self._execute_trap_effect(qq_id, trap_id, trap_name, player, column, position)

            # 记录成就计数
            self._increment_achievement_counter(qq_id, 'traps_triggered')

            # 添加成就
            self.achievement_dao.add_achievement(qq_id, trap_id, trap_name, 'normal')

            return ContentResult(True, f"⚠️ 触发陷阱：{trap_name}\n{message}", effects)
        else:
            # 非首次，固定扣10积分
            self.player_dao.add_score(qq_id, -10)
            return ContentResult(True, f"⚠️ 触发陷阱：{trap_name}\n积分-10")

    def _execute_trap_effect(self, qq_id: str, trap_id: int, trap_name: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """执行陷阱效果"""
        effects = {}

        # 陷阱效果映射
        trap_effects = {
            1: self._trap_fireball,        # 小小火球术
            2: self._trap_dont_look_back,  # 不要回头
            3: self._trap_wedding_ring,    # 婚戒
            4: self._trap_white_hook,      # 白色天○钩
            5: self._trap_closed_door,     # 紧闭的大门
            6: self._trap_odd_even,        # 奇变偶不变
            7: self._trap_thunder_king,    # 雷电法王
            8: self._trap_duel,           # 中门对狙
            9: self._trap_portal,         # 传送门
            10: self._trap_thorns,        # 扎扎实实
            11: self._trap_hesitate,      # 犹豫就会败北
            12: self._trap_octopus,       # 七色章鱼
            13: self._trap_hollow,        # 中空格子
            14: self._trap_oas_akaria,    # OAS阿卡利亚
            15: self._trap_witch_house,   # 魔女的小屋
            16: self._trap_witch_disturb, # 你惊扰了witch
            17: self._trap_tick_tock,     # 滴答滴答
            18: self._trap_no_entry,      # 非请勿入
            19: self._trap_no_air_force,  # 没有空军
            20: self._trap_lucky_day,     # LUCKY DAY
        }

        handler = trap_effects.get(trap_id)
        if handler:
            return handler(qq_id, player, column, position)

        return "陷阱效果未实现", effects

    # ==================== 具体陷阱效果 ====================

    def _trap_fireball(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱1: 小小火球术"""
        # 停止一回合，下回合固定出目
        return "停止一回合，下回合出目将固定为(4,5,5,5,6,6)\n*在完成此惩罚前不得主动结束当前轮次", {
            'skip_rounds': 1,
            'next_dice_fixed': [4, 5, 5, 5, 6, 6]
        }

    def _trap_dont_look_back(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱2: "不要回头" """
        # 清空当前列进度
        return "你看到了它的脸...一切都已经晚了\n当前列进度已清空，回到上一个永久棋子位置", {
            'clear_current_column': True,
            'column': column  # 包含列信息以便game_engine处理
        }

    def _trap_wedding_ring(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱3: 婚戒...？"""
        # 检查是否有契约
        # TODO: 实现契约系统后完善
        if not player.faction:
            return "强制暂停该轮次，请完成陷阱相关绘制", {
                'force_end_round': True,
                'requires_drawing': True
            }
        else:
            return "契约的力量守护了你\n你与你的契约者均可获得一次免费回合", {
                'free_round': True
            }

    def _trap_white_hook(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱4: 白色天○钩"""
        return "巨大的钩子将你拉起并向后移动\n当前列进度回退两格", {
            'retreat': 2,
            'column': column
        }

    def _trap_closed_door(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱5: 紧闭的大门"""
        return "门不能从这一侧打开\n请移动到相邻列", {
            'move_to_adjacent': True
        }

    def _trap_odd_even(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱6: 奇变偶不变"""
        return "奇变偶不变的神秘力量...\n下回合投掷结果将触发特殊检定", {
            'odd_even_check': True
        }

    def _trap_thunder_king(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱7: 雷电法王"""
        return "强劲的电流从脚底直达头顶\n下回合需要通过数学检定", {
            'math_check': True
        }

    def _trap_duel(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱8: 中门对狙"""
        return "有东西挡住了你的去路！\n请选择一位玩家对决(.r1d6比大小)", {
            'requires_duel': True
        }

    def _trap_portal(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱9: 传送门"""
        target_column = random.randint(3, 18)
        return f"你被传送到了随机列...\n传送目标：第{target_column}列", {
            'teleport_to': target_column,
            'column': column
        }

    def _trap_thorns(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱10: 刺儿扎扎"""
        dice_roll = random.randint(1, 20)
        if dice_roll > 18:
            self.inventory_dao.add_item(qq_id, 9999, "新鲜三文鱼", "hidden_item")
            return "灵巧地规避掉了，获得新鲜三文鱼一条！", {}
        else:
            self.player_dao.add_score(qq_id, -20)
            return "被扎到了，积分-20", {}

    def _trap_hesitate(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱11: 犹豫就会败北"""
        return "你的骰子自己丢了出去...\n强制再进行两回合后才能结束该轮次", {
            'force_rounds': 2
        }

    def _trap_octopus(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱12: 七色章鱼"""
        return "七色章鱼把你丢了出去\n所有列的当前进度回退一格", {
            'retreat_all': 1
        }

    def _trap_hollow(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱13: 中空格子"""
        return "一脚踩空快速下落...\n暂停2回合", {
            'skip_rounds': 2
        }

    def _trap_oas_akaria(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱14: OAS阿卡利亚"""
        loss = max(1, player.current_score // 4)
        self.player_dao.add_score(qq_id, -loss)
        return f"你的道心破碎了...\n积分减少1/4 (-{loss})", {}

    def _trap_witch_house(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱15: 魔女的小屋

        注意：这个陷阱需要玩家选择，应该作为遭遇处理，而不是普通陷阱
        """
        return "你能来帮帮忙吗？\n请选择：帮忙 或 离开", {
            'requires_choice': True,
            'choices': ['帮忙', '离开'],
            'column': column
        }

    def _trap_witch_disturb(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱16: 你惊扰了witch"""
        # ae阵营自动成功
        if player.faction == "Aeonreth":
            return "你迅速做出了反击，击退了那怪物，但你仍然受了些伤，看来需要休息一下了\n强制结束本轮次（ae自动成功）", {
                'force_end_round': True
            }

        # 其他玩家投骰检定
        dice_roll = random.randint(1, 20)
        if dice_roll >= 10:
            return f"门后的漆黑的房间，长着利爪的女性模样的怪物朝着你扑来！\n投掷d20={dice_roll}≥10：你迅速做出了反击，击退了那怪物，但你仍然受了些伤，看来需要休息一下了\n强制结束本轮次", {
                'force_end_round': True
            }
        else:
            self.player_dao.add_score(qq_id, -20)
            return f"门后的漆黑的房间，长着利爪的女性模样的怪物朝着你扑来！\n投掷d20={dice_roll}<10：你被攻击后陷入了昏迷...当你再次清醒过来时，发现身上的糖果都不见了...\n积分-20", {}

    def _trap_tick_tock(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱17: 滴答滴答"""
        # 随机失去一样道具
        inventory = self.inventory_dao.get_inventory(qq_id)
        regular_items = [item for item in inventory if item.item_type == 'item']

        if regular_items:
            lost_item = random.choice(regular_items)
            self.inventory_dao.remove_item(qq_id, lost_item.item_id, 'item')
            return f"你的时间我就收下了\n失去道具：{lost_item.item_name}", {}
        else:
            self.player_dao.add_score(qq_id, -100)
            return "你的时间我就收下了\n未持有道具，扣除100积分", {}

    def _trap_no_entry(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱18: 非请勿入"""
        return "小屋活过来了，你被困住了\n5d4+4个小时不能进行打卡和游玩", {
            'lockout_hours': random.randint(5, 24) + 4
        }

    def _trap_no_air_force(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱19: 没有空军"""
        self.player_dao.add_score(qq_id, -20)
        # 随机回退一个临时棋子
        return "漆黑的影子...你陷入不定性疯狂\n失去控制两回合，积分-20，随机回退一格临时棋子", {
            'skip_rounds': 2,
            'random_retreat': 1
        }

    def _trap_lucky_day(self, qq_id: str, player: Player, column: int = None, position: int = None) -> Tuple[str, Dict]:
        """陷阱20: LUCKY DAY！"""
        return "赌命的时候到了...\n下回合只投掷四个骰子，两两分组", {
            'next_dice_count': 4,
            'next_dice_groups': [2, 2]
        }

    # ==================== 遭遇处理 ====================

    def _handle_encounter(self, qq_id: str, encounter_id: int, encounter_name: str, is_first: bool, choice: str = None) -> ContentResult:
        """处理遭遇"""
        # 遭遇效果映射
        encounter_effects = {
            1: self._encounter_meow,              # 喵
            2: self._encounter_dream,             # 梦
            3: self._encounter_land_god,          # 河...土地神
            4: self._encounter_fortune_god,       # 财神福利
            5: self._encounter_flower,            # 小花
            6: self._encounter_gentleman,         # 一位绅士
            7: self._encounter_more_dice,         # 多多益善~
            8: self._encounter_hands,             # 一些手
            9: self._encounter_cockroach,         # 螂的诱惑
            10: self._encounter_inspection,       # 突击检查
            11: self._encounter_money_rain,       # 大撒币
            12: self._encounter_leap_of_faith,    # 信仰之跃
            13: self._encounter_cappuccino,       # 卡布奇诺
            14: self._encounter_price,            # 那么,代价是什么?
            15: self._encounter_tofu_brain,       # 豆腐脑
            16: self._encounter_pills,            # 神奇小药丸
            17: self._encounter_bridge,           # 造大桥?
            18: self._encounter_blocks,           # 积木
            19: self._encounter_android,          # 自助问答
            20: self._encounter_congrats,         # 恭喜你
            21: self._encounter_seeds,            # 葡萄蔷薇紫苑
            22: self._encounter_talent_market,    # 人才市场?
            23: self._encounter_bika,             # "bika"
            24: self._encounter_protect_brain,    # 保护好你的脑子!
            25: self._encounter_real_estate,      # 房产中介
            26: self._encounter_mouth,            # 嘴
            27: self._encounter_strange_dish,     # 奇异的菜肴
            28: self._encounter_fishing,          # 钓鱼大赛
            29: self._encounter_cold_joke,        # 冷笑话
            30: self._encounter_dance,            # 💃💃💃
            31: self._encounter_coop_game,        # 双人成列
            32: self._encounter_square_dance,     # 广场舞
            33: self._encounter_dice_song,        # 骰之歌
            34: self._encounter_warning,          # ⚠️警报⚠️
            35: self._encounter_mask,             # 面具
            36: self._encounter_cleanup,          # 清理大师
            37: self._encounter_survival,         # 饥寒交迫
            38: self._encounter_court,            # 法庭
            39: self._encounter_uno,              # 谁要走?!
            40: self._encounter_golden_chip,      # 黄金薯片
            41: self._encounter_blame,            # 我吗?
            42: self._encounter_new_clothes,      # 新衣服
            43: self._encounter_rhythm,           # 节奏大师
            44: self._encounter_cooking,          # 解约厨房
            45: self._encounter_ae_game,          # AeAe少女
            46: self._encounter_dice_song_dlc,    # 咦?!来真的?!
            47: self._encounter_library,          # 魔女的藏书室
            48: self._encounter_storybook,        # 故事书
            49: self._encounter_thousand_one,     # 一千零一
            50: self._encounter_shadow,           # 身影
            51: self._encounter_wild_west,        # 这就是狂野!
            52: self._encounter_loop,             # 循环往复
            53: self._encounter_corridor,         # 回廊
            54: self._encounter_programmer,       # 天下无程序员
            55: self._encounter_art_gallery,      # 欢迎参观美术展
            56: self._encounter_real_story,       # 真实的经历
            57: self._encounter_sisyphus,         # 初次见面
            58: self._encounter_underworld,       # 冥府之路
            59: self._encounter_name,             # 名字
            60: self._encounter_fog,              # 浓雾之中
        }

        handler = encounter_effects.get(encounter_id)
        if handler:
            return handler(qq_id, encounter_name, choice)

        # 默认遭遇（可完成打卡获得5积分）
        return ContentResult(True,
                           f"📖 遭遇：{encounter_name}\n解锁后进行相关打卡可额外获得5积分（每个事件仅限一次）",
                           {'bonus_available': True})

    def _encounter_meow(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇1: 喵"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"喵突然从灌木中窜了出来。喵\"喵\"地一声吃掉了你的骰子。",
                               requires_input=True,
                               choices=["\"吓死我了!\"", "摸摸猫", "静静看它走过去"])

        if choice == "\"吓死我了!\"":
            return ContentResult(True,
                               "\"这个不能吃哇!!!\" \n\n"
                               "下一次投掷只投5个骰子(.r5d6)，进行3、2分组。",
                               {'next_dice_count': 5, 'next_dice_groups': [3, 2]})
        elif choice == "摸摸猫":
            return ContentResult(True,
                               "喵呼噜呼噜的，靠在你脚边蹭蹭，似乎很享受。\n\n"
                               "解锁指令：摸摸喵、投喂喵（每天限5次）")
        else:  # 静静看它走过去
            return ContentResult(True, "喵走过去了。\n\n无事发生。")

    def _encounter_dream(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇2: 梦"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"氤氲的空气中弥漫着大片五彩斑斓的不明气团，边缘泛着朦胧的柔光，几只粉色的蝴蝶扑扇着翅膀穿梭其间，翅尖偶尔扫过气团，溅起细碎的光粒…",
                               requires_input=True,
                               choices=["绕过去(消耗5积分)", "直接过去"])

        if choice == "绕过去":
            if self.player_dao.consume_score(qq_id, 5):
                return ContentResult(True,
                                   "看起来太牙白了，还是绕远路走吧…\n\n"
                                   "你沿着气团边缘缓缓绕行，蝴蝶似乎被惊动，扑棱着飞向远方。\n\n"
                                   "无事发生。")
            else:
                return ContentResult(False, "积分不足，无法选择此项")
        elif choice == "直接过去":  # 直接过去
            return ContentResult(True,
                               "脚尖刚触到气团边缘，你整个人突然被一股轻柔的力量拉扯，眼前的景象骤然扭曲，瞬间坠入一片熟悉又陌生的旧日梦境之中。\n\n"
                               "朦胧的光影里，一个模糊的影子正背对着你，轮廓似曾相识。\n\n"
                               "是什么呢……")


    def _encounter_land_god(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇3: 河...土地神"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"ber的一声，你面前的空地冒出了一个白胡子小老头，向你伸出双手。\"你掉的是这个金骰子还是这个银骰子？\"",
                               requires_input=True,
                               choices=["都是我掉的", "金骰子", "银骰子", "普通d6骰子", "我没掉"])

        if choice == "都是我掉的":
            self.inventory_dao.add_item(qq_id, 9101, "金骰子", "hidden_item")
            self.inventory_dao.add_item(qq_id, 9102, "银骰子", "hidden_item")
            return ContentResult(True,
                               "\"年轻人就是要有野心!\" 老头给你留下了金灿灿和银灿灿的骰子\n获得：金骰子、银骰子\n你额外获得一个免费回合",
                               {'free_round': True})
        elif choice == "我没掉":
            return ContentResult(True, "\"真是诚实的孩子~\" 老头赞许地消失了。无事发生")
        else:  # 金骰子/银骰子/普通d6骰子
            return ContentResult(True,
                               "\"贪心的家伙!这就是你的报应!!\" 老头收走了所有的骰子消失了\n你停止一回合(消耗一回合积分)",
                               {'skip_rounds': 1})

    def _encounter_fortune_god(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇4: 财神福利"""
        # 自动获得后悔券
        self.inventory_dao.add_item(qq_id, 9001, "后悔券", "hidden_item")

        if choice == "谢谢财神":
            self.inventory_dao.add_item(qq_id, 9103, "免费掷骰券", "hidden_item")
            return ContentResult(True, "\"真是有礼貌的孩子!\" 财神额外给了你一张免费掷骰券")

        return ContentResult(True,
                           f"📖 {encounter_name}\n\n"
                           f"可爱的小玩家，到达这里一定经历了千辛万苦吧，这是给你的安慰礼，尽管拿去吧！财神给了你一张后悔券。\"让我们说，谢谢财神。\"\n\n"
                           f"获得后悔券（在没有触发[失败被动停止]的情况下，如果对当前掷骰结果不满意，可重新投掷一次。）\n\n"
                           f"立即回复[谢谢财神]可获得额外奖励",
                           {'bonus_trigger': 'thanks_fortune'})

    def _encounter_flower(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇5: 小花"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"一朵朵美丽的小花在你面前的草地上摇摆摇摆，摇摆摇摆，摇摆摇摆…",
                               requires_input=True,
                               choices=["靠近小花", "浇水(购买水壶-5积分)", "晃得头晕,走了"])

        if choice == "靠近小花":
            return ContentResult(True,
                               "\"哦不——那根本不是普通的花！\"你被巨大的\"花\"包围，花心长出无数尖牙一齐张开血盆大口向你袭来…你停止一回合（消耗一回合积分）。等你回过神来，你发现自己并没有外伤。花仍然在摇摆摇摆，摇摆摇摆……",
                               {'skip_rounds': 1})
        elif choice == "浇水":
            if self.player_dao.consume_score(qq_id, 5):
                return ContentResult(True,
                                   "小花快速生长变成了大花，大花仍然在摇摆摇摆，摇摆摇摆……\n\n*在你之后到达此处的玩家将失去[晃得头晕，走了]和[浇水]选项。")
            else:
                return ContentResult(False, "积分不足，无法购买水壶")
        else:  # 晃得头晕,走了
            return ContentResult(True, "小花仍然在摇摆摇摆，摇摆摇摆……无事发生。")

    def _encounter_inspection(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇10: 突击检查!"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"红框里的单词是？",
                               requires_input=True,
                               choices=["OAS", "其他回答"])

        if choice == "OAS":
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "太棒了！我都想聘请你当员工了！你的积分+5。")
        else:
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True, "连协会的缩写都记不住吗？！好受打击…嘤嘤！QAQ 你被扣除5积分。")

    def _encounter_congrats(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇20: 恭喜你"""
        return ContentResult(True, f"📖 {encounter_name}\n\n没什么，就是恭喜你一下。玩儿去吧~")

    def _encounter_gentleman(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇6: 一位绅士"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"一个带着礼帽浑身漆黑的男人出现在你面前。\"要和我赌一把吗？\"",
                               requires_input=True,
                               choices=["赌!", "不赌!", "老大行行好(-5积分)"])

        if choice == "赌!":
            player = self.player_dao.get_player(qq_id)
            self.player_dao.update_score(qq_id, 0, 0)  # 输光所有积分
            return ContentResult(True, "请输入[投入x积分]（至少10积分）\n"
                                       "→你输光了所有积分。珍爱生命，远离赌博。")
        elif choice == "不赌!":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True,
                               "你深知不能轻易上这种来路不明的东西的当。但你没想到的是，随着男人的消失，你发现身上少了些东西。你-5积分并且下一次投掷只投5个骰子(.r5d6)，进行3、2分组。",
                               {'next_dice_count': 5, 'next_dice_groups': [3, 2]})
        elif choice == "老大行行好":  # 老大行行好(-5积分)
            self.player_dao.add_score(qq_id, -10)
            return ContentResult(True, "你觉得这个男人肯定不简单，想要贿赂一下避免给你带来不便。但你没想到的是，随着男人的消失，你发现身上少了些东西。你额外-5积分。")

    def _encounter_more_dice(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇7: 多多益善~"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"财政部长丝塔茜正在拿着表格四处视察，并看见了你们。\"诶？你在丢骰子？怎么只有六个？这次活动的策划人怎么这么小气！\"还没等你解释，丝塔茜就不由分说地将一个骰子塞到了你的手里。\"想要多少骰子都可以，如果还不够的话记得向财政部申请哦~\"",
                               {'next_dice_count': 7, 'next_dice_groups': [3, 4]},
                               requires_input=True,
                               choices=["好的谢谢", "我要申请更多骰子!", "仔细观察塞过来的骰子"])

        if choice == "好的谢谢":
            return ContentResult(True,
                               "下一次投掷需要投7个骰子(.r7d6)，进行3，4分组。",
                               {'next_dice_count': 7, 'next_dice_groups': [3, 4]})
        elif choice == "我要申请更多骰子!":
            return ContentResult(True,
                               "更多骰子的骰子从天而降。你的下一次投掷骰子数量改成10d6，进行5，5分组。",
                               {'next_dice_count': 10, 'next_dice_groups': [5, 5]})
        elif choice == "仔细观察塞过来的骰子":
            self.inventory_dao.add_item(qq_id, 9104, "意外之财", "hidden_item")
            return ContentResult(True, "你发现这是一颗24K纯黄金打造的骰子。获得隐藏物品：意外之财。")

    def _encounter_hands(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇8: 一些手"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"\"嘿亲爱的，要不要我帮你看看会扔出什么？\"\n\n"
                               f"一只长着眼睛的手从地里长了出来",
                               requires_input=True,
                               choices=["好呀好呀", "还是算了"])

        if choice == "好呀好呀":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True,
                               "\"你难道没有好好听规则吗?!\" \n\n"
                               "又一只手从地里冒了出来，对你指指点点：\n\n"
                               "\"黄牌警告！禁止作弊！！\"\n\n"
                               "你被扣除5积分。")
        elif choice == "还是算了":
            return ContentResult(True, "手遗憾地缩了回去。\n\n无事发生。")

    def _encounter_cockroach(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇9: 螂的诱惑"""
        player = self.player_dao.get_player(qq_id)

        if choice is None:
            choices = ["啊啊啊啊啊", "喷杀虫剂(购买杀虫剂-5)"]
            if player.faction == "收养人":
                choices.append("化兽为友(收养人限定)")
            elif player.faction == "Aeonreth":
                choices.append("蟑螂驾驭(Ae限定)")

            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你的头顶探出一对双马尾。不，那不是双马尾……",
                               requires_input=True,
                               choices=choices)

        if choice == "啊啊啊啊啊":
            return ContentResult(True,
                               "你抵挡不住螂的力量，扔了骰子就跑，下次投掷固定数值(3,3,3,4,4,4)",
                               {'next_dice_fixed': [3, 3, 3, 4, 4, 4]})
        elif choice == "喷杀虫剂":
            if self.player_dao.consume_score(qq_id, 5):
                return ContentResult(True, "\"大螂，该吃药了\"——显然这点剂量难以脚刹大螂，不过它还是飞走了，你逃过一劫。")
            else:
                return ContentResult(False, "积分不足，无法购买杀虫剂")
        elif choice == "化兽为友":
            dice_roll = random.randint(1, 6)
            if dice_roll <= 3:
                return ContentResult(True,
                                   f"[暗骰一个d6骰] 结果={dice_roll}≤3：螂并不想听你的，你抵挡不住螂的力量，扔了骰子就跑，下次投掷固定数值(3,3,3,4,4,4)",
                                   {'next_dice_fixed': [3, 3, 3, 4, 4, 4]})
            else:
                return ContentResult(True,
                                   f"[暗骰一个d6骰] 结果={dice_roll}>3：蟑螂觉得你非常亲切，带着你飞快前进。当前临时标记额外向前移动一格。",
                                   {'move_temp_forward': 1})
        elif choice == "蟑螂驾驭":
            dice_roll = random.randint(1, 6)
            if dice_roll <= 3:
                return ContentResult(True,
                                   f"[暗骰一个d6骰] 结果={dice_roll}≤3：你成功驯服蟑螂，骑着它飞快前进。当前临时标记额外向前移动一格。",
                                   {'move_temp_forward': 1})
            else:
                return ContentResult(True,
                                   f"[暗骰一个d6骰] 结果={dice_roll}>3：螂并不想听你的，你抵挡不住螂的力量，扔了骰子就跑，下次投掷固定数值(3,3,3,4,4,4)",
                                   {'next_dice_fixed': [3, 3, 3, 4, 4, 4]})

    def _encounter_money_rain(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇11: 大撒币!"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你看见财政部部长丝塔茜在远处，身边似乎还有一个你从未见过的AE，但还没等你靠近，就看见了无数的小钱钱从天而降...",
                               requires_input=True,
                               choices=["小钱钱!赶快捡钱!", "先不管钱了!靠近丝塔茜!"])

        self.player_dao.add_score(qq_id, 10)
        if choice == "小钱钱!赶快捡钱!":
            return ContentResult(True, "你急忙在原地开始捡钱，很快就塞满了口袋...你的积分+10")
        elif choice == "先不管钱了!靠近丝塔茜!":
            return ContentResult(True,
                               "你靠近了丝塔茜的方向，但很快魔性的声音便在你的耳畔响起，且随着你的靠近声音也越来越大...最终，你彻底失去了意识，只记得那依然萦绕在你耳畔的诡异歌声...\"我恭喜你发财~\"醒来后，你发现你的口袋里被装满了钱。你的积分+10")

    def _encounter_leap_of_faith(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇12: 信仰之跃"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你前进后，惊讶地发现前方有一个大裂谷！向下望去，只有看不见底的深渊。已经没有道路了…",
                               requires_input=True,
                               choices=["321跳!", "还是回头吧..."])

        if choice == "321跳!":
            self.achievement_dao.add_achievement(qq_id, 101, "刺客大师", "normal")
            return ContentResult(True,
                               "你一跃而下，越强的坠落感包裹住了你，让你甚至无法睁开眼睛看清楚周围的情况，直到你突然感觉到了有什么东西在你的身下作为缓冲，你再次睁开眼睛，发现自己落在了一个干草堆中...无事发生，继续前进。获得成就：刺客大师")
        elif choice == "还是回头吧...":
            return ContentResult(True,
                               "你决定回头离开...但当你回头时，一个赤裸着半身的魁梧男人竟不知何时出现在了你的身后。他对你愤怒地大吼道：\"this is sparta（斯巴达）！\"随后便一脚将你踹入了深坑。你当前临时棋子的进度减1。",
                               {'temp_retreat': 1})

    def _encounter_cappuccino(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇13: 卡布奇诺"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"\"打…打打打…劫！\"\"玩了这么久渴了吧\"\"给pl来一杯卡布奇诺\"",
                               requires_input=True,
                               choices=["喝", "不喝"])

        if choice == "喝":
            return ContentResult(True,
                               "你觉得自己充满了活力和信心。\"六个骰子你能秒我？\"但你掷骰后发现自己高兴早了…下回合出目强制为(2,2,2,2,2,2)",
                               {'next_dice_fixed': [2, 2, 2, 2, 2, 2]})
        elif choice == "不喝":
            return ContentResult(True,
                               "你筋疲力尽，强制结束该轮次。",
                               {'force_end_round': True})

    def _encounter_price(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇14: 那么,代价是什么?"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"一位戴着漆黑斗篷和兜帽的神秘老者拦住了你们的去路。他从一个大锅中用杯子盛满了绿色液体递到了你的面前。\"孩子...喝下这个吧...这是...你的命运...\"",
                               requires_input=True,
                               choices=["喝!", "那么,代价是什么?"])

        if choice == "喝!":
            return ContentResult(True,
                               "你将老者递来的液体一饮而尽，随后你感到了体内翻涌起了狂暴的原始力量！但这股力量...你难以控制！你在下一回合投掷的同时再额外投掷一次d6，如果这次额外投掷出现6则因为你用力过猛，将你本次的骰子全部骰子掷碎了。本回合作废。",
                               {'extra_d6_check_six': True})
        elif choice == "那么,代价是什么?":
            self.achievement_dao.add_achievement(qq_id, 102, "兽人永不为奴!", "normal")
            return ContentResult(True,
                               "老者抬起头看向了你，随后发出了疯狂的笑声。下一刻，杯中的液体被倒在了地上并燃起了绿色火焰，而那个老者也掀开斗篷变成恶魔消失在了你的眼前。获得成就：兽人永不为奴！")

    def _encounter_tofu_brain(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇15: 豆腐脑"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你看到一面镜子，镜子里的你举起了两个形状奇异的豆腐。\"过去还是未来？\"",
                               requires_input=True,
                               choices=["过去", "未来"])

        if choice == "过去":
            return ContentResult(True,
                               "镜子中的你将头颅打开，置换了其中的豆腐脑。选择你上回合的三个点数，替换本回合三个点数。",
                               {'use_last_round_dice': True})
        elif choice == "未来":
            return ContentResult(True,
                               "镜子中的你将头颅打开，置换了其中的豆腐脑。选择本回合三个点数，强制重新投掷。",
                               {'reroll_selected_three': True})

    def _encounter_pills(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇16: 神奇小药丸"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"一个人在绿色的氛围灯下向你伸出双手，掌心放置着两颗药丸。\"红药丸，蓝药丸？\"",
                               requires_input=True,
                               choices=["红药丸", "蓝药丸"])

        if choice == "红药丸":
            return ContentResult(True,
                               "你选择了清醒。你从未觉得头脑如此清醒，你能做些什么？下一回合可以选择一颗骰子，任意改变它的数值。",
                               {'change_one_dice': True})
        elif choice == "蓝药丸":
            return ContentResult(True,
                               "你选择了沉溺。你感到一阵安宁，仿佛身处温暖的水流…你暂停一回合（消耗一回合积分）",
                               {'skip_rounds': 1})

    def _encounter_bridge(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇17: 造大桥?"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你来到了一条河边，一辆车停到了你的旁边，司机摇下车窗开口向你求助。司机想要开车过河，但不知为何，他有很多诡异的要求，例如必须经过某个在半空的地方，还有需要进行托马斯回旋往返跳之类的...真是莫名其妙。随后他给了你一大笔钱，让你去买些造桥的工程材料...",
                               requires_input=True,
                               choices=["造桥!", "拿钱跑路!"])

        if choice == "造桥!":
            self.inventory_dao.add_item(qq_id, 9105, "氮气加速器", "hidden_item")
            return ContentResult(True,
                               "在你的帮助下，司机和他的车完成了空中转体三百六十度托马斯回旋喷气式加速漂移完美落地，而你造的桥也将成为艺术品保留在这里被世人铭记。获得隐藏道具：氮气加速器。你可以选择一枚投掷结果将其数值+3。")
        elif choice == "拿钱跑路!":
            self.player_dao.add_score(qq_id, 10)
            self.achievement_dao.add_achievement(qq_id, 103, "和珅转世", "normal")
            return ContentResult(True,
                               "你拿着工程款跑路了，但当你转过头时却看见刚刚你跑路时顺脚踢飞的一块石子砸到了车上，没想到那车竟然弹射起飞完美地落在了对岸...不过这都和你无关了，你已经卷款跑路了。你获得10积分。获得成就：和珅转世")

    def _encounter_blocks(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇18: 积木"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"什么，不是积木吗？踩在标识上的一瞬间，你看到一个漆黑的人影站在一片湖面的中央，它的手向上托举，一黑一白两个方块在它的手中…",
                               requires_input=True,
                               choices=["我已经不是玩积木的年龄了", "黑色方块", "白色方块"])

        if choice == "我已经不是玩积木的年龄了":
            return ContentResult(True, "你转头就走，比起这个人为什么在湖里没有下沉反而以一种cos河神的姿势站在那，你还是更在意怎么继续前进。无事发生。")
        elif choice == "黑色方块":
            return ContentResult(True,
                               "哦不，一瞬间你的大脑闪回了无数糟糕的回忆…本回合进度视为无效。",
                               {'invalidate_round': True})
        elif choice == "白色方块":
            return ContentResult(True,
                               "你感到一阵温暖，美好的记忆像清风温和地轻抚你的额头…自选一个临时标记往前一格。",
                               {'move_temp_forward': 1})

    def _encounter_android(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇19: 自助问答"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"一个额头侧面闪着芯片光的仿生人向你问好\"有什么可以帮助你的吗？你可以询问我问题。\"",
                               requires_input=True,
                               choices=["随便问一点不为难它的问题", "问点悖论逗它玩"])

        if choice == "随便问一点不为难它的问题":
            return ContentResult(True,
                               "它尽职尽责地回答了你，你得到了你想要的资讯，它还陪伴你走了一段，非常体贴。下一回合可以选择一颗骰子，任意改变它的数值。",
                               {'change_one_dice': True})
        elif choice == "问点悖论逗它玩":
            return ContentResult(True, "你看着它在沉默中额头侧面的芯片越闪越快，从蓝到黄再到红，轻微的嗡鸣声后，它像死机了一样垂下头不动了。不会要赔吧？你赶快溜走了。（无事发生）")

    def _encounter_seeds(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇21: 葡萄蔷薇紫苑"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你面前摆放着三颗种子",
                               requires_input=True,
                               choices=["种下葡萄", "种下蔷薇", "种下紫苑", "什么都不种"])

        player = self.player_dao.get_player(qq_id)
        if choice == "种下葡萄":
            if player.faction == "Aeonreth":
                self.player_dao.add_score(qq_id, 5)
                return ContentResult(True, "• (ae限定)你感觉你的能力在恢复…不，是你的力量在上升……你的积分+5")
            elif player.faction == "收养人":
                # TODO: 检查是否有契约ae
                self.player_dao.add_score(qq_id, 5)
                return ContentResult(True, "• (小女孩限定)葡萄叶生长遮蔽了你的视线，是ae的力量吗？你不由得产生这种想法…如果你有契约ae，你的积分+5；如果没有，无事发生。")
            else:
                return ContentResult(True, "无事发生")
        elif choice == "种下蔷薇":
            return ContentResult(True,
                               "白色的蔷薇铺满了前行的道路。风过时，你看见另一个自己躺在花间。有什么悄然洇开，蜿蜒着，蔓延着，染红了雪白的毯…你的下次投掷消耗双倍积分。",
                               {'next_roll_double_cost': True})
        elif choice == "种下紫苑":
            return ContentResult(True,
                               "你感到有什么正在你的思想中盛开。\"老师，稿画完了吗？\"你仿佛听到来自深渊的诅咒在你耳边回响。是的，不是你，而是\"你\"。你下次必须通过绘制双倍的图获得相应单图积分。",
                               {'must_draw_double': True})
        elif choice == "什么都不种":
            return ContentResult(True,
                               "命运的分支拐向何方？你不知道，\"你\"不知道。强制暂停该轮次直到你完成任意内容物相关绘制（不计算积分）。",
                               {'force_end_until_draw': True})

    def _encounter_talent_market(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇22: 人才市场?"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"当你睁开眼时，发现你已经被穿上了捆绑服带到了一家疯人院中，并且飞快地帮你办理好了入院手续。接下来，有一高一矮两个人在你的面前，你可以选择其中一位成为你的疯人院室友。",
                               requires_input=True,
                               choices=["选择高个子的那个", "选择矮个子的那个"])

        if choice == "选择高个子的那个":
            return ContentResult(True, "你的室友是个话痨，他每天都在和你讲各种莫名其妙你完全听不懂的话，终于有一天，你忍不了了，暴揍了他一顿。谜语人滚出OAS！战斗力+1（并不存在这种东西）")
        elif choice == "选择矮个子的那个":
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "你的室友没过多久后就出院了，后来你听说，他成为了当地的市长。并且给作为曾经室友的你留下了一笔钱。你的积分+5")

    def _encounter_bika(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇23: \"bika\""""
        player = self.player_dao.get_player(qq_id)

        if choice is None:
            if player.faction == "收养人":
                choices = ["让我康康!", "不该看的不看"]
            elif player.faction == "Aeonreth":
                choices = ["谁管ae看什么呢~"]
            else:
                choices = ["继续前进"]

            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"\"bikabika\"\"bikabika\"一个模糊的粉色不明物体怪叫着跑了过来",
                               requires_input=True,
                               choices=choices)

        if choice == "让我康康!":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True, "\"小孩子不许看这个。\"魔女大姐姐略有些责备地把那个小东西抓走了，而你也受到了惩罚。你的积分-5")
        elif choice == "不该看的不看":
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "巡逻的魔女大姐姐赞许地点了点头，并把那个小东西抓走了。你的积分+5")
        elif choice == "谁管ae看什么呢~":
            return ContentResult(True, "当你发觉自己看到了什么的时候一切都已经来不及了…但话说回来，谁管ae看什么呢~无事发生。")
        elif choice == "继续前进":
            return ContentResult(True, "无事发生")

    def _encounter_protect_brain(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇24: 保护好你的脑子!"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"僵尸的嘶吼声传入你的耳中，不知何时你发现你已经来到了一个丧尸危机爆发的世界中，而现在，你被困在了一个老宅中，手边只有一个小袋子和一瓶洗手液，你必须要选择其中一个东西来保护好自己...",
                               requires_input=True,
                               choices=["选择小袋子", "选择洗手液"])

        if choice == "选择小袋子":
            self.player_dao.add_score(qq_id, 5)
            self.inventory_dao.add_item(qq_id, 9106, "小奖杯", "hidden_item")
            return ContentResult(True, "你打开小袋子，发现里面是一些...种子？顾不上这么多了，你立刻来到了你的后院，僵尸大军马上就要来了！你种下种子，随后长出了一株株向日葵和豌豆...你靠着这些植物抵御了僵尸的进攻，并且还下了多余的阳光。获得隐藏物品：小奖杯。你的积分+5")
        elif choice == "选择洗手液":
            self.achievement_dao.add_achievement(qq_id, 104, "洗手液战神", "normal")
            return ContentResult(True, "正当你拿起洗手液，一个巨大的僵尸就冲入了宅子中，僵尸强大的力量让你几乎失去意识，僵尸甚至扯断了你的手臂...但没想到的是，你打开了洗手液并倒在了自己的断手处，你所有的伤口居然全部愈合如初！你凭借着洗手液最终杀出重围成功生存。获得成就：洗手液战神")

    def _encounter_real_estate(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇25: 房产中介"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"\"哟？又带嫂子来看房啦？\"",
                               requires_input=True,
                               choices=["哪儿来的嫂子?", "不理它"])

        if choice == "哪儿来的嫂子?":
            dice_roll = random.randint(1, 20)
            if dice_roll >= 18:
                return ContentResult(True,
                                   f"你一回头，身后不知道什么时候出现了一个诡异的木偶，木偶伴随着你的惊叫开始移动追杀你。你投掷一个1d20→\n\n• 出目≥18（出目={dice_roll}）：凭借回头溜鬼的通用技巧，你轻松摆脱了木偶的追杀。你当前临时标记向前移动一格。",
                                   {'move_temp_forward': 1})
            elif dice_roll >= 5:
                return ContentResult(True, f"你一回头，身后不知道什么时候出现了一个诡异的木偶，木偶伴随着你的惊叫开始移动追杀你。你投掷一个1d20→\n\n• 出目5~17（出目={dice_roll}）：经过不懈的努力，你终于摆脱了木偶。")
            else:
                return ContentResult(True,
                                   f"你一回头，身后不知道什么时候出现了一个诡异的木偶，木偶伴随着你的惊叫开始移动追杀你。你投掷一个1d20→\n\n• 出目<5（出目={dice_roll}）：你没能成功逃离。当你睁开眼睛时，你距离刚才的位置已经倒退了一格。你当前临时标记向后移动一格。",
                                   {'temp_retreat': 1})
        elif choice == "不理它":
            return ContentResult(True, "似乎不是对你说的，你快步离开了。无事发生。")

    def _encounter_mouth(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇26: 嘴"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"\"你好。\"不知道从哪里传出声音。",
                               requires_input=True,
                               choices=["谁?", "寻找声音来源"])

        if choice == "谁?":
            return ContentResult(True,
                               "\"嘻嘻嘻嘻…\"声音再次响起，你突然被不知道什么东西砸晕了。你暂停一回合（消耗一回合积分）",
                               {'skip_rounds': 1})
        elif choice == "寻找声音来源":
            return ContentResult(True,
                               "你非常警惕，没有回应，顺着声音传来的方向，你看到一个嘴长在面前脚下的格子上。",
                               requires_input=True,
                               choices=["\"你好\"", "还是不回应了"])
        elif choice == "\"你好\"":
            return ContentResult(True,
                               "看到是张人畜无害的嘴，你还是开口了。\"嘻嘻嘻嘻…\"声音再次响起，你突然被不知道什么东西砸晕了。你暂停一回合（消耗一回合积分）",
                               {'skip_rounds': 1})
        elif choice == "还是不回应了":
            return ContentResult(True, "你收起脚步声悄悄从它旁边走过去。无事发生。")

    def _encounter_strange_dish(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇27: 奇异的菜肴"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你面前的锅里装着奇怪的食材，随着柴火加热咕嘟咕嘟冒着泡，飘出微妙的气味…",
                               requires_input=True,
                               choices=["好怪,尝一口", "好怪,还是不要吧", "好怪!一口闷了!"])

        if choice == "好怪,尝一口":
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "虽然入口就像炖轮胎佐鲱鱼罐头汤，但异味很快消失了，你感觉力气在恢复。你的积分+5")
        elif choice == "好怪,还是不要吧":
            return ContentResult(True, "你捏着鼻子走开了。无事发生。")
        elif choice == "好怪!一口闷了!":
            self.player_dao.add_score(qq_id, 10)
            return ContentResult(True, "虽然入口就像炖轮胎佐鲱鱼罐头汤，但本着猎奇的心理你还是干了，你感觉充满了力气！！你的积分+10")

    def _encounter_fishing(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇28: 钓鱼大赛"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你看到一个巨大的招牌立在池塘旁边。\"只需要钓上x条鱼就能够拿到大奖哦！\"似乎不参与就绕不过去。不知不觉中天黑了，而你只差几条就能拿到最终的奖励！",
                               requires_input=True,
                               choices=["坚持钓到最后一刻", "差不多得了,先交了走人"])

        if choice == "坚持钓到最后一刻":
            self.player_dao.add_score(qq_id, -10)
            return ContentResult(True, "钓鱼佬的尊严要求你在鱼竿边上坚守到底，时间流逝得比你想象中的快，在两点的闹钟（谁定的？）响起的时候，你眼前一黑——昏迷了。再醒来，已经躺在了门口的床上，一封信躺在你的枕头边上：\"亲爱的客户您好！昨晚，我们的一位员工发现您昏倒在了池塘边上。我们派出了一支医疗小队来把您安全地送到了床上。很高兴您没有事！这个服务会向您收取一定的费用。\"你一翻口袋，发现少了什么东西。你的积分-10")
        elif choice == "差不多得了,先交了走人":
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True, "见好就收，虽然没能拿到大奖，但是现在的收获也足够换一些奖励了。你快速交了鱼，得到了属于你的奖品。你的积分+5")

    def _encounter_cold_joke(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇29: 冷笑话"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"停，就是你，现在3分钟内讲一个冷笑话。",
                               requires_input=True,
                               choices=["完成后输入[冷笑话已完成]", "无法完成"])

        if choice == "完成后输入[冷笑话已完成]":
            return ContentResult(True, "完成任务！")
        elif choice == "无法完成":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True, "未能完成，自动积分-5")

    def _encounter_dance(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇30: 💃💃💃"""
        return ContentResult(True,
                           f"📖 {encounter_name}\n\n"
                           f"鎏金吊灯旋转着洒下光斑，复古留声机正流淌着慵懒旋律，地板的菱格纹随着光影忽明忽暗…\"可以和我跳一支舞吗？\"面前向你伸出手的是——？\n\n"
                           )

    def _encounter_coop_game(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇31: 双人成列"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"承载着两个手柄的展示台缓缓升起，在你面前，全息影像生成了一个双人小游戏界面…",
                               requires_input=True,
                               choices=["和契约对象一起玩", "可我没有契约对象"])

        if choice == "和契约对象一起玩":
            return ContentResult(True,
                               "和你的契约对象分别投一个d6骰，如果你们出目一样，则你们靠着出色的默契通关小游戏，各获得一次免费回合。")
        elif choice == "可我没有契约对象":
            return ContentResult(True,
                               "一个人怎么就不能用两个手柄！你还是上了。投3个d6骰，如果3次全部出目一样，则当前临时标记可以向前移动一格，且你本轮次主动结束不用打卡即可开启下一轮次。获得成就：单人硬行",
                               {'achievement_check': '单人硬行'})

    def _encounter_square_dance(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇32: 广场舞"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你看到远处有一群人在跳广场舞",
                               requires_input=True,
                               choices=["走近看看", "没兴趣"])

        if choice == "走近看看":
            return ContentResult(True,
                               "\"大爷大妈和大叔……♪\"靠近后你才发觉这个调子好像在哪里听过，而你的四肢却快过了你的思考不受控制地跟着跳了起来…你的下次掷骰也不受控制地变成(2,3,3,3,3,3)",
                               {'next_dice_fixed': [2, 3, 3, 3, 3, 3]})
        elif choice == "没兴趣":
            return ContentResult(True, "你对这种活动不感兴趣，还是继续游戏要紧。无事发生。")

    def _encounter_dice_song(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇33: 骰之歌"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"系统提醒你刚刚上线了一款新游戏mod，《骰之歌》，只不过似乎服务器还在维护没有开启。",
                               requires_input=True,
                               choices=["等待", "不等了"])

        if choice == "等待":
            return ContentResult(True,
                               "你等了不知道多少个回合，最终还是没有等来它的消息…你暂停一回合（消耗一回合积分）",
                               {'skip_rounds': 1})
        elif choice == "不等了":
            return ContentResult(True, "你不想为它浪费时间，于是继续进行游戏。无事发生。")

    def _encounter_warning(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇34: ⚠️警报⚠️"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"系统突然响起了警报，你的积分与进度面临崩溃风险！情急之下，你…",
                               requires_input=True,
                               choices=["抓起印着土豆的芯片", "抓起上面撒了墨水的芯片", "主持人救命", "还是找喵吧"])

        if choice == "抓起印着土豆的芯片":
            self.player_dao.add_score(qq_id, -10)
            return ContentResult(True,
                               "你的面前出现了更多的警报，数不胜数的警报，最终服务器崩溃了…你的积分-10并强制结束该轮次。",
                               {'force_end_turn': True})
        elif choice == "抓起上面撒了墨水的芯片":
            return ContentResult(True,
                               "失败了好几遍之后终于成功连接了，但是屏幕上的符号一直在转圈，你就这样等呀等，等呀等…你暂停一回合（消耗一回合积分）",
                               {'skip_rounds': 1})
        elif choice == "主持人救命":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True, "主持人也不懂呀，你俩大眼瞪小眼，直到系统崩溃。你的积分-5")
        elif choice == "还是找喵吧":
            return ContentResult(True, "靠谱的喵叫来了管理员维护，你的服务器保住了。")

    def _encounter_mask(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇35: 面具"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你的面前摆放着一个古老而精致的面具，似乎在引诱着你佩戴上它。",
                               requires_input=True,
                               choices=["戴面具", "抵抗诱惑"])

        if choice == "戴面具":
            player = self.player_dao.get_player(qq_id)
            if player.faction == "Aeonreth":
                return ContentResult(True,
                                   "• (ae阵营)你感到消失的力量在回流，你终于可以摆脱规则的束缚…你的下一回合可以选择任一出目改变其数值。",
                                   {'next_dice_modify_any': True})
            else:  # 收养人
                return ContentResult(True,
                                   "• (小女孩阵营)强大的血脉力量在呼唤着你——\"我不做人啦！OAS！\"你情不自禁地大喊出来。你的下一回合可以选择任一出目使其结果+3",
                                   {'next_dice_add_3_any': True})
        elif choice == "抵抗诱惑":
            dice_roll = random.randint(1, 6)
            if dice_roll > 3:
                return ContentResult(True, f"你投一个d6骰，若出目>3（出目={dice_roll}），则你成功抵抗诱惑进入下一回合；无事发生。")
            else:
                self.player_dao.add_score(qq_id, -5)
                return ContentResult(True, f"你投一个d6骰，若出目≤3（出目={dice_roll}），则你没能抵抗诱惑被面具侵蚀了心智，你的积分-5。")

    def _encounter_cleanup(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇36: 清理大师"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"咦，为什么保洁要找我？这个软趴趴的人也是垃圾？一眨眼你来到一个脏乱的别墅，被莫名其妙塞了一份工作，内容是清理……犯罪现场？！",
                               requires_input=True,
                               choices=["老实清理", "\"家具换装\"", "关我什么事啊!"])

        if choice == "老实清理":
            dice_roll = random.randint(1, 20)
            if dice_roll >= 17:
                self.player_dao.add_score(qq_id, 10)
                return ContentResult(True,
                                   f"你老老实实地接手了人民碎片的清理任务，这实在是一件累人且考验眼力的事情，但是过程中你摸到了不少零碎的小物件……清理到自己的口袋里也是清理！你掷一个d20骰：\n\n• 出目≥17（出目={dice_roll}）：你在这个考验眼力和耐心的游戏里获得了成功！你的口袋也被意外收获塞得满满当当，你心满意足地带着拖把桶离开了。（积分+10）")
            elif dice_roll >= 6:
                self.player_dao.add_score(qq_id, 5)
                return ContentResult(True,
                                   f"你老老实实地接手了人民碎片的清理任务，这实在是一件累人且考验眼力的事情，但是过程中你摸到了不少零碎的小物件……清理到自己的口袋里也是清理！你掷一个d20骰：\n\n• 出目6-17（出目={dice_roll}）：可能是你专注着往口袋里塞一些亮晶晶的东西，以至于稍微有点忽略了一些小细节……！你的委托人有了点小小的麻烦，你的佣金也受了影响。哎呀，你只剩下一口袋亮晶晶的东西和你做伴了。（积分+5）")
            else:
                self.player_dao.add_score(qq_id, -5)
                return ContentResult(True,
                                   f"你老老实实地接手了人民碎片的清理任务，这实在是一件累人且考验眼力的事情，但是过程中你摸到了不少零碎的小物件……清理到自己的口袋里也是清理！你掷一个d20骰：\n\n• 出目≤5（出目={dice_roll}）：哦不，你或许做了一些反方向的努力……人民碎片被你涂得到处都是，与雇主想象中的相去甚远……你口袋里的亮晶晶因为这件事情被没收走了。真是不干活就没饭吃，一干活就有苦吃啊。（积分-5）")
        elif choice == "\"家具换装\"":
            self.player_dao.add_score(qq_id, 20)
            self.achievement_dao.add_achievement(qq_id, 105, "人民粉刷匠", "normal")
            return ContentResult(True,
                               "你心生一计，将番茄酱均匀地涂抹在墙面地板家具上，装修风格焕然一新，一种红木老钱感扑面而来。甚至之后警方来调查撒了一把鲁米诺试剂大喊着\"谁扔的闪光弹\"就走了。你的雇主非常满意，给了你额外的奖励。（积分+20）获得成就：人民粉刷匠")
        elif choice == "关我什么事啊!":
            return ContentResult(True, "关你什么事啊！你跑路了，任由人民碎片就那么摆在那里接受调查。也许犯事的人被抓了，也许没有，但是那都和你没关系了。无事发生。")

    def _encounter_survival(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇37: 饥寒交迫"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"你已经玩了很久，不知不觉入夜了，向你袭来的是……",
                               requires_input=True,
                               choices=["饥饿", "寒冷", "恐惧", "我很好啊"])

        if choice in ["饥饿", "寒冷", "恐惧"]:
            dice_roll = random.randint(1, 6)
            if dice_roll > 3:
                self.player_dao.add_score(qq_id, 5)
                outcomes = {
                    "饥饿": "你寻找能填饱肚子的东西…你成功找到了食物",
                    "寒冷": "你寻找能取暖的东西…你成功维持住了体温",
                    "恐惧": "你找到了一些可爱的小生物贴贴度过长夜"
                }
                return ContentResult(True, f"{outcomes[choice]}，你掷一个d6骰，若>3（出目={dice_roll}），则积分+5。")
            else:
                self.player_dao.add_score(qq_id, -5)
                outcomes = {
                    "饥饿": "你寻找能填饱肚子的东西…你没有找到食物饿晕在荒野中",
                    "寒冷": "你寻找能取暖的东西…你因为寒冷晕倒在荒野中",
                    "恐惧": "你被黑暗中的爪牙侵蚀"
                }
                return ContentResult(True, f"{outcomes[choice]}，你掷一个d6骰，若≤3（出目={dice_roll}），则积分-5。")
        elif choice == "我很好啊":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True, "你试图强撑，但还是体力不支晕过去了。你的积分-5")

    def _encounter_court(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇38: 法庭"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"一阵恍惚后，你发现你站在了一个法庭上……咦？头顶光滑的审判长正看着你：\"辩护律师，你对什么提出异议？\"",
                               requires_input=True,
                               choices=["…这是什么,亮晶晶的?别管了,举证!", "我要……我要询问证人……!", "随便拿一个什么出示证物!"])

        if choice == "…这是什么,亮晶晶的?别管了,举证!":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True,
                               "你不知道现在是什么情况，但貌似你需要举证。你随手抓起一个亮亮的物件高高举起……请看！……诶？律师徽章？在严肃的法庭上玩这个显然有点太不分场合……审判长狠狠剐了你一眼，随即敲下锤子：\"有罪！\"作为辩护律师，你的行为有点太滑稽了。（积分-5）")
        elif choice == "我要……我要询问证人……!":
            dice_roll = random.randint(1, 20)
            if dice_roll >= 10:
                self.player_dao.add_score(qq_id, 5)
                return ContentResult(True,
                                   f"虽然什么都不知道但是你决定询问证人，问完也许你会对整个事件与流程有所了解。投掷d20\n\n• 出目≥10（出目={dice_roll}）：虽然证人的每一句话都会被你的\"等等\"打断，但是在这样消耗精力的问询中你居然也抓到了一些互相矛盾的细节……你对此提出了疑问，证词的真实性被推翻了。做的好！（积分+5）")
            else:
                self.player_dao.add_score(qq_id, -5)
                return ContentResult(True,
                                   f"虽然什么都不知道但是你决定询问证人，问完也许你会对整个事件与流程有所了解。投掷d20\n\n• 出目≤10（出目={dice_roll}）：虽然你每一句都仔仔细细盘问，但是对面的检察官显然不愿意见到你这么拖延时间。他要求你提出问题，但是你没有任何头绪。哦不，你的询问被认为是在浪费时间。（积分-5）")
        elif choice == "随便拿一个什么出示证物!":
            self.player_dao.add_score(qq_id, -5)
            self.inventory_dao.add_item(qq_id, 9107, "手电筒", "hidden_item")
            return ContentResult(True,
                               "你的手边只有一个刚刚保安随手放在这里的手电筒。你举着手电晃来晃去，引得众人一片哗然。\"带着你的破手电滚出去！\"理所当然的，你被以破坏法庭纪律为由赶走了。你的积分-5。获得隐藏道具：手电筒。")

    def _encounter_uno(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇39: 谁要走?!"""
        if choice is None:
            # 这是一个需要投骰的遭遇,返回骰子检查提示
            dice_roll = random.randint(1, 20)
            base_msg = f"📖 {encounter_name}\n\n你被拉入了一场OAS游戏里，看样子不打完是走不了了。随着时间的流逝，你只剩下一张牌了……你能不能走，只看你的上家抽出的卡是什么。\n\n投掷1d20\n"
            if dice_roll >= 17:
                self.player_dao.add_score(qq_id, 10)
                return ContentResult(True,
                                   base_msg + f"• 出目≥17（出目={dice_roll}）：多么幸运，你的上家甩出的牌刚好是你接得上的。你赢了！你的积分+10")
            elif dice_roll >= 12:
                self.player_dao.add_score(qq_id, -5)
                return ContentResult(True,
                                   base_msg + f"• 出目12-17（出目={dice_roll}）：呃，你的上家和下家一对眼神，默契地把你孤立了：你被反转牌剥夺了出牌机会，被迫留了下来。你的积分-5")
            elif dice_roll >= 6:
                self.player_dao.add_score(qq_id, -5)
                return ContentResult(True,
                                   base_msg + f"• 出目6-11（出目={dice_roll}）：你眼睁睁地看着上家扔出了一张万能牌……ta指定了你没有的颜色，你不得不抽了一张牌，现在你又得多待一阵子了。你的积分-5")
            else:
                return ContentResult(True,
                                   base_msg + f"• 出目1-5（出目={dice_roll}）：坏了，你的上家露出了笑容，一张+4就这么甩在了你的面前。牌数大增殖！谁准你就这么走了？！你被拖延住了……哎呀，有人在你之前出完了牌，你输了。你暂停一回合（消耗一回合积分）",
                                   {'skip_rounds': 1})

        # 不需要choice处理,因为这是一个自动投骰的遭遇
        return ContentResult(True, "无事发生")

    def _encounter_golden_chip(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇40: 黄金薯片"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"一个带着帽子的圆形东西在你面前出现：\"来吧，和我握个手，打开那扇门！\"",
                               requires_input=True,
                               choices=["握一下又能怎么样?", "不握,这是哪里来的薯片"])

        if choice == "握一下又能怎么样?":
            return ContentResult(True,
                               "当你被蓝色火焰触及，你感到一阵天旋地转，圆片似乎跨越了平面拥有了厚度，伴随着一阵\"wellwellwell\"的动静后，你短暂失去了对身体的控制。当你再度清醒，发现时间已经过去了很久，并且脑门上贴着一张纸条，细数了这段时间里\"你\"所搞的破坏。你暂停一回合（消耗一回合积分）",
                               {'skip_rounds': 1})
        elif choice == "不握,这是哪里来的薯片":
            return ContentResult(True, "你忽视了这个破薯片的邀请，离开了。无事发生。")

    def _encounter_blame(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇41: 我吗?"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"虽然你对前因后果一概不清楚甚至也不太明白你为什么突然站在了这里，但是现在你的面前正有人指着你的鼻子指责你",
                               requires_input=True,
                               choices=["虽然但是对不起", "对喷!", "叽里咕噜说什么呢听不懂"])

        if choice == "虽然但是对不起":
            self.player_dao.add_score(qq_id, 5)
            self.achievement_dao.add_achievement(qq_id, 106, "超级大窝囊", "normal")
            return ContentResult(True,
                               "……别管了先道个歉,有没有用再说吧……你窝窝囊囊地为你并不清楚起因经过结果的指责道歉,天呐。但是好在对面很快没了精力,扔给了你一个小袋子就走了。……这是你的窝囊费吗?\n你的积分+5\n获得成就:超级大窝囊")
        elif choice == "对喷!":
            return ContentResult(True,
                               "忍不了了和ta爆了,虽然你不太清楚起因经过结果但是你与对面激情对喷,貌似……短时间内过不去了。\n你本轮次内本列临时标记无法再移动",
                               {'freeze_current_column': True})
        elif choice == "叽里咕噜说什么呢听不懂":
            self.player_dao.add_score(qq_id, 10)
            return ContentResult(True,
                               "ta说东你答42号混凝土,ta说西你回记住我给的原理,就这么驴唇不对马嘴的一来一往,你们短暂陷入了诡异的沉默里。最后,ta叹了口气,捂着脑袋疲惫地扔给你一个袋子:\"你要不还是去充个值吧。\"你的积分+10")

    def _encounter_new_clothes(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇42: 新衣服"""
        # 互动类遭遇,不需要choice处理
        return ContentResult(True,
                           f"📖 {encounter_name}\n\n"
                           f"哇塞！是满满的一柜子的新衣服！玩了这么半天也该换套干净衣服了——你的新搭配是？\n\n"
                           f"💡 互动类遭遇，由玩家自行决定内容")

    def _encounter_rhythm(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇43: 节奏大师"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"身边响起了富有节奏感的音乐，你的脚下和手边浮现出一些正在移动的按键",
                               requires_input=True,
                               choices=["打歌!", "不懂,不管了"])

        if choice == "打歌!":
            dice_roll = random.randint(1, 6)
            if dice_roll >= 5:
                self.player_dao.add_score(qq_id, 10)
                return ContentResult(True, f"d6={dice_roll}≥5 你凭借出色的技巧全连pc,你的积分+10")
            elif dice_roll >= 3:
                self.player_dao.add_score(qq_id, 5)
                return ContentResult(True, f"d6={dice_roll}≥3 虽然有几个没有完美点到,但你还是侥幸全连了,你的积分+5")
            else:
                return ContentResult(True, f"d6={dice_roll}<3 你不熟悉这种游戏,出现了好几个miss,但所幸全打下来了,没有惩罚")
        elif choice == "不懂,不管了":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True, "你想直接离开,却发现身体无法移动,直到歌曲结束全部miss。你失败了,你的积分-5")

    def _encounter_cooking(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇44: 解约厨房"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"\"我做饭？真的假的？\"你突然接到任务，需要和你的契约对象配合完成几份食物的准备。",
                               requires_input=True,
                               choices=["要上了", "不做", "可我没有契约对象"])

        if choice == "要上了":
            dice_roll = random.randint(1, 6)
            if dice_roll >= 4:
                self.player_dao.add_score(qq_id, 5)
                return ContentResult(True,
                                   f"d6={dice_roll}≥4 你叫上契约对象就上了。你们配合完美,简直是最合适的搭档!你和你的契约对象各自积分+5\n(需要手动给契约对象加分)")
            else:
                return ContentResult(True,
                                   f"d6={dice_roll}<4 你们手忙脚乱失败了,虽然没有收到什么责罚,但你忍不住开始考虑和你契约对象之间的默契……无事发生")
        elif choice == "不做":
            return ContentResult(True,
                               "顾客气得跑来骂街,影响了你的游戏进程。\n你暂停一回合(消耗一回合积分)",
                               {'skip_rounds': 1})
        elif choice == "可我没有契约对象":
            dice_roll = random.randint(1, 6)
            if dice_roll == 6:
                self.player_dao.add_score(qq_id, 10)
                return ContentResult(True, f"d6={dice_roll}=6 没有契约对象的你一个人干两份活儿…你成功完成任务,积分+10")
            elif dice_roll >= 3:
                return ContentResult(True, f"d6={dice_roll} 你果然一个人还是忙不过来,任务失败。无事发生")
            else:
                self.player_dao.add_score(qq_id, -5)
                return ContentResult(True, f"d6={dice_roll}<3 你不仅没有完成任务,还惹怒了顾客,你的积分-5")

    def _encounter_ae_game(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇45: AeAe少女"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"中场小游戏时间~你们开始了一场类似狼○杀的Ae/少女双边游戏——当然真正的身份和自己并不一定相匹配。你分到了\"好人\"身份。现在到了最重要的决定成败的投票环节，你却被诬陷是\"坏人\"，你的选择是？",
                               requires_input=True,
                               choices=["\"相信我,全票打飞那个诬陷我的\"", "不会玩,认栽", "再盘一遍逻辑"])

        if choice == "\"相信我,全票打飞那个诬陷我的\"":
            dice_roll = random.randint(1, 6)
            if dice_roll >= 4:
                self.player_dao.add_score(qq_id, 5)
                return ContentResult(True, f"d6={dice_roll}≥4 你激动的情绪感染了其他队友,全票打飞坏人取得了胜利。你的积分+5")
            else:
                self.player_dao.add_score(qq_id, -5)
                return ContentResult(True, f"d6={dice_roll}<4 你激动的情绪让队友也以为你破防了在挣扎,最后投错,坏人胜利。你的积分-5")
        elif choice == "不会玩,认栽":
            self.player_dao.add_score(qq_id, -10)
            return ContentResult(True, "你不知如何狡辩,最后让坏人取得了胜利,并且你消极的态度似乎让队友很不满。你的积分-10")
        elif choice == "再盘一遍逻辑":
            dice_roll = random.randint(1, 6)
            if dice_roll >= 2:
                self.player_dao.add_score(qq_id, 10)
                return ContentResult(True, f"d6={dice_roll}≥2 你把游戏过程与细节梳理了一遍,最后发现那个诬陷你的才是真正的坏人,你帮助所有人取得了胜利,并获得了大家的好感。你的积分+10")
            else:
                self.player_dao.add_score(qq_id, -5)
                return ContentResult(True, f"d6={dice_roll}=1 你越盘越乱,最后把自己也绕进去了,再也没人相信你,最后坏人胜利。你的积分-5")

    def _encounter_dice_song_dlc(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇46: 咦?!来真的?!"""
        if choice is None:
            # 自动投骰遭遇
            dice_roll = random.randint(1, 20)
            base_msg = (f"📖 {encounter_name}\n\n"
                       f"你来到了这个屋子，这里平静得奇怪。你注意到了路边插着一个路牌，当你凑上前时，发现上面写着这样一行字：\"骰之歌开放了！我去打骰之歌了！我真幸运！刚测试完贪骰无厌就有dlc打！走过路过，抽个游戏参与权吧！——管理员\"……幸运吗？也许是吧，至少OAS没有跳票。你注意到一边的抽奖箱，上面写着\"每人限一次\"\n\n")

            if dice_roll >= 18:
                self.player_dao.add_score(qq_id, 20)
                return ContentResult(True,
                                   base_msg + f"投掷d20\n• 出目≥18（出目={dice_roll}）：你真幸运！抽到了奖项！获得一份游戏参与券！你的积分+20")
            else:
                return ContentResult(True,
                                   base_msg + f"投掷d20\n• 出目<18（出目={dice_roll}）：哎呀，没有抽到，但是要从这一箱子的奖券里抽出来一张特定的，并不容易，也可以理解。你平安无事地离开了这里，在路过随意摆放在路边的奇形怪状道具时忍不住庆幸这里的管理员玩游戏去了，空不出手来折腾你。无事发生")

        # 不需要choice处理
        return ContentResult(True, "无事发生")

    def _encounter_library(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇47: 魔女的藏书室"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\n"
                               f"书本杂乱地堆放着，隐形的人正在寻找可以将书本打捆用的绳子。\"可以帮我把这个放回书架吗？\"一本书被塞到了你的手中，而远处的书架中正有一处空缺，你看了看手中的书，书的名字是《读了就会死》。",
                               requires_input=True,
                               choices=["将书送回书架", "还有这种书?自己留着偷偷带走", "还有这种书?让我看看!"])

        if choice == "将书送回书架":
            self.inventory_dao.add_item(qq_id, 9108, "粉色蝴蝶", "hidden_item")
            return ContentResult(True,
                               "你将这本书送回了书架中填补了空缺,随后在书与书的缝隙中,一只粉色的发着光的蝴蝶轻盈地扇动翅膀飞了出来,安静地落在了你的手上。\n获得隐藏道具[粉色蝴蝶]:可以通过打卡(不计算积分)避免下一次陷阱的负面影响。你的意识突然陷入一片黑暗,当你再清醒过来时,只记得在黑暗中似乎有一个微弱的粉色光点。你的面前有一只死掉的蝴蝶,它的翅膀碎裂,如同被什么东西啃食了一般")
        elif choice == "还有这种书?自己留着偷偷带走":
            self.inventory_dao.add_item(qq_id, 9109, "读了就会死的书", "hidden_item")
            return ContentResult(True,
                               "获得隐藏道具[读了就会死的书]:可以主动清除一条纵列上的临时标记")
        elif choice == "还有这种书?让我看看!":
            return ContentResult(True,
                               "你翻看了书,书中的文字却在你的视线中越来越模糊,红色的液体污染了书页,你感到双眼越来越疼痛,你用手揉了揉眼睛,才发现那是从你眼中流出的鲜血...")

    def _encounter_storybook(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇48: 故事书"""
        # 打卡类遭遇,不需要choice处理
        return ContentResult(True,
                           f"📖 {encounter_name}\n\n"
                           f"一本鎏金烫边的立体翻页童话书在你眼前摊开。松软纸页翻动时带着轻微的沙沙声，森林从纸面隆起，雾气似有若无地萦绕在枝叶间。而不同于你所见过的一切故事，林间站着的主角，正是装束陌生却一眼能认出的你。当你轻轻掀起下一页，风铃声从纸页间溢出，故事随着你的翻动开始上演——Once upon a time…\n\n"
                           f"💡 此遭遇可与绑定ae或其他玩家联动完成。完成此打卡可在奖励指令后输入[*2]领取双倍奖励，一人限一次(非一张)。")

    def _encounter_thousand_one(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇49: 一千零一"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n她邀请你停下来聆听最后一个故事",
                               requires_input=True,
                               choices=["坐下", "对不起,没有时间……", "我有一个点子!🤓☝️"])

        if choice == "坐下":
            self.inventory_dao.add_item(qq_id, 9110, "一千零一个故事", "hidden_item")
            return ContentResult(True,
                               "她如同丝绸般柔滑的嗓音安抚着你的心绪,你不知不觉地倚靠着靠枕滑入了梦乡……她叙述的故事情节已经在你的记忆里淡化,苏醒后你只看到她原先所在的位置上遗留着一本厚厚的书。\n获得隐藏道具:一千零一个故事(如果本回合点数不理想被动停止,可以使用此道具,在原地留下永久棋子后本回合结束)")
        elif choice == "对不起,没有时间……":
            return ContentResult(True,
                               "她没有阻拦你,只是目送着你离开。当你的手搭上门把时,你隐约觉得背后有两道视线注视着你,但是你没有回头。无事发生")
        elif choice == "我有一个点子!🤓☝️":
            self.achievement_dao.add_achievement(qq_id, 107, "国王的认可", "normal")
            return ContentResult(True,
                               "故事会吗?这我在行!你表示你也有好故事可以分享,随后兴致勃勃地讲起了故事。在你没注意的时候,那颗被拥抱着的头颅睁开了眼睛,打量着你。\n获得成就:国王的认可\n完成相关内容打卡可获得隐藏道具:骷髅头胸针——使用后随机获得一件已解锁普通道具")

    def _encounter_shadow(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇50: 身影"""
        # 观察类遭遇,不需要choice处理
        return ContentResult(True,
                           f"📖 {encounter_name}\n层叠的几何建筑展开,如同可拆解的立体纸盒,顺着视线方向层层铺展。\n"
                           f"你在其间穿梭,瓷砖铺就的路径随视角转动不断重构——刚踏上的阶梯转头变成垂直的平面,抬手即可触碰的天花板俯身却踩在了脚下,闭合的大门侧身便出现了宽敞的道路…\n"
                           f"当你终于驻足注意到某座高悬的尖塔,试图去触摸那或许也并不真实的墙面时,竟从塔身的纹路里,瞥见无数个自己的残影,那些残影的身后也隐约透露出你所经过的建筑碎片…")


    def _encounter_wild_west(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇51: 这就是狂野!"""
        if choice is None:
            player = self.player_dao.get_player(qq_id)
            choices = ["比试枪法", "比试骑术", "给他一拳!"]
            if player.faction != "收养人":  # ae和未选阵营可以
                choices.insert(1, "比试酒量(小女孩禁选)")

            return ContentResult(True,
                               f"📖 {encounter_name}\n西部酒馆!\"来吧?小家伙,来比试比试。\"",
                               requires_input=True,
                               choices=choices)

        if choice == "比试枪法":
            return ContentResult(True,
                               "3天内完成此内容打卡则视为胜出。\n获得枪法比赛胜出后,你感到自己的眼睛似乎拥有了可以放慢时间流速的能力...\n获得隐藏道具:死神之眼,你可以选择一条你拥有标记的纵列开一枪(选择向上开还是向下开),被子弹击中的玩家需要在3天内画一张打卡,主题为\"西部对决\",否则-5积分")
        elif choice == "比试酒量(小女孩禁选)":
            return ContentResult(True,
                               "3天内完成此内容打卡则视为胜出。\n你喝倒了酒馆内的所有人!你不仅赢得了免单,还获得了这儿最大的酒杯作为纪念品!(一个木桶大小的酒杯)\n获得隐藏道具:摇摇晃摇!——你酒后醉醺醺的左右摇晃,可以选择一个临时标记向左或向右移动到另一个纵列,rd2随机决定左右")
        elif choice == "比试骑术":
            self.achievement_dao.add_achievement(qq_id, 108, "飙马野郎", "normal")
            return ContentResult(True,
                               "3天内完成此内容打卡则视为胜出。\n你牵着自己的马儿到酒馆外,并以最快的速度绕着小镇跑完了一整圈。\n获得成就:飙马野郎")
        elif choice == "给他一拳!":
            return ContentResult(True,
                               "你一拳打在了那个大块头的鼻子上!随后酒馆中的人也纷纷凑上来,很快就变成了一场斗殴大混战!\n3天内完成此内容打卡则视为胜出。\n• (胜出)你将大块头打倒在地,这只是一个序曲,很快,你就成为了这个小镇最出名的牛仔,没过多久,就是这个洲,这个地区,甚至整个西部的传奇牛仔。直到最后你看着远方的日落...结束了这一段的旅行。获得成就:荒野大镖客\n• (失败)你被大块头打倒在地,并被丢出了酒馆,外面突然下起大雨,你满身泥泞...这个世界真是太不友好了!获得成就:荒野大窝囊")

    def _encounter_loop(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇52: 循环往复"""
        # 谜题类遭遇,不需要choice处理
        return ContentResult(True,
                           f"📖 {encounter_name}\n面前是标着发光exit的大门,难道说终于走到头了?!你拧下把手,推开,踏入……?\n"
                           f"不对,这里是哪里?门后一扇一模一样的门在不远处闪着光,与此同时,你拽着的门消失了,只剩下一个把手在你的手上。\n"
                           f"你莫名地回头,在身后不远处,看到了一个熟悉的后脑勺,ta的手上也空捏着个把手。不对……不对?!!")

    def _encounter_corridor(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇53: 回廊"""
        if choice is None:
            inventory = self.inventory_dao.get_inventory(qq_id)
            has_flashlight = any(item.item_name == "手电筒" for item in inventory)

            choices = ["贴墙潜行(消耗5积分)", "快步穿过"]
            if has_flashlight:
                choices.append("旋转手电筒(需要在[法庭]遭遇获得[手电筒])")

            return ContentResult(True,
                               f"📖 {encounter_name}\n潮湿的木板路,黑影们背对着你一动不动...",
                               requires_input=True,
                               choices=choices)

        if choice == "贴墙潜行":
            if self.player_dao.consume_score(qq_id, 5):
                return ContentResult(True,
                                   "你佝偻着身子,沿着墙角缓缓挪动,心跳声在寂静中格外清晰。黑影们似乎毫无察觉。直到你绕过拐角,这才敢松了一口气。无事发生")
            else:
                return ContentResult(False, "积分不足,无法选择此选项")
        elif choice == "快步穿过":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True,
                               "你鼓足一口气,低着头快步冲向出口。刚走到黑影中间,最靠近你的那个突然缓缓转过身,一张没有五官的空白脸正对向你,冰冷的指尖擦过你的手臂。眼前的景象瞬间被黑暗吞噬,只留下刺耳的风声…你的积分-5")
        elif choice == "旋转手电筒":
            dice_rolls = [random.randint(1, 6) for _ in range(3)]
            bonus_score = sum(dice_rolls)
            self.player_dao.add_score(qq_id, bonus_score)
            return ContentResult(True,
                               f"正当你不知如何是好抓耳挠腮之时,你突然摸到兜里还有之前获得的手电筒,于是心生一计…你点亮手电像陀螺般飞速转动,光束化作耀眼光圈,黑影们瞬间僵硬转身,被光线逼得连连后退。你趁机穿过通道,回头对着愣神的黑影,挑衅般晃了晃手电扫过他们的空白脸,转身就走。\n投掷3d6={dice_rolls},你的积分+{bonus_score}")

    def _encounter_programmer(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇54: 天下无程序员"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\"打…打打打…劫!\"一个崩溃的程序员冲出来拦住了你",
                               requires_input=True,
                               choices=["溜走", "呼叫主持人", "报告打劫的,没有陷阱卡"])

        if choice == "溜走":
            return ContentResult(True,
                               "可怜的程序员熬夜敲代码还要时时修bug,现在的体力自然是追不上你,你就这样轻松地跑开了。无事发生")
        elif choice == "呼叫主持人":
            return ContentResult(True,
                               "主持人立即叫来了安保队,可怜的程序员熬夜敲代码还要时时修bug,现在的体力自然是抵挡不住身强力壮的安保,被像拎小鸡仔一样拎走了。无事发生")
        elif choice == "报告打劫的,没有陷阱卡":
            return ContentResult(True,
                               ":怎…怎么没有?!\n:我有陷阱你没有\n:把…把把你…你的给我我不就有了吗?!\n:那你踩吧大哥\n可怜的程序员替你踩了陷阱,你免疫下一次陷阱的负面伤害",
                               {'immune_next_trap': True})

    def _encounter_art_gallery(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇55: 欢迎参观美术展"""
        if choice is None:
            player = self.player_dao.get_player(qq_id)
            choices = ["黄玫瑰(通用)"]
            if player.faction == "收养人":
                choices.insert(0, "红玫瑰(小女孩限定)")
            if player.faction == "Aeonreth":
                choices.insert(0, "蓝玫瑰(ae限定)")

            return ContentResult(True,
                               f"📖 {encounter_name}\n水下的Aeonreth画作...花瓶中有一枝玫瑰",
                               requires_input=True,
                               choices=choices)

        if choice == "红玫瑰":
            self.inventory_dao.add_item(qq_id, 9111, "红玫瑰", "hidden_item")
            return ContentResult(True,
                               "那是一枝娇艳的红玫瑰,柔弱的花瓣仿佛会流出鲜血。\n获得隐藏道具:红玫瑰。当你触发失败被动停止时,可以消耗该道具与10积分重新进行一轮投掷")
        elif choice == "蓝玫瑰":
            self.inventory_dao.add_item(qq_id, 9112, "蓝玫瑰", "hidden_item")
            return ContentResult(True,
                               "那是一枝坚韧的蓝玫瑰,花瓣泛着微微的光芒。\n获得隐藏道具:蓝玫瑰。当你的收养人触发失败被动停止时,你可以消耗该道具与10积分让其重新进行一轮投掷。如果无收养人则可以对自己使用")
        elif choice == "黄玫瑰":
            self.inventory_dao.add_item(qq_id, 9113, "黄玫瑰", "hidden_item")
            return ContentResult(True,
                               "那是一枝虚假的黄玫瑰,塑料制成的花瓣永远不会枯萎。\n获得隐藏道具:黄玫瑰。你消耗该道具后,可指定一名玩家在移动临时标记时必须被迫重新进行投掷,且必须采用新一轮投掷的结果")

    def _encounter_real_story(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇56: 真实的经历"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n你穿越回了活动开始前,系统崩溃了!",
                               requires_input=True,
                               choices=["询问工程师", "调查服务器"])

        if choice == "询问工程师":
            self.inventory_dao.add_item(qq_id, 9114, "《写代码从入门到入土》", "hidden_item")
            self.inventory_dao.add_item(qq_id, 9115, "《五年代码三年bug》", "hidden_item")
            return ContentResult(True,
                               "\"师傅你是做什么工作的?\"你也不知道为什么脱口而出了这样的话,技术部的成员疑惑地看着你。随后他递给了你一本册子,上面写着《写代码从入门到入土》。\n获得隐藏物品:《写代码从入门到入土》、《五年代码三年bug》")
        elif choice == "调查服务器":
            self.player_dao.add_score(qq_id, 10)
            self.achievement_dao.add_achievement(qq_id, 109, "超时空救兵", "normal")
            return ContentResult(True,
                               "你觉得去检查服务器,或许是那里出了问题...果不其然,你在机房中发现了一只戴着红色围巾的企鹅,正在啃食OAS协会的服务器。你赶跑了那只企鹅,系统终于恢复了正常,活动如期开始!\n你的积分+10\n获得成就:超时空救兵")

    def _encounter_sisyphus(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇57: 初次见面"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n西西弗斯和他的巨石,你口袋多了一瓶金色酒液",
                               requires_input=True,
                               choices=["来都来了,送西西弗斯", "呃,送巨石?", "我自己喝!"])

        if choice == "来都来了,送西西弗斯":
            self.player_dao.add_score(qq_id, 20)
            return ContentResult(True,
                               "大个子不好意思地用蒲扇大的手挠着后脑勺,但还是收下了,作为回报,他送了你一些亮晶晶的小东西。你的积分+20")
        elif choice == "呃,送巨石?":
            self.player_dao.add_score(qq_id, 20)
            self.achievement_dao.add_achievement(qq_id, 110, "巨石的祝福", "hidden")
            return ContentResult(True,
                               "你恭恭敬敬地给这个两个大洞充作眼一个小洞做鼻子的巨石送了礼,不知道是不是你的错觉,你这么做了后,你的身体变得轻快了些。\n获得隐藏成就:巨石的祝福\n你的积分+20")
        elif choice == "我自己喝!":
            self.player_dao.add_score(qq_id, -20)
            return ContentResult(True,
                               "你拿起这瓶不知道从何而来的蜜露就往嘴里灌,金色的酒液尚未接触到你嘴唇,香气就几乎把你击倒。顺滑的液体黄金滑入你的咽喉,你不知道什么时候失去了意识,再次醒来时,周围已空无一物,只有身边躺着的那个圆形酒瓶提醒着你并非黄粱一梦。虽然蜜露确实美味,但是,喝酒误事啊!你不知道你昏迷了多久,只知道肯定耽误了不少时间。你的积分-20")

    def _encounter_underworld(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇58: 冥府之路"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n高耸的石制宫殿,一个声音告诉你不要回头,一直往前走",
                               requires_input=True,
                               choices=["我听劝,拜拜了您嘞。", "我倒要看看是什么东西!"])

        if choice == "我听劝,拜拜了您嘞。":
            self.inventory_dao.add_item(qq_id, 9116, "冥府里拉琴", "hidden_item")
            return ContentResult(True,
                               "也许你仍对这个声音有疑问,又或许你对这个声音深信不疑,但总之你选择听从建议。你一路快步走到了宫殿的尽头,当你踏入尽头处的光芒中之后,你隐约听到有人轻松的谢意从你耳边飘过。手中一重,出现了一把古朴的里拉琴。\n获得隐藏道具:冥府里拉琴。使用可让契约对象当前的任意临时标记向前一格;如没有契约对象,则可以让自己当前的任意临时标记向前一格")
        elif choice == "我倒要看看是什么东西!":
            return ContentResult(True,
                               "你是个有主见的个体!怎么能说不看就不看!你选择了违背那个声音,但当你回头的一瞬间,那个远远缀着你的身影一下变得僵硬,从头到脚,缓慢地泛起白,再崩起了一阵烟尘,最后失去了人形,化作大大小小的块状散落在地。你靠近一看,是盐块。无事发生")

    def _encounter_name(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇59: 名字"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n\"(群昵称名字),我叫你一声你敢答应吗?\"",
                               requires_input=True,
                               choices=["不敢不敢", "那我叫你一声你敢答应吗?", "唉多…"])

        if choice == "不敢不敢":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True,
                               "你一秒认怂,奈何对方还是对你纠缠不放,你只好上交过路费免得又给自己添不必要的麻烦。你的积分-5")
        elif choice == "那我叫你一声你敢答应吗?":
            dice_roll = random.randint(1, 6)
            if dice_roll >= 4:
                return ContentResult(True,
                                   f"d6={dice_roll}≥4 你骗过了对方,在他犹豫畏惧之时快步逃离了。无事发生")
            else:
                return ContentResult(True,
                                   f"d6={dice_roll}<4 你自作聪明,可你的身上根本没有相似的法宝,被对方一眼识破,把你收进了葫芦之中。\n你强制结束本轮次并额外消耗一回合积分",
                                   {'skip_rounds': 1, 'force_end_turn': True})
        elif choice == "唉多…":
            self.player_dao.add_score(qq_id, 10)
            self.inventory_dao.add_item(qq_id, 9117, "黑金绿葫芦", "hidden_item")
            return ContentResult(True,
                               "你爽快地点头并回答了他,但是什么都没有发生。对方恼羞成怒,\"怎么回事??!为什么没有反应?!!\"\n\"(群昵称名字)是谁啊?\"你邪魅一笑,原来你根本没有使用本名注册参加游戏。对方被你耍得团团转,你趁他气急败坏顺走了他的宝物和小钱钱。\n你的积分+10\n获得隐藏物品:黑金绿葫芦")

    def _encounter_fog(self, qq_id: str, encounter_name: str, choice: str = None) -> ContentResult:
        """遭遇60: 浓雾之中"""
        if choice is None:
            return ContentResult(True,
                               f"📖 {encounter_name}\n浓雾弥漫,你撞到了一个人,他示意你放轻声音",
                               requires_input=True,
                               choices=["听你的,VOL--", "老师我看不明白", "我就喜欢反着干,VOL++"])

        if choice == "听你的,VOL--":
            self.player_dao.add_score(qq_id, 5)
            return ContentResult(True,
                               "虽然来路不明但是此人这么做想来有他的道理,你用近乎耳语的声音向询问他是否见过离开这里的门。他似乎对你识时务的行为感到一阵放松,蹑手蹑脚地带着你走了一阵,很快便找到了通往下一个地点的门。这效率可比你自己找路要快多了,你正想向他道谢,一回头他已不见了踪影,融入了那片来时的浓雾。你的积分+5")
        elif choice == "老师我看不明白":
            self.player_dao.add_score(qq_id, -5)
            return ContentResult(True,
                               "不管你是真没懂还是假没懂,你无视他的手势以正常的音量询问了门的方位,在话音出口的一瞬间,你汗毛倒竖——只因浓雾里似乎有无数双眼睛齐刷刷地转过来注视着你。没人告诉你雾里全都是人啊!!那个人似乎对因为你不适当的音量引起的注意心惊胆战,在你分神的一瞬间就迅速无声滑进了浓雾,消失不见。这下,得靠你自己找路了。你的积分-5")
        elif choice == "我就喜欢反着干,VOL++":
            self.player_dao.add_score(qq_id, -20)
            return ContentResult(True,
                               "你靠近他,却深吸了一口气大声在侧耳倾听的他耳朵边上用相当大的音量喊出了关于门在哪里的问句。他被你吓得哆嗦了一下摔进了浓雾里,消失了踪影。但当你还在为恶作剧沾沾自喜时,你浑然未觉多少道视线锁定了你。直到……第一声犬吠响起。你的积分-20")

    # ==================== 道具使用 ====================

    def use_item(self, qq_id: str, item_id: int, item_name: str, **kwargs) -> ContentResult:
        """
        使用道具

        Args:
            qq_id: 玩家QQ号
            item_id: 道具ID
            item_name: 道具名称
            **kwargs: 额外参数(如choice等)

        Returns:
            ContentResult对象
        """
        # 检查玩家是否拥有该道具
        inventory = self.inventory_dao.get_inventory(qq_id)
        has_item = any(item.item_id == item_id for item in inventory)

        if not has_item:
            return ContentResult(False, f"你没有道具：{item_name}")

        # 道具使用映射
        item_handlers = {
            1: self._use_reload_save,           # 败者尘
            2: self._use_fly_forward,           # 放飞小○!
            3: self._use_sweet_talk,            # 花言巧语
            4: self._use_hammer_party,          # 揍击派对
            5: self._use_heavy_sword,           # 沉重的巨剑
            6: self._use_witch_trick,           # 女巫的魔法伎俩
            7: self._use_grow_mushroom,         # 变大蘑菇
            8: self._use_shrink_potion,         # 缩小药水
            9: self._use_super_cannon,          # 超级大炮
            10: self._use_golden_star,          # :)
            11: self._use_ae_mirror,            # 闹Ae魔镜
            12: self._use_girl_doll,            # 小女孩娃娃
            13: self._use_bonfire,              # 火堆
            14: self._use_liminal_space,        # 阈限空间
            15: self._use_pear,                 # 一斤鸭梨!
            16: self._use_the_room,             # The Room
            17: self._use_my_map,               # 我的地图
            18: self._use_rainbow_gems,         # 五彩宝石
            19: self._use_shopping_card,        # 购物卡
            20: self._use_biango_meow,          # Biango Meow
            21: self._use_black_meow,           # 黑喵
            22: self._use_fire_statue,          # 火人雕像
            23: self._use_ice_statue,           # 冰人雕像
            24: self._use_soul_leaf,            # 灵魂之叶
        }

        handler = item_handlers.get(item_id)
        if handler:
            result = handler(qq_id, **kwargs)
            # 如果使用成功，从背包移除
            if result.success and not result.requires_input:
                self.inventory_dao.remove_item(qq_id, item_id, 'item')
            return result

        return ContentResult(False, f"道具 {item_name} 的使用效果尚未实现")

    def _use_reload_save(self, qq_id: str, **kwargs) -> ContentResult:
        """道具1: 败者尘 - 重新投掷"""
        return ContentResult(True,
                           "使用败者尘！清空本回合点数，准备重新投掷",
                           {'clear_round': True, 'allow_reroll': True})

    def _use_fly_forward(self, qq_id: str, **kwargs) -> ContentResult:
        """道具2: 放飞小○! - 最远临时标记前进2格"""
        return ContentResult(True,
                           "放飞小○！你离终点最远的临时标记向前移动两格",
                           {'move_farthest_temp': 2})

    def _use_sweet_talk(self, qq_id: str, target_qq: str = None, **kwargs) -> ContentResult:
        """道具3: 花言巧语 - 封锁对手列"""
        if not target_qq:
            return ContentResult(False, "请指定目标玩家QQ号")

        return ContentResult(True,
                           f"使用花言巧语！目标玩家下一轮不能在其当前轮次的列上行进\n目标可投掷d6，出目6可抵消",
                           {'block_target': target_qq})

    def _use_hammer_party(self, qq_id: str, column: int = None, position: int = None, **kwargs) -> ContentResult:
        """道具4: 揍击派对 - 指定位置所有标记倒退1格"""
        if column is None or position is None:
            return ContentResult(False, "请指定列号和位置 (格式: column, position)")

        return ContentResult(True,
                           f"使用揍击派对！在({column}, {position})召唤疯狂大摆锤",
                           {'hammer_position': (column, position)})

    def _use_heavy_sword(self, qq_id: str, **kwargs) -> ContentResult:
        """道具5: 沉重的巨剑 - 重掷出1的骰子"""
        return ContentResult(True,
                           "使用沉重的巨剑！若掷出1，可以选择重掷一次",
                           {'reroll_on_one': True})

    def _use_witch_trick(self, qq_id: str, **kwargs) -> ContentResult:
        """道具6: 女巫的魔法伎俩 - 重掷出6的骰子"""
        return ContentResult(True,
                           "使用女巫的魔法伎俩！若掷出6，可以选择重掷一次",
                           {'reroll_on_six': True})

    def _use_grow_mushroom(self, qq_id: str, choice: str = None, **kwargs) -> ContentResult:
        """道具7: 变大蘑菇 - 所有出目+1"""
        if choice is None:
            return ContentResult(True,
                               "获得变大蘑菇！",
                               requires_input=True,
                               choices=["吃", "不吃"])

        if choice == "吃":
            return ContentResult(True,
                               "你吃下了蘑菇，身体不断变大！下次投掷所有结果+1",
                               {'all_dice_plus': 1})
        elif choice == "不吃":
            return ContentResult(True, "看起来有毒，还是算了")

    def _use_shrink_potion(self, qq_id: str, choice: str = None, **kwargs) -> ContentResult:
        """道具8: 缩小药水 - 所有出目-1"""
        if choice is None:
            return ContentResult(True,
                               "获得缩小药水！",
                               requires_input=True,
                               choices=["喝", "不喝"])

        if choice == "喝":
            return ContentResult(True,
                               "你喝下了药水，身体不断缩小！下次投掷所有结果-1",
                               {'all_dice_minus': 1})
        elif choice == "不喝":
            return ContentResult(True, "陌生人给的不能随便喝，还是算了")

    def _use_super_cannon(self, qq_id: str, desired_rolls: list = None, **kwargs) -> ContentResult:
        """道具9: 超级大炮 - 直接指定出目"""
        if not desired_rolls:
            return ContentResult(False, "请指定需要的出目 (格式: [1,2,3,4,5,6])")

        return ContentResult(True,
                           f"使用超级大炮！直接指定出目: {desired_rolls}",
                           {'forced_rolls': desired_rolls})

    def _use_golden_star(self, qq_id: str, choice: str = None, **kwargs) -> ContentResult:
        """道具10: :) - 临时标记转永久"""
        if choice is None:
            return ContentResult(True,
                               "一颗金色的星星在闪耀！",
                               requires_input=True,
                               choices=["互动", "不互动"])

        if choice == "互动":
            return ContentResult(True,
                               "这使你充满了决心！本次移动的临时标记转换为永久标记且你可以继续进行当前轮次",
                               {'temp_to_permanent': True, 'continue_round': True})
        elif choice == "不互动":
            return ContentResult(True, "你走了")

    def _use_ae_mirror(self, qq_id: str, specified_rolls: list = None, **kwargs) -> ContentResult:
        """道具11: 闹Ae魔镜 - 消耗积分指定出目"""
        player = self.player_dao.get_player(qq_id)
        # TODO: 检查是否有契约ae

        if not specified_rolls:
            return ContentResult(False, "请指定出目数值 (每个消耗10积分，格式: [1,2,3])")

        cost = len(specified_rolls) * 10
        if player.current_score < cost:
            return ContentResult(False, f"积分不足！需要{cost}积分")

        self.player_dao.add_score(qq_id, -cost)
        return ContentResult(True,
                           f"使用闹Ae魔镜！消耗{cost}积分，指定出目: {specified_rolls}",
                           {'partial_forced_rolls': specified_rolls})

    def _use_girl_doll(self, qq_id: str, choice: str = None, **kwargs) -> ContentResult:
        """道具12: 小女孩娃娃 - 免疫陷阱"""
        # TODO: 检查是否有契约小女孩
        if choice is None:
            return ContentResult(True,
                               "一个小女孩模样的娃娃",
                               requires_input=True,
                               choices=["戳戳脸蛋", "戳戳手", "拽拽腿"])

        if choice == "戳戳脸蛋":
            return ContentResult(True,
                               "小女孩对你笑笑。下个陷阱可以消耗5积分免疫",
                               {'trap_immunity_cost': 5})
        elif choice == "戳戳手":
            return ContentResult(True,
                               "小女孩拉拉你的手。下个陷阱可以通过绘制相关内容免疫",
                               {'trap_immunity_draw': True})
        elif choice == "拽拽腿":
            return ContentResult(True, "小女孩踹了你一脚，有点疼疼的")

    def _use_bonfire(self, qq_id: str, **kwargs) -> ContentResult:
        """道具13: 火堆 - 刷新上一个道具"""
        return ContentResult(True,
                           "使用火堆！可以刷新上一个已使用道具的效果",
                           {'refresh_last_item': True})

    def _use_liminal_space(self, qq_id: str, **kwargs) -> ContentResult:
        """道具14: 阈限空间 - 失败后重投"""
        return ContentResult(True,
                           "使用阈限空间！触发失败被动结束后可重新进行上一回合",
                           {'allow_retry_on_fail': True})

    def _use_pear(self, qq_id: str, reroll_values: list = None, **kwargs) -> ContentResult:
        """道具15: 一斤鸭梨! - 任选3个出目重投

        Args:
            qq_id: 玩家QQ号
            reroll_values: 要重投的骰子点数列表（例如 [3, 1, 6]）
        """
        if not reroll_values:
            return ContentResult(False, "请指定要重投的3个骰子点数\n格式：使用一斤鸭梨！ 3,1,6")

        if len(reroll_values) != 3:
            return ContentResult(False, "必须选择3个骰子点数重投")

        # 验证点数范围
        for val in reroll_values:
            if val < 1 or val > 6:
                return ContentResult(False, f"骰子点数 {val} 无效，必须在1-6之间")

        # 获取当前骰子结果
        from database.dao import GameStateDAO
        state_dao = GameStateDAO(self.conn)
        state = state_dao.get_state(qq_id)

        if not state.last_dice_result or len(state.last_dice_result) != 6:
            return ContentResult(False, "请先投掷6个骰子")

        # 从当前结果中移除指定点数的骰子（各移除一个）
        current_dice = state.last_dice_result.copy()
        kept_dice = []
        reroll_targets = reroll_values.copy()

        for die in current_dice:
            if die in reroll_targets:
                # 这个骰子要重投，从reroll_targets中移除一个
                reroll_targets.remove(die)
            else:
                # 保留这个骰子
                kept_dice.append(die)

        # 检查是否成功移除了所有指定点数
        if len(reroll_targets) > 0:
            missing = ', '.join(map(str, reroll_targets))
            return ContentResult(False, f"当前骰子结果中没有点数：{missing}")

        if len(kept_dice) != 3:
            return ContentResult(False, f"保留骰子数量错误（{len(kept_dice)}个），应该是3个")

        # 重新投掷3个d6
        import random
        new_dice = [random.randint(1, 6) for _ in range(3)]

        # 组合成新的6个骰子结果
        final_dice = kept_dice + new_dice

        # 更新玩家的骰子结果
        state.last_dice_result = final_dice
        state_dao.update_state(state)

        return ContentResult(True,
                           f"✨ 使用一斤鸭梨！\n"
                           f"原结果：{' '.join(map(str, current_dice))}\n"
                           f"保留骰子：{' '.join(map(str, kept_dice))}\n"
                           f"重投骰子：{' '.join(map(str, new_dice))}\n"
                           f"🎲 新结果：{' '.join(map(str, final_dice))}")

    def _use_the_room(self, qq_id: str, location: str = None, **kwargs) -> ContentResult:
        """道具16: The Room - 探索获得直接登顶机会"""
        if location is None:
            return ContentResult(True,
                               "一处可原地展开的虚拟密闭空间！\n请选择探索位置：",
                               requires_input=True,
                               choices=["桌子-抽屉", "桌子-摆件", "桌子-连接处",
                                      "放映机-把手", "放映机-胶卷", "放映机-架子",
                                      "柜子-隔断", "柜子-柜门", "柜子-顶端",
                                      "地板-地砖", "地板-墙角", "地板-地毯"])

        if location == "桌子-连接处":
            return ContentResult(True,
                               "你发现了一个隐藏的小抽屉，里面有一个协会特制徽章！",
                               requires_input=True,
                               choices=["直接登顶", "放弃"])
        else:
            return ContentResult(True, "什么都没有发现...")

    def _use_my_map(self, qq_id: str, new_column: int = None, new_position: int = None, **kwargs) -> ContentResult:
        """道具17: 我的地图 - 免疫陷阱并移动陷阱位置"""
        if new_column is None or new_position is None:
            return ContentResult(False, "请指定要移动陷阱到的新位置 (格式: column, position)")

        return ContentResult(True,
                           f"使用我的地图！免疫陷阱并将其移动到({new_column}, {new_position})",
                           {'move_trap_to': (new_column, new_position)})

    def _use_rainbow_gems(self, qq_id: str, **kwargs) -> ContentResult:
        """道具18: 五彩宝石 - 投掷决定效果"""
        dice_sum = sum([random.randint(1, 6) for _ in range(6)])

        if dice_sum > 9:
            return ContentResult(True,
                               f"投掷结果: {dice_sum} > 9\n全场随机一半玩家积分-10",
                               {'random_half_minus': 10})
        else:
            self.player_dao.add_score(qq_id, -50)
            return ContentResult(True,
                               f"投掷结果: {dice_sum} ≤ 9\n你的积分-50")

    def _use_shopping_card(self, qq_id: str, **kwargs) -> ContentResult:
        """道具19: 购物卡 - 商店物品半价"""
        return ContentResult(True,
                           "使用购物卡！下次购买商店物品半价",
                           {'next_purchase_half': True})

    def _use_biango_meow(self, qq_id: str, **kwargs) -> ContentResult:
        """道具20: Biango Meow - 随机奖励"""
        rewards = [
            ("30积分", {'score': 30}),
            ("道具卡：The Room", {'item': 16}),
            ("道具卡：阈限空间", {'item': 14}),
            ("道具卡：:）", {'item': 10}),
        ]

        reward = random.choice(rewards)

        if 'score' in reward[1]:
            self.player_dao.add_score(qq_id, reward[1]['score'])
        elif 'item' in reward[1]:
            self.inventory_dao.add_item(qq_id, reward[1]['item'], reward[0].split('：')[1], 'item')

        return ContentResult(True, f"Biango Meow! 喵～\n获得随机奖励: {reward[0]}")

    def _use_black_meow(self, qq_id: str, **kwargs) -> ContentResult:
        """道具21: 黑喵 - 永久减少回合积分消耗"""
        return ContentResult(True,
                           "使用黑喵！你之后的所有回合所需要消耗的积分-2",
                           {'permanent_cost_reduction': 2})

    def _use_fire_statue(self, qq_id: str, **kwargs) -> ContentResult:
        """道具22: 火人雕像 - 随机生成红宝石和蓝池沼"""
        # 随机选择未到达的格子
        return ContentResult(True,
                           "使用火人雕像！在地图上随机生成红色宝石(+100积分)和蓝色池沼(-10积分)",
                           {'spawn_gems': 'fire'})

    def _use_ice_statue(self, qq_id: str, **kwargs) -> ContentResult:
        """道具23: 冰人雕像 - 随机生成蓝宝石和红池沼"""
        return ContentResult(True,
                           "使用冰人雕像！在地图上随机生成蓝色宝石(+100积分)和红色池沼(-10积分)",
                           {'spawn_gems': 'ice'})

    def _use_soul_leaf(self, qq_id: str, column: int = None, **kwargs) -> ContentResult:
        """道具24: 灵魂之叶 - 永久棋子前进1格"""
        if column is None:
            return ContentResult(False, "请指定要移动的永久棋子所在列号")

        return ContentResult(True,
                           f"使用灵魂之叶！第{column}列的永久棋子向前移动一格",
                           {'move_permanent': (column, 1)})

    # ==================== 隐藏成就检测 ====================

    def check_hidden_achievements(self, qq_id: str, event_type: str, **kwargs):
        """检查并触发隐藏成就"""

        if event_type == 'return_home':
            # 成就1: 领地意识 - 在同一列回家三次
            column = kwargs.get('column')
            counter_key = f'return_home_column_{column}'
            count = self._increment_and_get(qq_id, counter_key)
            if count >= 3:
                if not self.achievement_dao.has_achievement(qq_id, 1, 'hidden'):
                    self.achievement_dao.add_achievement(qq_id, 1, "领地意识", "hidden")
                    self.inventory_dao.add_item(qq_id, 9001, "修改液", "hidden_item")
                    return "恭喜解锁隐藏成就【领地意识】\n您已在当前列回家三次\n获得隐藏奖励：修改液"

        elif event_type == 'first_trap':
            # 成就2: 出门没看黄历 - 遭遇三次首达陷阱
            count = self._increment_and_get(qq_id, 'first_trap_count')
            if count >= 3:
                if not self.achievement_dao.has_achievement(qq_id, 2, 'hidden'):
                    self.achievement_dao.add_achievement(qq_id, 2, "出门没看黄历", "hidden")
                    self.inventory_dao.add_item(qq_id, 9002, "风水罗盘", "hidden_item")
                    return "恭喜解锁隐藏成就【出门没看黄历】\n您已遭遇三次首达陷阱\n获得隐藏奖励：风水罗盘"

        elif event_type == 'one_round_complete':
            # 成就3: 看我一命通关！ - 一轮次内从起点到达列终点
            if not self.achievement_dao.has_achievement(qq_id, 3, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 3, "看我一命通关！", "hidden")
                self.inventory_dao.add_item(qq_id, 9003, "奇妙的变身器", "hidden_item")
                return "恭喜解锁隐藏成就【看我一命通关！】\n真正的读狗无惧挑战！\n获得隐藏奖励：奇妙的变身器"

        elif event_type == 'unlock_all_items':
            # 成就4: 收集癖 - 解锁全部地图及可购买道具
            if not self.achievement_dao.has_achievement(qq_id, 4, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 4, "收集癖", "hidden")
                return "恭喜解锁隐藏成就【收集癖】\n不拿全浑身难受啊\n您现在可以私信管理员领取自定义头衔"

        elif event_type == 'dice_all_ones':
            # 成就5: 一鸣惊人 - 掷骰结果均为1
            if not self.achievement_dao.has_achievement(qq_id, 5, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 5, "一鸣惊人", "hidden")
                self.inventory_dao.add_item(qq_id, 9005, "一本很火的同人画集", "hidden_item")
                return "恭喜解锁隐藏成就【一鸣惊人】\n六个骰子全是1！\n获得隐藏奖励：一本很火的同人画集"

        elif event_type == 'dice_all_sixes':
            # 成就6: 六六大顺 - 掷骰结果均为6
            if not self.achievement_dao.has_achievement(qq_id, 6, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 6, "六六大顺", "hidden")
                self.inventory_dao.add_item(qq_id, 9006, "恶魔的祝福", "hidden_item")
                return "恭喜解锁隐藏成就【六六大顺】\n六个骰子全是6！\n获得隐藏奖励：恶魔的祝福"

        elif event_type == 'self_harm':
            # 成就7: 自巡航 - 使用道具时触发陷阱/自己触发惩罚
            if not self.achievement_dao.has_achievement(qq_id, 7, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 7, "自巡航", "hidden")
                self.inventory_dao.add_item(qq_id, 9007, "婴儿般的睡眠", "hidden_item")
                return "恭喜解锁隐藏成就【自巡航】\n自巡航导弹但是是自己的自\n获得隐藏奖励：婴儿般的睡眠（下一回合免费）"

        elif event_type == 'trap_avoided':
            # 成就8: 雪中送炭 - 遭遇陷阱后触发奖励/规避惩罚
            if not self.achievement_dao.has_achievement(qq_id, 8, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 8, "雪中送炭", "hidden")
                self.inventory_dao.add_item(qq_id, 9008, "欧皇王冠", "hidden_item")
                return "恭喜解锁隐藏成就【雪中送炭】\n惩罚了吗？哎↗ 没有～\n获得隐藏奖励：欧皇王冠"

            # 成就12: 主持人的猜忌 - 2次在遭遇陷阱后触发奖励/规避惩罚
            count = self._increment_and_get(qq_id, 'trap_avoided_count')
            if count >= 2:
                if not self.achievement_dao.has_achievement(qq_id, 12, 'hidden'):
                    self.achievement_dao.add_achievement(qq_id, 12, "主持人的猜忌", "hidden")
                    self.inventory_dao.add_item(qq_id, 9012, "黄牌警告", "hidden_item")
                    return "恭喜解锁隐藏成就【主持人的猜忌】\n获得隐藏奖励：黄牌警告"

        elif event_type == 'encounter_nothing':
            # 成就9: 平平淡淡才是真 - 遭遇中三次选择结果均无事发生
            count = self._increment_and_get(qq_id, 'encounter_nothing_count')
            if count >= 3:
                if not self.achievement_dao.has_achievement(qq_id, 9, 'hidden'):
                    self.achievement_dao.add_achievement(qq_id, 9, "平平淡淡才是真", "hidden")
                    self.inventory_dao.add_item(qq_id, 9009, "老头款大背心", "hidden_item")
                    return "恭喜解锁隐藏成就【平平淡淡才是真】\n啊？还有这事？\n获得隐藏奖励：老头款大背心"

        elif event_type == 'encounter_special':
            # 成就10: 善恶有报 - 遭遇中三次选择结果均触发特殊效果
            count = self._increment_and_get(qq_id, 'encounter_special_count')
            if count >= 3:
                if not self.achievement_dao.has_achievement(qq_id, 10, 'hidden'):
                    self.achievement_dao.add_achievement(qq_id, 10, "善恶有报", "hidden")
                    self.inventory_dao.add_item(qq_id, 9010, "游戏机打折券", "hidden_item")
                    return "恭喜解锁隐藏成就【善恶有报】\n怪我吗？\n获得隐藏奖励：游戏机打折券"

        # 成就11: 天机算不尽 - 已解锁3个隐藏成就
        hidden_count = self._get_hidden_achievement_count(qq_id)
        if hidden_count >= 3:
            if not self.achievement_dao.has_achievement(qq_id, 11, 'hidden'):
                self.achievement_dao.add_achievement(qq_id, 11, "天机算不尽", "hidden")
                self.inventory_dao.add_item(qq_id, 9011, "套娃", "hidden_item")
                return "恭喜解锁隐藏成就【天机算不尽】\n是劫还是缘\n获得隐藏奖励：套娃"

        return None

    def _increment_and_get(self, qq_id: str, counter_type: str) -> int:
        """增加计数器并返回新值"""
        self._increment_achievement_counter(qq_id, counter_type, 1)
        return self.get_achievement_counter(qq_id, counter_type)

    def _get_hidden_achievement_count(self, qq_id: str) -> int:
        """获取玩家已解锁的隐藏成就数量"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM player_achievements
            WHERE qq_id = ? AND achievement_type = 'hidden'
        ''', (qq_id,))
        row = cursor.fetchone()
        return row['count'] if row else 0

    # ==================== 辅助方法 ====================

    def _increment_achievement_counter(self, qq_id: str, counter_type: str, amount: int = 1):
        """增加成就计数器"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO achievement_counters (qq_id, counter_type, count)
            VALUES (?, ?, ?)
            ON CONFLICT(qq_id, counter_type)
            DO UPDATE SET count = count + ?
        ''', (qq_id, counter_type, amount, amount))
        self.conn.commit()

    def get_achievement_counter(self, qq_id: str, counter_type: str) -> int:
        """获取成就计数器"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT count FROM achievement_counters
            WHERE qq_id = ? AND counter_type = ?
        ''', (qq_id, counter_type))
        row = cursor.fetchone()
        return row['count'] if row else 0
