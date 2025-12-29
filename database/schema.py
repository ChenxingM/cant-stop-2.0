# -*- coding: utf-8 -*-
"""
数据库表结构定义
Database Schema for Can't Stop Game
"""

import sqlite3
from pathlib import Path
from datetime import datetime


class DatabaseSchema:
    """数据库结构管理类"""

    @staticmethod
    def create_tables(conn: sqlite3.Connection):
        """创建所有数据库表"""
        cursor = conn.cursor()

        # ==================== 玩家基础信息表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            qq_id TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            faction TEXT CHECK(faction IN ('收养人', 'Aeonreth', NULL)),
            total_score INTEGER DEFAULT 0,
            current_score INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # ==================== 玩家位置表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,
            column_number INTEGER NOT NULL,
            position INTEGER NOT NULL,
            marker_type TEXT CHECK(marker_type IN ('temp', 'permanent')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (qq_id) REFERENCES players(qq_id),
            UNIQUE(qq_id, column_number, marker_type)
        )
        ''')

        # ==================== 玩家背包/道具表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,
            item_type TEXT CHECK(item_type IN ('item', 'hidden_item', 'special')),
            item_id INTEGER,
            item_name TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            obtained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (qq_id) REFERENCES players(qq_id)
        )
        ''')

        # ==================== 成就记录表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,
            achievement_id INTEGER NOT NULL,
            achievement_name TEXT NOT NULL,
            achievement_type TEXT CHECK(achievement_type IN ('normal', 'hidden', 'first_clear')),
            obtained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (qq_id) REFERENCES players(qq_id),
            UNIQUE(qq_id, achievement_id, achievement_type)
        )
        ''')

        # ==================== 游戏状态表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_state (
            qq_id TEXT PRIMARY KEY,
            current_round_active BOOLEAN DEFAULT 0,
            can_start_new_round BOOLEAN DEFAULT 1,
            temp_markers_used INTEGER DEFAULT 0,
            dice_history TEXT,
            last_dice_result TEXT,
            topped_columns TEXT,
            skipped_rounds INTEGER DEFAULT 0,
            pending_encounter TEXT,
            FOREIGN KEY (qq_id) REFERENCES players(qq_id)
        )
        ''')

        # 为已存在的game_state表添加字段（如果不存在）
        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN skipped_rounds INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN pending_encounter TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN extra_d6_check_six INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN pending_encounters TEXT')
        except sqlite3.OperationalError:
            pass

        # 陷阱效果相关字段
        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN next_dice_fixed TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN next_dice_count INTEGER')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN next_dice_groups TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN current_dice_count INTEGER')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN current_dice_groups TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN forced_remaining_rounds INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN odd_even_check_active INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN math_check_active INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN lockout_until TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN pending_trap_choice TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN trap_immunity_cost INTEGER')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN trap_immunity_draw INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN trap_immunity_count INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN requires_drawing INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN sweet_talk_blocked TEXT')
        except sqlite3.OperationalError:
            pass

        # 道具效果相关字段
        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN allow_reroll INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN reroll_on_one INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN reroll_on_six INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN all_dice_modifier INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN forced_rolls TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN partial_forced_rolls TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN allow_retry_on_fail INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN next_purchase_half INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN cost_reduction INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN last_used_item_id INTEGER')
        except sqlite3.OperationalError:
            pass

        # 遭遇效果相关字段
        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN immune_next_trap INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN free_rounds INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN next_roll_double_cost INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN change_one_dice_available INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN use_last_dice_available INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN frozen_columns TEXT')
        except sqlite3.OperationalError:
            pass

        # 新增遭遇效果字段
        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN must_draw_double INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN force_end_until_draw INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN next_dice_modify_any INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN next_dice_add_3_any INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN disabled_columns_this_round TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN pending_duel TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN pending_bonus_trigger TEXT')
        except sqlite3.OperationalError:
            pass

        # 限时打卡系统
        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN pending_timed_checkins TEXT')
        except sqlite3.OperationalError:
            pass

        # 玫瑰道具字段
        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN has_red_rose INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN has_blue_rose_from TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN yellow_rose_target TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE game_state ADD COLUMN force_reroll_next_move INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        # ==================== 商店道具表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS shop_items (
            item_id INTEGER PRIMARY KEY,
            item_name TEXT UNIQUE NOT NULL,
            item_type TEXT,
            price INTEGER NOT NULL,
            faction_limit TEXT,
            global_limit INTEGER DEFAULT -1,
            global_sold INTEGER DEFAULT 0,
            unlocked BOOLEAN DEFAULT 0,
            description TEXT,
            player_limit INTEGER DEFAULT -1
        )
        ''')

        # 添加 player_limit 字段（如果不存在）
        try:
            cursor.execute('ALTER TABLE shop_items ADD COLUMN player_limit INTEGER DEFAULT -1')
        except sqlite3.OperationalError:
            pass

        # ==================== 每日限制记录表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            date TEXT NOT NULL,
            FOREIGN KEY (qq_id) REFERENCES players(qq_id),
            UNIQUE(qq_id, action_type, date)
        )
        ''')

        # ==================== 地图内容触发记录表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS content_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            column_number INTEGER NOT NULL,
            position INTEGER NOT NULL,
            content_type TEXT CHECK(content_type IN ('encounter', 'item', 'trap')),
            content_id INTEGER NOT NULL,
            first_trigger_qq TEXT,
            first_trigger_time TIMESTAMP,
            trigger_count INTEGER DEFAULT 0
        )
        ''')

        # ==================== 首达记录表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS first_achievements (
            column_number INTEGER PRIMARY KEY,
            first_qq_id TEXT NOT NULL,
            achieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (first_qq_id) REFERENCES players(qq_id)
        )
        ''')

        # ==================== 隐藏成就计数器表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS achievement_counters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,
            counter_type TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            FOREIGN KEY (qq_id) REFERENCES players(qq_id),
            UNIQUE(qq_id, counter_type)
        )
        ''')

        # ==================== 游戏通关排名表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_rankings (
            rank INTEGER PRIMARY KEY,
            qq_id TEXT NOT NULL,
            finished_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (qq_id) REFERENCES players(qq_id)
        )
        ''')

        # ==================== 契约关系表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1_qq TEXT NOT NULL,
            player2_qq TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (player1_qq) REFERENCES players(qq_id),
            FOREIGN KEY (player2_qq) REFERENCES players(qq_id),
            UNIQUE(player1_qq),
            UNIQUE(player2_qq)
        )
        ''')

        # ==================== 宝石池沼表 ====================
        # 存储火人雕像/冰人雕像生成的宝石和池沼
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS gem_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_qq TEXT NOT NULL,
            gem_type TEXT NOT NULL CHECK(gem_type IN ('red_gem', 'blue_gem', 'red_pool', 'blue_pool')),
            column_number INTEGER NOT NULL,
            position INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_qq) REFERENCES players(qq_id)
        )
        ''')

        # ==================== 自定义口令表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_commands (
            command_id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            response TEXT NOT NULL,
            score_reward INTEGER DEFAULT 0,
            per_player_limit INTEGER DEFAULT 1,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # ==================== 自定义口令使用记录表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_command_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qq_id TEXT NOT NULL,
            command_id INTEGER NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (qq_id) REFERENCES players(qq_id),
            FOREIGN KEY (command_id) REFERENCES custom_commands(command_id)
        )
        ''')

        # ==================== 支线活动表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS branch_events (
            event_id INTEGER PRIMARY KEY,
            event_name TEXT,
            is_active INTEGER DEFAULT 0,
            started_at TIMESTAMP,
            ended_at TIMESTAMP
        )
        ''')

        # ==================== 支线队伍表 ====================
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS branch_teams (
            team_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            player1_qq TEXT NOT NULL,
            player2_qq TEXT,
            is_solo INTEGER DEFAULT 0,
            total_points INTEGER DEFAULT 0,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (event_id) REFERENCES branch_events(event_id),
            FOREIGN KEY (player1_qq) REFERENCES players(qq_id),
            FOREIGN KEY (player2_qq) REFERENCES players(qq_id)
        )
        ''')

        conn.commit()

    @staticmethod
    def initialize_shop_items(conn: sqlite3.Connection):
        """初始化商店道具"""
        cursor = conn.cursor()

        # (item_id, item_name, item_type, price, faction_limit, global_limit, description, player_limit)
        shop_items = [
            (1, "败者○尘", "item", 100, "通用", -1,
             "是游戏就有读档！当本回合掷骰没有达到理想效果时，清空本回合点数重新投掷。\n💡使用指令：使用败者○尘", 1),
            (2, "放飞小○！", "item", 200, "通用", -1,
             "飞起来孩子飞起来！将你离终点最远的临时标记向前移动两格。\n💡使用指令：使用放飞小○！", 1),
            (3, "花言巧语", "item", 150, "通用", -1,
             "封锁道路的窗子。选择一个玩家，强制其下一轮不能在当前轮次的列上行进。目标可投d6，出6抵消。\n💡使用指令：使用花言巧语 目标QQ号", 1),
            (4, "揍击派对", "item", 0, "通用", -1,
             "吃我一锤！在指定坐标召唤疯狂大摆锤，该坐标上所有玩家的临时标记和永久棋子倒退一格。\n💡使用指令：使用揍击派对 列号,位置", 1),
            (5, "沉重的巨剑", "item", 50, "Aeonreth", -1,
             "足以劈开骰子的大剑。若任意掷骰出1，可选择重掷一次，但必须接受重掷结果。\n💡使用指令：使用沉重的巨剑", 1),
            (6, "女巫的魔法伎俩", "item", 50, "收养人", -1,
             "悄悄更换花纹的小魔法。若任意掷骰出6，可选择重掷一次，但必须接受重掷结果。\n💡使用指令：使用女巫的魔法伎俩", 1),
            (7, "变大蘑菇", "item", 50, "Aeonreth", -1,
             "神秘的红帽子胡子大叔给你的蘑菇。\n💡使用指令：使用变大蘑菇", 1),
            (8, "缩小药水", "item", 50, "收养人", -1,
             "写着Drink Me的玻璃瓶\n💡使用指令：使用缩小药水", 1),
            (9, "超级大炮", "item", 200, "通用", -1,
             "外型凶猛的超级手持大炮。在任意回合掷骰前使用，可直接指定需要的出目(6个数字)。\n💡使用指令：使用超级大炮 1,2,3,4,5,6", 1),
            (10, ":）", "item", 100, "通用", -1,
             "一颗金色的星星。\n💡使用指令：使用:）", 1),
            (11, "闹Ae魔镜", "item", 50, "收养人", -1,
             "华丽的欧式圆镜。有契约Ae时：掷骰前使用，每消耗10积分可指定一个出目，最多6个。无契约Ae：直接+5积分。\n💡使用指令：使用闹Ae魔镜 出目1,出目2,...", 1),
            (12, "小女孩娃娃", "item", 100, "Aeonreth", -1,
             "小女孩模样的娃娃。\n💡使用指令：使用小女孩娃娃", 1),
            (13, "火堆", "item", 0, "通用", -1,
             "令人安心的温暖火堆。使用后可以刷新上一个已使用道具的效果。\n💡使用指令：使用火堆", 1),
            (14, "阈限空间", "item", 100, "通用", -1,
             "空旷寂静的空白。当轮次触发失败被动结束后使用，可重新进行上一回合(不可再重投)。\n💡使用指令：使用阈限空间", 1),
            (15, "一斤鸭梨！", "item", 50, "通用", -1,
             "贿赂管理员！当本回合掷骰没有达到理想效果时，任选3个出目重新投掷。\n💡使用指令：使用一斤鸭梨！ 点数1,点数2,点数3", 1),
            (16, "The Room", "item", 0, "通用", -1,
             "虚拟密闭空间，只有一次探索机会。\n💡使用指令：使用The Room", 1),
            (17, "我的地图", "item", 500, "通用", -1,
             "DLC操作界面。获得后首次触发的陷阱可使用，免疫该陷阱并将其移动到地图任意位置。\n💡使用指令：使用我的地图 列号,位置", 1),
            (18, "五彩宝石", "item", 200, "通用", -1,
             "6枚蕴含强大力量的宝石。投6d6，出目>9则全场随机一半玩家-10积分，≤9则自己-50积分。\n💡使用指令：使用五彩宝石", 1),
            (19, "购物卡", "item", 0, "通用", -1,
             "商店任一物品可半价购入。下次购买道具时自动生效。\n💡使用指令：使用购物卡", 1),
            (20, "Biango Meow", "item", 100, "通用", 5,
             "投骰奖励～累计投满100个骰子后解锁。使用后随机获得：30积分/The Room/阈限空间/:）。\n💡使用指令：使用Biango Meow", 1),
            (21, "黑喵", "item", 100, "通用", 2,
             "黑色的喵喵。使用后永久效果：之后所有回合消耗的积分-2。\n💡使用指令：使用黑喵", 1),
            (22, "火人雕像", "item", 0, "Aeonreth", -1,
             "与Ae共鸣的雕像。使用后在未抵达的版块上随机生成红色宝石和蓝色池沼。\n💡使用指令：使用火人雕像", 1),
            (23, "冰人雕像", "item", 0, "收养人", -1,
             "与小女孩共鸣的雕像。使用后在未抵达的版块上随机生成蓝色宝石和红色池沼。\n💡使用指令：使用冰人雕像", 1),
            (24, "灵魂之叶", "item", 100, "通用", -1,
             "灵魂最后的赠礼。使用后可选择一个永久棋子，向前移动一格。\n💡使用指令：使用灵魂之叶 列号", 1),
            (999, "丑喵玩偶", "special", 150, "通用", -1,
             "可以捏捏的玩偶，每天限捏3次。\n💡使用指令：捏捏丑喵玩偶", 1),
        ]

        cursor.executemany('''
            INSERT OR IGNORE INTO shop_items
            (item_id, item_name, item_type, price, faction_limit, global_limit, description, player_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', shop_items)

        # 更新已存在道具的描述和限购数量
        for item in shop_items:
            item_id, item_name, item_type, price, faction_limit, global_limit, description, player_limit = item
            cursor.execute('''
                UPDATE shop_items SET description = ?, player_limit = ? WHERE item_id = ?
            ''', (description, player_limit, item_id))

        conn.commit()

    @staticmethod
    def clear_board(conn: sqlite3.Connection):
        """清除棋盘（只清除棋子位置和游戏状态，保留玩家信息和积分）"""
        cursor = conn.cursor()

        # 清除所有棋子位置
        cursor.execute('DELETE FROM player_positions')

        # 清除宝石池沼
        cursor.execute('DELETE FROM gem_pools')

        # 清除首达记录
        cursor.execute('DELETE FROM first_achievements')

        # 重置游戏状态（保留记录但重置所有字段）
        cursor.execute('''
            UPDATE game_state SET
                current_round_active = 0,
                can_start_new_round = 1,
                temp_markers_used = 0,
                dice_history = NULL,
                last_dice_result = NULL,
                topped_columns = NULL,
                skipped_rounds = 0,
                pending_encounter = NULL,
                pending_encounters = NULL,
                extra_d6_check_six = 0,
                next_dice_fixed = NULL,
                next_dice_count = NULL,
                next_dice_groups = NULL,
                forced_remaining_rounds = 0,
                odd_even_check_active = 0,
                math_check_active = 0,
                lockout_until = NULL,
                pending_trap_choice = NULL,
                trap_immunity_cost = NULL,
                trap_immunity_draw = 0,
                trap_immunity_count = 0,
                requires_drawing = 0,
                sweet_talk_blocked = NULL,
                allow_reroll = 0,
                reroll_on_one = 0,
                reroll_on_six = 0,
                all_dice_modifier = 0,
                forced_rolls = NULL,
                partial_forced_rolls = NULL,
                allow_retry_on_fail = 0,
                next_purchase_half = 0,
                cost_reduction = 0,
                last_used_item_id = NULL,
                immune_next_trap = 0,
                free_rounds = 0,
                next_roll_double_cost = 0,
                change_one_dice_available = 0,
                use_last_dice_available = 0,
                frozen_columns = NULL,
                must_draw_double = 0,
                force_end_until_draw = 0,
                next_dice_modify_any = 0,
                next_dice_add_3_any = 0,
                disabled_columns_this_round = NULL,
                pending_duel = NULL,
                pending_timed_checkins = NULL,
                has_red_rose = 0,
                has_blue_rose_from = NULL,
                yellow_rose_target = NULL,
                force_reroll_next_move = 0
        ''')

        # 清除地图内容触发记录
        cursor.execute('DELETE FROM content_triggers')

        conn.commit()

    @staticmethod
    def reset_game(conn: sqlite3.Connection):
        """重置游戏（删除所有数据但保留表结构）"""
        cursor = conn.cursor()

        tables = [
            'players',
            'player_positions',
            'player_inventory',
            'player_achievements',
            'game_state',
            'daily_limits',
            'content_triggers',
            'first_achievements',
            'achievement_counters',
            'game_rankings',
            'gem_pools'  # 宝石和池沼
        ]

        for table in tables:
            cursor.execute(f'DELETE FROM {table}')

        # 重置商店库存
        cursor.execute('UPDATE shop_items SET global_sold = 0, unlocked = 0')

        conn.commit()


def init_database(db_path: str = "data/game.db") -> sqlite3.Connection:
    """
    初始化数据库

    Args:
        db_path: 数据库文件路径

    Returns:
        数据库连接对象
    """
    # 确保目录存在
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # 连接数据库，增加超时时间
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问

    # 启用WAL模式，支持多连接同时读写
    conn.execute("PRAGMA journal_mode=WAL")
    # 设置busy_timeout，当数据库被锁定时等待而不是立即报错
    conn.execute("PRAGMA busy_timeout=30000")

    # 创建表
    DatabaseSchema.create_tables(conn)

    # 初始化商店道具
    DatabaseSchema.initialize_shop_items(conn)

    return conn


if __name__ == "__main__":
    # 测试数据库创建
    print("正在创建数据库...")
    conn = init_database("../data/game.db")
    print("数据库创建成功！")

    # 显示所有表
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()

    print("\n已创建的表:")
    for table in tables:
        print(f"  - {table[0]}")

    conn.close()
