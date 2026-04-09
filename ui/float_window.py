"""
悬浮窗
始终置顶、半透明、可拖拽的迷你对话窗口
点击展开/收缩，快速发送消息
"""

from PyQt6.QtCore    import Qt, QPoint, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize
from PyQt6.QtGui     import (QColor, QPainter, QPainterPath, QFont,
                              QLinearGradient, QMouseEvent)
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLineEdit, QPushButton, QLabel,
                              QTextEdit, QSizePolicy, QCheckBox)

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


class FloatingWindow(QWidget):
    """
    悬浮窗主体
    - 始终置顶
    - 可拖拽移动
    - 展开/收缩动画
    - 半透明背景
    """

    message_sent    = pyqtSignal(str)   # 用户发送消息
    screenshot_requested = pyqtSignal() # 请求截图
    closed          = pyqtSignal()
    proactive_replied = pyqtSignal(str, str) # (主动消息, 用户回复内容)

    COLLAPSED_H = 56    # 收缩高度（标题栏高度）
    EXPANDED_H  = 420   # 展开高度
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

        # ── 主动发言状态（已迁移到 main.py 全局管理）────────
        self.agent = None  # 由 main.py 注入
        self._pending_proactive_msg = None  # 待回复的主动消息内容

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

        # ── 消息区 ──────────────────────────────
        self._msg_area = QWidget()
        self._msg_area.setStyleSheet("background:transparent;")
        self._msg_layout = QVBoxLayout(self._msg_area)
        self._msg_layout.setContentsMargins(10, 4, 10, 4)
        self._msg_layout.setSpacing(4)
        self._msg_layout.addStretch()

        from PyQt6.QtWidgets import QScrollArea
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
        self._anim.setStartValue(self.size())
        self._anim.setEndValue(QSize(self.WIDTH, self.EXPANDED_H))
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
        from PyQt6.QtCore import QTimer
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
