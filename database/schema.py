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
            description TEXT
        )
        ''')

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

        conn.commit()

    @staticmethod
    def initialize_shop_items(conn: sqlite3.Connection):
        """初始化商店道具"""
        cursor = conn.cursor()

        shop_items = [
            (1, "败者○尘", "item", 100, "通用", -1, "游戏就有读档！"),
            (2, "放飞小○！", "item", 200, "通用", -1, "飞起来孩子飞起来"),
            (3, "花言巧语", "item", 150, "通用", -1, "封锁道路的窗子"),
            (4, "揍击派对", "item", 0, "通用", -1, "疯狂大摆锤"),
            (5, "沉重的巨剑", "item", 50, "Aeonreth", -1, "足以劈开骰子的大剑"),
            (6, "女巫的魔法伎俩", "item", 50, "收养人", -1, "悄悄更换花纹的小魔法"),
            (7, "变大蘑菇", "item", 50, "Aeonreth", -1, "神秘的红帽子胡子大叔的蘑菇"),
            (8, "中门对狙", "item", 0, "通用", -1, "对决道具"),
            (9, "超级大炮", "item", 200, "通用", -1, "外型凶猛的超级手持大炮"),
            (10, ":）", "item", 100, "通用", -1, "一颗金色的星星"),
            (11, "闹Ae魔镜", "item", 50, "收养人", -1, "华丽的欧式圆镜"),
            (12, "小女孩娃娃", "item", 100, "Aeonreth", -1, "小女孩模样的娃娃"),
            (13, "火堆", "item", 0, "通用", -1, "令人安心的温暖火堆"),
            (14, "阈限空间", "item", 100, "通用", -1, "空旷寂静的空白"),
            (15, "一斤鸭梨！", "item", 50, "通用", -1, "贿赂管理员"),
            (16, "The Room", "item", 0, "通用", -1, "虚拟密闭空间"),
            (17, "我的地图", "item", 500, "通用", -1, "DLC操作界面"),
            (18, "五彩宝石", "item", 200, "通用", -1, "6枚蕴含强大力量的宝石"),
            (19, "购物卡", "item", 0, "通用", -1, "半价购入"),
            (20, "Biango Meow", "item", 100, "通用", 5, "投骰奖励"),
            (21, "黑喵", "item", 100, "通用", 2, "回合消耗积分-2"),
            (22, "火人雕像", "item", 0, "Aeonreth", -1, "红色宝石和蓝色池沼"),
            (23, "冰人雕像", "item", 0, "收养人", -1, "蓝色宝石和红色池沼"),
            (24, "灵魂之叶", "item", 100, "通用", -1, "灵魂的赠礼"),
            (999, "丑喵玩偶", "special", 150, "通用", -1, "可以捏捏的玩偶"),
        ]

        cursor.executemany('''
            INSERT OR IGNORE INTO shop_items
            (item_id, item_name, item_type, price, faction_limit, global_limit, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', shop_items)

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
            'game_rankings'
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

    # 连接数据库
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问

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
