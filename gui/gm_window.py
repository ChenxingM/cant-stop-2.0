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
    QHeaderView, QScrollArea, QFrame, QSplitter, QComboBox,
    QSpinBox, QCheckBox, QToolTip, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QProgressBar, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize, QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QCursor

from database.schema import init_database
from database.dao import (
    PlayerDAO, PositionDAO, ShopDAO, AchievementDAO,
    InventoryDAO, GameStateDAO, GemPoolDAO, ContractDAO, CustomCommandDAO
)
from data.board_config import BOARD_DATA, COLUMN_HEIGHTS, VALID_COLUMNS
from datetime import datetime, timedelta


class BoardWidget(QWidget):
    """棋盘显示组件 - 支持悬浮提示和点击交互"""

    # 信号：点击了某个玩家的棋子
    player_clicked = Signal(str)  # 发送qq_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1200, 600)
        self.setMouseTracking(True)  # 启用鼠标追踪

        self.players_positions = {}  # {qq_id: [(column, position, marker_type), ...]}
        self.player_info = {}  # {qq_id: {'nickname': ..., 'faction': ...}}
        self.cell_contents = {}  # 从BOARD_DATA加载
        self.gem_pools = []  # 宝石池沼列表

        # 绘制参数
        self.cell_width = 65
        self.cell_height = 42
        self.start_x = 130
        self.start_y = 520

        # 悬浮提示相关
        self.hovered_players = []  # 当前悬浮位置的玩家列表
        self.hover_pos = None  # 鼠标位置

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

    def update_player_info(self, player_info: dict):
        """更新玩家信息"""
        self.player_info = player_info

    def update_gem_pools(self, gem_pools: list):
        """更新宝石池沼位置"""
        self.gem_pools = gem_pools
        self.update()

    def _get_cell_rect(self, column: int, position: int) -> QRect:
        """获取格子的矩形区域"""
        x = self.start_x + (column - 3) * (self.cell_width + 8)
        y = self.start_y - position * self.cell_height
        return QRect(x, y, self.cell_width, self.cell_height)

    def _get_players_at_position(self, column: int, position: int) -> list:
        """获取指定位置的所有玩家"""
        players = []
        for qq_id, positions in self.players_positions.items():
            for col, pos, marker_type in positions:
                if col == column and pos == position:
                    info = self.player_info.get(qq_id, {})
                    players.append({
                        'qq_id': qq_id,
                        'nickname': info.get('nickname', qq_id),
                        'faction': info.get('faction', '未知'),
                        'marker_type': marker_type
                    })
        return players

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - 显示悬浮提示"""
        pos = event.pos()
        self.hover_pos = pos

        # 查找鼠标所在的格子
        found_players = []
        for col_num in VALID_COLUMNS:
            height = COLUMN_HEIGHTS[col_num]
            for pos_num in range(1, height + 1):
                rect = self._get_cell_rect(col_num, pos_num)
                if rect.contains(pos):
                    found_players = self._get_players_at_position(col_num, pos_num)
                    break
            if found_players:
                break

        self.hovered_players = found_players

        # 显示悬浮提示
        if found_players:
            tooltip_text = ""
            for p in found_players:
                marker = "🟠临时" if p['marker_type'] == 'temp' else "🔵永久"
                tooltip_text += f"{p['nickname']} ({p['qq_id']})\n阵营: {p['faction']}\n标记: {marker}\n\n"
            QToolTip.showText(event.globalPos(), tooltip_text.strip(), self)
        else:
            QToolTip.hideText()

        self.update()

    def mousePressEvent(self, event):
        """鼠标点击事件 - 跳转到玩家管理"""
        if event.button() == Qt.LeftButton and self.hovered_players:
            # 如果有多个玩家，选择第一个
            qq_id = self.hovered_players[0]['qq_id']
            self.player_clicked.emit(qq_id)

    def paintEvent(self, event):
        """绘制棋盘"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制每列
        for col_num in VALID_COLUMNS:
            height = COLUMN_HEIGHTS[col_num]
            x = self.start_x + (col_num - 3) * (self.cell_width + 8)

            # 绘制列号
            painter.setPen(QPen(Qt.black, 2))
            painter.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
            painter.drawText(x, self.start_y + 25, self.cell_width, 20, Qt.AlignCenter, f"{col_num}")

            # 绘制格子
            for pos in range(height, 0, -1):
                y = self.start_y - pos * self.cell_height

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

                painter.drawRect(x, y, self.cell_width, self.cell_height)

                # 绘制位置编号
                painter.setPen(QPen(Qt.gray))
                painter.setFont(QFont("Arial", 8))
                painter.drawText(x + 2, y + 2, 15, 15, Qt.AlignCenter, str(pos))

                # 绘制玩家标记
                self._draw_markers(painter, col_num, pos, x, y, self.cell_width, self.cell_height)

                # 绘制宝石/池沼
                self._draw_gems(painter, col_num, pos, x, y, self.cell_width, self.cell_height)

        # 绘制图例
        self._draw_legend(painter)

    def _draw_markers(self, painter, column, position, x, y, width, height):
        """绘制玩家标记"""
        temp_players = []
        perm_players = []

        for qq_id, positions in self.players_positions.items():
            for col, pos, marker_type in positions:
                if col == column and pos == position:
                    info = self.player_info.get(qq_id, {})
                    player_data = {'qq_id': qq_id, 'nickname': info.get('nickname', qq_id[:4])}
                    if marker_type == 'temp':
                        temp_players.append(player_data)
                    else:
                        perm_players.append(player_data)

        marker_size = 14

        # 绘制永久标记（圆形）
        if perm_players:
            for i, p in enumerate(perm_players[:3]):
                offset_x = x + width - marker_size - 2 - i * (marker_size + 2)
                offset_y = y + height - marker_size - 2

                # 绘制蓝色圆形
                painter.setBrush(QBrush(QColor(30, 144, 255)))
                painter.setPen(QPen(QColor(0, 0, 139), 1))
                painter.drawEllipse(offset_x, offset_y, marker_size, marker_size)

                # 显示昵称首字
                painter.setPen(QPen(Qt.white))
                painter.setFont(QFont("Microsoft YaHei", 7, QFont.Bold))
                first_char = p['nickname'][0] if p['nickname'] else '?'
                painter.drawText(offset_x, offset_y, marker_size, marker_size, Qt.AlignCenter, first_char)

        # 绘制临时标记（方形）
        if temp_players:
            for i, p in enumerate(temp_players[:3]):
                offset_x = x + width - marker_size - 2 - i * (marker_size + 2)
                offset_y = y + 2

                # 绘制橙色方形
                painter.setBrush(QBrush(QColor(255, 140, 0)))
                painter.setPen(QPen(QColor(200, 100, 0), 1))
                painter.drawRect(offset_x, offset_y, marker_size, marker_size)

                # 显示昵称首字
                painter.setPen(QPen(Qt.white))
                painter.setFont(QFont("Microsoft YaHei", 7, QFont.Bold))
                first_char = p['nickname'][0] if p['nickname'] else '?'
                painter.drawText(offset_x, offset_y, marker_size, marker_size, Qt.AlignCenter, first_char)

    def _draw_gems(self, painter, column, position, x, y, width, height):
        """绘制宝石和池沼"""
        gems_at_pos = [g for g in self.gem_pools
                      if g.get('column_number') == column and g.get('position') == position]

        if not gems_at_pos:
            return

        gem_size = 10
        for i, gem in enumerate(gems_at_pos[:2]):
            gem_type = gem.get('gem_type', '')
            offset_x = x + 2 + i * (gem_size + 2)
            offset_y = y + height // 2 - gem_size // 2

            if gem_type == 'red_gem':
                painter.setBrush(QBrush(QColor(255, 0, 0)))
                painter.setPen(QPen(QColor(139, 0, 0), 2))
                self._draw_diamond(painter, offset_x, offset_y, gem_size)
            elif gem_type == 'blue_gem':
                painter.setBrush(QBrush(QColor(0, 100, 255)))
                painter.setPen(QPen(QColor(0, 0, 139), 2))
                self._draw_diamond(painter, offset_x, offset_y, gem_size)
            elif gem_type == 'red_pool':
                painter.setBrush(QBrush(QColor(255, 100, 100, 180)))
                painter.setPen(QPen(QColor(139, 0, 0), 1))
                painter.drawEllipse(offset_x, offset_y, gem_size, gem_size)
            elif gem_type == 'blue_pool':
                painter.setBrush(QBrush(QColor(100, 100, 255, 180)))
                painter.setPen(QPen(QColor(0, 0, 139), 1))
                painter.drawEllipse(offset_x, offset_y, gem_size, gem_size)

    def _draw_diamond(self, painter, x, y, size):
        """绘制菱形（宝石形状）"""
        from PySide6.QtGui import QPolygon
        from PySide6.QtCore import QPoint
        points = QPolygon([
            QPoint(x + size // 2, y),
            QPoint(x + size, y + size // 2),
            QPoint(x + size // 2, y + size),
            QPoint(x, y + size // 2)
        ])
        painter.drawPolygon(points)

    def _draw_legend(self, painter):
        """绘制图例"""
        legend_x = 15
        legend_y = 15

        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.setPen(QPen(Qt.black))
        painter.drawText(legend_x, legend_y, "【图例】")

        # 内容类型
        items = [
            (QColor(173, 216, 230), "遭遇", 25),
            (QColor(144, 238, 144), "道具", 45),
            (QColor(255, 182, 193), "陷阱", 65),
        ]

        for color, text, offset in items:
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.black, 1))
            painter.drawRect(legend_x, legend_y + offset, 18, 14)
            painter.drawText(legend_x + 22, legend_y + offset + 12, text)

        # 标记类型
        painter.drawText(legend_x, legend_y + 100, "【标记】")

        painter.setBrush(QBrush(QColor(255, 140, 0)))
        painter.drawRect(legend_x, legend_y + 115, 14, 14)
        painter.drawText(legend_x + 18, legend_y + 127, "临时")

        painter.setBrush(QBrush(QColor(30, 144, 255)))
        painter.drawEllipse(legend_x, legend_y + 135, 14, 14)
        painter.drawText(legend_x + 18, legend_y + 147, "永久")

        # 宝石池沼
        painter.drawText(legend_x, legend_y + 175, "【宝石/池沼】")

        painter.setBrush(QBrush(QColor(255, 0, 0)))
        self._draw_diamond(painter, legend_x, legend_y + 190, 12)
        painter.drawText(legend_x + 16, legend_y + 200, "红宝石")

        painter.setBrush(QBrush(QColor(0, 100, 255)))
        self._draw_diamond(painter, legend_x, legend_y + 210, 12)
        painter.drawText(legend_x + 16, legend_y + 220, "蓝宝石")

        painter.setBrush(QBrush(QColor(255, 100, 100, 180)))
        painter.drawEllipse(legend_x, legend_y + 230, 12, 12)
        painter.drawText(legend_x + 16, legend_y + 240, "红池沼")

        painter.setBrush(QBrush(QColor(100, 100, 255, 180)))
        painter.drawEllipse(legend_x, legend_y + 250, 12, 12)
        painter.drawText(legend_x + 16, legend_y + 260, "蓝池沼")

        # 操作提示
        painter.setPen(QPen(QColor(100, 100, 100)))
        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.drawText(legend_x, legend_y + 290, "💡 悬浮棋子查看玩家")
        painter.drawText(legend_x, legend_y + 305, "💡 点击棋子跳转管理")


class GMWindow(QMainWindow):
    """GM管理主窗口"""

    def __init__(self, db_path: str = "data/game.db"):
        super().__init__()
        self.setWindowTitle("贪骰无厌 2.0 - GM管理界面")
        self.setGeometry(50, 50, 1500, 900)

        # 保存数据库路径
        self.db_path = db_path

        # 初始化数据库
        self.db_conn = init_database(db_path)
        self.player_dao = PlayerDAO(self.db_conn)
        self.position_dao = PositionDAO(self.db_conn)
        self.shop_dao = ShopDAO(self.db_conn)
        self.achievement_dao = AchievementDAO(self.db_conn)
        self.inventory_dao = InventoryDAO(self.db_conn)
        self.state_dao = GameStateDAO(self.db_conn)
        self.gem_dao = GemPoolDAO(self.db_conn)
        self.contract_dao = ContractDAO(self.db_conn)
        self.custom_cmd_dao = CustomCommandDAO(self.db_conn)

        # 当前选中的玩家
        self.selected_qq_id = None

        # Tab组件引用
        self.tabs = None

        # 初始化UI
        self._init_ui()

        # 定时刷新
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_all)
        self.refresh_timer.start(2000)

    def _init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # 创建选项卡
        self.tabs = QTabWidget()

        # 地图视图选项卡
        self.map_tab = self._create_map_tab()
        self.tabs.addTab(self.map_tab, "🗺️ 地图视图")

        # 玩家管理选项卡
        self.players_tab = self._create_players_tab()
        self.tabs.addTab(self.players_tab, "👥 玩家管理")

        # 全局控制选项卡
        self.control_tab = self._create_control_tab()
        self.tabs.addTab(self.control_tab, "🌍 全局控制")

        # 商店管理选项卡
        self.shop_tab = self._create_shop_tab()
        self.tabs.addTab(self.shop_tab, "🛒 商店管理")

        # 口令管理选项卡
        self.command_tab = self._create_command_tab()
        self.tabs.addTab(self.command_tab, "📣 口令管理")

        # 系统管理选项卡
        self.system_tab = self._create_system_tab()
        self.tabs.addTab(self.system_tab, "⚙️ 系统管理")

        main_layout.addWidget(self.tabs)

        # 刷新数据
        self.refresh_all()

    def _create_map_tab(self) -> QWidget:
        """创建地图视图选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 工具栏
        toolbar = QHBoxLayout()

        refresh_btn = QPushButton("🔄 刷新地图")
        refresh_btn.clicked.connect(self.refresh_map)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()

        # 玩家筛选
        toolbar.addWidget(QLabel("筛选玩家:"))
        self.map_player_filter = QComboBox()
        self.map_player_filter.addItem("显示全部", None)
        self.map_player_filter.setMinimumWidth(150)
        toolbar.addWidget(self.map_player_filter)

        layout.addLayout(toolbar)

        # 棋盘显示
        self.board_widget = BoardWidget()
        self.board_widget.player_clicked.connect(self._on_board_player_clicked)

        scroll = QScrollArea()
        scroll.setWidget(self.board_widget)
        scroll.setWidgetResizable(True)

        layout.addWidget(scroll)

        return widget

    def _on_board_player_clicked(self, qq_id: str):
        """地图上点击玩家棋子时跳转到玩家管理"""
        self.selected_qq_id = qq_id
        self.tabs.setCurrentIndex(1)  # 切换到玩家管理tab

        # 在玩家列表中选中该玩家
        for i in range(self.players_table.rowCount()):
            if self.players_table.item(i, 0).text() == qq_id:
                self.players_table.selectRow(i)
                break

        self._show_player_detail(qq_id)

    def _create_players_tab(self) -> QWidget:
        """创建玩家管理选项卡（整合玩家操控功能）"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 左侧：玩家列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # 搜索栏
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self.player_search = QLineEdit()
        self.player_search.setPlaceholderText("输入QQ号或昵称...")
        self.player_search.textChanged.connect(self._filter_players)
        search_layout.addWidget(self.player_search)
        left_layout.addLayout(search_layout)

        # 手动注册玩家
        register_group = QGroupBox("📝 注册玩家")
        register_layout = QGridLayout()

        register_layout.addWidget(QLabel("QQ号:"), 0, 0)
        self.register_qq_input = QLineEdit()
        self.register_qq_input.setPlaceholderText("输入QQ号")
        register_layout.addWidget(self.register_qq_input, 0, 1)

        register_layout.addWidget(QLabel("昵称:"), 1, 0)
        self.register_nickname_input = QLineEdit()
        self.register_nickname_input.setPlaceholderText("输入昵称")
        register_layout.addWidget(self.register_nickname_input, 1, 1)

        register_layout.addWidget(QLabel("阵营:"), 2, 0)
        self.register_faction_combo = QComboBox()
        self.register_faction_combo.addItems(["未选择", "收养人", "Aeonreth"])
        register_layout.addWidget(self.register_faction_combo, 2, 1)

        register_layout.addWidget(QLabel("初始积分:"), 3, 0)
        self.register_score_input = QSpinBox()
        self.register_score_input.setRange(0, 99999)
        self.register_score_input.setValue(0)
        register_layout.addWidget(self.register_score_input, 3, 1)

        register_btn_layout = QHBoxLayout()
        register_btn = QPushButton("注册玩家")
        register_btn.clicked.connect(self._register_player)
        register_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        register_btn_layout.addWidget(register_btn)

        import_csv_btn = QPushButton("导入CSV")
        import_csv_btn.clicked.connect(self._import_players_csv)
        import_csv_btn.setStyleSheet("background-color: #2196F3; color: white;")
        register_btn_layout.addWidget(import_csv_btn)

        delete_btn = QPushButton("删除玩家")
        delete_btn.clicked.connect(self._delete_player)
        delete_btn.setStyleSheet("background-color: #f44336; color: white;")
        register_btn_layout.addWidget(delete_btn)

        register_layout.addLayout(register_btn_layout, 4, 0, 1, 2)

        register_group.setLayout(register_layout)
        left_layout.addWidget(register_group)

        # 玩家列表
        self.players_table = QTableWidget()
        self.players_table.setColumnCount(7)
        self.players_table.setHorizontalHeaderLabels(
            ["QQ号", "昵称", "阵营", "当前积分", "总积分", "登顶列数", "状态"]
        )
        self.players_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.players_table.itemSelectionChanged.connect(self._on_player_selected)
        self.players_table.setSelectionBehavior(QTableWidget.SelectRows)

        left_layout.addWidget(self.players_table)

        # 中间：玩家详情和基础操作
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)

        # 使用滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # 玩家进度显示
        progress_group = QGroupBox("📊 玩家进度")
        progress_layout = QVBoxLayout()

        self.progress_display = QTextEdit()
        self.progress_display.setReadOnly(True)
        self.progress_display.setMaximumHeight(150)
        progress_layout.addWidget(self.progress_display)

        progress_group.setLayout(progress_layout)
        scroll_layout.addWidget(progress_group)

        # 玩家详情
        detail_group = QGroupBox("📋 详细信息")
        detail_layout = QVBoxLayout()

        self.player_detail = QTextEdit()
        self.player_detail.setReadOnly(True)
        self.player_detail.setMaximumHeight(200)
        detail_layout.addWidget(self.player_detail)

        detail_group.setLayout(detail_layout)
        scroll_layout.addWidget(detail_group)

        # 积分管理
        score_group = QGroupBox("💰 积分管理")
        score_layout = QGridLayout()

        score_layout.addWidget(QLabel("数值:"), 0, 0)
        self.score_input = QLineEdit()
        self.score_input.setPlaceholderText("正数增加，负数扣除")
        score_layout.addWidget(self.score_input, 0, 1)

        score_layout.addWidget(QLabel("类型:"), 1, 0)
        self.score_type_combo = QComboBox()
        self.score_type_combo.addItems(["当前积分", "总积分", "同时修改"])
        score_layout.addWidget(self.score_type_combo, 1, 1)

        btn_row = QHBoxLayout()
        for text, color, func in [
            ("增加", "#4CAF50", self._add_score),
            ("设置", "#2196F3", self._set_score),
            ("重置", "#f44336", self._reset_score)
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(func)
            btn.setStyleSheet(f"background-color: {color}; color: white;")
            btn_row.addWidget(btn)
        score_layout.addLayout(btn_row, 2, 0, 1, 2)

        # 快捷按钮
        quick_btns = QHBoxLayout()
        for amount in [50, 100, 500, -50, -100]:
            btn_text = f"+{amount}" if amount > 0 else str(amount)
            btn = QPushButton(btn_text)
            btn.clicked.connect(lambda checked, a=amount: self._quick_add_score(a))
            btn.setStyleSheet(f"background-color: {'#4CAF50' if amount > 0 else '#FF9800'}; color: white;")
            quick_btns.addWidget(btn)
        score_layout.addLayout(quick_btns, 3, 0, 1, 2)

        score_group.setLayout(score_layout)
        scroll_layout.addWidget(score_group)

        # 道具派发
        item_group = QGroupBox("🎁 道具派发")
        item_layout = QGridLayout()

        item_layout.addWidget(QLabel("道具:"), 0, 0)
        self.item_combo = QComboBox()
        self.item_combo.setMinimumWidth(200)
        self._init_item_combo()
        item_layout.addWidget(self.item_combo, 0, 1)

        item_layout.addWidget(QLabel("数量:"), 1, 0)
        self.item_quantity_input = QSpinBox()
        self.item_quantity_input.setRange(1, 99)
        self.item_quantity_input.setValue(1)
        item_layout.addWidget(self.item_quantity_input, 1, 1)

        give_item_btn = QPushButton("派发道具")
        give_item_btn.clicked.connect(self._give_item)
        give_item_btn.setStyleSheet("background-color: #9C27B0; color: white;")
        item_layout.addWidget(give_item_btn, 2, 0, 1, 2)

        item_group.setLayout(item_layout)
        scroll_layout.addWidget(item_group)

        # 成就派发
        achievement_group = QGroupBox("🏆 成就派发")
        achievement_layout = QGridLayout()

        achievement_layout.addWidget(QLabel("成就:"), 0, 0)
        self.achievement_combo = QComboBox()
        self.achievement_combo.setMinimumWidth(200)
        self._init_achievement_combo()
        achievement_layout.addWidget(self.achievement_combo, 0, 1)

        achievement_layout.addWidget(QLabel("自定义:"), 1, 0)
        self.achievement_name_input = QLineEdit()
        self.achievement_name_input.setPlaceholderText("留空则使用上方选择")
        achievement_layout.addWidget(self.achievement_name_input, 1, 1)

        give_achievement_btn = QPushButton("派发成就")
        give_achievement_btn.clicked.connect(self._give_achievement)
        give_achievement_btn.setStyleSheet("background-color: #FF9800; color: white;")
        achievement_layout.addWidget(give_achievement_btn, 2, 0, 1, 2)

        achievement_group.setLayout(achievement_layout)
        scroll_layout.addWidget(achievement_group)

        scroll.setWidget(scroll_content)
        middle_layout.addWidget(scroll)

        # 右侧：游戏控制（从游戏控制tab移过来）
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 使用滚动区域
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll_content = QWidget()
        right_scroll_layout = QVBoxLayout(right_scroll_content)

        # 轮次控制
        round_group = QGroupBox("🎲 轮次控制")
        round_layout = QGridLayout()

        self.force_start_round_btn = QPushButton("强制开始轮次")
        self.force_start_round_btn.clicked.connect(self._force_start_round)
        round_layout.addWidget(self.force_start_round_btn, 0, 0)

        self.force_end_round_btn = QPushButton("强制结束轮次")
        self.force_end_round_btn.clicked.connect(self._force_end_round)
        round_layout.addWidget(self.force_end_round_btn, 0, 1)

        self.clear_temp_markers_btn = QPushButton("清除临时标记")
        self.clear_temp_markers_btn.clicked.connect(self._clear_temp_markers)
        self.clear_temp_markers_btn.setStyleSheet("background-color: #f44336; color: white;")
        round_layout.addWidget(self.clear_temp_markers_btn, 1, 0)

        self.clear_all_markers_btn = QPushButton("清除所有标记")
        self.clear_all_markers_btn.clicked.connect(self._clear_all_markers)
        self.clear_all_markers_btn.setStyleSheet("background-color: #f44336; color: white;")
        round_layout.addWidget(self.clear_all_markers_btn, 1, 1)

        round_group.setLayout(round_layout)
        right_scroll_layout.addWidget(round_group)

        # 位置控制
        position_group = QGroupBox("📍 位置控制")
        position_layout = QGridLayout()

        position_layout.addWidget(QLabel("列号:"), 0, 0)
        self.position_column_input = QSpinBox()
        self.position_column_input.setRange(3, 18)
        self.position_column_input.setValue(7)
        position_layout.addWidget(self.position_column_input, 0, 1)

        position_layout.addWidget(QLabel("位置:"), 1, 0)
        self.position_pos_input = QSpinBox()
        self.position_pos_input.setRange(1, 13)
        self.position_pos_input.setValue(1)
        position_layout.addWidget(self.position_pos_input, 1, 1)

        position_layout.addWidget(QLabel("类型:"), 2, 0)
        self.position_type_combo = QComboBox()
        self.position_type_combo.addItems(["临时标记", "永久标记"])
        position_layout.addWidget(self.position_type_combo, 2, 1)

        add_marker_btn = QPushButton("添加标记")
        add_marker_btn.clicked.connect(self._add_marker)
        add_marker_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        position_layout.addWidget(add_marker_btn, 3, 0)

        remove_marker_btn = QPushButton("移除标记")
        remove_marker_btn.clicked.connect(self._remove_marker)
        remove_marker_btn.setStyleSheet("background-color: #f44336; color: white;")
        position_layout.addWidget(remove_marker_btn, 3, 1)

        position_group.setLayout(position_layout)
        right_scroll_layout.addWidget(position_group)

        # 协会特制徽章（直接登顶）
        badge_group = QGroupBox("🏅 协会特制徽章")
        badge_layout = QGridLayout()

        badge_layout.addWidget(QLabel("登顶列号:"), 0, 0)
        self.badge_column_input = QSpinBox()
        self.badge_column_input.setRange(3, 18)
        self.badge_column_input.setValue(7)
        badge_layout.addWidget(self.badge_column_input, 0, 1)

        direct_top_btn = QPushButton("🎖️ 直接登顶")
        direct_top_btn.clicked.connect(self._direct_top_column)
        direct_top_btn.setStyleSheet("background-color: #FFD700; color: black; font-weight: bold;")
        badge_layout.addWidget(direct_top_btn, 1, 0, 1, 2)

        badge_info = QLabel("⚠️ 该操作会触发首达检查和12小时禁止")
        badge_info.setStyleSheet("color: #FF5722; font-size: 10px;")
        badge_layout.addWidget(badge_info, 2, 0, 1, 2)

        badge_group.setLayout(badge_layout)
        right_scroll_layout.addWidget(badge_group)

        # 状态控制
        state_group = QGroupBox("⚡ 状态控制")
        state_layout = QGridLayout()

        # 锁定控制
        state_layout.addWidget(QLabel("锁定时长(小时):"), 0, 0)
        self.lockout_hours_input = QSpinBox()
        self.lockout_hours_input.setRange(1, 72)
        self.lockout_hours_input.setValue(12)
        state_layout.addWidget(self.lockout_hours_input, 0, 1)

        lock_btn = QPushButton("🔒 锁定玩家")
        lock_btn.clicked.connect(self._lock_player)
        state_layout.addWidget(lock_btn, 1, 0)

        unlock_btn = QPushButton("🔓 解锁玩家")
        unlock_btn.clicked.connect(self._unlock_player)
        state_layout.addWidget(unlock_btn, 1, 1)

        # 跳过回合
        state_layout.addWidget(QLabel("跳过回合数:"), 2, 0)
        self.skip_rounds_input = QSpinBox()
        self.skip_rounds_input.setRange(0, 10)
        self.skip_rounds_input.setValue(1)
        state_layout.addWidget(self.skip_rounds_input, 2, 1)

        set_skip_btn = QPushButton("设置跳过回合")
        set_skip_btn.clicked.connect(self._set_skip_rounds)
        state_layout.addWidget(set_skip_btn, 3, 0, 1, 2)

        state_group.setLayout(state_layout)
        right_scroll_layout.addWidget(state_group)

        # 契约管理
        contract_group = QGroupBox("💕 契约管理")
        contract_layout = QGridLayout()

        # 当前契约显示
        contract_layout.addWidget(QLabel("当前契约:"), 0, 0)
        self.contract_display = QLabel("无")
        self.contract_display.setStyleSheet("font-weight: bold; color: #E91E63;")
        contract_layout.addWidget(self.contract_display, 0, 1)

        # 设置契约对象
        contract_layout.addWidget(QLabel("契约对象:"), 1, 0)
        self.contract_target_combo = QComboBox()
        self.contract_target_combo.setMinimumWidth(120)
        contract_layout.addWidget(self.contract_target_combo, 1, 1)

        set_contract_btn = QPushButton("💍 建立契约")
        set_contract_btn.clicked.connect(self._set_contract)
        set_contract_btn.setStyleSheet("background-color: #E91E63; color: white;")
        contract_layout.addWidget(set_contract_btn, 2, 0)

        remove_contract_btn = QPushButton("💔 解除契约")
        remove_contract_btn.clicked.connect(self._remove_contract)
        remove_contract_btn.setStyleSheet("background-color: #607D8B; color: white;")
        contract_layout.addWidget(remove_contract_btn, 2, 1)

        contract_group.setLayout(contract_layout)
        right_scroll_layout.addWidget(contract_group)

        # 当前状态显示
        status_group = QGroupBox("📊 当前状态")
        status_layout = QVBoxLayout()

        self.control_status_display = QTextEdit()
        self.control_status_display.setReadOnly(True)
        self.control_status_display.setMaximumHeight(150)
        status_layout.addWidget(self.control_status_display)

        status_group.setLayout(status_layout)
        right_scroll_layout.addWidget(status_group)

        right_scroll.setWidget(right_scroll_content)
        right_layout.addWidget(right_scroll)

        # 使用分割器（三栏布局）
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(middle_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 2)

        layout.addWidget(splitter)

        return widget

    def _create_control_tab(self) -> QWidget:
        """创建全局控制选项卡"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 左侧：宝石池沼管理
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # 宝石池沼管理
        gem_group = QGroupBox("💎 宝石池沼管理")
        gem_layout = QGridLayout()

        gem_layout.addWidget(QLabel("列:"), 0, 0)
        self.gem_column_input = QSpinBox()
        self.gem_column_input.setRange(3, 18)
        self.gem_column_input.setValue(7)
        gem_layout.addWidget(self.gem_column_input, 0, 1)

        gem_layout.addWidget(QLabel("位置:"), 1, 0)
        self.gem_pos_input = QSpinBox()
        self.gem_pos_input.setRange(1, 13)
        self.gem_pos_input.setValue(1)
        gem_layout.addWidget(self.gem_pos_input, 1, 1)

        gem_layout.addWidget(QLabel("类型:"), 2, 0)
        self.gem_type_combo = QComboBox()
        self.gem_type_combo.addItems(["红宝石", "蓝宝石", "红池沼", "蓝池沼"])
        gem_layout.addWidget(self.gem_type_combo, 2, 1)

        add_gem_btn = QPushButton("添加宝石/池沼")
        add_gem_btn.clicked.connect(self._add_gem)
        add_gem_btn.setStyleSheet("background-color: #E91E63; color: white;")
        gem_layout.addWidget(add_gem_btn, 3, 0, 1, 2)

        clear_gems_btn = QPushButton("清除所有宝石/池沼")
        clear_gems_btn.clicked.connect(self._clear_all_gems)
        clear_gems_btn.setStyleSheet("background-color: #607D8B; color: white;")
        gem_layout.addWidget(clear_gems_btn, 4, 0, 1, 2)

        gem_group.setLayout(gem_layout)
        left_layout.addWidget(gem_group)

        # 当前宝石池沼列表
        gem_list_group = QGroupBox("📋 当前宝石/池沼")
        gem_list_layout = QVBoxLayout()

        self.gem_list_display = QTextEdit()
        self.gem_list_display.setReadOnly(True)
        gem_list_layout.addWidget(self.gem_list_display)

        refresh_gem_btn = QPushButton("刷新列表")
        refresh_gem_btn.clicked.connect(self._refresh_gem_list)
        gem_list_layout.addWidget(refresh_gem_btn)

        gem_list_group.setLayout(gem_list_layout)
        left_layout.addWidget(gem_list_group)

        left_layout.addStretch()

        # 右侧：批量操作
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 批量操作
        batch_group = QGroupBox("📦 批量操作")
        batch_layout = QVBoxLayout()

        batch_score_layout = QHBoxLayout()
        batch_score_layout.addWidget(QLabel("全员积分:"))
        self.batch_score_input = QSpinBox()
        self.batch_score_input.setRange(-1000, 1000)
        self.batch_score_input.setValue(100)
        batch_score_layout.addWidget(self.batch_score_input)

        batch_score_btn = QPushButton("发放")
        batch_score_btn.clicked.connect(self._batch_add_score)
        batch_score_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        batch_score_layout.addWidget(batch_score_btn)
        batch_layout.addLayout(batch_score_layout)

        unlock_all_btn = QPushButton("解锁所有道具")
        unlock_all_btn.clicked.connect(self._unlock_all_items)
        batch_layout.addWidget(unlock_all_btn)

        clear_all_lockouts_btn = QPushButton("解除所有玩家锁定")
        clear_all_lockouts_btn.clicked.connect(self._clear_all_lockouts)
        batch_layout.addWidget(clear_all_lockouts_btn)

        batch_group.setLayout(batch_layout)
        right_layout.addWidget(batch_group)

        # 首达记录
        first_group = QGroupBox("🏆 首达记录")
        first_layout = QVBoxLayout()

        self.first_achievement_display = QTextEdit()
        self.first_achievement_display.setReadOnly(True)
        first_layout.addWidget(self.first_achievement_display)

        refresh_first_btn = QPushButton("刷新首达记录")
        refresh_first_btn.clicked.connect(self._refresh_first_achievements)
        first_layout.addWidget(refresh_first_btn)

        first_group.setLayout(first_layout)
        right_layout.addWidget(first_group)

        right_layout.addStretch()

        # 使用分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

        return widget

    def _create_shop_tab(self) -> QWidget:
        """创建商店管理选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 工具栏
        toolbar = QHBoxLayout()

        unlock_all_btn = QPushButton("解锁所有道具")
        unlock_all_btn.clicked.connect(self._unlock_all_items)
        toolbar.addWidget(unlock_all_btn)

        reset_sold_btn = QPushButton("重置销售数量")
        reset_sold_btn.clicked.connect(self._reset_shop_sold)
        toolbar.addWidget(reset_sold_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 商店表格
        self.shop_table = QTableWidget()
        self.shop_table.setColumnCount(8)
        self.shop_table.setHorizontalHeaderLabels(
            ["ID", "名称", "类型", "价格", "阵营", "全局限制", "已售", "已解锁"]
        )
        self.shop_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout.addWidget(self.shop_table)

        return widget

    def _create_command_tab(self) -> QWidget:
        """创建口令管理选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 工具栏
        toolbar = QHBoxLayout()

        add_cmd_btn = QPushButton("➕ 添加口令")
        add_cmd_btn.clicked.connect(self._add_command_dialog)
        add_cmd_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        toolbar.addWidget(add_cmd_btn)

        refresh_cmd_btn = QPushButton("🔄 刷新列表")
        refresh_cmd_btn.clicked.connect(self._refresh_commands)
        toolbar.addWidget(refresh_cmd_btn)

        toolbar.addStretch()

        import_btn = QPushButton("📥 导入配置")
        import_btn.clicked.connect(self._import_commands)
        toolbar.addWidget(import_btn)

        export_btn = QPushButton("📤 导出配置")
        export_btn.clicked.connect(self._export_commands)
        toolbar.addWidget(export_btn)

        # 显示配置文件路径提示
        config_path_label = QLabel("配置文件: data/custom_commands.json")
        config_path_label.setStyleSheet("color: gray; font-size: 11px;")
        toolbar.addWidget(config_path_label)

        layout.addLayout(toolbar)

        # 口令表格
        self.command_table = QTableWidget()
        self.command_table.setColumnCount(7)
        self.command_table.setHorizontalHeaderLabels(
            ["ID", "关键词", "回复消息", "积分奖励", "每人限制", "启用", "操作"]
        )
        self.command_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.command_table.setColumnWidth(0, 50)
        self.command_table.setColumnWidth(3, 80)
        self.command_table.setColumnWidth(4, 80)
        self.command_table.setColumnWidth(5, 60)
        self.command_table.setColumnWidth(6, 150)

        layout.addWidget(self.command_table)

        # 初始加载
        self._refresh_commands()

        return widget

    def _refresh_commands(self):
        """刷新口令列表"""
        commands = self.custom_cmd_dao.get_all_commands()
        self.command_table.setRowCount(len(commands))

        for row, cmd in enumerate(commands):
            # ID
            self.command_table.setItem(row, 0, QTableWidgetItem(str(cmd.command_id)))

            # 关键词
            self.command_table.setItem(row, 1, QTableWidgetItem(cmd.keyword))

            # 回复消息（截断显示）
            response_display = cmd.response[:30] + "..." if len(cmd.response) > 30 else cmd.response
            self.command_table.setItem(row, 2, QTableWidgetItem(response_display))

            # 积分奖励
            self.command_table.setItem(row, 3, QTableWidgetItem(str(cmd.score_reward)))

            # 每人限制
            limit_text = "无限" if cmd.per_player_limit == 0 else str(cmd.per_player_limit)
            self.command_table.setItem(row, 4, QTableWidgetItem(limit_text))

            # 启用状态
            status_text = "✓" if cmd.enabled else "✗"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.command_table.setItem(row, 5, status_item)

            # 操作按钮
            ops_widget = QWidget()
            ops_layout = QHBoxLayout(ops_widget)
            ops_layout.setContentsMargins(2, 2, 2, 2)

            edit_btn = QPushButton("编辑")
            edit_btn.setFixedWidth(45)
            edit_btn.clicked.connect(lambda checked, cid=cmd.command_id: self._edit_command_dialog(cid))
            ops_layout.addWidget(edit_btn)

            toggle_btn = QPushButton("禁用" if cmd.enabled else "启用")
            toggle_btn.setFixedWidth(45)
            toggle_btn.clicked.connect(lambda checked, cid=cmd.command_id: self._toggle_command(cid))
            ops_layout.addWidget(toggle_btn)

            del_btn = QPushButton("删除")
            del_btn.setFixedWidth(45)
            del_btn.setStyleSheet("background-color: #f44336; color: white;")
            del_btn.clicked.connect(lambda checked, cid=cmd.command_id: self._delete_command(cid))
            ops_layout.addWidget(del_btn)

            self.command_table.setCellWidget(row, 6, ops_widget)

    def _add_command_dialog(self):
        """添加口令对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加口令")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # 关键词
        keyword_layout = QHBoxLayout()
        keyword_layout.addWidget(QLabel("关键词:"))
        keyword_input = QLineEdit()
        keyword_input.setPlaceholderText("如：领取圣诞礼物")
        keyword_layout.addWidget(keyword_input)
        layout.addLayout(keyword_layout)

        # 回复消息
        response_layout = QVBoxLayout()
        response_layout.addWidget(QLabel("回复消息:"))
        response_input = QTextEdit()
        response_input.setPlaceholderText("如：恭喜领取成功！")
        response_input.setMaximumHeight(100)
        response_layout.addWidget(response_input)
        layout.addLayout(response_layout)

        # 积分奖励
        score_layout = QHBoxLayout()
        score_layout.addWidget(QLabel("积分奖励:"))
        score_input = QSpinBox()
        score_input.setRange(0, 10000)
        score_input.setValue(0)
        score_layout.addWidget(score_input)
        layout.addLayout(score_layout)

        # 每人限制
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("每人限制:"))
        limit_input = QSpinBox()
        limit_input.setRange(0, 999)
        limit_input.setValue(1)
        limit_input.setSpecialValueText("无限")
        limit_layout.addWidget(limit_input)
        limit_layout.addWidget(QLabel("(0=无限)"))
        layout.addLayout(limit_layout)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            keyword = keyword_input.text().strip()
            response = response_input.toPlainText().strip()
            score = score_input.value()
            limit = limit_input.value()

            if not keyword:
                QMessageBox.warning(self, "错误", "关键词不能为空")
                return
            if not response:
                QMessageBox.warning(self, "错误", "回复消息不能为空")
                return

            success, msg = self.custom_cmd_dao.add_command(keyword, response, score, limit)
            if success:
                QMessageBox.information(self, "成功", msg)
                self._refresh_commands()
                self._log(f"添加口令: {keyword}")
            else:
                QMessageBox.warning(self, "错误", msg)

    def _edit_command_dialog(self, command_id: int):
        """编辑口令对话框"""
        cmd = self.custom_cmd_dao.get_command_by_id(command_id)
        if not cmd:
            QMessageBox.warning(self, "错误", "口令不存在")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑口令")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # 关键词
        keyword_layout = QHBoxLayout()
        keyword_layout.addWidget(QLabel("关键词:"))
        keyword_input = QLineEdit()
        keyword_input.setText(cmd.keyword)
        keyword_layout.addWidget(keyword_input)
        layout.addLayout(keyword_layout)

        # 回复消息
        response_layout = QVBoxLayout()
        response_layout.addWidget(QLabel("回复消息:"))
        response_input = QTextEdit()
        response_input.setText(cmd.response)
        response_input.setMaximumHeight(100)
        response_layout.addWidget(response_input)
        layout.addLayout(response_layout)

        # 积分奖励
        score_layout = QHBoxLayout()
        score_layout.addWidget(QLabel("积分奖励:"))
        score_input = QSpinBox()
        score_input.setRange(0, 10000)
        score_input.setValue(cmd.score_reward)
        score_layout.addWidget(score_input)
        layout.addLayout(score_layout)

        # 每人限制
        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("每人限制:"))
        limit_input = QSpinBox()
        limit_input.setRange(0, 999)
        limit_input.setValue(cmd.per_player_limit)
        limit_input.setSpecialValueText("无限")
        limit_layout.addWidget(limit_input)
        limit_layout.addWidget(QLabel("(0=无限)"))
        layout.addLayout(limit_layout)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.Accepted:
            keyword = keyword_input.text().strip()
            response = response_input.toPlainText().strip()
            score = score_input.value()
            limit = limit_input.value()

            if not keyword:
                QMessageBox.warning(self, "错误", "关键词不能为空")
                return
            if not response:
                QMessageBox.warning(self, "错误", "回复消息不能为空")
                return

            success, msg = self.custom_cmd_dao.update_command(command_id, keyword, response, score, limit)
            if success:
                QMessageBox.information(self, "成功", msg)
                self._refresh_commands()
                self._log(f"编辑口令: {keyword}")
            else:
                QMessageBox.warning(self, "错误", msg)

    def _toggle_command(self, command_id: int):
        """切换口令启用状态"""
        success, new_state = self.custom_cmd_dao.toggle_command(command_id)
        if success:
            status = "启用" if new_state else "禁用"
            self._refresh_commands()
            self._log(f"口令ID {command_id} 已{status}")
        else:
            QMessageBox.warning(self, "错误", "操作失败")

    def _delete_command(self, command_id: int):
        """删除口令"""
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这个口令吗？\n删除后使用记录也会被清除。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.custom_cmd_dao.delete_command(command_id):
                self._refresh_commands()
                self._log(f"删除口令ID: {command_id}")
            else:
                QMessageBox.warning(self, "错误", "删除失败")

    def _import_commands(self):
        """从配置文件导入口令"""
        from pathlib import Path
        config_path = Path(__file__).parent.parent / "data" / "custom_commands.json"

        if not config_path.exists():
            QMessageBox.warning(self, "错误", f"配置文件不存在:\n{config_path}")
            return

        reply = QMessageBox.question(
            self, "确认导入",
            f"从以下文件导入口令:\n{config_path}\n\n已存在的口令会被更新，新口令会被添加。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            success, skip, errors = self.custom_cmd_dao.import_from_json(str(config_path))
            self._refresh_commands()

            msg = f"导入完成！\n新增: {success} 条\n更新/跳过: {skip} 条"
            if errors:
                msg += f"\n\n错误:\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    msg += f"\n... 还有 {len(errors) - 5} 条错误"

            QMessageBox.information(self, "导入结果", msg)
            self._log(f"导入口令: 新增 {success}, 跳过 {skip}")

    def _export_commands(self):
        """导出口令到配置文件"""
        from pathlib import Path
        config_path = Path(__file__).parent.parent / "data" / "custom_commands.json"

        success, msg = self.custom_cmd_dao.export_to_json(str(config_path))
        if success:
            QMessageBox.information(self, "导出成功", f"{msg}\n\n文件位置:\n{config_path}")
            self._log(f"导出口令配置到 {config_path}")
        else:
            QMessageBox.warning(self, "导出失败", msg)

    def _create_system_tab(self) -> QWidget:
        """创建系统管理选项卡"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # 左侧：统计信息
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        stats_group = QGroupBox("📈 游戏统计")
        stats_layout = QGridLayout()

        self.stats_labels = {}
        stats_items = [
            ("总玩家数", "0"),
            ("进行中玩家", "0"),
            ("已登顶玩家", "0"),
            ("总积分发放", "0"),
            ("道具总数", "0"),
            ("成就总数", "0"),
        ]

        for i, (item, default) in enumerate(stats_items):
            row = i // 2
            col = (i % 2) * 2
            stats_layout.addWidget(QLabel(f"{item}:"), row, col)
            label = QLabel(default)
            label.setStyleSheet("font-weight: bold; color: #2196F3;")
            self.stats_labels[item] = label
            stats_layout.addWidget(label, row, col + 1)

        stats_group.setLayout(stats_layout)
        left_layout.addWidget(stats_group)

        # 排行榜
        rank_group = QGroupBox("🏆 排行榜 (积分TOP10)")
        rank_layout = QVBoxLayout()

        self.rank_list = QListWidget()
        rank_layout.addWidget(self.rank_list)

        rank_group.setLayout(rank_layout)
        left_layout.addWidget(rank_group)

        # 右侧：系统操作
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        ops_group = QGroupBox("⚠️ 危险操作")
        ops_layout = QVBoxLayout()

        clear_board_btn = QPushButton("🧹 清除棋盘 (保留玩家和积分)")
        clear_board_btn.clicked.connect(self._clear_board)
        clear_board_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        ops_layout.addWidget(clear_board_btn)

        reset_btn = QPushButton("🗑️ 重置游戏 (清除所有数据)")
        reset_btn.clicked.connect(self._reset_game)
        reset_btn.setStyleSheet("background-color: #ff4444; color: white; font-weight: bold;")
        ops_layout.addWidget(reset_btn)

        backup_btn = QPushButton("💾 备份数据库")
        backup_btn.clicked.connect(self._backup_database)
        ops_layout.addWidget(backup_btn)

        ops_group.setLayout(ops_layout)
        right_layout.addWidget(ops_group)

        # 日志
        log_group = QGroupBox("📝 操作日志")
        log_layout = QVBoxLayout()

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumHeight(200)
        log_layout.addWidget(self.log_display)

        log_group.setLayout(log_layout)
        right_layout.addWidget(log_group)

        right_layout.addStretch()

        # 使用分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)

        layout.addWidget(splitter)

        return widget

    # ==================== 事件处理 ====================

    def _on_player_selected(self):
        """玩家选中事件"""
        selected_items = self.players_table.selectedItems()
        if not selected_items:
            self.selected_qq_id = None
            return

        row = selected_items[0].row()
        qq_id = self.players_table.item(row, 0).text()
        self.selected_qq_id = qq_id

        self._show_player_detail(qq_id)
        self._show_player_progress(qq_id)
        self._update_control_status(qq_id)
        self._update_contract_display(qq_id)
        self._refresh_contract_combo(qq_id)

    def _filter_players(self):
        """筛选玩家"""
        search_text = self.player_search.text().lower()
        for i in range(self.players_table.rowCount()):
            qq_id = self.players_table.item(i, 0).text().lower()
            nickname = self.players_table.item(i, 1).text().lower()
            if search_text in qq_id or search_text in nickname:
                self.players_table.showRow(i)
            else:
                self.players_table.hideRow(i)

    def _register_player(self):
        """手动注册玩家"""
        qq_id = self.register_qq_input.text().strip()
        nickname = self.register_nickname_input.text().strip()
        faction = self.register_faction_combo.currentText()
        initial_score = self.register_score_input.value()

        if not qq_id:
            QMessageBox.warning(self, "错误", "请输入QQ号")
            return

        if not nickname:
            QMessageBox.warning(self, "错误", "请输入昵称")
            return

        # 检查QQ号是否为纯数字
        if not qq_id.isdigit():
            QMessageBox.warning(self, "错误", "QQ号必须为纯数字")
            return

        # 检查玩家是否已存在
        existing = self.player_dao.get_player(qq_id)
        if existing:
            QMessageBox.warning(self, "错误", f"玩家 {qq_id} ({existing.nickname}) 已存在")
            return

        # 注册玩家
        player = self.player_dao.create_player(qq_id, nickname)
        if player:
            # 设置阵营
            if faction and faction != "未选择":
                self.player_dao.update_faction(qq_id, faction)
            # 设置初始积分
            if initial_score > 0:
                self.player_dao.add_score(qq_id, initial_score)
            faction_text = faction if faction != "未选择" else "未选择"
            QMessageBox.information(self, "成功", f"已注册玩家: {nickname} ({qq_id})\n阵营: {faction_text}\n初始积分: {initial_score}")
            self.register_qq_input.clear()
            self.register_nickname_input.clear()
            self.register_faction_combo.setCurrentIndex(0)
            self.register_score_input.setValue(0)
            self._refresh_players()
        else:
            QMessageBox.warning(self, "错误", "注册失败")

    def _delete_player(self):
        """删除选中的玩家"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "错误", "请先选择要删除的玩家")
            return

        player = self.player_dao.get_player(self.selected_qq_id)
        if not player:
            QMessageBox.warning(self, "错误", "玩家不存在")
            return

        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除玩家 {player.nickname} ({player.qq_id}) 吗？\n\n此操作将删除该玩家的所有数据，包括:\n- 积分和成就\n- 背包物品\n- 位置标记\n- 契约关系\n\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.player_dao.delete_player(self.selected_qq_id):
                QMessageBox.information(self, "成功", f"已删除玩家: {player.nickname} ({player.qq_id})")
                self.selected_qq_id = None
                self._refresh_players()
                self.player_detail.clear()
                self.progress_display.clear()
                self.control_status_display.clear()
            else:
                QMessageBox.warning(self, "错误", "删除失败")

    def _import_players_csv(self):
        """从CSV导入玩家
        CSV格式: QQ号,昵称[,阵营][,初始积分]
        第三列阵营可选(收养人/Aeonreth)，第四列积分可选
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择CSV文件",
            "",
            "CSV文件 (*.csv);;所有文件 (*)"
        )

        if not file_path:
            return

        import csv
        success_count = 0
        skip_count = 0
        error_count = 0
        errors = []

        def process_row(row, row_num):
            """处理单行数据"""
            nonlocal success_count, skip_count, error_count

            if len(row) < 2:
                error_count += 1
                errors.append(f"第{row_num}行: 列数不足")
                return

            qq_id = str(row[0]).strip()
            nickname = str(row[1]).strip()
            faction = None
            initial_score = 0

            # 解析可选的第三列阵营
            if len(row) >= 3 and row[2].strip():
                faction_val = row[2].strip()
                if faction_val in ["收养人", "Aeonreth"]:
                    faction = faction_val

            # 解析可选的第四列积分
            if len(row) >= 4 and row[3].strip():
                try:
                    initial_score = int(row[3].strip())
                except ValueError:
                    error_count += 1
                    errors.append(f"第{row_num}行: 积分格式错误 ({row[3]})")
                    return

            if not qq_id or not nickname:
                error_count += 1
                errors.append(f"第{row_num}行: QQ号或昵称为空")
                return

            if not qq_id.isdigit():
                error_count += 1
                errors.append(f"第{row_num}行: QQ号不是数字 ({qq_id})")
                return

            existing = self.player_dao.get_player(qq_id)
            if existing:
                skip_count += 1
                return

            try:
                self.player_dao.create_player(qq_id, nickname)
                if faction:
                    self.player_dao.update_faction(qq_id, faction)
                if initial_score > 0:
                    self.player_dao.add_score(qq_id, initial_score)
                success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"第{row_num}行: {str(e)}")

        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                # 尝试跳过表头
                first_row = next(reader, None)
                if first_row and first_row[0].lower() in ['qq', 'qq号', 'qqid', 'qq_id']:
                    pass  # 跳过表头
                else:
                    # 不是表头，处理第一行
                    if first_row:
                        process_row(first_row, 1)

                # 处理剩余行
                for row_num, row in enumerate(reader, start=2):
                    process_row(row, row_num)

            # 显示结果
            msg = f"导入完成!\n\n成功: {success_count} 个\n跳过(已存在): {skip_count} 个\n失败: {error_count} 个"
            if errors:
                msg += f"\n\n错误详情:\n" + "\n".join(errors[:10])
                if len(errors) > 10:
                    msg += f"\n... 还有 {len(errors) - 10} 个错误"

            QMessageBox.information(self, "导入结果", msg)
            self._refresh_players()

        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"读取CSV文件失败: {str(e)}")

    # ==================== 显示函数 ====================

    def _show_player_detail(self, qq_id: str):
        """显示玩家详细信息"""
        player = self.player_dao.get_player(qq_id)
        if not player:
            return

        achievements = self.achievement_dao.get_achievements(qq_id)
        inventory = self.inventory_dao.get_inventory(qq_id)
        state = self.state_dao.get_state(qq_id)

        # 获取契约信息
        partner_qq = self.contract_dao.get_contract_partner(qq_id)
        partner_info = ""
        if partner_qq:
            partner = self.player_dao.get_player(partner_qq)
            partner_info = f"\n契约对象: {partner.nickname if partner else partner_qq}"

        detail_text = f"""=== 基本信息 ===
QQ号: {player.qq_id}
昵称: {player.nickname}
阵营: {player.faction or '未选择'}
当前积分: {player.current_score}
历史总积分: {player.total_score}{partner_info}

=== 背包物品 ({len(inventory)}) ===
"""
        if inventory:
            for item in inventory:
                detail_text += f"• {item.item_name} x{item.quantity}\n"
        else:
            detail_text += "背包为空\n"

        detail_text += f"\n=== 成就 ({len(achievements)}) ===\n"
        for ach in achievements:
            detail_text += f"• {ach.achievement_name} ({ach.achievement_type})\n"

        # 状态信息
        if state:
            detail_text += f"\n=== 游戏状态 ===\n"
            detail_text += f"轮次进行中: {'是' if state.current_round_active else '否'}\n"
            detail_text += f"跳过回合数: {state.skipped_rounds}\n"
            if state.lockout_until:
                try:
                    lockout_time = datetime.fromisoformat(state.lockout_until)
                    if datetime.now() < lockout_time:
                        remaining = lockout_time - datetime.now()
                        detail_text += f"锁定剩余: {int(remaining.total_seconds()//3600)}小时\n"
                except:
                    pass

        self.player_detail.setText(detail_text)

    def _show_player_progress(self, qq_id: str):
        """显示玩家进度"""
        positions = self.position_dao.get_positions(qq_id)
        state = self.state_dao.get_state(qq_id)

        temp_positions = [p for p in positions if p.marker_type == 'temp']
        perm_positions = [p for p in positions if p.marker_type == 'permanent']

        progress_text = "=== 当前进度 ===\n\n"

        # 临时标记
        progress_text += f"🟠 临时标记 ({len(temp_positions)}):\n"
        if temp_positions:
            for pos in sorted(temp_positions, key=lambda x: x.column_number):
                height = COLUMN_HEIGHTS.get(pos.column_number, 0)
                percent = int((pos.position / height) * 100) if height > 0 else 0
                progress_text += f"  列{pos.column_number}: 第{pos.position}格/{height} ({percent}%)\n"
        else:
            progress_text += "  无\n"

        # 永久标记
        progress_text += f"\n🔵 永久标记 ({len(perm_positions)}):\n"
        if perm_positions:
            for pos in sorted(perm_positions, key=lambda x: x.column_number):
                height = COLUMN_HEIGHTS.get(pos.column_number, 0)
                is_topped = pos.position >= height
                status = "✅ 已登顶" if is_topped else f"第{pos.position}格/{height}"
                progress_text += f"  列{pos.column_number}: {status}\n"
        else:
            progress_text += "  无\n"

        # 登顶统计
        topped_count = len([p for p in perm_positions if p.position >= COLUMN_HEIGHTS.get(p.column_number, 0)])
        progress_text += f"\n🏆 登顶列数: {topped_count}/3\n"

        if topped_count >= 3:
            progress_text += "🎉 已达成胜利条件！\n"

        self.progress_display.setText(progress_text)

    def _update_control_status(self, qq_id: str):
        """更新控制面板状态显示"""
        player = self.player_dao.get_player(qq_id)
        state = self.state_dao.get_state(qq_id)
        positions = self.position_dao.get_positions(qq_id)

        if not player:
            self.control_status_display.setText("玩家不存在")
            return

        status_text = f"""玩家: {player.nickname} ({qq_id})
阵营: {player.faction or '未选择'}
积分: {player.current_score}

=== 轮次状态 ===
轮次进行中: {'是' if state.current_round_active else '否'}
可开始新轮次: {'是' if state.can_start_new_round else '否'}
已用临时标记: {state.temp_markers_used}
跳过回合数: {state.skipped_rounds}

=== 锁定状态 ==="""

        if state.lockout_until:
            try:
                lockout_time = datetime.fromisoformat(state.lockout_until)
                if datetime.now() < lockout_time:
                    remaining = lockout_time - datetime.now()
                    hours = int(remaining.total_seconds() // 3600)
                    mins = int((remaining.total_seconds() % 3600) // 60)
                    status_text += f"\n🔒 锁定中，剩余 {hours}小时{mins}分钟"
                else:
                    status_text += "\n🔓 未锁定"
            except:
                status_text += "\n🔓 未锁定"
        else:
            status_text += "\n🔓 未锁定"

        status_text += f"\n\n=== 位置信息 ===\n"
        temp_pos = [p for p in positions if p.marker_type == 'temp']
        perm_pos = [p for p in positions if p.marker_type == 'permanent']
        status_text += f"临时标记: {len(temp_pos)}个\n"
        status_text += f"永久标记: {len(perm_pos)}个\n"

        self.control_status_display.setText(status_text)

    def _update_lockout_display(self, state):
        """更新锁定状态显示"""
        pass  # 已在其他方法中实现

    # ==================== 积分操作 ====================

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
        """设置积分"""
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
        """重置积分"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return
        reply = QMessageBox.question(self, "确认", "确定要重置积分吗？")
        if reply == QMessageBox.Yes:
            self._modify_score(0, is_add=False)

    def _quick_add_score(self, amount: int):
        """快捷增加积分"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return
        self._modify_score(amount, is_add=True)

    def _modify_score(self, amount: int, is_add: bool = True):
        """修改积分核心方法"""
        player = self.player_dao.get_player(self.selected_qq_id)
        if not player:
            return

        score_type = self.score_type_combo.currentText()
        cursor = self.db_conn.cursor()

        try:
            if score_type == "当前积分":
                new_score = player.current_score + amount if is_add else amount
                cursor.execute("UPDATE players SET current_score = ? WHERE qq_id = ?",
                             (max(0, new_score), self.selected_qq_id))
            elif score_type == "总积分":
                new_score = player.total_score + amount if is_add else amount
                cursor.execute("UPDATE players SET total_score = ? WHERE qq_id = ?",
                             (max(0, new_score), self.selected_qq_id))
            else:
                new_current = player.current_score + amount if is_add else amount
                new_total = player.total_score + amount if is_add else amount
                cursor.execute("UPDATE players SET current_score = ?, total_score = ? WHERE qq_id = ?",
                             (max(0, new_current), max(0, new_total), self.selected_qq_id))

            self.db_conn.commit()
            self._log(f"修改 {player.nickname} 积分: {'+' if is_add else '='}{amount}")

            self.refresh_players()
            self._show_player_detail(self.selected_qq_id)
            self.score_input.clear()

        except Exception as e:
            self.db_conn.rollback()
            QMessageBox.critical(self, "错误", f"修改失败: {str(e)}")

    # ==================== 道具操作 ====================

    def _give_item(self):
        """派发道具"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        item_data = self.item_combo.currentData()
        if not item_data:
            QMessageBox.warning(self, "警告", "请选择一个道具")
            return

        item_id, item_name, item_type = item_data
        quantity = self.item_quantity_input.value()

        try:
            for _ in range(quantity):
                self.inventory_dao.add_item(self.selected_qq_id, item_id, item_name, item_type)

            player = self.player_dao.get_player(self.selected_qq_id)
            self._log(f"向 {player.nickname} 派发 {quantity}个 [{item_name}]")
            QMessageBox.information(self, "成功", f"已派发 {quantity}个 [{item_name}]")
            self._show_player_detail(self.selected_qq_id)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"派发失败: {str(e)}")

    def _init_item_combo(self):
        """初始化道具下拉框"""
        self.item_combo.clear()
        items = self.shop_dao.get_all_items()
        for item in items:
            display_name = f"{item.item_name} ({item.faction_limit or '通用'})"
            self.item_combo.addItem(display_name, (item.item_id, item.item_name, item.item_type))

    # ==================== 成就操作 ====================

    def _init_achievement_combo(self):
        """初始化成就下拉框"""
        achievements = [
            ("--- 首达成就 ---", "", ""),
            ("OAS游戏王", "OAS游戏王", "first_clear"),
            ("银闪闪", "银闪闪", "first_clear"),
            ("吉祥三宝", "吉祥三宝", "first_clear"),
            ("一步之遥", "一步之遥", "first_clear"),
            ("鹤立oas群", "鹤立oas群", "first_clear"),
            ("--- 隐藏成就 ---", "", ""),
            ("领地意识", "领地意识", "hidden"),
            ("出门没看黄历", "出门没看黄历", "hidden"),
            ("看我一命通关！", "看我一命通关！", "hidden"),
            ("收集癖", "收集癖", "hidden"),
            ("一鸣惊人", "一鸣惊人", "hidden"),
            ("六六大顺", "六六大顺", "hidden"),
            ("自巡航", "自巡航", "hidden"),
            ("雪中送炭", "雪中送炭", "hidden"),
            ("平平淡淡才是真", "平平淡淡才是真", "hidden"),
            ("善恶有报", "善恶有报", "hidden"),
            ("天机算不尽", "天机算不尽", "hidden"),
            ("主持人的猜忌", "主持人的猜忌", "hidden"),
            ("--- 检定成就 ---", "", ""),
            ("数学大王", "数学大王", "hidden"),
            ("数学0蛋", "数学0蛋", "hidden"),
            ("哭哭做题家", "哭哭做题家", "hidden"),
            ("进去吧你！", "进去吧你！", "hidden"),
            ("--- 对决成就 ---", "", ""),
            ("狙神", "狙神", "hidden"),
            ("尸体", "尸体", "hidden"),
            ("虚晃一枪", "虚晃一枪", "hidden"),
            ("--- 遭遇成就 ---", "", ""),
            ("荒野大镖客", "荒野大镖客", "hidden"),
            ("荒野大窝囊", "荒野大窝囊", "hidden"),
            ("飙马野郎", "飙马野郎", "normal"),
            ("--- 契约成就 ---", "", ""),
            ("产品金婚", "产品金婚", "hidden"),
            ("--- 陷阱成就 ---", "", ""),
            ("悲伤的小画家", "悲伤的小画家", "hidden"),
            ("switch", "switch", "hidden"),
            ("时管大师", "时管大师", "hidden"),
            ("讨厌您来", "讨厌您来", "hidden"),
            ("万物皆可钓", "万物皆可钓", "hidden"),
            ("厄运儿", "厄运儿", "hidden"),
            ("--- 其他成就 ---", "", ""),
            ("你，审核不通过。", "你，审核不通过。", "hidden"),
        ]

        for display_name, ach_name, ach_type in achievements:
            if ach_name:
                self.achievement_combo.addItem(display_name, (ach_name, ach_type))
            else:
                self.achievement_combo.addItem(display_name, None)

    def _give_achievement(self):
        """派发成就"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        custom_name = self.achievement_name_input.text().strip()
        if custom_name:
            achievement_name = custom_name
            achievement_type = "hidden"
        else:
            combo_data = self.achievement_combo.currentData()
            if not combo_data:
                QMessageBox.warning(self, "警告", "请选择一个有效的成就")
                return
            achievement_name, achievement_type = combo_data

        try:
            success = self.achievement_dao.add_achievement(
                self.selected_qq_id, 0, achievement_name, achievement_type
            )

            if not success:
                QMessageBox.warning(self, "警告", f"该玩家已拥有成就【{achievement_name}】")
                return

            player = self.player_dao.get_player(self.selected_qq_id)
            self._log(f"向 {player.nickname} 派发成就【{achievement_name}】")
            QMessageBox.information(self, "成功", f"已派发成就【{achievement_name}】")

            self.achievement_name_input.clear()
            self._show_player_detail(self.selected_qq_id)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"派发失败: {str(e)}")

    # ==================== 游戏控制操作 ====================

    def _force_start_round(self):
        """强制开始轮次"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        state = self.state_dao.get_state(qq_id)
        state.current_round_active = True
        state.can_start_new_round = False
        self.state_dao.update_state(state)

        player = self.player_dao.get_player(qq_id)
        self._log(f"强制开始 {player.nickname} 的轮次")
        self._update_control_status(qq_id)
        self.refresh_map()

    def _force_end_round(self):
        """强制结束轮次"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        state = self.state_dao.get_state(qq_id)
        state.current_round_active = False
        state.can_start_new_round = True
        state.temp_markers_used = 0
        self.state_dao.update_state(state)

        player = self.player_dao.get_player(qq_id)
        self._log(f"强制结束 {player.nickname} 的轮次")
        self._update_control_status(qq_id)

    def _clear_temp_markers(self):
        """清除临时标记"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        self.position_dao.clear_temp_positions(qq_id)

        player = self.player_dao.get_player(qq_id)
        self._log(f"清除 {player.nickname} 的所有临时标记")
        self._update_control_status(qq_id)
        self.refresh_map()

    def _clear_all_markers(self):
        """清除所有标记"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        reply = QMessageBox.warning(self, "警告", "确定要清除该玩家的所有标记吗？",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        cursor = self.db_conn.cursor()
        cursor.execute("DELETE FROM player_positions WHERE qq_id = ?", (qq_id,))
        self.db_conn.commit()

        player = self.player_dao.get_player(qq_id)
        self._log(f"清除 {player.nickname} 的所有标记")
        self._update_control_status(qq_id)
        self.refresh_map()

    def _add_marker(self):
        """添加标记"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        column = self.position_column_input.value()
        position = self.position_pos_input.value()
        marker_type = 'temp' if self.position_type_combo.currentIndex() == 0 else 'permanent'

        # 验证位置
        max_height = COLUMN_HEIGHTS.get(column, 0)
        if position > max_height:
            QMessageBox.warning(self, "警告", f"列{column}最大位置为{max_height}")
            return

        self.position_dao.add_or_update_position(qq_id, column, position, marker_type)

        player = self.player_dao.get_player(qq_id)
        self._log(f"为 {player.nickname} 添加{marker_type}标记: 列{column}第{position}格")
        self._update_control_status(qq_id)
        self.refresh_map()

    def _remove_marker(self):
        """移除标记"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        column = self.position_column_input.value()
        marker_type = 'temp' if self.position_type_combo.currentIndex() == 0 else 'permanent'

        cursor = self.db_conn.cursor()
        cursor.execute(
            "DELETE FROM player_positions WHERE qq_id = ? AND column_number = ? AND marker_type = ?",
            (qq_id, column, marker_type)
        )
        self.db_conn.commit()

        player = self.player_dao.get_player(qq_id)
        self._log(f"移除 {player.nickname} 在列{column}的{marker_type}标记")
        self._update_control_status(qq_id)
        self.refresh_map()

    def _direct_top_column(self):
        """使用协会特制徽章直接登顶"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        column = self.badge_column_input.value()

        # 验证列号
        if column not in VALID_COLUMNS:
            QMessageBox.warning(self, "警告", f"无效的列号: {column}")
            return

        # 检查是否已经登顶
        state = self.state_dao.get_state(qq_id)
        if column in state.topped_columns:
            QMessageBox.warning(self, "警告", f"玩家已在列{column}登顶")
            return

        player = self.player_dao.get_player(qq_id)
        reply = QMessageBox.question(
            self, "确认",
            f"确定要让 {player.nickname} 直接登顶列{column}吗？\n\n"
            f"⚠️ 这将触发：\n"
            f"• 基础登顶奖励(+10积分)\n"
            f"• 首达检查（如果是全图首达则+20积分并锁定12小时）\n"
            f"• 胜利检查（如果达成3列登顶）"
        )
        if reply != QMessageBox.Yes:
            return

        # 调用游戏引擎的直接登顶方法
        from engine.game_engine import GameEngine
        engine = GameEngine(self.db_conn)
        result_msg = engine._direct_top_column(qq_id, column)

        self._log(f"使用协会特制徽章让 {player.nickname} 直接登顶列{column}")

        # 显示结果
        if result_msg:
            QMessageBox.information(self, "登顶成功", f"🎉 {player.nickname} 已登顶列{column}！\n\n{result_msg}")
        else:
            QMessageBox.information(self, "登顶成功", f"🎉 {player.nickname} 已登顶列{column}！")

        self._update_control_status(qq_id)
        self._show_player_progress(qq_id)
        self.refresh_map()
        self.refresh_players()

    def _lock_player(self):
        """锁定玩家"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        hours = self.lockout_hours_input.value()
        lockout_time = datetime.now() + timedelta(hours=hours)

        state = self.state_dao.get_state(qq_id)
        state.lockout_until = lockout_time.isoformat()
        self.state_dao.update_state(state)

        player = self.player_dao.get_player(qq_id)
        self._log(f"锁定 {player.nickname} {hours}小时")
        self._update_control_status(qq_id)
        self.refresh_players()

    def _unlock_player(self):
        """解锁玩家"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        state = self.state_dao.get_state(qq_id)
        state.lockout_until = None
        self.state_dao.update_state(state)

        player = self.player_dao.get_player(qq_id)
        self._log(f"解锁 {player.nickname}")
        self._update_control_status(qq_id)
        self.refresh_players()

    def _set_skip_rounds(self):
        """设置跳过回合"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        skip_rounds = self.skip_rounds_input.value()

        state = self.state_dao.get_state(qq_id)
        state.skipped_rounds = skip_rounds
        self.state_dao.update_state(state)

        player = self.player_dao.get_player(qq_id)
        self._log(f"设置 {player.nickname} 跳过{skip_rounds}回合")
        self._update_control_status(qq_id)

    def _add_gem(self):
        """添加宝石/池沼"""
        column = self.gem_column_input.value()
        position = self.gem_pos_input.value()
        gem_type_index = self.gem_type_combo.currentIndex()
        gem_types = ['red_gem', 'blue_gem', 'red_pool', 'blue_pool']
        gem_type = gem_types[gem_type_index]

        self.gem_dao.add_gem('GM', gem_type, column, position)

        self._log(f"在列{column}第{position}格添加{self.gem_type_combo.currentText()}")
        self.refresh_map()
        self._refresh_gem_list()

    def _clear_all_gems(self):
        """清除所有宝石池沼"""
        reply = QMessageBox.question(self, "确认", "确定要清除所有宝石和池沼吗？")
        if reply == QMessageBox.Yes:
            cursor = self.db_conn.cursor()
            cursor.execute("UPDATE gem_pools SET is_active = 0")
            self.db_conn.commit()
            self._log("清除所有宝石和池沼")
            self.refresh_map()
            self._refresh_gem_list()

    def _refresh_gem_list(self):
        """刷新宝石池沼列表"""
        gems = self.gem_dao.get_all_active_gems()

        gem_type_names = {
            'red_gem': '🔴 红宝石',
            'blue_gem': '🔵 蓝宝石',
            'red_pool': '🟠 红池沼',
            'blue_pool': '🟣 蓝池沼'
        }

        if not gems:
            self.gem_list_display.setText("当前没有活跃的宝石/池沼")
            return

        text = f"共 {len(gems)} 个活跃的宝石/池沼:\n\n"
        for gem in sorted(gems, key=lambda x: (x.get('column_number', 0), x.get('position', 0))):
            gem_type = gem.get('gem_type', '')
            col = gem.get('column_number', 0)
            pos = gem.get('position', 0)
            type_name = gem_type_names.get(gem_type, gem_type)
            text += f"  列{col} 第{pos}格: {type_name}\n"

        self.gem_list_display.setText(text)

    def _refresh_first_achievements(self):
        """刷新首达记录"""
        cursor = self.db_conn.cursor()
        cursor.execute('''
            SELECT f.column_number, f.first_qq_id, p.nickname
            FROM first_achievements f
            LEFT JOIN players p ON f.first_qq_id = p.qq_id
            ORDER BY f.column_number
        ''')
        records = cursor.fetchall()

        if not records:
            self.first_achievement_display.setText("暂无首达记录")
            return

        text = f"共 {len(records)} 个首达记录:\n\n"
        for record in records:
            col = record['column_number']
            qq_id = record['first_qq_id']
            nickname = record['nickname'] or qq_id
            text += f"  列{col}: {nickname}\n"

        # 显示未被首达的列
        achieved_columns = {r['column_number'] for r in records}
        unachieved = [c for c in VALID_COLUMNS if c not in achieved_columns]
        if unachieved:
            text += f"\n未首达的列: {', '.join(map(str, unachieved))}"

        self.first_achievement_display.setText(text)

    def _batch_add_score(self):
        """批量发放积分"""
        amount = self.batch_score_input.value()
        players = self.player_dao.get_all_players()

        if not players:
            QMessageBox.warning(self, "警告", "没有玩家")
            return

        reply = QMessageBox.question(
            self, "确认",
            f"确定要给所有{len(players)}位玩家发放{amount}积分吗？"
        )
        if reply != QMessageBox.Yes:
            return

        for player in players:
            self.player_dao.add_score(player.qq_id, amount)

        self._log(f"全员发放积分: {amount}")
        self.refresh_players()
        QMessageBox.information(self, "成功", f"已向{len(players)}位玩家发放{amount}积分")

    def _clear_all_lockouts(self):
        """解除所有玩家锁定"""
        reply = QMessageBox.question(self, "确认", "确定要解除所有玩家的锁定吗？")
        if reply != QMessageBox.Yes:
            return

        cursor = self.db_conn.cursor()
        cursor.execute("UPDATE game_state SET lockout_until = NULL")
        self.db_conn.commit()

        self._log("解除所有玩家锁定")
        self.refresh_players()

    # ==================== 契约管理操作 ====================

    def _set_contract(self):
        """建立契约"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        target_qq = self.contract_target_combo.currentData()
        if not target_qq:
            QMessageBox.warning(self, "警告", "请选择契约对象")
            return

        if target_qq == self.selected_qq_id:
            QMessageBox.warning(self, "警告", "不能与自己建立契约")
            return

        qq_id = self.selected_qq_id
        player = self.player_dao.get_player(qq_id)
        target_player = self.player_dao.get_player(target_qq)

        # 检查是否已有契约
        existing_partner = self.contract_dao.get_contract_partner(qq_id)
        if existing_partner:
            existing_name = self.player_dao.get_player(existing_partner)
            existing_name = existing_name.nickname if existing_name else existing_partner
            reply = QMessageBox.question(
                self, "确认",
                f"{player.nickname} 已与 {existing_name} 建立契约。\n是否解除旧契约并与 {target_player.nickname} 建立新契约？"
            )
            if reply != QMessageBox.Yes:
                return
            # 解除旧契约
            self.contract_dao.remove_contract(qq_id)

        # 检查目标是否已有契约
        target_partner = self.contract_dao.get_contract_partner(target_qq)
        if target_partner:
            target_partner_name = self.player_dao.get_player(target_partner)
            target_partner_name = target_partner_name.nickname if target_partner_name else target_partner
            reply = QMessageBox.question(
                self, "确认",
                f"{target_player.nickname} 已与 {target_partner_name} 建立契约。\n是否解除对方旧契约？"
            )
            if reply != QMessageBox.Yes:
                return
            # 解除目标的旧契约
            self.contract_dao.remove_contract(target_qq)

        # 建立新契约
        success, msg = self.contract_dao.create_contract(qq_id, target_qq)
        if success:
            self._log(f"建立契约: {player.nickname} ↔ {target_player.nickname}")
            QMessageBox.information(self, "成功", f"💍 {player.nickname} 与 {target_player.nickname} 建立了契约！")
            self._update_contract_display(qq_id)
            self._show_player_detail(qq_id)
        else:
            QMessageBox.warning(self, "失败", msg)

    def _remove_contract(self):
        """解除契约"""
        if not self.selected_qq_id:
            QMessageBox.warning(self, "警告", "请先选择一个玩家")
            return

        qq_id = self.selected_qq_id
        partner_qq = self.contract_dao.get_contract_partner(qq_id)

        if not partner_qq:
            QMessageBox.warning(self, "警告", "该玩家没有契约关系")
            return

        player = self.player_dao.get_player(qq_id)
        partner = self.player_dao.get_player(partner_qq)
        partner_name = partner.nickname if partner else partner_qq

        reply = QMessageBox.question(
            self, "确认",
            f"确定要解除 {player.nickname} 与 {partner_name} 的契约吗？"
        )
        if reply != QMessageBox.Yes:
            return

        if self.contract_dao.remove_contract(qq_id):
            self._log(f"解除契约: {player.nickname} ↔ {partner_name}")
            QMessageBox.information(self, "成功", f"💔 已解除 {player.nickname} 与 {partner_name} 的契约")
            self._update_contract_display(qq_id)
            self._show_player_detail(qq_id)
        else:
            QMessageBox.warning(self, "失败", "解除契约失败")

    def _update_contract_display(self, qq_id: str):
        """更新契约显示"""
        partner_qq = self.contract_dao.get_contract_partner(qq_id)
        if partner_qq:
            partner = self.player_dao.get_player(partner_qq)
            partner_name = partner.nickname if partner else partner_qq
            self.contract_display.setText(f"{partner_name}")
            self.contract_display.setStyleSheet("font-weight: bold; color: #E91E63;")
        else:
            self.contract_display.setText("无")
            self.contract_display.setStyleSheet("font-weight: bold; color: #9E9E9E;")

    def _refresh_contract_combo(self, exclude_qq: str = None):
        """刷新契约对象下拉框"""
        self.contract_target_combo.clear()
        self.contract_target_combo.addItem("-- 选择玩家 --", None)

        players = self.player_dao.get_all_players()
        for player in players:
            if player.qq_id != exclude_qq:
                self.contract_target_combo.addItem(
                    f"{player.nickname} ({player.qq_id})",
                    player.qq_id
                )

    # ==================== 商店操作 ====================

    def _unlock_all_items(self):
        """解锁所有道具"""
        reply = QMessageBox.question(self, "确认", "确定要解锁所有道具吗？")
        if reply == QMessageBox.Yes:
            cursor = self.db_conn.cursor()
            cursor.execute("UPDATE shop_items SET unlocked = 1")
            self.db_conn.commit()
            self._log("解锁所有道具")
            self.refresh_shop()

    def _reset_shop_sold(self):
        """重置销售数量"""
        reply = QMessageBox.question(self, "确认", "确定要重置所有道具的销售数量吗？")
        if reply == QMessageBox.Yes:
            cursor = self.db_conn.cursor()
            cursor.execute("UPDATE shop_items SET global_sold = 0")
            self.db_conn.commit()
            self._log("重置商店销售数量")
            self.refresh_shop()

    # ==================== 系统操作 ====================

    def _clear_board(self):
        """清除棋盘（保留玩家和积分）"""
        reply = QMessageBox.warning(
            self, "⚠️ 清除棋盘",
            "确定要清除棋盘吗？\n\n将清除：\n• 所有棋子位置\n• 游戏状态\n• 首达记录\n• 宝石池沼\n\n将保留：\n• 玩家信息\n• 积分\n• 背包道具\n• 成就\n\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            from database.schema import DatabaseSchema
            DatabaseSchema.clear_board(self.db_conn)
            self._log("棋盘已清除（保留玩家和积分）")
            QMessageBox.information(self, "成功", "棋盘已清除，玩家信息和积分已保留")
            self.refresh_all()

    def _reset_game(self):
        """重置游戏"""
        reply = QMessageBox.warning(
            self, "⚠️ 危险操作",
            "确定要重置游戏吗？\n这将清除所有玩家数据！\n\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            from database.schema import DatabaseSchema
            DatabaseSchema.reset_game(self.db_conn)
            self._log("游戏已重置")
            QMessageBox.information(self, "成功", "游戏已重置")
            self.refresh_all()

    def _backup_database(self):
        """备份数据库（使用 SQLite 备份 API，确保数据完整）"""
        import sqlite3
        from pathlib import Path

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_dir = Path(self.db_path).parent
        backup_path = db_dir / f"game_backup_{timestamp}.db"

        try:
            # 使用 SQLite 备份 API（比直接复制文件更安全）
            backup_conn = sqlite3.connect(str(backup_path))
            self.db_conn.backup(backup_conn)
            backup_conn.close()

            self._log(f"数据库已备份: {backup_path}")
            QMessageBox.information(self, "成功", f"数据库已备份到:\n{backup_path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"备份失败: {str(e)}")

    def _log(self, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_text = f"[{timestamp}] {message}\n"
        self.log_display.insertPlainText(log_text)
        self.log_display.verticalScrollBar().setValue(
            self.log_display.verticalScrollBar().maximum()
        )

    # ==================== 刷新函数 ====================

    def refresh_all(self):
        """刷新所有数据"""
        self.refresh_players()
        self.refresh_map()
        self.refresh_shop()
        self.refresh_stats()
        # 注意：不在自动刷新中刷新道具下拉框，避免用户选择时被重置
        # 道具列表在初始化时已填充，无需每次刷新
        self._refresh_map_player_filter()
        self._refresh_gem_list()
        self._refresh_first_achievements()

        if self.selected_qq_id:
            self._update_control_status(self.selected_qq_id)

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

            # 获取登顶列数
            positions = self.position_dao.get_positions(player.qq_id, 'permanent')
            topped = sum(1 for p in positions if p.position >= COLUMN_HEIGHTS.get(p.column_number, 0))
            self.players_table.setItem(i, 5, QTableWidgetItem(f"{topped}/3"))

            # 获取状态
            state = self.state_dao.get_state(player.qq_id)
            status = "正常"
            if state and state.lockout_until:
                try:
                    lockout_time = datetime.fromisoformat(state.lockout_until)
                    if datetime.now() < lockout_time:
                        remaining = lockout_time - datetime.now()
                        hours = int(remaining.total_seconds() // 3600)
                        status = f"🔒 {hours}h"
                except:
                    pass

            status_item = QTableWidgetItem(status)
            if status.startswith("🔒"):
                status_item.setForeground(QColor(244, 67, 54))
            self.players_table.setItem(i, 6, status_item)

    def refresh_map(self):
        """刷新地图"""
        all_positions = self.position_dao.get_all_positions_on_map()

        positions_dict = {}
        for qq_id, positions in all_positions.items():
            positions_dict[qq_id] = [
                (p.column_number, p.position, p.marker_type)
                for p in positions
            ]

        # 更新玩家信息
        player_info = {}
        for player in self.player_dao.get_all_players():
            player_info[player.qq_id] = {
                'nickname': player.nickname,
                'faction': player.faction or '未知'
            }

        self.board_widget.update_player_info(player_info)
        self.board_widget.update_positions(positions_dict)

        # 刷新宝石池沼
        gem_pools = self.gem_dao.get_all_active_gems()
        self.board_widget.update_gem_pools(gem_pools)

    def refresh_shop(self):
        """刷新商店"""
        items = self.shop_dao.get_all_items()

        self.shop_table.setRowCount(len(items))

        for i, item in enumerate(items):
            self.shop_table.setItem(i, 0, QTableWidgetItem(str(item.item_id)))
            self.shop_table.setItem(i, 1, QTableWidgetItem(item.item_name))
            self.shop_table.setItem(i, 2, QTableWidgetItem(item.item_type))
            self.shop_table.setItem(i, 3, QTableWidgetItem(str(item.price)))
            self.shop_table.setItem(i, 4, QTableWidgetItem(item.faction_limit or "通用"))
            self.shop_table.setItem(i, 5, QTableWidgetItem(
                str(item.global_limit) if item.global_limit > 0 else "∞"
            ))
            self.shop_table.setItem(i, 6, QTableWidgetItem(str(item.global_sold)))
            self.shop_table.setItem(i, 7, QTableWidgetItem("✅" if item.unlocked else "❌"))

    def refresh_stats(self):
        """刷新统计"""
        players = self.player_dao.get_all_players()

        total_players = len(players)
        total_score = sum(p.total_score for p in players)

        # 统计进行中玩家
        active_count = 0
        topped_count = 0
        for p in players:
            state = self.state_dao.get_state(p.qq_id)
            if state and state.current_round_active:
                active_count += 1

            positions = self.position_dao.get_positions(p.qq_id, 'permanent')
            topped = sum(1 for pos in positions if pos.position >= COLUMN_HEIGHTS.get(pos.column_number, 0))
            if topped >= 3:
                topped_count += 1

        # 统计道具和成就
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM player_inventory")
        item_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM player_achievements")
        ach_count = cursor.fetchone()[0]

        self.stats_labels["总玩家数"].setText(str(total_players))
        self.stats_labels["进行中玩家"].setText(str(active_count))
        self.stats_labels["已登顶玩家"].setText(str(topped_count))
        self.stats_labels["总积分发放"].setText(str(total_score))
        self.stats_labels["道具总数"].setText(str(item_count))
        self.stats_labels["成就总数"].setText(str(ach_count))

        # 刷新排行榜
        self.rank_list.clear()
        sorted_players = sorted(players, key=lambda x: x.current_score, reverse=True)[:10]
        for i, p in enumerate(sorted_players):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
            self.rank_list.addItem(f"{medal} {p.nickname}: {p.current_score}分")

    def _refresh_map_player_filter(self):
        """刷新地图玩家筛选下拉框"""
        current_data = self.map_player_filter.currentData()
        self.map_player_filter.clear()
        self.map_player_filter.addItem("显示全部", None)

        players = self.player_dao.get_all_players()
        for player in players:
            self.map_player_filter.addItem(
                f"{player.nickname}",
                player.qq_id
            )


def main():
    """主函数"""
    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle('Fusion')

    window = GMWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
