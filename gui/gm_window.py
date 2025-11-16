# -*- coding: utf-8 -*-
"""
GM管理界面 (PySide6)
Game Master GUI for Can't Stop
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextEdit, QLineEdit, QGroupBox, QGridLayout, QMessageBox,
    QHeaderView, QScrollArea, QFrame, QSplitter, QComboBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush

from database.schema import init_database
from database.dao import PlayerDAO, PositionDAO, ShopDAO, AchievementDAO
from data.board_config import BOARD_DATA, COLUMN_HEIGHTS, VALID_COLUMNS


class BoardWidget(QWidget):
    """棋盘显示组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1200, 600)
        self.players_positions = {}  # {qq_id: [(column, position, marker_type), ...]}
        self.cell_contents = {}  # 从BOARD_DATA加载

        self._load_cell_contents()

    def _load_cell_contents(self):
        """加载格子内容"""
        for column, cells in BOARD_DATA.items():
            for position, (cell_type, content_id, name) in enumerate(cells, start=1):
                self.cell_contents[(column, position)] = (cell_type, name)

    def update_positions(self, positions_dict: dict):
        """更新玩家位置"""
        self.players_positions = positions_dict
        self.update()

    def paintEvent(self, event):
        """绘制棋盘"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 计算绘制参数
        cell_width = 60
        cell_height = 40
        start_x = 50
        start_y = 500

        # 绘制每列
        for col_num in VALID_COLUMNS:
            height = COLUMN_HEIGHTS[col_num]
            x = start_x + (col_num - 3) * (cell_width + 10)

            # 绘制列号
            painter.setPen(QPen(Qt.black, 2))
            painter.setFont(QFont("Arial", 12, QFont.Bold))
            painter.drawText(x, start_y + 30, cell_width, 20, Qt.AlignCenter, f"{col_num}")

            # 绘制格子
            for pos in range(height, 0, -1):
                y = start_y - pos * cell_height

                # 绘制格子边框
                painter.setPen(QPen(Qt.black, 1))

                # 根据内容类型设置颜色
                cell_type, cell_name = self.cell_contents.get((col_num, pos), (None, ""))
                if cell_type == "E":
                    painter.setBrush(QBrush(QColor(173, 216, 230)))  # 浅蓝色 - 遭遇
                elif cell_type == "I":
                    painter.setBrush(QBrush(QColor(144, 238, 144)))  # 浅绿色 - 道具
                elif cell_type == "T":
                    painter.setBrush(QBrush(QColor(255, 182, 193)))  # 浅红色 - 陷阱
                else:
                    painter.setBrush(QBrush(Qt.white))

                painter.drawRect(x, y, cell_width, cell_height)

                # 绘制位置编号
                painter.setPen(QPen(Qt.black))
                painter.setFont(QFont("Arial", 8))
                painter.drawText(x + 2, y + 2, 15, 15, Qt.AlignCenter, str(pos))

                # 绘制玩家标记
                self._draw_markers(painter, col_num, pos, x, y, cell_width, cell_height)

        # 绘制图例
        self._draw_legend(painter)

    def _draw_markers(self, painter, column, position, x, y, width, height):
        """绘制玩家标记"""
        temp_players = []
        perm_players = []

        for qq_id, positions in self.players_positions.items():
            for col, pos, marker_type in positions:
                if col == column and pos == position:
                    if marker_type == 'temp':
                        temp_players.append(qq_id)
                    else:
                        perm_players.append(qq_id)

        # 绘制永久标记（圆形）
        if perm_players:
            marker_size = 12
            painter.setBrush(QBrush(QColor(0, 0, 255)))  # 蓝色
            for i, qq_id in enumerate(perm_players[:3]):
                offset_x = x + width - marker_size - 2 - i * (marker_size + 2)
                offset_y = y + height - marker_size - 2
                painter.drawEllipse(offset_x, offset_y, marker_size, marker_size)

        # 绘制临时标记（方形）
        if temp_players:
            marker_size = 12
            painter.setBrush(QBrush(QColor(255, 165, 0)))  # 橙色
            for i, qq_id in enumerate(temp_players[:3]):
                offset_x = x + width - marker_size - 2 - i * (marker_size + 2)
                offset_y = y + 2
                painter.drawRect(offset_x, offset_y, marker_size, marker_size)

    def _draw_legend(self, painter):
        """绘制图例"""
        legend_x = 20
        legend_y = 20

        painter.setFont(QFont("Arial", 10))

        # 内容类型图例
        painter.setPen(QPen(Qt.black))
        painter.drawText(legend_x, legend_y, "图例:")

        # 遭遇
        painter.setBrush(QBrush(QColor(173, 216, 230)))
        painter.drawRect(legend_x, legend_y + 20, 20, 15)
        painter.drawText(legend_x + 25, legend_y + 32, "遭遇")

        # 道具
        painter.setBrush(QBrush(QColor(144, 238, 144)))
        painter.drawRect(legend_x, legend_y + 40, 20, 15)
        painter.drawText(legend_x + 25, legend_y + 52, "道具")

        # 陷阱
        painter.setBrush(QBrush(QColor(255, 182, 193)))
        painter.drawRect(legend_x, legend_y + 60, 20, 15)
        painter.drawText(legend_x + 25, legend_y + 72, "陷阱")

        # 标记类型图例
        painter.drawText(legend_x, legend_y + 100, "标记:")

        # 临时标记
        painter.setBrush(QBrush(QColor(255, 165, 0)))
        painter.drawRect(legend_x, legend_y + 120, 12, 12)
        painter.drawText(legend_x + 17, legend_y + 130, "临时")

        # 永久标记
        painter.setBrush(QBrush(QColor(0, 0, 255)))
        painter.drawEllipse(legend_x, legend_y + 140, 12, 12)
        painter.drawText(legend_x + 17, legend_y + 150, "永久")


class GMWindow(QMainWindow):
    """GM管理主窗口"""

    def __init__(self, db_path: str = "data/game.db"):
        super().__init__()
        self.setWindowTitle("贪骰无厌 2.0 - GM管理界面")
        self.setGeometry(100, 100, 1400, 800)

        # 初始化数据库
        self.db_conn = init_database(db_path)
        self.player_dao = PlayerDAO(self.db_conn)
        self.position_dao = PositionDAO(self.db_conn)
        self.shop_dao = ShopDAO(self.db_conn)
        self.achievement_dao = AchievementDAO(self.db_conn)

        # 初始化UI
        self._init_ui()

        # 定时刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_all)
        self.refresh_timer.start(2000)  # 每2秒刷新一次

    def _init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # 创建选项卡
        tabs = QTabWidget()

        # 地图视图选项卡
        self.map_tab = self._create_map_tab()
        tabs.addTab(self.map_tab, "地图视图")

        # 玩家管理选项卡
        self.players_tab = self._create_players_tab()
        tabs.addTab(self.players_tab, "玩家管理")

        # 商店管理选项卡
        self.shop_tab = self._create_shop_tab()
        tabs.addTab(self.shop_tab, "商店管理")

        # 系统管理选项卡
        self.system_tab = self._create_system_tab()
        tabs.addTab(self.system_tab, "系统管理")

        main_layout.addWidget(tabs)

        # 刷新数据
        self.refresh_all()

    def _create_map_tab(self) -> QWidget:
        """创建地图视图选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 棋盘显示
        self.board_widget = BoardWidget()
        scroll = QScrollArea()
        scroll.setWidget(self.board_widget)
        scroll.setWidgetResizable(True)

        layout.addWidget(scroll)

        return widget

    def _create_players_tab(self) -> QWidget:
        """创建玩家管理选项卡"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 左侧：玩家列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        left_layout.addWidget(QLabel("玩家列表"))

        self.players_table = QTableWidget()
        self.players_table.setColumnCount(5)
        self.players_table.setHorizontalHeaderLabels(["QQ号", "昵称", "阵营", "当前积分", "总积分"])
        self.players_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.players_table.itemSelectionChanged.connect(self._on_player_selected)

        left_layout.addWidget(self.players_table)

        # 右侧：玩家详情
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        right_layout.addWidget(QLabel("玩家详情"))

        self.player_detail = QTextEdit()
        self.player_detail.setReadOnly(True)

        right_layout.addWidget(self.player_detail)

        # 使用分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        return widget

    def _create_shop_tab(self) -> QWidget:
        """创建商店管理选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("道具商店"))

        self.shop_table = QTableWidget()
        self.shop_table.setColumnCount(7)
        self.shop_table.setHorizontalHeaderLabels(["ID", "名称", "价格", "阵营", "全局限制", "已售", "已解锁"])
        self.shop_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.shop_table)

        # 操作按钮
        btn_layout = QHBoxLayout()

        unlock_all_btn = QPushButton("解锁所有道具")
        unlock_all_btn.clicked.connect(self._unlock_all_items)
        btn_layout.addWidget(unlock_all_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        return widget

    def _create_system_tab(self) -> QWidget:
        """创建系统管理选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 游戏统计
        stats_group = QGroupBox("游戏统计")
        stats_layout = QGridLayout()

        self.stats_labels = {}
        stats_items = ["总玩家数", "进行中玩家", "已登顶玩家", "总积分发放"]

        for i, item in enumerate(stats_items):
            stats_layout.addWidget(QLabel(f"{item}:"), i, 0)
            label = QLabel("0")
            self.stats_labels[item] = label
            stats_layout.addWidget(label, i, 1)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # 系统操作
        ops_group = QGroupBox("系统操作")
        ops_layout = QVBoxLayout()

        reset_btn = QPushButton("重置游戏")
        reset_btn.clicked.connect(self._reset_game)
        reset_btn.setStyleSheet("background-color: #ff4444; color: white;")
        ops_layout.addWidget(reset_btn)

        refresh_btn = QPushButton("刷新所有数据")
        refresh_btn.clicked.connect(self.refresh_all)
        ops_layout.addWidget(refresh_btn)

        ops_group.setLayout(ops_layout)
        layout.addWidget(ops_group)

        layout.addStretch()

        return widget

    def _on_player_selected(self):
        """玩家选中事件"""
        selected_items = self.players_table.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        qq_id = self.players_table.item(row, 0).text()

        # 显示玩家详细信息
        self._show_player_detail(qq_id)

    def _show_player_detail(self, qq_id: str):
        """显示玩家详细信息"""
        player = self.player_dao.get_player(qq_id)
        if not player:
            return

        positions = self.position_dao.get_positions(qq_id)
        achievements = self.achievement_dao.get_achievements(qq_id)

        detail_text = f"""
=== 玩家信息 ===
QQ号: {player.qq_id}
昵称: {player.nickname}
阵营: {player.faction or '未选择'}
当前积分: {player.current_score}
历史总积分: {player.total_score}

=== 位置信息 ===
"""

        temp_positions = [p for p in positions if p.marker_type == 'temp']
        perm_positions = [p for p in positions if p.marker_type == 'permanent']

        if temp_positions:
            detail_text += "临时标记:\n"
            for pos in temp_positions:
                detail_text += f"  - 列{pos.column_number}第{pos.position}格\n"
        else:
            detail_text += "临时标记: 无\n"

        if perm_positions:
            detail_text += "\n永久标记:\n"
            for pos in perm_positions:
                detail_text += f"  - 列{pos.column_number}第{pos.position}格\n"
        else:
            detail_text += "\n永久标记: 无\n"

        detail_text += f"\n=== 成就信息 ({len(achievements)}) ===\n"
        for ach in achievements:
            detail_text += f"- {ach.achievement_name} ({ach.achievement_type})\n"

        self.player_detail.setText(detail_text)

    def _unlock_all_items(self):
        """解锁所有道具"""
        reply = QMessageBox.question(
            self, "确认", "确定要解锁所有道具吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            cursor = self.db_conn.cursor()
            cursor.execute("UPDATE shop_items SET unlocked = 1")
            self.db_conn.commit()
            QMessageBox.information(self, "成功", "已解锁所有道具")
            self.refresh_shop()

    def _reset_game(self):
        """重置游戏"""
        reply = QMessageBox.warning(
            self, "警告", "确定要重置游戏吗？\n这将清除所有玩家数据！",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            from database.schema import DatabaseSchema
            DatabaseSchema.reset_game(self.db_conn)
            QMessageBox.information(self, "成功", "游戏已重置")
            self.refresh_all()

    def refresh_all(self):
        """刷新所有数据"""
        self.refresh_players()
        self.refresh_map()
        self.refresh_shop()
        self.refresh_stats()

    def refresh_players(self):
        """刷新玩家列表"""
        players = self.player_dao.get_all_players()

        self.players_table.setRowCount(len(players))

        for i, player in enumerate(players):
            self.players_table.setItem(i, 0, QTableWidgetItem(player.qq_id))
            self.players_table.setItem(i, 1, QTableWidgetItem(player.nickname))
            self.players_table.setItem(i, 2, QTableWidgetItem(player.faction or "未选择"))
            self.players_table.setItem(i, 3, QTableWidgetItem(str(player.current_score)))
            self.players_table.setItem(i, 4, QTableWidgetItem(str(player.total_score)))

    def refresh_map(self):
        """刷新地图"""
        all_positions = self.position_dao.get_all_positions_on_map()

        positions_dict = {}
        for qq_id, positions in all_positions.items():
            positions_dict[qq_id] = [
                (p.column_number, p.position, p.marker_type)
                for p in positions
            ]

        self.board_widget.update_positions(positions_dict)

    def refresh_shop(self):
        """刷新商店"""
        items = self.shop_dao.get_all_items()

        self.shop_table.setRowCount(len(items))

        for i, item in enumerate(items):
            self.shop_table.setItem(i, 0, QTableWidgetItem(str(item.item_id)))
            self.shop_table.setItem(i, 1, QTableWidgetItem(item.item_name))
            self.shop_table.setItem(i, 2, QTableWidgetItem(str(item.price)))
            self.shop_table.setItem(i, 3, QTableWidgetItem(item.faction_limit or "通用"))
            self.shop_table.setItem(i, 4, QTableWidgetItem(str(item.global_limit) if item.global_limit > 0 else "无限"))
            self.shop_table.setItem(i, 5, QTableWidgetItem(str(item.global_sold)))
            self.shop_table.setItem(i, 6, QTableWidgetItem("是" if item.unlocked else "否"))

    def refresh_stats(self):
        """刷新统计"""
        players = self.player_dao.get_all_players()

        total_players = len(players)
        total_score = sum(p.total_score for p in players)

        self.stats_labels["总玩家数"].setText(str(total_players))
        self.stats_labels["总积分发放"].setText(str(total_score))

        # TODO: 添加更多统计


def main():
    """主函数"""
    app = QApplication(sys.argv)

    window = GMWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
