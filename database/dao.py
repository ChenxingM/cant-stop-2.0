# -*- coding: utf-8 -*-
"""
数据访问对象层 (DAO - Data Access Object)
封装所有数据库操作
"""

import sqlite3
from typing import List, Optional, Dict, Tuple
from datetime import datetime, date
import json

from .models import (
    Player, Position, InventoryItem, Achievement,
    PlayerGameState, ShopItem, ContentTrigger, GameRanking
)


class PlayerDAO:
    """玩家数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_player(self, qq_id: str, nickname: str) -> Player:
        """创建新玩家"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO players (qq_id, nickname)
            VALUES (?, ?)
        ''', (qq_id, nickname))
        self.conn.commit()

        # 同时创建游戏状态
        cursor.execute('''
            INSERT OR IGNORE INTO game_state (qq_id)
            VALUES (?)
        ''', (qq_id,))
        self.conn.commit()

        return self.get_player(qq_id)

    def get_player(self, qq_id: str) -> Optional[Player]:
        """获取玩家信息"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM players WHERE qq_id = ?', (qq_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return Player(
            qq_id=row['qq_id'],
            nickname=row['nickname'],
            faction=row['faction'],
            total_score=row['total_score'],
            current_score=row['current_score'],
            created_at=row['created_at'],
            last_active=row['last_active']
        )

    def update_faction(self, qq_id: str, faction: str):
        """更新玩家阵营"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE players
            SET faction = ?, last_active = CURRENT_TIMESTAMP
            WHERE qq_id = ?
        ''', (faction, qq_id))
        self.conn.commit()

    def add_score(self, qq_id: str, amount: int):
        """增加积分"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE players
            SET current_score = current_score + ?,
                total_score = total_score + ?,
                last_active = CURRENT_TIMESTAMP
            WHERE qq_id = ?
        ''', (amount, amount if amount > 0 else 0, qq_id))
        self.conn.commit()

    def consume_score(self, qq_id: str, amount: int) -> bool:
        """消耗积分，返回是否成功"""
        player = self.get_player(qq_id)
        if not player or player.current_score < amount:
            return False

        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE players
            SET current_score = current_score - ?,
                last_active = CURRENT_TIMESTAMP
            WHERE qq_id = ?
        ''', (amount, qq_id))
        self.conn.commit()
        return True

    def get_all_players(self) -> List[Player]:
        """获取所有玩家"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM players ORDER BY total_score DESC')
        rows = cursor.fetchall()

        return [Player(
            qq_id=row['qq_id'],
            nickname=row['nickname'],
            faction=row['faction'],
            total_score=row['total_score'],
            current_score=row['current_score'],
            created_at=row['created_at'],
            last_active=row['last_active']
        ) for row in rows]


class PositionDAO:
    """位置数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_positions(self, qq_id: str, marker_type: Optional[str] = None) -> List[Position]:
        """获取玩家位置"""
        cursor = self.conn.cursor()

        if marker_type:
            cursor.execute('''
                SELECT column_number, position, marker_type
                FROM player_positions
                WHERE qq_id = ? AND marker_type = ?
                ORDER BY column_number
            ''', (qq_id, marker_type))
        else:
            cursor.execute('''
                SELECT column_number, position, marker_type
                FROM player_positions
                WHERE qq_id = ?
                ORDER BY column_number, marker_type
            ''', (qq_id,))

        rows = cursor.fetchall()
        return [Position(
            column_number=row['column_number'],
            position=row['position'],
            marker_type=row['marker_type']
        ) for row in rows]

    def add_or_update_position(self, qq_id: str, column: int, position: int, marker_type: str):
        """添加或更新位置"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO player_positions
            (qq_id, column_number, position, marker_type)
            VALUES (?, ?, ?, ?)
        ''', (qq_id, column, position, marker_type))
        self.conn.commit()

    def remove_position(self, qq_id: str, column: int, marker_type: str):
        """移除位置"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM player_positions
            WHERE qq_id = ? AND column_number = ? AND marker_type = ?
        ''', (qq_id, column, marker_type))
        self.conn.commit()

    def clear_temp_positions(self, qq_id: str):
        """清除所有临时标记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM player_positions
            WHERE qq_id = ? AND marker_type = 'temp'
        ''', (qq_id,))
        self.conn.commit()

    def convert_temp_to_permanent(self, qq_id: str):
        """将所有临时标记转换为永久标记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE player_positions
            SET marker_type = 'permanent'
            WHERE qq_id = ? AND marker_type = 'temp'
        ''', (qq_id,))
        self.conn.commit()

    def get_all_positions_on_map(self) -> Dict[str, List[Position]]:
        """获取地图上所有玩家的位置"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT qq_id, column_number, position, marker_type
            FROM player_positions
            ORDER BY qq_id, column_number
        ''')
        rows = cursor.fetchall()

        result = {}
        for row in rows:
            qq_id = row['qq_id']
            if qq_id not in result:
                result[qq_id] = []
            result[qq_id].append(Position(
                column_number=row['column_number'],
                position=row['position'],
                marker_type=row['marker_type']
            ))

        return result


class InventoryDAO:
    """背包数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_item(self, qq_id: str, item_id: int, item_name: str, item_type: str = 'item'):
        """添加物品"""
        cursor = self.conn.cursor()
        # 检查是否已有该物品
        cursor.execute('''
            SELECT id, quantity FROM player_inventory
            WHERE qq_id = ? AND item_id = ? AND item_type = ?
        ''', (qq_id, item_id, item_type))
        row = cursor.fetchone()

        if row:
            # 增加数量
            cursor.execute('''
                UPDATE player_inventory
                SET quantity = quantity + 1
                WHERE id = ?
            ''', (row['id'],))
        else:
            # 新增物品
            cursor.execute('''
                INSERT INTO player_inventory
                (qq_id, item_type, item_id, item_name, quantity)
                VALUES (?, ?, ?, ?, 1)
            ''', (qq_id, item_type, item_id, item_name))

        self.conn.commit()

    def remove_item(self, qq_id: str, item_id: int, item_type: str = 'item') -> bool:
        """移除物品，返回是否成功"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, quantity FROM player_inventory
            WHERE qq_id = ? AND item_id = ? AND item_type = ?
        ''', (qq_id, item_id, item_type))
        row = cursor.fetchone()

        if not row:
            return False

        if row['quantity'] > 1:
            cursor.execute('''
                UPDATE player_inventory
                SET quantity = quantity - 1
                WHERE id = ?
            ''', (row['id'],))
        else:
            cursor.execute('''
                DELETE FROM player_inventory
                WHERE id = ?
            ''', (row['id'],))

        self.conn.commit()
        return True

    def get_inventory(self, qq_id: str) -> List[InventoryItem]:
        """获取背包物品"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM player_inventory
            WHERE qq_id = ?
            ORDER BY obtained_at DESC
        ''', (qq_id,))
        rows = cursor.fetchall()

        return [InventoryItem(
            item_id=row['item_id'],
            item_name=row['item_name'],
            item_type=row['item_type'],
            quantity=row['quantity'],
            obtained_at=row['obtained_at']
        ) for row in rows]

    def has_item(self, qq_id: str, item_id: int, item_type: str = 'item') -> bool:
        """检查是否拥有某物品"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM player_inventory
            WHERE qq_id = ? AND item_id = ? AND item_type = ?
        ''', (qq_id, item_id, item_type))
        row = cursor.fetchone()
        return row['count'] > 0


class GameStateDAO:
    """游戏状态数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_state(self, qq_id: str) -> PlayerGameState:
        """获取游戏状态"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM game_state WHERE qq_id = ?', (qq_id,))
        row = cursor.fetchone()

        if not row:
            # 如果不存在，创建默认状态
            cursor.execute('INSERT INTO game_state (qq_id) VALUES (?)', (qq_id,))
            self.conn.commit()
            return PlayerGameState(qq_id=qq_id)

        return PlayerGameState.from_dict(qq_id, dict(row))

    def update_state(self, state: PlayerGameState):
        """更新游戏状态"""
        cursor = self.conn.cursor()
        data = state.to_dict()
        cursor.execute('''
            UPDATE game_state
            SET current_round_active = ?,
                can_start_new_round = ?,
                temp_markers_used = ?,
                dice_history = ?,
                last_dice_result = ?,
                topped_columns = ?
            WHERE qq_id = ?
        ''', (
            data['current_round_active'],
            data['can_start_new_round'],
            data['temp_markers_used'],
            data['dice_history'],
            data['last_dice_result'],
            data['topped_columns'],
            state.qq_id
        ))
        self.conn.commit()


class ShopDAO:
    """商店数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_all_items(self, unlocked_only: bool = False) -> List[ShopItem]:
        """获取所有商店道具"""
        cursor = self.conn.cursor()

        if unlocked_only:
            cursor.execute('SELECT * FROM shop_items WHERE unlocked = 1 OR item_type = "special" ORDER BY item_id')
        else:
            cursor.execute('SELECT * FROM shop_items ORDER BY item_id')

        rows = cursor.fetchall()
        return [ShopItem(
            item_id=row['item_id'],
            item_name=row['item_name'],
            item_type=row['item_type'],
            price=row['price'],
            faction_limit=row['faction_limit'],
            global_limit=row['global_limit'],
            global_sold=row['global_sold'],
            unlocked=bool(row['unlocked']),
            description=row['description']
        ) for row in rows]

    def get_item(self, item_id: int) -> Optional[ShopItem]:
        """获取单个道具"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM shop_items WHERE item_id = ?', (item_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return ShopItem(
            item_id=row['item_id'],
            item_name=row['item_name'],
            item_type=row['item_type'],
            price=row['price'],
            faction_limit=row['faction_limit'],
            global_limit=row['global_limit'],
            global_sold=row['global_sold'],
            unlocked=bool(row['unlocked']),
            description=row['description']
        )

    def unlock_item(self, item_id: int):
        """解锁道具"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE shop_items SET unlocked = 1 WHERE item_id = ?', (item_id,))
        self.conn.commit()

    def purchase_item(self, item_id: int):
        """购买道具（增加已售数量）"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE shop_items SET global_sold = global_sold + 1 WHERE item_id = ?', (item_id,))
        self.conn.commit()


class AchievementDAO:
    """成就数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_achievement(self, qq_id: str, achievement_id: int, achievement_name: str, achievement_type: str):
        """添加成就"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO player_achievements
            (qq_id, achievement_id, achievement_name, achievement_type)
            VALUES (?, ?, ?, ?)
        ''', (qq_id, achievement_id, achievement_name, achievement_type))
        self.conn.commit()

    def has_achievement(self, qq_id: str, achievement_id: int, achievement_type: str) -> bool:
        """检查是否拥有成就"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) as count FROM player_achievements
            WHERE qq_id = ? AND achievement_id = ? AND achievement_type = ?
        ''', (qq_id, achievement_id, achievement_type))
        row = cursor.fetchone()
        return row['count'] > 0

    def get_achievements(self, qq_id: str) -> List[Achievement]:
        """获取所有成就"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM player_achievements
            WHERE qq_id = ?
            ORDER BY obtained_at DESC
        ''', (qq_id,))
        rows = cursor.fetchall()

        return [Achievement(
            achievement_id=row['achievement_id'],
            achievement_name=row['achievement_name'],
            achievement_type=row['achievement_type'],
            obtained_at=row['obtained_at']
        ) for row in rows]


class DailyLimitDAO:
    """每日限制数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_count(self, qq_id: str, action_type: str) -> int:
        """获取今日次数"""
        today = date.today().isoformat()
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT count FROM daily_limits
            WHERE qq_id = ? AND action_type = ? AND date = ?
        ''', (qq_id, action_type, today))
        row = cursor.fetchone()
        return row['count'] if row else 0

    def increment(self, qq_id: str, action_type: str):
        """增加次数"""
        today = date.today().isoformat()
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO daily_limits (qq_id, action_type, count, date)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(qq_id, action_type, date)
            DO UPDATE SET count = count + 1
        ''', (qq_id, action_type, today))
        self.conn.commit()

    def can_do(self, qq_id: str, action_type: str, limit: int) -> Tuple[bool, int]:
        """检查是否可以执行，返回(是否可以, 剩余次数)"""
        count = self.get_count(qq_id, action_type)
        remaining = max(0, limit - count)
        return count < limit, remaining
