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
from database.dao import PlayerDAO, PositionDAO, ShopDAO, AchievementDAO, InventoryDAO, GameStateDAO
from data.board_config import BOARD_DATA, COLUMN_HEIGHTS, VALID_COLUMNS
from datetime import datetime, timedelta


class BoardWidget(QWidget):
    """棋盘显示组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1200, 600)
        self.players_positions = {}  # {qq_id: [(column, position, marker_type), ...]}
        self.cell_contents = {}  # 从BOARD_DATA加载
        self.gem_pools = []  # 宝石池沼列表 [{gem_type, column_number, position, owner_name}, ...]

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

    def update_gem_pools(self, gem_pools: list):
        """更新宝石池沼位置"""
        self.gem_pools = gem_pools
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

                # 绘制宝石/池沼
                self._draw_gems(painter, col_num, pos, x, y, cell_width, cell_height)

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

    def _draw_gems(self, painter, column, position, x, y, width, height):
        """绘制宝石和池沼"""
        gems_at_pos = [g for g in self.gem_pools
                      if g.get('column_number') == column and g.get('position') == position]

        if not gems_at_pos:
            return

        gem_size = 10
        for i, gem in enumerate(gems_at_pos[:2]):  # 最多显示2个
            gem_type = gem.get('gem_type', '')
            offset_x = x + 2 + i * (gem_size + 2)
            offset_y = y + height // 2 - gem_size // 2

            # 根据类型设置颜色和形状
            if gem_type == 'red_gem':
                # 红色宝石 - 红色菱形
                painter.setBrush(QBrush(QColor(255, 0, 0)))
                painter.setPen(QPen(QColor(139, 0, 0), 2))
                self._draw_diamond(painter, offset_x, offset_y, gem_size)
            elif gem_type == 'blue_gem':
                # 蓝色宝石 - 蓝色菱形
                painter.setBrush(QBrush(QColor(0, 100, 255)))
                painter.setPen(QPen(QColor(0, 0, 139), 2))
                self._draw_diamond(painter, offset_x, offset_y, gem_size)
            elif gem_type == 'red_pool':
                # 红色池沼 - 红色波浪圆
                painter.setBrush(QBrush(QColor(255, 100, 100, 180)))
                painter.setPen(QPen(QColor(139, 0, 0), 1))
                painter.drawEllipse(offset_x, offset_y, gem_size, gem_size)
                # 画波浪线表示池沼
                painter.setPen(QPen(QColor(139, 0, 0), 1))
                painter.drawLine(offset_x + 2, offset_y + gem_size//2,
                               offset_x + gem_size - 2, offset_y + gem_size//2)
            elif gem_type == 'blue_pool':
                # 蓝色池沼 - 蓝色波浪圆
                painter.setBrush(QBrush(QColor(100, 100, 255, 180)))
                painter.setPen(QPen(QColor(0, 0, 139), 1))
                painter.drawEllipse(offset_x, offset_y, gem_size, gem_size)
                # 画波浪线表示池沼
                painter.setPen(QPen(QColor(0, 0, 139), 1))
                painter.drawLine(offset_x + 2, offset_y + gem_size//2,
                               offset_x + gem_size - 2, offset_y + gem_size//2)

    def _draw_diamond(self, painter, x, y, size):
        """绘制菱形（宝石形状）"""
        from PySide6.QtGui import QPolygon
        from PySide6.QtCore import QPoint
        points = QPolygon([
            QPoint(x + size // 2, y),           # 上
            QPoint(x + size, y + size // 2),    # 右
            QPoint(x + size // 2, y + size),    # 下
            QPoint(x, y + size // 2)            # 左
        ])
        painter.drawPolygon(points)

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

        # 宝石池沼图例
        painter.drawText(legend_x, legend_y + 180, "宝石/池沼:")

        # 红色宝石
        painter.setBrush(QBrush(QColor(255, 0, 0)))
        painter.setPen(QPen(QColor(139, 0, 0), 2))
        self._draw_diamond(painter, legend_x, legend_y + 195, 12)
        painter.setPen(QPen(Qt.black))
        painter.drawText(legend_x + 17, legend_y + 205, "红宝石")

        # 蓝色宝石
        painter.setBrush(QBrush(QColor(0, 100, 255)))
        painter.setPen(QPen(QColor(0, 0, 139), 2))
        self._draw_diamond(painter, legend_x, legend_y + 215, 12)
        painter.setPen(QPen(Qt.black))
        painter.drawText(legend_x + 17, legend_y + 225, "蓝宝石")

        # 红色池沼
        painter.setBrush(QBrush(QColor(255, 100, 100, 180)))
        painter.setPen(QPen(QColor(139, 0, 0), 1))
        painter.drawEllipse(legend_x, legend_y + 235, 12, 12)
        painter.setPen(QPen(Qt.black))
        painter.drawText(legend_x + 17, legend_y + 245, "红池沼")

        # 蓝色池沼
        painter.setBrush(QBrush(QColor(100, 100, 255, 180)))
        painter.setPen(QPen(QColor(0, 0, 139), 1))
        painter.drawEllipse(legend_x, legend_y + 255, 12, 12)
        painter.setPen(QPen(Qt.black))
        painter.drawText(legend_x + 17, legend_y + 265, "蓝池沼")


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
        self.inventory_dao = InventoryDAO(self.db_conn)
        self.state_dao = GameStateDAO(self.db_conn)

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
        self.players_table.setColumnCount(6)
        self.players_table.setHorizontalHeaderLabels(["QQ号", "昵称", "阵营", "当前积分", "总积分", "锁定状态"])
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

        # 积分修改系统
        score_group = QGroupBox("积分管理")
        score_layout = QGridLayout()

        # 当前选中的玩家QQ号
        self.selected_qq_id = None

        # 积分修改输入
        score_layout.addWidget(QLabel("修改积分:"), 0, 0)
        self.score_input = QLineEdit()
        self.score_input.setPlaceholderText("输入积分数值（正数为增加，负数为扣除）")
        score_layout.addWidget(self.score_input, 0, 1)

        # 积分类型选择
        score_layout.addWidget(QLabel("积分类型:"), 1, 0)
        self.score_type_combo = QComboBox()
        self.score_type_combo.addItems(["当前积分", "总积分", "同时修改两者"])
        score_layout.addWidget(self.score_type_combo, 1, 1)

        # 操作按钮
        btn_row = QHBoxLayout()

        add_score_btn = QPushButton("增加积分")
        add_score_btn.clicked.connect(self._add_score)
        add_score_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        btn_row.addWidget(add_score_btn)

        set_score_btn = QPushButton("设置积分")
        set_score_btn.clicked.connect(self._set_score)
        set_score_btn.setStyleSheet("background-color: #2196F3; color: white;")
        btn_row.addWidget(set_score_btn)

        reset_score_btn = QPushButton("重置积分")
        reset_score_btn.clicked.connect(self._reset_score)
        reset_score_btn.setStyleSheet("background-color: #f44336; color: white;")
        btn_row.addWidget(reset_score_btn)

        score_layout.addLayout(btn_row, 2, 0, 1, 2)

        # 快捷操作
        quick_label = QLabel("快捷操作:")
        score_layout.addWidget(quick_label, 3, 0)

        quick_btns = QHBoxLayout()
        for amount in [100, 500, 1000, -100, -500]:
            btn_text = f"+{amount}" if amount > 0 else str(amount)
            btn = QPushButton(btn_text)
            btn.clicked.connect(lambda checked, a=amount: self._quick_add_score(a))
            if amount > 0:
                btn.setStyleSheet("background-color: #4CAF50; color: white;")
            else:
                btn.setStyleSheet("background-color: #FF9800; color: white;")
            quick_btns.addWidget(btn)

        score_layout.addLayout(quick_btns, 3, 1)

        score_group.setLayout(score_layout)
        right_layout.addWidget(score_group)

        # 道具派发系统
        item_group = QGroupBox("道具派发")
        item_layout = QGridLayout()

        # 道具选择下拉框
        item_layout.addWidget(QLabel("选择道具:"), 0, 0)
        self.item_combo = QComboBox()
        self.item_combo.setMinimumWidth(200)
        item_layout.addWidget(self.item_combo, 0, 1)

        # 数量输入
        item_layout.addWidget(QLabel("数量:"), 1, 0)
        self.item_quantity_input = QLineEdit()
        self.item_quantity_input.setText("1")
        self.item_quantity_input.setPlaceholderText("输入数量")
        item_layout.addWidget(self.item_quantity_input, 1, 1)

        # 派发按钮
        give_item_btn = QPushButton("派发道具")
        give_item_btn.clicked.connect(self._give_item)
        give_item_btn.setStyleSheet("background-color: #9C27B0; color: white;")
        item_layout.addWidget(give_item_btn, 2, 0, 1, 2)

        item_group.setLayout(item_layout)
        right_layout.addWidget(item_group)

        # 锁定管理系统
        lockout_group = QGroupBox("锁定管理")
        lockout_layout = QGridLayout()

        # 锁定状态显示
        lockout_layout.addWidget(QLabel("锁定状态:"), 0, 0)
        self.lockout_status_label = QLabel("未选择玩家")
        self.lockout_status_label.setStyleSheet("font-weight: bold;")
        lockout_layout.addWidget(self.lockout_status_label, 0, 1)

        # 倒计时显示
        lockout_layout.addWidget(QLabel("剩余时间:"), 1, 0)
        self.lockout_countdown_label = QLabel("-")
        self.lockout_countdown_label.setStyleSheet("color: #f44336; font-weight: bold;")
        lockout_layout.addWidget(self.lockout_countdown_label, 1, 1)

        # 锁定时长输入
        lockout_layout.addWidget(QLabel("锁定时长(小时):"), 2, 0)
        self.lockout_hours_input = QLineEdit()
        self.lockout_hours_input.setText("12")
        self.lockout_hours_input.setPlaceholderText("输入锁定小时数")
        lockout_layout.addWidget(self.lockout_hours_input, 2, 1)

        # 操作按钮
        lockout_btn_row = QHBoxLayout()

        lock_btn = QPushButton("锁定玩家")
        lock_btn.clicked.connect(self._lock_player)
        lock_btn.setStyleSheet("background-color: #f44336; color: white;")
        lockout_btn_row.addWidget(lock_btn)

        unlock_btn = QPushButton("解锁玩家")
        unlock_btn.clicked.connect(self._unlock_player)
        unlock_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        lockout_btn_row.addWidget(unlock_btn)

        lockout_layout.addLayout(lockout_btn_row, 3, 0, 1, 2)

        lockout_group.setLayout(lockout_layout)
        right_layout.addWidget(lockout_group)

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
            self.selected_qq_id = None
            return

        row = selected_items[0].row()
        qq_id = self.players_table.item(row, 0).text()
        self.selected_qq_id = qq_id

        # 显示玩家详细信息
        self._show_player_detail(qq_id)

    def _show_player_detail(self, qq_id: str):
        """显示玩家详细信息"""
        player = self.player_dao.get_player(qq_id)
        if not player:
            return

        positions = self.position_dao.get_positions(qq_id)
        achievements = self.achievement_dao.get_achievements(qq_id)
        inventory = self.inventory_dao.get_inventory(qq_id)
        state = self.state_dao.get_state(qq_id)

        # 更新锁定状态显示
        self._update_lockout_display(state)

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

        detail_text += f"\n=== 背包物品 ({len(inventory)}) ===\n"
        if inventory:
            for item in inventory:
                detail_text += f"- {item.item_name} x{item.quantity}\n"
        else:
            detail_text += "背包为空\n"

        detail_text += f"\n=== 成就信息 ({len(achievements)}) ===\n"
        for ach in achievements:
            detail_text += f"- {ach.achievement_name} ({ach.achievement_type})\n"

        self.player_detail.setText(detail_text)

    def _add_score(self):
        """增加积分"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        try:
            amount = int(self.score_input.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的数字")
            return

        self._modify_score(amount, is_add=True)

    def _set_score(self):
        """设置积分（直接覆盖）"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        try:
            amount = int(self.score_input.text())
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的数字")
            return

        self._modify_score(amount, is_add=False)

    def _reset_score(self):
        """重置积分为0"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        reply = QMessageBox.question(
            self, "确认", f"确定要重置玩家 {self.selected_qq_id} 的积分吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._modify_score(0, is_add=False)

    def _quick_add_score(self, amount: int):
        """快捷增加/扣除积分"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        self._modify_score(amount, is_add=True)

    def _modify_score(self, amount: int, is_add: bool = True):
        """修改积分的核心方法"""
        player = self.player_dao.get_player(self.selected_qq_id)
        if not player:
            QMessageBox.warning(self, "错误", "玩家不存在")
            return

        score_type = self.score_type_combo.currentText()
        cursor = self.db_conn.cursor()

        try:
            if score_type == "当前积分":
                if is_add:
                    new_score = player.current_score + amount
                else:
                    new_score = amount

                cursor.execute(
                    "UPDATE players SET current_score = ? WHERE qq_id = ?",
                    (max(0, new_score), self.selected_qq_id)
                )
                msg = f"当前积分已{'增加' if is_add else '设置为'} {amount if is_add else new_score}"

            elif score_type == "总积分":
                if is_add:
                    new_score = player.total_score + amount
                else:
                    new_score = amount

                cursor.execute(
                    "UPDATE players SET total_score = ? WHERE qq_id = ?",
                    (max(0, new_score), self.selected_qq_id)
                )
                msg = f"总积分已{'增加' if is_add else '设置为'} {amount if is_add else new_score}"

            else:  # 同时修改两者
                if is_add:
                    new_current = player.current_score + amount
                    new_total = player.total_score + amount
                else:
                    new_current = amount
                    new_total = amount

                cursor.execute(
                    "UPDATE players SET current_score = ?, total_score = ? WHERE qq_id = ?",
                    (max(0, new_current), max(0, new_total), self.selected_qq_id)
                )
                msg = f"当前积分和总积分已{'增加' if is_add else '设置为'} {amount if is_add else new_total}"

            self.db_conn.commit()
            QMessageBox.information(self, "成功", msg)

            # 刷新显示
            self.refresh_players()
            self._show_player_detail(self.selected_qq_id)
            self.score_input.clear()

        except Exception as e:
            self.db_conn.rollback()
            QMessageBox.critical(self, "错误", f"修改失败: {str(e)}")

    def _give_item(self):
        """派发道具给选中的玩家"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        if self.item_combo.count() == 0:
            QMessageBox.warning(self, "警告", "没有可用的道具")
            return

        # 获取选中的道具信息
        item_data = self.item_combo.currentData()
        if not item_data:
            QMessageBox.warning(self, "警告", "请选择一个道具")
            return

        item_id, item_name, item_type = item_data

        # 获取数量
        try:
            quantity = int(self.item_quantity_input.text())
            if quantity <= 0:
                raise ValueError()
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的正整数数量")
            return

        # 派发道具
        try:
            for _ in range(quantity):
                self.inventory_dao.add_item(
                    self.selected_qq_id,
                    item_id,
                    item_name,
                    item_type
                )

            player = self.player_dao.get_player(self.selected_qq_id)
            QMessageBox.information(
                self, "成功",
                f"已向玩家 {player.nickname} 派发 {quantity} 个 [{item_name}]"
            )

            # 刷新玩家详情
            self._show_player_detail(self.selected_qq_id)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"派发失败: {str(e)}")

    def _refresh_item_combo(self):
        """刷新道具下拉框"""
        self.item_combo.clear()

        # 从商店获取所有道具
        items = self.shop_dao.get_all_items()
        for item in items:
            # 显示名称，存储 (id, name, type)
            display_name = f"{item.item_name} ({item.faction_limit or '通用'})"
            self.item_combo.addItem(display_name, (item.item_id, item.item_name, item.item_type))

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
        self._refresh_item_combo()

        # 刷新当前选中玩家的锁定倒计时
        if self.selected_qq_id:
            state = self.state_dao.get_state(self.selected_qq_id)
            self._update_lockout_display(state)

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

            # 获取锁定状态
            state = self.state_dao.get_state(player.qq_id)
            lockout_status = "正常"
            if state and state.lockout_until:
                try:
                    lockout_time = datetime.fromisoformat(state.lockout_until)
                    if datetime.now() < lockout_time:
                        remaining = lockout_time - datetime.now()
                        hours = int(remaining.total_seconds() // 3600)
                        mins = int((remaining.total_seconds() % 3600) // 60)
                        lockout_status = f"🔒 {hours}h{mins}m"
                except ValueError:
                    lockout_status = "异常"

            lockout_item = QTableWidgetItem(lockout_status)
            if lockout_status.startswith("🔒"):
                lockout_item.setForeground(QColor(244, 67, 54))  # 红色
            self.players_table.setItem(i, 5, lockout_item)

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

        # 刷新宝石池沼
        from database.dao import GemPoolDAO
        gem_dao = GemPoolDAO(self.db_conn)
        gem_pools = gem_dao.get_all_active_gems()
        self.board_widget.update_gem_pools(gem_pools)

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

    def _update_lockout_display(self, state):
        """更新锁定状态显示"""
        if not state or not state.lockout_until:
            self.lockout_status_label.setText("未锁定")
            self.lockout_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.lockout_countdown_label.setText("-")
            return

        try:
            lockout_time = datetime.fromisoformat(state.lockout_until)
            now = datetime.now()

            if now < lockout_time:
                # 仍在锁定中
                self.lockout_status_label.setText("🔒 已锁定")
                self.lockout_status_label.setStyleSheet("color: #f44336; font-weight: bold;")

                # 计算剩余时间
                remaining = lockout_time - now
                total_seconds = remaining.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                seconds = int(total_seconds % 60)

                self.lockout_countdown_label.setText(
                    f"{hours}小时{minutes}分{seconds}秒\n解锁时间: {lockout_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            else:
                # 锁定已过期
                self.lockout_status_label.setText("未锁定")
                self.lockout_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
                self.lockout_countdown_label.setText("-")
        except ValueError:
            self.lockout_status_label.setText("状态异常")
            self.lockout_status_label.setStyleSheet("color: #FF9800; font-weight: bold;")
            self.lockout_countdown_label.setText("-")

    def _lock_player(self):
        """锁定玩家"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        try:
            hours = float(self.lockout_hours_input.text())
            if hours <= 0:
                QMessageBox.warning(self, "警告", "锁定时长必须大于0")
                return
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的小时数")
            return

        # 确认操作
        player = self.player_dao.get_player(self.selected_qq_id)
        reply = QMessageBox.question(
            self, "确认锁定",
            f"确定要锁定玩家 {player.nickname}({self.selected_qq_id}) {hours} 小时吗？\n"
            f"锁定期间该玩家将无法进行游戏。",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # 设置锁定时间
            state = self.state_dao.get_state(self.selected_qq_id)
            lockout_time = datetime.now() + timedelta(hours=hours)
            state.lockout_until = lockout_time.isoformat()
            self.state_dao.update_state(state)

            QMessageBox.information(
                self, "锁定成功",
                f"玩家 {player.nickname} 已被锁定 {hours} 小时\n"
                f"解锁时间: {lockout_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # 刷新显示
            self._show_player_detail(self.selected_qq_id)

    def _unlock_player(self):
        """解锁玩家"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        state = self.state_dao.get_state(self.selected_qq_id)
        if not state.lockout_until:
            QMessageBox.information(self, "提示", "该玩家当前未被锁定")
            return

        # 确认操作
        player = self.player_dao.get_player(self.selected_qq_id)
        reply = QMessageBox.question(
            self, "确认解锁",
            f"确定要解锁玩家 {player.nickname}({self.selected_qq_id}) 吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # 清除锁定
            state.lockout_until = None
            self.state_dao.update_state(state)

            QMessageBox.information(self, "解锁成功", f"玩家 {player.nickname} 已被解锁")

            # 刷新显示
            self._show_player_detail(self.selected_qq_id)


def main():
    """主函数"""
    app = QApplication(sys.argv)

    window = GMWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
