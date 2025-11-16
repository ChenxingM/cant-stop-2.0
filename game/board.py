"""
游戏棋盘类
GameBoard Class for Can't Stop
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.board_config import (
    BOARD_DATA,
    COLUMN_HEIGHTS,
    CELL_TYPES,
    CELL_TYPE_NAMES,
    VALID_COLUMNS,
    BOARD_STATS,
)


class Cell:
    """棋盘格子"""

    def __init__(self, column: int, position: int, type_code: str, content_id: int, name: str):
        self.column = column
        self.position = position
        self.type_code = type_code  # E/I/T
        self.type = CELL_TYPES[type_code]  # encounter/item/trap
        self.type_name = CELL_TYPE_NAMES[type_code]  # 遭遇/道具/陷阱
        self.content_id = content_id
        self.name = name

    def __repr__(self):
        return f"Cell(列{self.column}第{self.position}格: {self.type_name}{self.content_id} - {self.name})"

    def __str__(self):
        return f"[{self.type_code}{self.content_id}] {self.name}"

    def is_encounter(self) -> bool:
        """是否为遭遇"""
        return self.type_code == "E"

    def is_item(self) -> bool:
        """是否为道具"""
        return self.type_code == "I"

    def is_trap(self) -> bool:
        """是否为陷阱"""
        return self.type_code == "T"

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "column": self.column,
            "position": self.position,
            "type": self.type,
            "type_name": self.type_name,
            "id": self.content_id,
            "name": self.name,
        }


class Column:
    """棋盘列"""

    def __init__(self, number: int):
        if number not in VALID_COLUMNS:
            raise ValueError(f"无效的列号: {number}，有效范围是 3-18")

        self.number = number
        self.height = COLUMN_HEIGHTS[number]
        self.cells = self._load_cells()

    def _load_cells(self) -> list[Cell]:
        """加载该列的所有格子"""
        cells = []
        for position, (type_code, content_id, name) in enumerate(BOARD_DATA[self.number], start=1):
            cell = Cell(self.number, position, type_code, content_id, name)
            cells.append(cell)
        return cells

    def get_cell(self, position: int) -> Cell | None:
        """根据位置获取格子"""
        if 1 <= position <= len(self.cells):
            return self.cells[position - 1]
        return None

    def __repr__(self):
        return f"Column(列{self.number}, 高度{self.height})"

    def __str__(self):
        lines = [f"=== 第{self.number}列 (高度: {self.height}) ==="]
        for cell in self.cells:
            lines.append(f"  {cell.position}. {cell}")
        return "\n".join(lines)


class GameBoard:
    """游戏棋盘"""

    def __init__(self):
        self.columns = {num: Column(num) for num in VALID_COLUMNS}
        self.stats = BOARD_STATS.copy()

    def get_column(self, column_num: int) -> Column | None:
        """获取指定列"""
        return self.columns.get(column_num)

    def get_cell(self, column: int, position: int) -> Cell | None:
        """获取指定格子"""
        col = self.get_column(column)
        return col.get_cell(position) if col else None

    def get_column_height(self, column: int) -> int:
        """获取列高度"""
        return COLUMN_HEIGHTS.get(column, 0)

    def is_valid_column(self, column: int) -> bool:
        """检查列号是否有效"""
        return column in VALID_COLUMNS

    def is_valid_position(self, column: int, position: int) -> bool:
        """检查位置是否有效"""
        if not self.is_valid_column(column):
            return False
        return 1 <= position <= self.get_column_height(column)

    def get_all_cells_by_type(self, cell_type: str) -> list[Cell]:
        """
        获取所有指定类型的格子
        cell_type: "E" (遭遇) / "I" (道具) / "T" (陷阱)
        """
        cells = []
        for col in self.columns.values():
            for cell in col.cells:
                if cell.type_code == cell_type:
                    cells.append(cell)
        return cells

    def get_encounters(self) -> list[Cell]:
        """获取所有遭遇"""
        return self.get_all_cells_by_type("E")

    def get_items(self) -> list[Cell]:
        """获取所有道具"""
        return self.get_all_cells_by_type("I")

    def get_traps(self) -> list[Cell]:
        """获取所有陷阱"""
        return self.get_all_cells_by_type("T")

    def print_board(self):
        """打印整个棋盘"""
        print("=" * 60)
        print("贪骰无厌 2.0 - 游戏棋盘")
        print("=" * 60)
        print(f"总格子数: {self.stats['total_cells']}")
        print(f"遭遇: {self.stats['total_encounters']} | 道具: {self.stats['total_items']} | 陷阱: {self.stats['total_traps']}")
        print("=" * 60)

        for col_num in VALID_COLUMNS:
            col = self.get_column(col_num)
            print(f"\n{col}")

    def print_column(self, column: int):
        """打印指定列"""
        col = self.get_column(column)
        if col:
            print(col)
        else:
            print(f"列 {column} 不存在")

    def print_stats(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("棋盘统计信息")
        print("=" * 60)

        # 按类型统计
        encounters = self.get_encounters()
        items = self.get_items()
        traps = self.get_traps()

        print(f"\n📖 遭遇总数: {len(encounters)}")
        print(f"🎁 道具总数: {len(items)}")
        print(f"⚠️  陷阱总数: {len(traps)}")

        # 按列统计
        print("\n各列分布:")
        for col_num in VALID_COLUMNS:
            col = self.get_column(col_num)
            e_count = sum(1 for c in col.cells if c.is_encounter())
            i_count = sum(1 for c in col.cells if c.is_item())
            t_count = sum(1 for c in col.cells if c.is_trap())
            print(f"  列{col_num:2d} (高度{col.height:2d}): 遭遇×{e_count} 道具×{i_count} 陷阱×{t_count}")


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 创建棋盘
    board = GameBoard()

    print("取第3列第1格")
    cell = board.get_cell(3, 1)
    print(f"  {cell}\n")

    for col in VALID_COLUMNS:
        board.print_column(col)
