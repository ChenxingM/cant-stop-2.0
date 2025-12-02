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

    def clear_temp_position_by_column(self, qq_id: str, column: int):
        """清除指定玩家在指定列的临时标记"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM player_positions
            WHERE qq_id = ? AND column_number = ? AND marker_type = 'temp'
        ''', (qq_id, column))
        self.conn.commit()

    def clear_all_temp_positions_by_column(self, column: int):
        """清除所有玩家在指定列的临时标记（登顶时调用）"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM player_positions
            WHERE column_number = ? AND marker_type = 'temp'
        ''', (column,))
        self.conn.commit()

    def convert_temp_to_permanent(self, qq_id: str):
        """将所有临时标记转换为永久标记"""
        cursor = self.conn.cursor()

        # 首先获取所有临时标记的列号
        cursor.execute('''
            SELECT DISTINCT column_number
            FROM player_positions
            WHERE qq_id = ? AND marker_type = 'temp'
        ''', (qq_id,))
        temp_columns = [row['column_number'] for row in cursor.fetchall()]

        # 删除这些列上已有的永久标记
        for column in temp_columns:
            cursor.execute('''
                DELETE FROM player_positions
                WHERE qq_id = ? AND column_number = ? AND marker_type = 'permanent'
            ''', (qq_id, column))

        # 将临时标记转换为永久标记
        cursor.execute('''
            UPDATE player_positions
            SET marker_type = 'permanent'
            WHERE qq_id = ? AND marker_type = 'temp'
        ''', (qq_id,))

        self.conn.commit()

    def convert_temp_to_permanent_by_column(self, qq_id: str, column: int):
        """将指定列的临时标记转换为永久标记"""
        cursor = self.conn.cursor()

        # 首先删除该列已有的永久标记
        cursor.execute('''
            DELETE FROM player_positions
            WHERE qq_id = ? AND column_number = ? AND marker_type = 'permanent'
        ''', (qq_id, column))

        # 将该列的临时标记转换为永久标记
        cursor.execute('''
            UPDATE player_positions
            SET marker_type = 'permanent'
            WHERE qq_id = ? AND column_number = ? AND marker_type = 'temp'
        ''', (qq_id, column))

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

    def get_item_count(self, qq_id: str, item_id: int, item_type: str = 'item') -> int:
        """获取玩家拥有某物品的数量"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT COALESCE(SUM(quantity), 0) as total FROM player_inventory
            WHERE qq_id = ? AND item_id = ? AND item_type = ?
        ''', (qq_id, item_id, item_type))
        row = cursor.fetchone()
        return row['total']


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
                topped_columns = ?,
                skipped_rounds = ?,
                pending_encounter = ?,
                pending_encounters = ?,
                extra_d6_check_six = ?,
                next_dice_fixed = ?,
                next_dice_count = ?,
                next_dice_groups = ?,
                forced_remaining_rounds = ?,
                odd_even_check_active = ?,
                math_check_active = ?,
                lockout_until = ?,
                pending_trap_choice = ?,
                trap_immunity_cost = ?,
                trap_immunity_draw = ?,
                sweet_talk_blocked = ?
            WHERE qq_id = ?
        ''', (
            data['current_round_active'],
            data['can_start_new_round'],
            data['temp_markers_used'],
            data['dice_history'],
            data['last_dice_result'],
            data['topped_columns'],
            data['skipped_rounds'],
            data['pending_encounter'],
            data['pending_encounters'],
            data['extra_d6_check_six'],
            data['next_dice_fixed'],
            data['next_dice_count'],
            data['next_dice_groups'],
            data['forced_remaining_rounds'],
            data['odd_even_check_active'],
            data['math_check_active'],
            data['lockout_until'],
            data['pending_trap_choice'],
            data['trap_immunity_cost'],
            data['trap_immunity_draw'],
            data['sweet_talk_blocked'],
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
            description=row['description'],
            player_limit=row['player_limit'] if 'player_limit' in row.keys() else -1
        ) for row in rows]

    def get_item(self, item_id: int) -> Optional[ShopItem]:
        """获取单个道具（通过ID）"""
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
            description=row['description'],
            player_limit=row['player_limit'] if 'player_limit' in row.keys() else -1
        )

    def get_item_by_name(self, item_name: str) -> Optional[ShopItem]:
        """获取单个道具（通过名称）"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM shop_items WHERE item_name = ?', (item_name,))
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
            description=row['description'],
            player_limit=row['player_limit'] if 'player_limit' in row.keys() else -1
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


class ContractDAO:
    """契约关系数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_contract(self, player1_qq: str, player2_qq: str) -> Tuple[bool, str]:
        """
        建立契约关系
        返回: (是否成功, 消息)
        """
        cursor = self.conn.cursor()

        # 检查两人是否已有契约
        existing1 = self.get_contract_partner(player1_qq)
        existing2 = self.get_contract_partner(player2_qq)

        if existing1:
            return False, f"您已经与其他玩家建立了契约关系"
        if existing2:
            return False, f"对方已经与其他玩家建立了契约关系"

        # 建立契约（确保player1_qq < player2_qq以保持一致性）
        if player1_qq > player2_qq:
            player1_qq, player2_qq = player2_qq, player1_qq

        try:
            cursor.execute('''
                INSERT INTO player_contracts (player1_qq, player2_qq)
                VALUES (?, ?)
            ''', (player1_qq, player2_qq))
            self.conn.commit()
            return True, "契约建立成功"
        except Exception as e:
            return False, f"契约建立失败: {str(e)}"

    def get_contract_partner(self, qq_id: str) -> Optional[str]:
        """获取契约对象的QQ号，如果没有返回None"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT player1_qq, player2_qq FROM player_contracts
            WHERE player1_qq = ? OR player2_qq = ?
        ''', (qq_id, qq_id))
        row = cursor.fetchone()

        if not row:
            return None

        # 返回另一方的QQ号
        if row['player1_qq'] == qq_id:
            return row['player2_qq']
        else:
            return row['player1_qq']

    def has_contract(self, qq_id: str) -> bool:
        """检查玩家是否有契约"""
        return self.get_contract_partner(qq_id) is not None

    def are_contracted(self, qq_id1: str, qq_id2: str) -> bool:
        """检查两个玩家是否互为契约对象"""
        partner = self.get_contract_partner(qq_id1)
        return partner == qq_id2

    def remove_contract(self, qq_id: str) -> bool:
        """解除契约关系"""
        cursor = self.conn.cursor()
        cursor.execute('''
            DELETE FROM player_contracts
            WHERE player1_qq = ? OR player2_qq = ?
        ''', (qq_id, qq_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_all_contracts(self) -> List[Tuple[str, str, str]]:
        """获取所有契约关系，返回 [(player1_qq, player2_qq, created_at), ...]"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT player1_qq, player2_qq, created_at FROM player_contracts')
        rows = cursor.fetchall()
        return [(row['player1_qq'], row['player2_qq'], row['created_at']) for row in rows]


class GemPoolDAO:
    """宝石池沼数据访问对象"""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create_gem(self, owner_qq: str, gem_type: str, column: int, position: int) -> int:
        """
        创建宝石或池沼
        gem_type: 'red_gem', 'blue_gem', 'red_pool', 'blue_pool'
        返回: 记录ID
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO gem_pools (owner_qq, gem_type, column_number, position)
            VALUES (?, ?, ?, ?)
        ''', (owner_qq, gem_type, column, position))
        self.conn.commit()
        return cursor.lastrowid

    def get_player_gems(self, owner_qq: str, active_only: bool = True) -> List[Dict]:
        """获取玩家创建的所有宝石和池沼"""
        cursor = self.conn.cursor()
        if active_only:
            cursor.execute('''
                SELECT * FROM gem_pools
                WHERE owner_qq = ? AND is_active = 1
            ''', (owner_qq,))
        else:
            cursor.execute('''
                SELECT * FROM gem_pools WHERE owner_qq = ?
            ''', (owner_qq,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_gem_at_position(self, column: int, position: int, active_only: bool = True) -> List[Dict]:
        """获取指定位置的所有宝石和池沼"""
        cursor = self.conn.cursor()
        if active_only:
            cursor.execute('''
                SELECT * FROM gem_pools
                WHERE column_number = ? AND position = ? AND is_active = 1
            ''', (column, position))
        else:
            cursor.execute('''
                SELECT * FROM gem_pools
                WHERE column_number = ? AND position = ?
            ''', (column, position))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_all_active_gems(self) -> List[Dict]:
        """获取所有活跃的宝石和池沼"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT gp.*, p.nickname as owner_name
            FROM gem_pools gp
            LEFT JOIN players p ON gp.owner_qq = p.qq_id
            WHERE gp.is_active = 1
        ''')
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def deactivate_gem(self, gem_id: int):
        """使宝石/池沼失效"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE gem_pools SET is_active = 0 WHERE id = ?
        ''', (gem_id,))
        self.conn.commit()

    def deactivate_player_gems(self, owner_qq: str, gem_type: str = None):
        """使玩家的宝石/池沼失效
        如果指定gem_type则只使该类型失效，否则使所有类型失效
        """
        cursor = self.conn.cursor()
        if gem_type:
            cursor.execute('''
                UPDATE gem_pools SET is_active = 0
                WHERE owner_qq = ? AND gem_type = ?
            ''', (owner_qq, gem_type))
        else:
            cursor.execute('''
                UPDATE gem_pools SET is_active = 0 WHERE owner_qq = ?
            ''', (owner_qq,))
        self.conn.commit()

    def get_opposite_pool_positions(self, statue_type: str) -> List[Dict]:
        """
        获取使用相反雕像玩家的池沼位置
        statue_type: 'fire' 返回冰人雕像的红色池沼位置
                    'ice' 返回火人雕像的蓝色池沼位置
        """
        cursor = self.conn.cursor()
        if statue_type == 'fire':
            # 火人雕像用户想知道冰人雕像用户的红色池沼位置
            cursor.execute('''
                SELECT gp.*, p.nickname as owner_name
                FROM gem_pools gp
                LEFT JOIN players p ON gp.owner_qq = p.qq_id
                WHERE gp.gem_type = 'red_pool' AND gp.is_active = 1
            ''')
        else:
            # 冰人雕像用户想知道火人雕像用户的蓝色池沼位置
            cursor.execute('''
                SELECT gp.*, p.nickname as owner_name
                FROM gem_pools gp
                LEFT JOIN players p ON gp.owner_qq = p.qq_id
                WHERE gp.gem_type = 'blue_pool' AND gp.is_active = 1
            ''')
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
