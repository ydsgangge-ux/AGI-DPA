"""
悬浮窗
始终置顶、半透明、可拖拽的迷你对话窗口
点击展开/收缩，快速发送消息
内嵌 SimLife 生活状态面板
"""

from PyQt6.QtCore    import Qt, QPoint, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize, QTimer
from PyQt6.QtGui     import (QColor, QPainter, QPainterPath, QFont,
                              QLinearGradient, QMouseEvent, QCursor)
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLineEdit, QPushButton, QLabel,
                              QTextEdit, QSizePolicy, QCheckBox, QScrollArea)

from engine.i18n import t


class FloatBubble(QWidget):
    """单条消息气泡"""
    def __init__(self, text: str, is_user: bool, is_proactive: bool = False,
                 on_replied=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(2)

        # 主动消息勾选栏
        if not is_user and is_proactive:
            top = QHBoxLayout()
            top.setContentsMargins(4, 0, 4, 0)
            chk = QCheckBox("已回复")
            chk.setStyleSheet(
                "QCheckBox{color:#8b949e;font-size:10px;spacing:3px;}"
                "QCheckBox::indicator{width:12px;height:12px;"
                "border:1px solid #30363d;border-radius:2px;}"
                "QCheckBox::indicator:checked{background:#3fb950;"
                "border-color:#3fb950;image:none;}"
            )
            status_lbl = QLabel("未回复")
            status_lbl.setStyleSheet("color:#d29922;font-size:10px;")

            def _toggle(state, s=status_lbl, msg=text, cb=on_replied):
                if state == Qt.CheckState.Checked.value:
                    s.setText("已回复")
                    s.setStyleSheet("color:#3fb950;font-size:10px;")
                    if cb:
                        cb(msg)
                else:
                    s.setText("未回复")
                    s.setStyleSheet("color:#d29922;font-size:10px;")
            chk.stateChanged.connect(_toggle)
            top.addWidget(chk)
            top.addWidget(status_lbl)
            top.addStretch()
            layout.addLayout(top)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(260)
        label.setStyleSheet(f"""
            background: {'#1f6feb' if is_user else '#21262d'};
            color: #e6edf3;
            border-radius: 10px;
            padding: 7px 11px;
            font-size: 12px;
            line-height: 1.5;
        """)

        if is_user:
            row.addStretch()
            row.addWidget(label)
        else:
            row.addWidget(label)
            row.addStretch()

        layout.addLayout(row)


class SimLifePanel(QWidget):
    """SimLife 生活状态面板（嵌入悬浮窗内）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_page = 0
        self._log_per_page = 6
        self._log_data = []
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)

        # ── 状态头部 ──
        header = QHBoxLayout()
        header.setSpacing(8)

        self._avatar = QLabel("😊")
        self._avatar.setFixedSize(32, 32)
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._avatar.setStyleSheet(
            "background:#1f6feb; border-radius:16px; font-size:16px;"
        )

        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        self._name_lbl = QLabel("零一花")
        self._name_lbl.setStyleSheet("color:#e6edf3; font-size:13px; font-weight:600;")

        self._scene_lbl = QLabel("晚间放松")
        self._scene_lbl.setStyleSheet("color:#8b949e; font-size:11px;")

        info_col.addWidget(self._name_lbl)
        info_col.addWidget(self._scene_lbl)

        header.addWidget(self._avatar)
        header.addLayout(info_col)
        header.addStretch()

        # 心情
        mood_box = QVBoxLayout()
        mood_box.setSpacing(0)
        mood_box.setAlignment(Qt.AlignmentFlag.AlignRight)

        self._mood_emoji = QLabel("😊")
        self._mood_emoji.setStyleSheet("font-size:20px;")
        self._mood_emoji.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._mood_lbl = QLabel("87")
        self._mood_lbl.setStyleSheet("color:#e6edf3; font-size:12px; font-weight:700;")
        self._mood_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        mood_box.addWidget(self._mood_emoji)
        mood_box.addWidget(self._mood_lbl)
        header.addLayout(mood_box)

        root.addLayout(header)

        # ── 分隔线 ──
        sep = QLabel("")
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#21262d;")
        root.addWidget(sep)

        # ── 当前活动 ──
        self._activity_row = QHBoxLayout()
        self._activity_row.setSpacing(6)
        act_icon = QLabel("▶")
        act_icon.setStyleSheet("color:#58a6ff; font-size:10px; font-weight:bold;")
        self._activity_lbl = QLabel("正在刷手机")
        self._activity_lbl.setStyleSheet("color:#c9d1d9; font-size:12px;")
        self._activity_lbl.setWordWrap(True)
        self._activity_row.addWidget(act_icon)
        self._activity_row.addWidget(self._activity_lbl, 1)
        root.addLayout(self._activity_row)

        # ── 天气 + 时间 ──
        self._weather_time_lbl = QLabel("☁️ 多云 · 22:00")
        self._weather_time_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        root.addWidget(self._weather_time_lbl)

        # ── 今日动态标题 ──
        log_header = QHBoxLayout()
        log_header.setSpacing(4)
        log_title = QLabel("📋 今日动态")
        log_title.setStyleSheet("color:#8b949e; font-size:11px; font-weight:600;")
        self._log_count_lbl = QLabel("")
        self._log_count_lbl.setStyleSheet("color:#484f58; font-size:10px;")
        log_header.addWidget(log_title)
        log_header.addWidget(self._log_count_lbl)
        log_header.addStretch()
        root.addLayout(log_header)

        # ── 日志滚动区 ──
        self._log_container = QWidget()
        self._log_layout = QVBoxLayout(self._log_container)
        self._log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_layout.setSpacing(3)
        self._log_layout.addStretch()

        self._log_scroll = QScrollArea()
        self._log_scroll.setWidget(self._log_container)
        self._log_scroll.setWidgetResizable(True)
        self._log_scroll.setFixedHeight(130)
        self._log_scroll.setStyleSheet("""
            QScrollArea { background:transparent; border:none; }
            QScrollBar:vertical { width:3px; }
            QScrollBar::handle:vertical { background:#30363d; border-radius:2px; }
        """)
        root.addWidget(self._log_scroll)

        # 无数据占位
        self._empty_lbl = QLabel("暂无今日动态")
        self._empty_lbl.setStyleSheet("color:#484f58; font-size:11px;")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._log_layout.insertWidget(0, self._empty_lbl)

    def update_data(self, summary: dict):
        """用 SimLife 数据更新面板"""
        if not summary:
            return

        # 角色名
        name = summary.get("name", "")
        if name:
            self._name_lbl.setText(name)

        # 场景
        scene = summary.get("scene", "")
        self._scene_lbl.setText(scene if scene else "未知场景")

        # 心情
        mood = summary.get("mood", 70)
        self._mood_emoji.setText(summary.get("mood_emoji", "😊"))
        self._mood_lbl.setText(str(mood))

        # 心情颜色
        if mood >= 80:
            avatar_bg = "#238636"
        elif mood >= 60:
            avatar_bg = "#1f6feb"
        elif mood >= 40:
            avatar_bg = "#9e6a03"
        else:
            avatar_bg = "#da3633"
        self._avatar.setStyleSheet(
            f"background:{avatar_bg}; border-radius:16px; font-size:16px;"
        )

        # 当前活动
        activity = summary.get("activity", "")
        self._activity_lbl.setText(activity if activity else "空闲中")

        # 天气 + 时间 + 节假日
        weather = summary.get("weather", "")
        time_str = summary.get("time_str", "")
        holiday = summary.get("holiday")
        parts = []
        if weather:
            parts.append(weather)
        if holiday and holiday.get("label"):
            parts.append(f"🎉 {holiday['label']}")
        if time_str:
            parts.append(time_str)
        self._weather_time_lbl.setText(" · ".join(parts) if parts else "")

        # 节假日时场景标签加颜色
        if holiday and holiday.get("type") == "public_holiday":
            self._scene_lbl.setStyleSheet("color:#3fb950; font-size:11px;")
        else:
            self._scene_lbl.setStyleSheet("color:#8b949e; font-size:11px;")

        # 日志
        logs = summary.get("today_log", [])
        self._log_data = logs
        self._log_count_lbl.setText(f"{len(logs)} 条")
        self._render_logs(logs)

    def _render_logs(self, logs: list, page: int = 0):
        """渲染日志列表（按页）"""
        # 清除旧日志（保留 stretch）
        while self._log_layout.count() > 1:
            item = self._log_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not logs:
            lbl = QLabel("暂无今日动态")
            lbl.setStyleSheet("color:#484f58; font-size:11px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._log_layout.insertWidget(0, lbl)
            return

        # 倒序显示（最新在上）
        total = len(logs)
        start = max(0, total - (page + 1) * self._log_per_page)
        end = total - page * self._log_per_page

        for i in range(end - 1, start - 1, -1):
            entry = logs[i]
            time_str = entry.get("time", "")
            event = entry.get("event", "")

            row = QHBoxLayout()
            row.setSpacing(6)

            time_lbl = QLabel(time_str)
            time_lbl.setFixedWidth(36)
            time_lbl.setStyleSheet("color:#484f58; font-size:10px;")

            event_lbl = QLabel(event)
            event_lbl.setWordWrap(True)
            event_lbl.setStyleSheet("color:#c9d1d9; font-size:11px;")

            row.addWidget(time_lbl)
            row.addWidget(event_lbl, 1)
            self._log_layout.insertWidget(0, row)


class FloatingWindow(QWidget):
    """
    悬浮窗主体
    - 始终置顶
    - 可拖拽移动
    - 展开/收缩动画
    - 半透明背景
    - 内嵌 SimLife 生活状态面板
    """

    message_sent    = pyqtSignal(str)   # 用户发送消息
    screenshot_requested = pyqtSignal() # 请求截图
    closed          = pyqtSignal()
    proactive_replied = pyqtSignal(str, str) # (主动消息, 用户回复内容)

    COLLAPSED_H = 56    # 收缩高度（标题栏高度）
    EXPANDED_H  = 520   # 展开高度（加大以容纳状态面板）
    WIDTH       = 340

    def __init__(self, opacity: float = 0.95, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(opacity)
        self.resize(self.WIDTH, self.EXPANDED_H)

        self._drag_pos: QPoint | None = None
        self._expanded = True
        self._simlife_shown = False  # 状态面板是否展开

        # ── 主动发言状态（已迁移到 main.py 全局管理）────────
        self.agent = None  # 由 main.py 注入
        self._pending_proactive_msg = None  # 待回复的主动消息内容
        self.simlife_client = None  # 由 main.py 注入

        self._setup_ui()
        self._setup_animation()
        self._position_bottom_right()

    def _setup_ui(self):
        # 给主窗口自身加 Layout，确保 container 完美贴合
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self._container = QWidget(self)
        self._container.setObjectName("float_container")
        self._container.setStyleSheet("""
            #float_container {
                background: rgba(13,17,23,0.96);
                border: 1px solid #30363d;
                border-radius: 14px;
            }
        """)
        main_layout.addWidget(self._container)

        root = QVBoxLayout(self._container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 标题栏 ──────────────────────────────
        self._titlebar = QWidget()
        self._titlebar.setFixedHeight(self.COLLAPSED_H)
        self._titlebar.setStyleSheet("background: transparent;")
        tb_layout = QHBoxLayout(self._titlebar)
        tb_layout.setContentsMargins(14, 8, 10, 8)

        self._brain_icon = QLabel("AG")
        self._brain_icon.setStyleSheet(
            "color:#58a6ff; font-weight:700; font-size:13px; "
            "background:#1f6feb; border-radius:6px; "
            "min-width:22px; max-width:22px; padding:2px 0px;"
        )
        self._brain_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._title_lbl = QLabel(t("app_name"))
        self._title_lbl.setStyleSheet(
            "color:#58a6ff; font-weight:700; font-size:13px;"
        )

        self._emotion_lbl = QLabel(f"· {t('ready')}")
        self._emotion_lbl.setStyleSheet("color:#8b949e; font-size:11px;")

        btn_shot = QPushButton("P")
        btn_shot.setFixedSize(28, 28)
        btn_shot.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_shot.setStyleSheet(
            "QPushButton{background:#1f6feb;border:none;border-radius:6px;"
            "color:#ffffff;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#388bfd;}"
        )
        btn_shot.clicked.connect(self.screenshot_requested)

        self._btn_toggle = QPushButton("-")
        self._btn_toggle.setFixedSize(28, 28)
        self._btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_toggle.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;border-radius:6px;"
            "color:#ffffff;font-size:16px;font-weight:bold;}"
            "QPushButton:hover{background:#30363d;border-color:#58a6ff;}"
        )
        self._btn_toggle.clicked.connect(self.toggle_expand)

        btn_close = QPushButton("X")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;border-radius:6px;"
            "color:#ffffff;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{color:#f85149;border-color:#f85149;}"
        )
        btn_close.clicked.connect(self._on_close)

        tb_layout.addWidget(self._brain_icon)
        tb_layout.addWidget(self._title_lbl)
        tb_layout.addWidget(self._emotion_lbl)
        tb_layout.addStretch()
        tb_layout.addWidget(btn_shot)
        tb_layout.addWidget(self._btn_toggle)
        tb_layout.addWidget(btn_close)

        # ── SimLife 状态触发条 ──────────────────
        self._simlife_tab = QWidget()
        self._simlife_tab.setFixedHeight(36)
        self._simlife_tab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._simlife_tab.setStyleSheet(
            "background:transparent; border-bottom:1px solid #21262d;"
        )
        tab_layout = QHBoxLayout(self._simlife_tab)
        tab_layout.setContentsMargins(12, 0, 12, 0)

        self._simlife_indicator = QLabel("😊")
        self._simlife_indicator.setFixedSize(18, 18)
        self._simlife_indicator.setStyleSheet(
            "background:#238636; border-radius:9px; font-size:10px;"
        )
        self._simlife_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._simlife_brief = QLabel("点击查看生活状态")
        self._simlife_brief.setStyleSheet("color:#8b949e; font-size:11px;")

        self._simlife_arrow = QLabel("▼")
        self._simlife_arrow.setStyleSheet("color:#484f58; font-size:9px;")

        tab_layout.addWidget(self._simlife_indicator)
        tab_layout.addWidget(self._simlife_brief, 1)
        tab_layout.addWidget(self._simlife_arrow)

        # 点击展开/收起状态面板
        self._simlife_tab.mousePressEvent = lambda e: self._toggle_simlife_panel()

        # ── SimLife 状态面板 ────────────────────
        self._simlife_panel = SimLifePanel()
        self._simlife_panel.setStyleSheet("background:transparent;")
        self._simlife_panel.hide()

        # ── 消息区 ──────────────────────────────
        self._msg_area = QWidget()
        self._msg_area.setStyleSheet("background:transparent;")
        self._msg_layout = QVBoxLayout(self._msg_area)
        self._msg_layout.setContentsMargins(10, 4, 10, 4)
        self._msg_layout.setSpacing(4)
        self._msg_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._msg_area)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { background:transparent; border:none; }
            QScrollBar:vertical { width:4px; }
            QScrollBar::handle:vertical { background:#30363d; border-radius:2px; }
        """)
        self._scroll = scroll

        # ── 输入栏 ──────────────────────────────
        self._input_bar = QWidget()
        self._input_bar.setStyleSheet(
            "background:transparent; border-top:1px solid #21262d;"
        )
        self._input_bar.setFixedHeight(52)
        in_layout = QHBoxLayout(self._input_bar)
        in_layout.setContentsMargins(10, 8, 10, 8)

        self._input = QLineEdit()
        self._input.setPlaceholderText(t("float_input_placeholder"))
        self._input.setStyleSheet("""
            QLineEdit {
                background:#161b22; border:1px solid #30363d;
                border-radius:8px; padding:6px 10px;
                color:#e6edf3; font-size:12px;
            }
            QLineEdit:focus { border-color:#58a6ff; }
        """)
        self._input.returnPressed.connect(self._send)

        btn_send = QPushButton("↑")
        btn_send.setFixedSize(32, 32)
        btn_send.setStyleSheet("""
            QPushButton {
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #1f6feb,stop:1 #7c3aed);
                border:none; border-radius:8px;
                color:white; font-size:16px; font-weight:bold;
            }
            QPushButton:hover { opacity:0.9; }
        """)
        btn_send.clicked.connect(self._send)

        in_layout.addWidget(self._input)
        in_layout.addWidget(btn_send)

        # ── 组装 ────────────────────────────────
        root.addWidget(self._titlebar)
        root.addWidget(self._simlife_tab)
        root.addWidget(self._simlife_panel)
        root.addWidget(scroll)
        root.addWidget(self._input_bar)

        self._scroll.hide() if not self._expanded else None

    def _setup_animation(self):
        self._anim = QPropertyAnimation(self, b"size")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _position_bottom_right(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right()  - self.WIDTH - 20,
            screen.bottom() - self.EXPANDED_H - 20
        )

    def update_chat_time(self):
        """用户发消息时调用，重置空闲计时（兼容旧接口）"""
        pass  # 已由 main.py AGIApp 全局管理

    # ── SimLife 面板 ────────────────────────────
    def _toggle_simlife_panel(self):
        if self._simlife_shown:
            self._simlife_panel.hide()
            self._simlife_arrow.setText("▼")
            self._simlife_shown = False
            # 恢复高度
            self.resize(self.WIDTH, self.EXPANDED_H)
        else:
            self._refresh_simlife()
            self._simlife_panel.show()
            self._simlife_arrow.setText("▲")
            self._simlife_shown = True
            # 加高以容纳面板
            self.resize(self.WIDTH, self.EXPANDED_H + 200)

    def _refresh_simlife(self):
        """从 simlife_client 读取数据并刷新面板"""
        if not self.simlife_client:
            return
        try:
            summary = self.simlife_client.get_life_summary()
            if summary:
                self._simlife_panel.update_data(summary)
                # 更新标签栏简报
                emoji = summary.get("mood_emoji", "😊")
                scene = summary.get("scene", "")
                activity = summary.get("activity", "")
                if activity:
                    brief = f"{scene} · {activity[:12]}"
                else:
                    brief = scene if scene else "点击查看生活状态"
                self._simlife_brief.setText(brief)
                self._simlife_indicator.setText(emoji)
                # 心情颜色
                mood = summary.get("mood", 70)
                if mood >= 80:
                    bg = "#238636"
                elif mood >= 60:
                    bg = "#1f6feb"
                elif mood >= 40:
                    bg = "#9e6a03"
                else:
                    bg = "#da3633"
                self._simlife_indicator.setStyleSheet(
                    f"background:{bg}; border-radius:9px; font-size:10px;"
                )
        except Exception:
            pass

    def refresh_simlife_state(self):
        """外部定时调用，刷新 SimLife 面板数据（如果面板可见）"""
        if self._simlife_shown:
            self._refresh_simlife()

    # ── 展开 / 收缩 ────────────────────────────
    def toggle_expand(self):
        if self._expanded:
            self._collapse()
        else:
            self._expand()

    def _expand(self):
        self._expanded = True
        self._btn_toggle.setText("-")
        self._scroll.show()
        self._input_bar.show()
        self._simlife_tab.show()
        target_h = self.EXPANDED_H + (200 if self._simlife_shown else 0)
        self._anim.setStartValue(self.size())
        self._anim.setEndValue(QSize(self.WIDTH, target_h))
        try:
            self._anim.finished.disconnect()
        except Exception:
            pass
        self._anim.start()

    def _collapse(self):
        self._expanded = False
        self._btn_toggle.setText("+")
        self._scroll.hide()
        self._input_bar.hide()
        self._simlife_tab.hide()
        self._simlife_panel.hide()
        self._anim.setStartValue(self.size())
        self._anim.setEndValue(QSize(self.WIDTH, self.COLLAPSED_H))
        try:
            self._anim.finished.disconnect()
        except Exception:
            pass
        self._anim.start()

    # ── 消息 ────────────────────────────────────
    def _send(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.update_chat_time()
        self.add_message(text, is_user=True)
        # 有待回复的主动消息时，把主动消息+用户回复一起关联存储
        if self._pending_proactive_msg:
            self.proactive_replied.emit(self._pending_proactive_msg, text)
            self._pending_proactive_msg = None
        self.message_sent.emit(text)

    def _on_proactive_check(self, message: str):
        """主动消息勾选'已回复'时触发（手动勾选，无回复文本）"""
        self.proactive_replied.emit(message, "")
        self._pending_proactive_msg = None

    def add_message(self, text: str, is_user: bool = False, is_proactive: bool = False):
        if not is_user and is_proactive:
            self._pending_proactive_msg = text
        bubble = FloatBubble(text, is_user, is_proactive=is_proactive,
                             on_replied=self._on_proactive_check)
        self._msg_layout.insertWidget(
            self._msg_layout.count() - 1, bubble
        )
        # 滚动到底部
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def set_thinking(self, thinking: bool):
        if thinking:
            self._emotion_lbl.setText(f"· {t('thinking')}")
            self._brain_icon.setText("⏳")
        else:
            self._brain_icon.setText("🧠")

    def update_emotion(self, emotion: str, intensity: float):
        emoji = {
            "joy": "😊", "sadness": "😔", "anger": "😤",
            "fear": "😨", "surprise": "😲", "curious": "🤔",
            "nostalgic": "😌", "trust": "🤝", "neutral": "😐"
        }.get(emotion, "🧠")
        self._brain_icon.setText(emoji)
        self._emotion_lbl.setText(f"· {emotion} {int(intensity*10)}/10")

    # ── 拖拽移动 ────────────────────────────────
    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(e.position().toPoint())
            if isinstance(child, (QPushButton, QLineEdit, QTextEdit)):
                return
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e: QMouseEvent):
        if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def _on_close(self):
        self.hide()
        self.closed.emit()
