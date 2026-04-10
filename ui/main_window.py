"""
主窗口
包含：对话、记忆库、人格设定、工具箱、系统设置 五个标签页
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore    import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui     import QFont, QIcon, QColor, QPixmap, QPainter
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton,
    QListWidget, QListWidgetItem, QTabWidget,
    QSplitter, QGroupBox, QCheckBox, QSlider,
    QComboBox, QScrollArea, QFrame, QStatusBar,
    QSizePolicy, QApplication, QFileDialog,
    QGridLayout, QSpacerItem, QMessageBox,
    QTextBrowser, QProgressBar
)

from desktop.config import APP_NAME, load_config, save_config, DARK_QSS
from desktop.system import make_tray_icon


def _get_desktop() -> Path:
    """Get user Desktop folder (cross-platform)"""
    import subprocess
    p = Path.home() / "Desktop"
    if p.exists():
        return p
    if sys.platform == "linux":
        try:
            result = subprocess.run(
                ["xdg-user-dir", "DESKTOP"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                alt = Path(result.stdout.strip())
                if alt.exists():
                    return alt
        except Exception:
            pass
    return Path.home()

def _make_label(text: str, style: str) -> QLabel:
    """创建带样式的 QLabel（PyQt6 不支持构造函数传 styleSheet）"""
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl



# ── AGI 工作线程 ──────────────────────────────────
class AGIWorker(QThread):
    """在后台线程运行 A 层处理，避免卡界面"""

    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)
    confirm_requested = pyqtSignal(str, object)  # (tool_name, params_dict)

    TIMEOUT_SEC = 120   # 最长等待时间，超时后报错

    def __init__(self, agent, user_input: str):
        super().__init__()
        self.agent = agent
        self.user_input = user_input
        self._confirm_result = None   # 主线程写，子线程读
        self._confirm_event  = None   # threading.Event 用于跨线程等待

    def run(self):
        if self.agent is None:
            self.error.emit("AGI 引擎尚未初始化，请稍候再试")
            return

        import threading
        self._confirm_event = threading.Event()

        # 把 confirm 替换为线程安全的版本
        original_confirm = self.agent.b.confirm
        self.agent.b.confirm = self._thread_safe_confirm

        try:
            result = self.agent.process(self.user_input)
            self.finished.emit(result)
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()[-300:]}")
        finally:
            self.agent.b.confirm = original_confirm

    def _thread_safe_confirm(self, tool_name: str, params: dict) -> bool:
        """从工作线程调用 → 发信号给主线程弹窗 → 等待结果"""
        self._confirm_result = None
        self._confirm_event.clear()
        self.confirm_requested.emit(tool_name, params)
        # 等待主线程设置结果（超时 120 秒）
        self._confirm_event.wait(timeout=120)
        return self._confirm_result if self._confirm_result is not None else False

    def set_confirm_result(self, allowed: bool):
        """主线程槽：设置确认结果并唤醒工作线程"""
        self._confirm_result = allowed
        if self._confirm_event:
            self._confirm_event.set()


# ── 消息气泡组件 ─────────────────────────────────
class MessageBubble(QFrame):
    """消息气泡 — QLabel + wordWrap，高度可靠"""

    def __init__(self, text: str, is_user: bool,
                 meta: dict = None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._is_proactive = (meta or {}).get("proactive", False)
        self._replied = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        bg = "#1f6feb" if is_user else "#21262d"

        # ── 主动消息：顶部勾选栏 ──
        if not is_user and self._is_proactive:
            top_bar = QHBoxLayout()
            top_bar.setContentsMargins(2, 0, 2, 0)
            self._reply_chk = QCheckBox()
            self._reply_chk.setText("已回复")
            self._reply_chk.setStyleSheet(
                "QCheckBox{color:#8b949e;font-size:11px;spacing:4px;}"
                "QCheckBox::indicator{width:14px;height:14px;"
                "border:1px solid #30363d;border-radius:3px;}"
                "QCheckBox::indicator:checked{background:#3fb950;"
                "border-color:#3fb950;image:none;}"
            )
            self._reply_chk.stateChanged.connect(self._on_reply_checked)

            self._reply_status = QLabel("📌 未回复")
            self._reply_status.setStyleSheet("color:#d29922;font-size:11px;")

            top_bar.addWidget(self._reply_chk)
            top_bar.addWidget(self._reply_status)
            top_bar.addStretch()
            layout.addLayout(top_bar)

        # ── 内容气泡：QLabel，wordWrap，可选中 ──
        content = QLabel(text)
        content.setWordWrap(True)
        content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        content.setStyleSheet(f"""
            QLabel {{
                background: {bg};
                color: #e6edf3;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 13px;
                line-height: 1.5;
            }}
        """)
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum
        )

        if is_user:
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(content)
            layout.addLayout(row)
        else:
            layout.addWidget(content)

        # ── AI 消息底部：元信息 + 朗读按钮 ──
        if not is_user:
            bottom = QHBoxLayout()
            bottom.setContentsMargins(2, 0, 2, 0)

            # 元信息
            if meta:
                parts = []
                if meta.get("emotion"):
                    e = meta["emotion"]
                    parts.append(f"情绪:{e.get('primary','?')} "
                                 f"{int(e.get('intensity',0)*10)}/10")
                if meta.get("tools_used"):
                    parts.append(f"🔧 {','.join(meta['tools_used'])}")
                if meta.get("stored"):
                    parts.append("📝 已记忆")
                if parts:
                    ml = QLabel("  ·  ".join(parts))
                    ml.setStyleSheet("color:#6e7681;font-size:10px;")
                    bottom.addWidget(ml)

            bottom.addStretch()

            # 朗读按钮
            btn_tts = QPushButton("朗读")
            btn_tts.setFixedSize(36, 22)
            btn_tts.setToolTip("朗读此消息 / 点击停止")
            btn_tts.setStyleSheet(
                "QPushButton{background:#21262d;border:1px solid #30363d;"
                "border-radius:6px;color:#58a6ff;font-size:11px;padding:0 4px;}"
                "QPushButton:hover{background:#30363d;border-color:#58a6ff;}"
            )
            _tts_active = [False]
            _msg_text   = text

            def _speak(_, t=_msg_text, b=btn_tts, active=_tts_active):
                try:
                    from engine.tts_engine import get_tts
                    tts = get_tts()
                    if active[0]:
                        tts.stop()
                        active[0] = False
                        b.setText("朗读")
                        return
                    from desktop.config import load_config
                    cfg = load_config()
                    tts.set_voice(cfg.get("tts_voice", "zh-CN-XiaoxiaoNeural"))
                    tts.set_rate(cfg.get("tts_rate", 0))
                    active[0] = True
                    b.setText("停止")
                    def _done():
                        active[0] = False
                        b.setText("朗读")
                    def _on_err(e):
                        print(f"[TTS] 朗读失败: {e}")
                        active[0] = False
                        b.setText("朗读")
                    tts.speak(t, on_done=_done, on_error=_on_err)
                except Exception as ex:
                    print(f"[TTS] 调用异常: {ex}")

            btn_tts.clicked.connect(_speak)
            bottom.addWidget(btn_tts)
            layout.addLayout(bottom)

            # 工具步骤
            if meta:
                for s in (meta.get("tool_steps") or [])[:5]:
                    ok  = s.get("result", {}).get("ok", False)
                    lbl = QLabel(
                        f"  {'✅' if ok else '❌'} {s['tool']}"
                        f"({str(s.get('params',''))[:40]})"
                    )
                    lbl.setStyleSheet(
                        f"color:{'#3fb950' if ok else '#f85149'};"
                        "font-size:10px;font-family:monospace;"
                    )
                    layout.addWidget(lbl)

    def _on_reply_checked(self, state):
        """勾选回复状态"""
        self._replied = (state == Qt.CheckState.Checked.value)
        if self._replied:
            self._reply_status.setText("✅ 已回复")
            self._reply_status.setStyleSheet("color:#3fb950;font-size:11px;")
        else:
            self._reply_status.setText("📌 未回复")
            self._reply_status.setStyleSheet("color:#d29922;font-size:11px;")


# ── 工具面板（右侧）─────────────────────────────
class ToolPanel(QWidget):
    """
    右侧工具面板
    显示全部17个工具，点击填入输入框
    """
    tool_clicked = pyqtSignal(str, str)   # (tool_name, description)

    RISK_COLOR = {"low": "#3fb950", "medium": "#d29922", "high": "#f85149"}
    RISK_LABEL = {"low": "安全", "medium": "中等", "high": "高危"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet("background:#161b22;border-left:1px solid #30363d;")
        self._setup_ui()
        self._load_tools()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        header = QWidget()
        header.setFixedHeight(42)
        header.setStyleSheet(
            "background:#1c2128;border-bottom:1px solid #30363d;"
        )
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(12, 0, 12, 0)
        title = QLabel("🔧  工具箱")
        title.setStyleSheet("color:#58a6ff;font-weight:700;font-size:13px;")
        hint = QLabel("点击填入输入框")
        hint.setStyleSheet("color:#8b949e;font-size:10px;")
        hlay.addWidget(title)
        hlay.addStretch()
        hlay.addWidget(hint)

        # 搜索框
        search_wrap = QWidget()
        search_wrap.setStyleSheet("background:#161b22;padding:8px;")
        slay = QVBoxLayout(search_wrap)
        slay.setContentsMargins(8, 8, 8, 4)
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索工具…")
        self._search.setStyleSheet(
            "QLineEdit{background:#21262d;border:1px solid #30363d;"
            "border-radius:6px;padding:5px 8px;color:#e6edf3;font-size:11px;}"
            "QLineEdit:focus{border-color:#58a6ff;}"
        )
        self._search.textChanged.connect(self._filter)
        slay.addWidget(self._search)

        # 工具列表
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{background:#161b22;border:none;outline:none;}"
            "QListWidget::item{padding:0px;border:none;}"
            "QListWidget::item:hover{background:transparent;}"
        )
        self._list.setSpacing(2)
        self._list.itemClicked.connect(self._on_click)

        layout.addWidget(header)
        layout.addWidget(search_wrap)
        layout.addWidget(self._list)

    def _load_tools(self):
        try:
            from engine.tools import TOOL_REGISTRY
            self._tools = [
                {
                    "name": name,
                    "desc": info["schema"]["description"],
                    "risk": info["risk"],
                    "params": list(
                        info["schema"]["input_schema"]
                        .get("properties", {}).keys()
                    )
                }
                for name, info in TOOL_REGISTRY.items()
            ]
        except Exception:
            self._tools = []
        self._render(self._tools)

    def _render(self, tools):
        self._list.clear()
        for t in tools:
            item = QListWidgetItem()
            item.setSizeHint(QSize(200, 68))
            item.setData(Qt.ItemDataRole.UserRole, t)
            self._list.addItem(item)

            # 自定义卡片 widget
            card = self._make_card(t)
            self._list.setItemWidget(item, card)

    def _make_card(self, t: dict) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "QWidget{background:#1c2128;border-radius:6px;margin:2px 6px;}"
            "QWidget:hover{background:#21262d;border:1px solid #30363d;}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(3)

        # 第一行：名称 + 风险标签
        top = QHBoxLayout()
        name_lbl = QLabel(t["name"])
        name_lbl.setStyleSheet(
            "color:#e6edf3;font-size:12px;font-weight:600;"
            "background:transparent;"
        )
        risk_color = self.RISK_COLOR.get(t["risk"], "#8b949e")
        risk_lbl = QLabel(self.RISK_LABEL.get(t["risk"], t["risk"]))
        risk_lbl.setStyleSheet(
            f"color:{risk_color};font-size:10px;background:transparent;"
            f"border:1px solid {risk_color};border-radius:3px;padding:1px 5px;"
        )
        top.addWidget(name_lbl)
        top.addStretch()
        top.addWidget(risk_lbl)

        # 第二行：描述
        desc_lbl = QLabel(t["desc"][:52] + ("…" if len(t["desc"]) > 52 else ""))
        desc_lbl.setStyleSheet(
            "color:#8b949e;font-size:11px;background:transparent;"
        )
        desc_lbl.setWordWrap(True)

        lay.addLayout(top)
        lay.addWidget(desc_lbl)
        return card

    def _filter(self, text: str):
        filtered = [
            t for t in self._tools
            if text.lower() in t["name"].lower()
            or text.lower() in t["desc"].lower()
        ] if text else self._tools
        self._render(filtered)

    def _on_click(self, item: QListWidgetItem):
        t = item.data(Qt.ItemDataRole.UserRole)
        if t:
            self.tool_clicked.emit(t["name"], t["desc"])


# ── 斜杠命令补全弹窗 ──────────────────────────────
class SlashCompleter(QWidget):
    """
    输入 / 时弹出的命令补全列表
    选中后填入输入框
    """
    selected = pyqtSignal(str)   # 选中的命令文本

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFixedWidth(280)
        self.setStyleSheet(
            "QWidget{background:#161b22;border:1px solid #30363d;"
            "border-radius:8px;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget{background:transparent;border:none;outline:none;}"
            "QListWidget::item{padding:7px 12px;border-radius:4px;"
            "font-size:12px;color:#e6edf3;}"
            "QListWidget::item:selected{background:#1f6feb;}"
            "QListWidget::item:hover{background:#21262d;}"
        )
        self._list.itemClicked.connect(
            lambda item: self.selected.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        layout.addWidget(self._list)
        self._all_commands = []

    def load_commands(self):
        """从工具注册表加载所有命令"""
        try:
            from engine.tools import TOOL_REGISTRY
            self._all_commands = [
                {
                    "cmd":   f"/{name}",
                    "label": f"/{name}  —  {info['schema']['description'][:40]}",
                    "fill":  f"请帮我使用 {name} 工具，"
                }
                for name, info in TOOL_REGISTRY.items()
            ]
        except Exception:
            self._all_commands = []

    def show_for(self, text: str, pos):
        """根据已输入的 /xxx 过滤并显示"""
        query = text.lstrip("/").lower()
        filtered = [
            c for c in self._all_commands
            if query in c["cmd"].lower() or query in c["label"].lower()
        ] if query or text == "/" else self._all_commands

        self._list.clear()
        for c in filtered[:10]:
            item = QListWidgetItem(c["label"])
            item.setData(Qt.ItemDataRole.UserRole, c["fill"])
            self._list.addItem(item)

        if filtered:
            h = min(len(filtered), 10) * 32 + 8
            self.setFixedHeight(h)
            self.move(pos)
            self.show()
        else:
            self.hide()


# ── 对话页 ────────────────────────────────────────
class ChatPage(QWidget):

    message_sent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._completer = SlashCompleter(self)
        self._completer.load_commands()
        self._setup_ui()

    def _setup_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 左侧：消息 + 输入
        left = QWidget()
        layout = QVBoxLayout(left)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 消息滚动区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            "QScrollArea{border:none;background:#0d1117;}"
        )
        self._msg_container = QWidget()
        self._msg_container.setStyleSheet("background:#0d1117;")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(16, 16, 16, 16)
        self._msg_layout.setSpacing(10)
        self._msg_layout.addStretch()
        self._scroll.setWidget(self._msg_container)

        # 输入区
        input_frame = QFrame()
        input_frame.setStyleSheet(
            "QFrame{background:#161b22;border-top:1px solid #30363d;}"
        )
        input_frame.setFixedHeight(100)
        in_layout = QHBoxLayout(input_frame)
        in_layout.setContentsMargins(14, 10, 14, 10)

        self._input = QTextEdit()
        self._input.setPlaceholderText(
            "输入消息或任务… / 输入 / 选择工具  (Enter发送, Shift+Enter换行)"
        )
        self._input.setFixedHeight(72)
        # 禁用自动URL检测，防止输入网址时丢失前面的文字
        self._input.setAutoFormatting(QTextEdit.AutoFormattingFlag.AutoNone)
        self._input.setStyleSheet(
            "QTextEdit{background:#21262d;border:1px solid #30363d;"
            "border-radius:8px;padding:8px;color:#e6edf3;font-size:13px;}"
            "QTextEdit:focus{border-color:#58a6ff;}"
        )
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._on_text_changed)

        # 附件按钮（图片/文件）
        self._pending_file = None   # 待发送的附件路径
        btn_attach = QPushButton("📎 文件")
        btn_attach.setFixedSize(56, 72)
        btn_attach.setToolTip("上传图片或 Office 文件")
        btn_attach.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:8px;color:#8b949e;font-size:12px;padding:2px;}"
            "QPushButton:hover{color:#58a6ff;border-color:#58a6ff;}"
        )
        btn_attach.clicked.connect(self._pick_file)

        # 附件预览标签
        self._attach_lbl = QLabel("")
        self._attach_lbl.setStyleSheet(
            "color:#58a6ff;font-size:11px;padding:0 4px;"
        )
        self._attach_lbl.setMaximumWidth(160)
        self._attach_lbl.setWordWrap(False)

        btn_send = QPushButton("发送")
        btn_send.setObjectName("btn_primary")
        btn_send.setFixedSize(72, 72)
        btn_send.setStyleSheet(
            "QPushButton#btn_primary{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #1f6feb,stop:1 #7c3aed);"
            "border:none;border-radius:8px;color:white;"
            "font-size:13px;font-weight:700;}"
        )
        btn_send.clicked.connect(self._send)

        in_layout.addWidget(btn_attach)
        in_layout.addWidget(self._attach_lbl)
        in_layout.addWidget(self._input)
        in_layout.addWidget(btn_send)

        layout.addWidget(self._scroll)
        layout.addWidget(input_frame)

        # 右侧：工具面板
        self.tool_panel = ToolPanel()
        self.tool_panel.tool_clicked.connect(self._on_tool_clicked)

        # 补全选中
        self._completer.selected.connect(self._on_completer_selected)

        outer.addWidget(left, stretch=1)
        outer.addWidget(self.tool_panel)

    def _on_text_changed(self):
        """检测 / 开头，弹出补全"""
        text = self._input.toPlainText()
        if text.startswith("/") and "\n" not in text:
            # 计算弹窗位置（输入框上方）
            pos = self._input.mapToGlobal(self._input.pos())
            from PyQt6.QtCore import QPoint
            popup_pos = self._input.mapToGlobal(
                QPoint(0, -self._completer.height() - 4)
            )
            self._completer.show_for(text, popup_pos)
        else:
            self._completer.hide()

    def _on_completer_selected(self, fill_text: str):
        """补全选中：替换输入框内容"""
        self._input.setPlainText(fill_text)
        self._completer.hide()
        # 光标移到末尾
        cursor = self._input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.setFocus()

    def _on_tool_clicked(self, tool_name: str, desc: str):
        """点击工具面板卡片：填入输入框"""
        current = self._input.toPlainText().strip()
        if current:
            # 已有内容：追加工具指令
            self._input.setPlainText(
                f"{current}（使用 {tool_name} 工具完成）"
            )
        else:
            self._input.setPlainText(f"请帮我使用 {tool_name} 工具，")
        cursor = self._input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.setFocus()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            # Tab / Enter 确认补全
            if (self._completer.isVisible() and
                    event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Down)):
                self._completer._list.setFocus()
                self._completer._list.setCurrentRow(0)
                return True
            if event.key() == Qt.Key.Key_Escape:
                self._completer.hide()
                return False
            if (event.key() == Qt.Key.Key_Return and
                    not event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self._completer.hide()
                self._send()
                return True
        return super().eventFilter(obj, event)

    def _pick_file(self):
        """打开文件选择器，支持图片和 Office 文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择文件",
            str(Path.home()),
            "图片和文档 (*.png *.jpg *.jpeg *.gif *.webp "
            "*.docx *.xlsx *.pptx *.pdf *.csv *.txt *.md);;"
            "图片 (*.png *.jpg *.jpeg *.gif *.webp);;"
            "Office 文档 (*.docx *.xlsx *.pptx *.pdf *.csv)"
        )
        if path:
            self._pending_file = path
            fname = Path(path).name
            self._attach_lbl.setText(f"📎 {fname[:20]}")
            self._attach_lbl.setToolTip(path)

    def _send(self):
        text = self._input.toPlainText().strip()
        pending = self._pending_file

        if not text and not pending:
            return

        # ── 从富文本中提取 URL（浏览器复制链接时 toPlainText 只返回标题）──
        html = self._input.toHtml()
        if "<a href=" in html and "http" not in text:
            import re
            urls = re.findall(r'<a[^>]+href="([^"]+)"', html)
            if urls:
                url_str = "\n".join(urls)
                text = (text + "\n" + url_str).strip()

        # 清空输入
        self._input.clear()
        self._pending_file = None
        self._attach_lbl.setText("")

        if pending:
            ext = Path(pending).suffix.lower()
            is_image = ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")

            if is_image:
                # 显示图片气泡
                self._show_image_bubble(pending)
                # 构建含图片路径的消息
                msg = f"[图片: {pending}]"
                if text:
                    msg += f"\n{text}"
                else:
                    msg += "\n请分析这张图片"
            else:
                # 非图片文件：显示文件标记
                self.add_user_message(f"📎 {Path(pending).name}\n{text or '请分析这个文件'}")
                msg = f"[文件: {pending}]\n{text or '请分析这个文件的内容'}"

            self.message_sent.emit(msg)
        elif text:
            self.message_sent.emit(text)

    def _show_image_bubble(self, image_path: str, is_user: bool = True):
        """在聊天区显示图片预览气泡"""
        from PyQt6.QtGui import QPixmap
        bubble = QFrame()
        bubble.setFrameShape(QFrame.Shape.NoFrame)
        bl = QHBoxLayout(bubble)
        img_lbl = QLabel()
        pix = QPixmap(image_path)
        if not pix.isNull():
            pix = pix.scaledToWidth(
                280, Qt.TransformationMode.SmoothTransformation
            )
            img_lbl.setPixmap(pix)
        else:
            img_lbl.setText(f"🖼 {Path(image_path).name}")
        if is_user:
            bl.addStretch()
            img_lbl.setStyleSheet(
                "background:#1f6feb;border-radius:10px;padding:6px;"
            )
        else:
            img_lbl.setStyleSheet(
                "background:#21262d;border-radius:10px;padding:6px;"
            )
        bl.addWidget(img_lbl)
        if not is_user:
            bl.addStretch()
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)
        self._scroll_to_bottom()

    def fill_input(self, text: str):
        """外部调用：填入输入框（如 OCR 结果）"""
        self._input.setPlainText(text)
        cursor = self._input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.setFocus()

    def add_user_message(self, text: str):
        bubble = MessageBubble(text, is_user=True)
        self._msg_layout.insertWidget(
            self._msg_layout.count() - 1, bubble
        )
        self._scroll_to_bottom()

    def add_ai_message(self, text: str, meta: dict = None):
        bubble = MessageBubble(text, is_user=False, meta=meta)
        self._msg_layout.insertWidget(
            self._msg_layout.count() - 1, bubble
        )
        self._scroll_to_bottom()

    def add_thinking_indicator(self) -> QLabel:
        lbl = QLabel("⏳ 思考中…")
        lbl.setStyleSheet(
            "color:#8b949e;font-size:12px;padding:8px 14px;"
            "background:#21262d;border-radius:8px;"
        )
        lbl.setObjectName("thinking_indicator")
        self._msg_layout.insertWidget(
            self._msg_layout.count() - 1, lbl,
            alignment=Qt.AlignmentFlag.AlignLeft
        )
        self._scroll_to_bottom()
        return lbl

    def remove_thinking_indicator(self):
        for i in range(self._msg_layout.count()):
            item = self._msg_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.objectName() == "thinking_indicator":
                    self._msg_layout.removeWidget(w)
                    w.deleteLater()
                    break

    def _scroll_to_bottom(self):
        QTimer.singleShot(
            80,
            lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            )
        )


# ── 记忆库页 ──────────────────────────────────────
class MemoryPage(QWidget):
    def __init__(self, db_file: str, auth_ref=None, parent=None):
        super().__init__(parent)
        self.db_file = db_file
        self._auth_ref = auth_ref
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # 搜索栏
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("语义搜索记忆…")
        self._search.returnPressed.connect(self.search)
        btn_search = QPushButton("搜索")
        btn_search.clicked.connect(self.search)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.load)

        # 清除记忆按钮（红色，放在右侧）
        btn_clear = QPushButton("🗑  清除记忆")
        btn_clear.setFixedHeight(30)
        btn_clear.setStyleSheet(
            "QPushButton{background:rgba(248,81,73,.1);border:1px solid #f85149;"
            "border-radius:6px;color:#f85149;font-size:12px;padding:0 12px;}"
            "QPushButton:hover{background:rgba(248,81,73,.25);}"
        )
        btn_clear.clicked.connect(self._clear_memory_dialog)

        search_row.addWidget(self._search)
        search_row.addWidget(btn_search)
        search_row.addWidget(btn_refresh)
        search_row.addStretch()
        search_row.addWidget(btn_clear)

        # 过滤标签
        filter_row = QHBoxLayout()
        self._filters = {}
        for f, lbl in [("all","全部"),("detail","细节"),
                        ("outline","细纲"),("summary","大纲"),
                        ("emotional","情感"),("semantic","语义")]:
            btn = QPushButton(lbl)
            btn.setCheckable(True)
            btn.setChecked(f == "all")
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                "QPushButton{background:#21262d;border:1px solid #30363d;"
                "border-radius:12px;padding:0 12px;font-size:11px;}"
                "QPushButton:checked{background:rgba(31,111,235,.2);"
                "color:#58a6ff;border-color:#58a6ff;}"
            )
            btn.clicked.connect(lambda checked, flt=f: self._apply_filter(flt))
            self._filters[f] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()

        # 统计栏
        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet("color:#8b949e;font-size:11px;margin:4px 0;")

        # 记忆列表
        self._list = QListWidget()
        self._list.setSpacing(4)
        self._list.setStyleSheet(
            "QListWidget{background:#161b22;border:1px solid #30363d;"
            "border-radius:8px;}"
            "QListWidget::item{padding:10px;border-radius:6px;"
            "border-bottom:1px solid #21262d;}"
            "QListWidget::item:selected{background:#1f3a5c;}"
        )

        layout.addLayout(search_row)
        layout.addLayout(filter_row)
        layout.addWidget(self._stats_lbl)
        layout.addWidget(self._list)

        self._all_items = []
        self._current_filter = "all"

    def load(self):
        from engine.db_guard import guarded_connect

        # 未登录时显示提示
        if self._auth_ref and self._auth_ref() and self._auth_ref().is_guest():
            self._list.clear()
            self._stats_lbl.setText("")
            item = QListWidgetItem("🔒  请先登录后查看记忆库")
            item.setForeground(QColor("#8b949e"))
            self._list.addItem(item)
            return

        # 获取当前用户 ID
        user_id = None
        if self._auth_ref and self._auth_ref() and not self._auth_ref().is_guest():
            user_id = self._auth_ref().user_id

        try:
            with guarded_connect(self.db_file) as conn:
                if user_id:
                    rows = conn.execute(
                        "SELECT id,content,modality,level,emotion_json,"
                        "importance,created_at FROM memories "
                        "WHERE user_id=? OR user_id='default' OR user_id='system' "
                        "ORDER BY created_at DESC, importance DESC LIMIT 300",
                        (user_id,)
                    ).fetchall()
                    total = conn.execute(
                        "SELECT COUNT(*) FROM memories "
                        "WHERE user_id=? OR user_id='default' OR user_id='system'",
                        (user_id,)
                    ).fetchone()[0]
                else:
                    rows = conn.execute(
                        "SELECT id,content,modality,level,emotion_json,"
                        "importance,created_at FROM memories "
                        "ORDER BY created_at DESC, importance DESC LIMIT 300"
                    ).fetchall()
                    total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                edges = conn.execute(
                    "SELECT COUNT(*) FROM memory_edges"
                ).fetchone()[0] if self._table_exists(conn, "memory_edges") else 0
            self._all_items = rows
            self._stats_lbl.setText(
                f"共 {total} 条记忆  ·  {edges} 条关联边  "
                f"·  当前显示 {min(len(rows), 300)} 条  "
                f"·  双击查看完整内容"
            )
            self._render(rows)
        except Exception as e:
            self._list.clear()
            self._list.addItem(f"加载失败: {e}")

    def _table_exists(self, conn, table_name: str) -> bool:
        res = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ).fetchone()
        return res is not None

    def _clear_memory_dialog(self):
        """
        三次确认清除记忆
        第1次：选择清除范围
        第2次：文字确认
        第3次：最终确认
        """
        from engine.db_guard import guarded_connect

        # ── 第1次：选择清除范围 ──────────────────
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QRadioButton, QButtonGroup

        dlg1 = QDialog(self)
        dlg1.setWindowTitle("清除记忆 — 第 1/3 步")
        dlg1.setFixedWidth(420)
        dlg1.setStyleSheet(
            "QDialog{background:#161b22;color:#e6edf3;}"
            "QLabel{color:#e6edf3;}"
            "QRadioButton{color:#e6edf3;padding:6px;font-size:13px;}"
            "QRadioButton::indicator{width:16px;height:16px;}"
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:6px;padding:6px 16px;color:#e6edf3;}"
            "QPushButton:hover{border-color:#58a6ff;}"
        )
        lay1 = QVBoxLayout(dlg1)
        lay1.setSpacing(12)
        lay1.setContentsMargins(20, 20, 20, 20)

        warning_lbl = QLabel(
            "⚠️  <b style='color:#f85149;'>清除记忆不可撤销！</b><br>"
            "请选择要清除的范围："
        )
        warning_lbl.setTextFormat(Qt.TextFormat.RichText)
        warning_lbl.setWordWrap(True)
        lay1.addWidget(warning_lbl)

        btn_group = QButtonGroup(dlg1)
        options = [
            ("all",      "🗑  清除全部记忆（包括关联网络）"),
            ("detail",   "清除细节层记忆（保留大纲和细纲）"),
            ("outline",  "清除细纲层记忆"),
            ("summary",  "清除大纲层记忆"),
            ("emotional","清除情感模态记忆"),
            ("semantic", "清除语义模态记忆"),
        ]
        radios = {}
        for val, text in options:
            rb = QRadioButton(text)
            if val == "all":
                rb.setChecked(True)
            btn_group.addButton(rb)
            radios[rb] = val
            lay1.addWidget(rb)

        btns1 = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns1.button(QDialogButtonBox.StandardButton.Ok).setText("下一步 →")
        btns1.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns1.accepted.connect(dlg1.accept)
        btns1.rejected.connect(dlg1.reject)
        lay1.addWidget(btns1)

        if dlg1.exec() != QDialog.DialogCode.Accepted:
            return

        clear_scope = next((v for rb, v in radios.items() if rb.isChecked()), "all")
        scope_label = dict(options)[clear_scope]

        # ── 第2次：输入确认文字 ──────────────────
        from PyQt6.QtWidgets import QInputDialog
        confirm_word = "确认清除"
        text, ok = QInputDialog.getText(
            self,
            "清除记忆 — 第 2/3 步",
            f"即将执行：{scope_label}\n\n"
            f"请在下方输入「{confirm_word}」以继续：",
        )
        if not ok or text.strip() != confirm_word:
            QMessageBox.warning(self, "已取消", "输入不匹配，操作已取消。")
            return

        # ── 第3次：最终确认弹窗 ──────────────────
        final = QMessageBox(self)
        final.setWindowTitle("清除记忆 — 第 3/3 步 · 最终确认")
        final.setIcon(QMessageBox.Icon.Critical)
        final.setText(
            f"<b style='color:#f85149; font-size:14px;'>最后一次确认</b><br><br>"
            f"操作：<b>{scope_label}</b><br><br>"
            "此操作 <b>不可撤销</b>，确定要继续吗？"
        )
        final.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        final.setDefaultButton(QMessageBox.StandardButton.No)
        final.button(QMessageBox.StandardButton.Yes).setText("✅ 确认清除")
        final.button(QMessageBox.StandardButton.No).setText("❌ 取消")
        final.setStyleSheet(
            "QMessageBox{background:#161b22;}"
            "QLabel{color:#e6edf3;font-size:13px;}"
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:6px;padding:6px 20px;color:#e6edf3;min-width:100px;}"
            "QPushButton:hover{border-color:#58a6ff;}"
        )
        if final.exec() != QMessageBox.StandardButton.Yes:
            return

        # ── 执行清除 ─────────────────────────────
        self._do_clear(clear_scope)

    def _do_clear(self, scope: str):
        """实际执行清除操作"""
        from engine.db_guard import guarded_connect
        try:
            with guarded_connect(self.db_file) as conn:
                if scope == "all":
                    conn.execute("DELETE FROM memories")
                    if self._table_exists(conn, "memory_edges"):
                        conn.execute("DELETE FROM memory_edges")
                    if self._table_exists(conn, "memory_entities"):
                        conn.execute("DELETE FROM memory_entities")
                    if self._table_exists(conn, "formed_cognition"):
                        conn.execute("DELETE FROM formed_cognition")
                    # 重置自增序列
                    conn.execute(
                        "DELETE FROM sqlite_sequence WHERE name='memories'"
                    ) if self._table_exists(conn, "sqlite_sequence") else None
                    deleted_msg = "全部记忆及关联网络"
                elif scope in ("detail", "outline", "summary"):
                    count = conn.execute(
                        "SELECT COUNT(*) FROM memories WHERE level=?", (scope,)
                    ).fetchone()[0]
                    conn.execute("DELETE FROM memories WHERE level=?", (scope,))
                    deleted_msg = f"{count} 条{scope}层记忆"
                elif scope in ("emotional", "semantic", "visual",
                               "auditory", "procedural", "autobio"):
                    count = conn.execute(
                        "SELECT COUNT(*) FROM memories WHERE modality=?", (scope,)
                    ).fetchone()[0]
                    conn.execute("DELETE FROM memories WHERE modality=?", (scope,))
                    deleted_msg = f"{count} 条{scope}模态记忆"
                else:
                    deleted_msg = "未知范围"

                conn.commit()

            # 刷新列表
            self.load()
            QMessageBox.information(
                self, "清除完成",
                f"✅ 已清除：{deleted_msg}\n\n记忆库已更新。"
            )
        except Exception as e:
            QMessageBox.critical(self, "清除失败", f"❌ 操作失败：{e}")

    def search(self):
        q = self._search.text().strip()
        if not q:
            self._render(self._all_items)
            return
        # 简单关键词过滤（真实环境用向量搜索）
        filtered = [r for r in self._all_items if q.lower() in r[1].lower()]
        self._render(filtered)

    def _apply_filter(self, flt: str):
        for k, btn in self._filters.items():
            btn.setChecked(k == flt)
        self._current_filter = flt
        if flt == "all":
            self._render(self._all_items)
        else:
            filtered = [r for r in self._all_items
                        if r[2] == flt or r[3] == flt]
            self._render(filtered)

    def _render(self, rows):
        self._list.clear()
        level_color = {"detail": "#3fb950", "outline": "#d29922", "summary": "#58a6ff"}
        for row in rows:
            mid, content, modality, level, em_json, importance, created = row
            try:
                em = json.loads(em_json)
            except Exception:
                em = {}
            color = level_color.get(level, "#8b949e")
            lbl = {"detail":"细节","outline":"细纲","summary":"大纲"}.get(level, level)
            preview = content[:120] + ("…" if len(content) > 120 else "")

            item = QListWidgetItem(
                f"[{lbl}·{modality}]  {preview}\n"
                f"重要性:{int(importance*10)}/10  "
                f"情绪:{em.get('primary','—')}  "
                f"{(created or '')[:16]}"
            )
            item.setForeground(QColor(color))
            # 完整内容放在 tooltip
            item.setToolTip(content)
            item.setData(Qt.ItemDataRole.UserRole, content)
            self._list.addItem(item)

        # 双击显示完整内容
        try:
            self._list.itemDoubleClicked.disconnect()
        except Exception:
            pass
        def _show_full(item):
            full = item.data(Qt.ItemDataRole.UserRole) or item.text()
            dlg = QTextBrowser()
            dlg.setWindowTitle("完整记忆内容")
            dlg.setWindowFlag(Qt.WindowType.Window)
            dlg.setPlainText(full)
            dlg.setMinimumSize(500, 300)
            dlg.setStyleSheet(
                "QTextBrowser{background:#161b22;color:#e6edf3;"
                "font-size:13px;padding:16px;border:none;}"
            )
            dlg.show()
            self._detail_dlg = dlg  # keep ref
        self._list.itemDoubleClicked.connect(_show_full)


# ── 设置页 ────────────────────────────────────────
class LearnerPage(QWidget):
    """
    主动学习页
    - 手动触发 AGI 主动学习（抓新闻/文章）
    - 配置学习主题、学习时间
    - 查看经历认知列表
    - 实时日志
    """
    learn_requested = pyqtSignal(list)  # 发出主题列表

    def __init__(self, db_file: str, parent=None):
        super().__init__(parent)
        self.db_file = db_file
        self._worker  = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部栏
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background:#161b22;border-bottom:1px solid #30363d;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)
        title = QLabel("🎓  主动学习")
        title.setStyleSheet("color:#e6edf3;font-size:15px;font-weight:700;")
        self._status_lbl = QLabel("就绪")
        self._status_lbl.setStyleSheet("color:#8b949e;font-size:12px;")
        h_lay.addWidget(title)
        h_lay.addStretch()
        h_lay.addWidget(self._status_lbl)
        layout.addWidget(header)

        # 主体：上下分割
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setStyleSheet("QSplitter::handle{background:#21262d;height:1px;}")

        # ── 上半：配置 + 经历认知 ──
        top_widget = QWidget()
        top_widget.setStyleSheet("background:#0d1117;")
        top_lay = QHBoxLayout(top_widget)
        top_lay.setContentsMargins(16, 16, 16, 16)
        top_lay.setSpacing(16)

        # 左：学习配置
        config_box = QWidget()
        config_box.setStyleSheet(
            "QWidget{background:#161b22;border:1px solid #30363d;border-radius:10px;}"
        )
        config_box.setFixedWidth(300)
        cl = QVBoxLayout(config_box)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)

        cl.addWidget(_make_label("📚  学习配置", "color:#e6edf3;font-size:13px;font-weight:700;background:transparent;border:none;"))

        cl.addWidget(_make_label("学习主题（每行一个）", "color:#8b949e;font-size:11px;background:transparent;border:none;"))
        self._topics_edit = QTextEdit()
        self._topics_edit.setFixedHeight(100)
        self._topics_edit.setStyleSheet(
            "QTextEdit{background:#0d1117;border:1px solid #30363d;border-radius:6px;"
            "color:#e6edf3;font-size:12px;padding:6px;}"
        )
        self._topics_edit.setPlainText("AI人工智能\n科技新闻\n世界新闻")
        cl.addWidget(self._topics_edit)

        cl.addWidget(_make_label("定时学习（每天几点）", "color:#8b949e;font-size:11px;background:transparent;border:none;"))
        hour_row = QHBoxLayout()
        self._hour_spin = QComboBox()
        self._hour_spin.addItems([f"{h:02d}:00" for h in range(24)])
        self._hour_spin.setCurrentIndex(8)
        self._hour_spin.setStyleSheet(
            "QComboBox{background:#0d1117;border:1px solid #30363d;border-radius:6px;"
            "color:#e6edf3;padding:4px 8px;font-size:12px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#161b22;color:#e6edf3;border:1px solid #30363d;}"
        )
        self._auto_learn_chk = QCheckBox("启用定时学习")
        self._auto_learn_chk.setStyleSheet("color:#c9d1d9;font-size:12px;")
        hour_row.addWidget(self._hour_spin)
        hour_row.addWidget(self._auto_learn_chk)
        cl.addLayout(hour_row)

        cl.addStretch()

        btn_learn = QPushButton("🚀  立即学习")
        btn_learn.setFixedHeight(36)
        btn_learn.setStyleSheet(
            "QPushButton{background:rgba(31,111,235,.2);border:1px solid #1f6feb;"
            "border-radius:8px;color:#58a6ff;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:rgba(31,111,235,.4);}"
            "QPushButton:disabled{opacity:0.4;}"
        )
        btn_learn.clicked.connect(self._start_learning)
        self._btn_learn = btn_learn
        cl.addWidget(btn_learn)

        top_lay.addWidget(config_box)

        # 右：经历认知展示
        cognition_box = QWidget()
        cognition_box.setStyleSheet(
            "QWidget{background:#161b22;border:1px solid #30363d;border-radius:10px;}"
        )
        cog_lay = QVBoxLayout(cognition_box)
        cog_lay.setContentsMargins(16, 14, 16, 14)
        cog_lay.setSpacing(8)

        cog_header = QHBoxLayout()
        cog_header.addWidget(_make_label("🧠  经历认知（不可外部修改）",
            "color:#e6edf3;font-size:13px;font-weight:700;background:transparent;border:none;"))
        self._cog_count = QLabel("0 条")
        self._cog_count.setStyleSheet("color:#8b949e;font-size:11px;")
        cog_header.addStretch()
        cog_header.addWidget(self._cog_count)
        btn_refresh_cog = QPushButton("刷新")
        btn_refresh_cog.setFixedHeight(24)
        btn_refresh_cog.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:4px;color:#8b949e;font-size:11px;padding:0 8px;}"
            "QPushButton:hover{color:#c9d1d9;}"
        )
        btn_refresh_cog.clicked.connect(self._load_cognitions)
        cog_header.addWidget(btn_refresh_cog)
        cog_lay.addLayout(cog_header)

        hint = QLabel("💡 由对话和学习自动形成，只有清除全部记忆才能删除")
        hint.setStyleSheet("color:#6e7681;font-size:11px;font-style:italic;")
        cog_lay.addWidget(hint)

        self._cog_list = QListWidget()
        self._cog_list.setStyleSheet(
            "QListWidget{background:#0d1117;border:1px solid #21262d;"
            "border-radius:6px;outline:none;}"
            "QListWidget::item{color:#c9d1d9;padding:8px 12px;font-size:12px;"
            "border-bottom:1px solid #21262d;}"
            "QListWidget::item:selected{background:#21262d;}"
        )
        cog_lay.addWidget(self._cog_list)
        top_lay.addWidget(cognition_box)

        splitter.addWidget(top_widget)

        # ── 下半：实时日志 ──
        log_widget = QWidget()
        log_widget.setStyleSheet("background:#0d1117;")
        ll = QVBoxLayout(log_widget)
        ll.setContentsMargins(16, 8, 16, 12)
        ll.setSpacing(6)
        log_header = QHBoxLayout()
        log_header.addWidget(_make_label("📋  学习日志", "color:#8b949e;font-size:12px;font-weight:600;"))
        btn_clear_log = QPushButton("清空")
        btn_clear_log.setFixedHeight(22)
        btn_clear_log.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:#6e7681;font-size:11px;}"
            "QPushButton:hover{color:#c9d1d9;}"
        )
        btn_clear_log.clicked.connect(lambda: self._log_view.clear())
        log_header.addStretch()
        log_header.addWidget(btn_clear_log)
        ll.addLayout(log_header)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setStyleSheet(
            "QTextEdit{background:#161b22;border:1px solid #30363d;border-radius:8px;"
            "color:#8b949e;font-family:Consolas,'Courier New',monospace;font-size:11px;padding:8px;}"
        )
        ll.addWidget(self._log_view)
        splitter.addWidget(log_widget)
        splitter.setSizes([320, 200])

        layout.addWidget(splitter)
        self._load_cognitions()

    def _load_cognitions(self):
        try:
            from engine.learner import FormedCognitionStore
            store = FormedCognitionStore(self.db_file)
            items = store.get_all()
            self._cog_count.setText(f"{len(items)} 条")
            self._cog_list.clear()
            SOURCE_ICON = {"conversation": "💬", "learning": "📖", "reflection": "🔍"}
            for it in items:
                icon = SOURCE_ICON.get(it["source"], "·")
                strength_mark = " ★" if it["strength"] >= 1.5 else ""
                text = f"{icon} {it['content']}{strength_mark}"
                item = QListWidgetItem(text)
                item.setToolTip(
                    f"来源：{it['source']}\n触发：{it.get('trigger','')}\n"
                    f"时间：{it['formed_at'][:16]}\n强度：{it['strength']:.1f}"
                )
                self._cog_list.addItem(item)
            if not items:
                self._cog_list.addItem("（暂无，继续对话和学习后会自动形成）")
        except Exception:
            pass

    def _start_learning(self):
        topics_text = self._topics_edit.toPlainText().strip()
        topics = [t.strip() for t in topics_text.splitlines() if t.strip()]
        if not topics:
            return
        self._btn_learn.setEnabled(False)
        self._btn_learn.setText("学习中…")
        self._status_lbl.setText("🔄 学习中…")
        self._log("=" * 40)
        self._log(f"开始学习，主题：{', '.join(topics)}")
        self.learn_requested.emit(topics)

    def _log(self, msg: str):
        self._log_view.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        self._log_view.verticalScrollBar().setValue(
            self._log_view.verticalScrollBar().maximum()
        )

    def on_learn_done(self):
        self._btn_learn.setEnabled(True)
        self._btn_learn.setText("🚀  立即学习")
        self._status_lbl.setText("✅ 学习完成")
        self._load_cognitions()
        QTimer.singleShot(3000, lambda: self._status_lbl.setText("就绪"))

    def on_learn_log(self, msg: str):
        self._log(msg)


class SettingsPage(QWidget):

    settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = load_config()
        self._setup_ui()

    def _setup_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── LLM 配置（多服务商）──
        from engine.llm_client import PROVIDER_INFO
        from engine.i18n import LANGUAGES, set_language, get_language

        api_box = QGroupBox("LLM Configuration")
        api_lay = QGridLayout(api_box)
        COMBO_STYLE = (
            "QComboBox{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;padding:5px 8px;color:#e6edf3;font-size:12px;}"
            "QComboBox QAbstractItemView{background:#21262d;color:#e6edf3;"
            "selection-background-color:#1f6feb;border:1px solid #30363d;}"
        )

        # 语言选择
        api_lay.addWidget(QLabel("Interface Language:"), 0, 0)
        self._lang_combo = QComboBox()
        self._lang_combo.setStyleSheet(COMBO_STYLE)
        for code, name in LANGUAGES.items():
            self._lang_combo.addItem(name, code)
        saved_lang = self._cfg.get("language", "zh")
        for i in range(self._lang_combo.count()):
            if self._lang_combo.itemData(i) == saved_lang:
                self._lang_combo.setCurrentIndex(i); break
        api_lay.addWidget(self._lang_combo, 0, 1)

        # Provider 选择
        api_lay.addWidget(QLabel("LLM Provider:"), 1, 0)
        self._provider = QComboBox()
        self._provider.setStyleSheet(COMBO_STYLE)
        self._provider_keys = list(PROVIDER_INFO.keys())
        for key in self._provider_keys:
            self._provider.addItem(PROVIDER_INFO[key]["name"], key)
        saved_provider = self._cfg.get("api_provider", "deepseek")
        for i in range(self._provider.count()):
            if self._provider.itemData(i) == saved_provider:
                self._provider.setCurrentIndex(i); break
        self._provider.currentIndexChanged.connect(self._on_provider_changed)
        api_lay.addWidget(self._provider, 1, 1)

        # 模型选择
        api_lay.addWidget(QLabel("Model:"), 2, 0)
        self._model_combo = QComboBox()
        self._model_combo.setStyleSheet(COMBO_STYLE)
        self._model_combo.setEditable(True)
        api_lay.addWidget(self._model_combo, 2, 1)

        # API Key
        api_lay.addWidget(QLabel("API Key:"), 3, 0)
        self._api_key = QLineEdit(self._cfg.get("api_key", ""))
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("Enter your API key")
        api_lay.addWidget(self._api_key, 3, 1)

        # 注册链接
        self._api_link_lbl = QLabel("")
        self._api_link_lbl.setOpenExternalLinks(True)
        self._api_link_lbl.setStyleSheet("color:#58a6ff;font-size:11px;")
        api_lay.addWidget(self._api_link_lbl, 4, 1)

        # ── 多模态模型配置（Vision）──
        from engine.vision_client import VISION_PROVIDER_INFO, check_vision_available

        vision_box = QGroupBox("👁️ 多模态模型（Vision）")
        vision_lay = QGridLayout(vision_box)

        # 说明标签
        vision_desc = QLabel(
            "配置独立的多模态模型，用于图片/视频/音频理解分析。\n"
            "与文本 LLM 独立运行，互不影响。留空则自动继承主 LLM 的多模态能力。"
        )
        vision_desc.setStyleSheet("color:#8b949e;font-size:11px;")
        vision_desc.setWordWrap(True)
        vision_lay.addWidget(vision_desc, 0, 0, 1, 2)

        # Vision Provider 选择
        vision_lay.addWidget(QLabel("多模态服务商:"), 1, 0)
        self._vision_provider = QComboBox()
        self._vision_provider.setStyleSheet(COMBO_STYLE)
        # 添加"自动继承"选项
        self._vision_provider.addItem("🔄 自动继承主 LLM", "")
        for key in VISION_PROVIDER_INFO:
            info = VISION_PROVIDER_INFO[key]
            self._vision_provider.addItem(info["name"], key)
        saved_vision_provider = self._cfg.get("vision_provider", "")
        for i in range(self._vision_provider.count()):
            if self._vision_provider.itemData(i) == saved_vision_provider:
                self._vision_provider.setCurrentIndex(i); break
        self._vision_provider.currentIndexChanged.connect(self._on_vision_provider_changed)
        vision_lay.addWidget(self._vision_provider, 1, 1)

        # Vision 模型选择
        vision_lay.addWidget(QLabel("Vision 模型:"), 2, 0)
        self._vision_model = QComboBox()
        self._vision_model.setStyleSheet(COMBO_STYLE)
        self._vision_model.setEditable(True)
        vision_lay.addWidget(self._vision_model, 2, 1)

        # Vision API Key
        vision_lay.addWidget(QLabel("API Key:"), 3, 0)
        self._vision_api_key = QLineEdit(self._cfg.get("vision_api_key", ""))
        self._vision_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._vision_api_key.setPlaceholderText("留空则继承主 LLM 的 API Key")
        vision_lay.addWidget(self._vision_api_key, 3, 1)

        # Vision Base URL（高级设置）
        vision_lay.addWidget(QLabel("自定义地址:"), 4, 0)
        self._vision_base_url = QLineEdit(self._cfg.get("vision_base_url", ""))
        self._vision_base_url.setPlaceholderText("留空使用默认地址")
        vision_lay.addWidget(self._vision_base_url, 4, 1)

        # 支持的模态标签
        self._vision_support_lbl = QLabel("")
        self._vision_support_lbl.setStyleSheet("font-size:11px;color:#8b949e;")
        vision_lay.addWidget(self._vision_support_lbl, 5, 0, 1, 2)

        # Vision 注册链接
        self._vision_link_lbl = QLabel("")
        self._vision_link_lbl.setOpenExternalLinks(True)
        self._vision_link_lbl.setStyleSheet("color:#58a6ff;font-size:11px;")
        vision_lay.addWidget(self._vision_link_lbl, 6, 1)

        # 初始化 vision provider 状态
        self._on_vision_provider_changed(self._vision_provider.currentIndex())

        # Ollama 额外设置（只有选 Ollama 时显示）
        self._ollama_widget = QWidget()
        ol_lay = QGridLayout(self._ollama_widget)
        ol_lay.setContentsMargins(0, 0, 0, 0)
        ol_lay.addWidget(QLabel("Ollama URL:"), 0, 0)
        self._ollama_url = QLineEdit(self._cfg.get("ollama_url", "http://localhost:11434"))
        ol_lay.addWidget(self._ollama_url, 0, 1)
        ol_lay.addWidget(QLabel("Ollama Model:"), 1, 0)
        self._ollama_model = QLineEdit(self._cfg.get("ollama_model", "qwen2.5:7b"))
        self._ollama_model.setPlaceholderText("qwen2.5:7b / llama3.1:8b / ...")
        ol_lay.addWidget(self._ollama_model, 1, 1)
        btn_check_ollama = QPushButton("🔍 Test Ollama")
        btn_check_ollama.setFixedHeight(28)
        btn_check_ollama.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;color:#e6edf3;font-size:12px;}"
            "QPushButton:hover{border-color:#58a6ff;}"
        )
        btn_check_ollama.clicked.connect(self._check_ollama)
        self._ollama_status = QLabel("")
        self._ollama_status.setStyleSheet("font-size:11px;color:#8b949e;")
        ol_row = QHBoxLayout()
        ol_row.addWidget(btn_check_ollama)
        ol_row.addWidget(self._ollama_status)
        ol_row.addStretch()
        ol_lay.addLayout(ol_row, 2, 1)
        api_lay.addWidget(self._ollama_widget, 5, 0, 1, 2)

        self._on_provider_changed(self._provider.currentIndex())

        # 热键配置
        hotkey_box = QGroupBox("全局热键")
        hk_lay = QGridLayout(hotkey_box)

        hk_lay.addWidget(QLabel("唤醒悬浮窗:"), 0, 0)
        self._hk_activate = QLineEdit(
            self._cfg.get("hotkey_activate", "ctrl+shift+space")
        )
        hk_lay.addWidget(self._hk_activate, 0, 1)

        hk_lay.addWidget(QLabel("截图识别:"), 1, 0)
        self._hk_screenshot = QLineEdit(
            self._cfg.get("hotkey_screenshot", "ctrl+shift+s")
        )
        hk_lay.addWidget(self._hk_screenshot, 1, 1)

        # 窗口行为
        win_box = QGroupBox("窗口行为")
        win_lay = QVBoxLayout(win_box)

        self._chk_tray = QCheckBox("关闭窗口时最小化到托盘（不退出）")
        self._chk_tray.setChecked(self._cfg.get("tray_minimize", True))
        win_lay.addWidget(self._chk_tray)

        self._chk_autostart = QCheckBox("开机自启动")
        from desktop.system import AutoStart
        self._chk_autostart.setChecked(AutoStart.is_enabled())
        self._chk_autostart.stateChanged.connect(self._toggle_autostart)
        win_lay.addWidget(self._chk_autostart)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("悬浮窗透明度:"))
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(40, 100)
        self._opacity_slider.setValue(int(self._cfg.get("float_opacity", 0.95) * 100))
        self._opacity_lbl = QLabel(f"{self._opacity_slider.value()}%")
        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_lbl.setText(f"{v}%")
        )
        opacity_row.addWidget(self._opacity_slider)
        opacity_row.addWidget(self._opacity_lbl)
        win_lay.addLayout(opacity_row)

        # OCR
        ocr_box = QGroupBox("OCR 设置")
        ocr_lay = QGridLayout(ocr_box)
        ocr_lay.addWidget(QLabel("识别语言:"), 0, 0)
        self._ocr_lang = QLineEdit(self._cfg.get("ocr_language", "chi_sim+eng"))
        ocr_lay.addWidget(self._ocr_lang, 0, 1)
        ocr_lay.addWidget(QLabel(
            "Tesseract 语言代码，如 chi_sim+eng\n"
            "需要安装：https://github.com/tesseract-ocr/tesseract"
        ), 1, 1)

        # 保存按钮
        btn_save = QPushButton("💾  保存设置")
        btn_save.setObjectName("btn_primary")
        btn_save.setFixedHeight(40)
        btn_save.clicked.connect(self._save)

        self._save_msg = QLabel("")
        self._save_msg.setStyleSheet("color:#3fb950;font-size:12px;")

        # 语音合成（TTS）
        tts_box = QGroupBox("🔊 语音合成（TTS）")
        tts_lay = QGridLayout(tts_box)

        tts_lay.addWidget(QLabel("启用语音："), 0, 0)
        self._tts_enable = QCheckBox("回复完成后自动朗读")
        self._tts_enable.setChecked(self._cfg.get("tts_enabled", False))
        tts_lay.addWidget(self._tts_enable, 0, 1)

        tts_lay.addWidget(QLabel("声音选择："), 1, 0)
        self._tts_voice = QComboBox()
        from engine.tts_engine import VOICE_OPTIONS
        for vid, vname in VOICE_OPTIONS:
            self._tts_voice.addItem(vname, vid)
        saved_voice = self._cfg.get("tts_voice", "zh-CN-XiaoxiaoNeural")
        for i in range(self._tts_voice.count()):
            if self._tts_voice.itemData(i) == saved_voice:
                self._tts_voice.setCurrentIndex(i)
                break
        self._tts_voice.setStyleSheet(
            "QComboBox{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;padding:5px 8px;color:#e6edf3;}"
            "QComboBox QAbstractItemView{background:#21262d;color:#e6edf3;"
            "selection-background-color:#1f6feb;}"
        )
        tts_lay.addWidget(self._tts_voice, 1, 1)

        tts_lay.addWidget(QLabel("语速调节："), 2, 0)
        rate_row = QHBoxLayout()
        self._tts_rate = QSlider(Qt.Orientation.Horizontal)
        self._tts_rate.setRange(-50, 50)
        self._tts_rate.setValue(self._cfg.get("tts_rate", 0))
        self._tts_rate_lbl = QLabel(f"{self._tts_rate.value():+d}%")
        self._tts_rate.valueChanged.connect(
            lambda v: self._tts_rate_lbl.setText(f"{v:+d}%")
        )
        rate_row.addWidget(self._tts_rate)
        rate_row.addWidget(self._tts_rate_lbl)
        tts_lay.addLayout(rate_row, 2, 1)

        # 检测 edge-tts 是否安装
        try:
            import edge_tts
            tts_status = "✅ edge-tts 已安装（高质量）"
            tts_status_color = "#3fb950"
        except ImportError:
            tts_status = "⚠️ 未安装 edge-tts，运行：pip install edge-tts"
            tts_status_color = "#d29922"
        tts_status_lbl = QLabel(tts_status)
        tts_status_lbl.setStyleSheet(f"color:{tts_status_color};font-size:11px;")
        tts_lay.addWidget(tts_status_lbl, 3, 1)

        # 新闻 API（NewsAPI）
        news_box = QGroupBox("📰 新闻 API（NewsAPI）")
        news_lay = QGridLayout(news_box)

        news_lay.addWidget(QLabel("API Key:"), 0, 0)
        self._newsapi_key = QLineEdit(self._cfg.get("newsapi_key", ""))
        self._newsapi_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._newsapi_key.setPlaceholderText("来自 newsapi.org 的 API Key")
        news_lay.addWidget(self._newsapi_key, 0, 1)

        # 检测 newsapi-python 是否安装
        try:
            import newsapi
            news_status = "✅ newsapi-python 已安装"
            news_status_color = "#3fb950"
        except ImportError:
            news_status = "⚠️ 未安装，运行 install_newsapi.bat"
            news_status_color = "#d29922"
        news_status_lbl = QLabel(news_status)
        news_status_lbl.setStyleSheet(f"color:{news_status_color};font-size:11px;")
        news_lay.addWidget(news_status_lbl, 1, 1)

        news_link = QLabel('<a href="https://newsapi.org/register" style="color:#58a6ff;">免费申请 NewsAPI Key →</a>')
        news_link.setOpenExternalLinks(True)
        news_link.setStyleSheet("font-size:11px;")
        news_lay.addWidget(news_link, 2, 1)

        layout.addWidget(api_box)
        layout.addWidget(vision_box)
        layout.addWidget(hotkey_box)
        layout.addWidget(win_box)
        layout.addWidget(tts_box)
        layout.addWidget(news_box)
        layout.addWidget(ocr_box)
        layout.addWidget(btn_save)
        layout.addWidget(self._save_msg)
        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _on_provider_changed(self, idx: int):
        from engine.llm_client import PROVIDER_INFO
        key = self._provider.itemData(idx) or "deepseek"
        info = PROVIDER_INFO.get(key, {})
        is_ollama = key == "ollama"

        # 更新模型列表
        self._model_combo.clear()
        for m in info.get("models", []):
            self._model_combo.addItem(m)
        saved_model = self._cfg.get("llm_model") or info.get("default_model", "")
        self._model_combo.setCurrentText(saved_model)

        # 更新注册链接
        url = info.get("url", "")
        name = info.get("name", "")
        if url:
            self._api_link_lbl.setText(
                f'Get API key: <a href="{url}" style="color:#58a6ff;">{url}</a>'
            )
        else:
            self._api_link_lbl.setText("")

        # Ollama 额外设置显示/隐藏
        self._ollama_widget.setVisible(is_ollama)
        self._api_key.setEnabled(not is_ollama)
        self._api_key.setPlaceholderText("" if is_ollama else "Enter your API key")

    def _on_vision_provider_changed(self, idx: int):
        from engine.vision_client import VISION_PROVIDER_INFO
        key = self._vision_provider.itemData(idx) or ""

        # 更新模型列表
        self._vision_model.clear()
        if key and key in VISION_PROVIDER_INFO:
            info = VISION_PROVIDER_INFO[key]
            for m in info.get("models", []):
                self._vision_model.addItem(m)
            saved_vision_model = self._cfg.get("vision_model") or info.get("default_model", "")
            self._vision_model.setCurrentText(saved_vision_model)

            # 显示支持的模态
            supports = info.get("supports", [])
            support_icons = {"image": "🖼️ 图片", "video": "🎬 视频", "audio_note": "📝 视频帧", "audio": "🎵 音频"}
            support_text = "支持: " + " | ".join(
                support_icons.get(s, s) for s in supports
            )
            self._vision_support_lbl.setText(support_text)

            # 注册链接
            url = info.get("url", "")
            if url:
                self._vision_link_lbl.setText(
                    f'注册地址: <a href="{url}" style="color:#58a6ff;">{url}</a>'
                )
            else:
                self._vision_link_lbl.setText("")

            # Ollama 不需要 API Key
            self._vision_api_key.setEnabled(key != "ollama")
            self._vision_api_key.setPlaceholderText(
                "Ollama 本地运行，无需 API Key" if key == "ollama"
                else "留空则继承主 LLM 的 API Key"
            )
        else:
            # 自动继承模式
            self._vision_support_lbl.setText("将自动使用主 LLM 的多模态能力")
            self._vision_link_lbl.setText("")
            self._vision_api_key.setEnabled(False)
            self._vision_api_key.setPlaceholderText("自动继承，无需单独配置")

    def _check_ollama(self):
        from engine.llm_client import OllamaClient
        url = self._ollama_url.text().strip() or "http://localhost:11434"
        client = OllamaClient(base_url=url)
        if client.is_running():
            models = client.list_models()
            # 更新模型下拉
            self._ollama_model.setText(models[0] if models else "qwen2.5:7b")
            self._ollama_status.setText(
                f"✅ Connected  |  Models: {', '.join(models[:4]) or 'none'}"
            )
            self._ollama_status.setStyleSheet("font-size:11px;color:#3fb950;")
        else:
            self._ollama_status.setText("❌ Not running. Run: ollama serve")
            self._ollama_status.setStyleSheet("font-size:11px;color:#f85149;")

    def _toggle_autostart(self, state):
        from desktop.system import AutoStart
        if state == Qt.CheckState.Checked.value:
            AutoStart.enable()
        else:
            AutoStart.disable()

    def _save(self):
        provider_key = self._provider.currentData() or "deepseek"
        lang_key     = self._lang_combo.currentData() or "zh"

        self._cfg["api_provider"]      = provider_key
        self._cfg["language"]          = lang_key
        self._cfg["api_key"]           = self._api_key.text().strip()
        self._cfg["llm_model"]         = self._model_combo.currentText().strip()
        self._cfg["ollama_url"]        = self._ollama_url.text().strip()
        self._cfg["ollama_model"]      = self._ollama_model.text().strip()
        self._cfg["hotkey_activate"]   = self._hk_activate.text().strip()
        self._cfg["hotkey_screenshot"] = self._hk_screenshot.text().strip()
        self._cfg["tray_minimize"]     = self._chk_tray.isChecked()
        self._cfg["float_opacity"]     = self._opacity_slider.value() / 100.0
        self._cfg["tts_enabled"]       = self._tts_enable.isChecked()
        self._cfg["tts_voice"]         = self._tts_voice.currentData()
        self._cfg["tts_rate"]          = self._tts_rate.value()
        self._cfg["ocr_language"]      = self._ocr_lang.text().strip()
        self._cfg["newsapi_key"]       = self._newsapi_key.text().strip()
        # 多模态 Vision 配置
        self._cfg["vision_provider"]   = self._vision_provider.currentData() or ""
        self._cfg["vision_model"]      = self._vision_model.currentText().strip()
        self._cfg["vision_api_key"]    = self._vision_api_key.text().strip()
        self._cfg["vision_base_url"]   = self._vision_base_url.text().strip()

        # 立即应用语言
        try:
            from engine.i18n import set_language
            set_language(lang_key)
        except Exception:
            pass

        save_config(self._cfg)
        self.settings_changed.emit(self._cfg)
        self._save_msg.setText("✅ Saved. Restart to apply.")
        QTimer.singleShot(3000, lambda: self._save_msg.setText(""))


# ── 工具测试页 ────────────────────────────────────
class ToolTestPage(QWidget):
    """
    工具测试台
    左：工具列表 + 参数填写
    右：执行结果（原始 JSON + 格式化展示）
    历史记录可回溯
    """

    RISK_COLOR = {"low": "#3fb950", "medium": "#d29922", "high": "#f85149"}
    RISK_LABEL = {"low": "🟢 安全", "medium": "🟡 中等风险", "high": "🔴 高危"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tools      = {}   # name -> info
        self._current    = None # 当前选中工具名
        self._param_widgets = {}  # param_name -> QLineEdit/QTextEdit
        self._history    = []   # 执行历史
        self._setup_ui()
        self._load_tools()

    # ────────────────── UI 构建 ──────────────────
    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 左侧：工具列表 ───────────────────────
        left = QWidget()
        left.setFixedWidth(240)
        left.setStyleSheet(
            "background:#161b22;border-right:1px solid #30363d;"
        )
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        # 左侧标题
        left_header = QLabel("  🔧  选择工具")
        left_header.setFixedHeight(42)
        left_header.setStyleSheet(
            "background:#1c2128;color:#58a6ff;font-weight:700;"
            "font-size:13px;border-bottom:1px solid #30363d;padding-left:8px;"
        )

        # 分类过滤
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(8, 6, 8, 4)
        self._risk_filter = QComboBox()
        self._risk_filter.addItems(["全部风险", "🟢 安全", "🟡 中等", "🔴 高危"])
        self._risk_filter.setStyleSheet(
            "QComboBox{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;padding:4px 8px;color:#e6edf3;font-size:11px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#21262d;color:#e6edf3;"
            "selection-background-color:#1f6feb;}"
        )
        self._risk_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._risk_filter)

        # 搜索
        self._tool_search = QLineEdit()
        self._tool_search.setPlaceholderText("搜索…")
        self._tool_search.setStyleSheet(
            "QLineEdit{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;padding:4px 8px;color:#e6edf3;font-size:11px;}"
            "QLineEdit:focus{border-color:#58a6ff;}"
        )
        self._tool_search.textChanged.connect(self._apply_filter)

        # 工具列表
        self._tool_list = QListWidget()
        self._tool_list.setStyleSheet(
            "QListWidget{background:transparent;border:none;outline:none;}"
            "QListWidget::item{padding:10px 12px;border-bottom:1px solid #21262d;"
            "color:#e6edf3;font-size:12px;}"
            "QListWidget::item:selected{background:#1f3a5c;color:#58a6ff;}"
            "QListWidget::item:hover{background:#21262d;}"
        )
        self._tool_list.currentItemChanged.connect(self._on_tool_selected)

        # 历史记录按钮 + 自检按钮
        bottom_row = QHBoxLayout()
        btn_history = QPushButton("📋  历史")
        btn_history.setFixedHeight(34)
        btn_history.setStyleSheet(
            "QPushButton{background:#1c2128;border:none;color:#8b949e;"
            "font-size:12px;border-top:1px solid #30363d;}"
            "QPushButton:hover{color:#58a6ff;}"
        )
        btn_history.clicked.connect(self._show_history)

        btn_self_test = QPushButton("🔬  自检")
        btn_self_test.setFixedHeight(34)
        btn_self_test.setStyleSheet(
            "QPushButton{background:#1c2128;border:none;color:#8b949e;"
            "font-size:12px;border-top:1px solid #30363d;"
            "border-left:1px solid #30363d;}"
            "QPushButton:hover{color:#3fb950;}"
        )
        btn_self_test.clicked.connect(self.run_self_test)
        bottom_row.addWidget(btn_history)
        bottom_row.addWidget(btn_self_test)
        bottom_row.setSpacing(0)
        bottom_row.setContentsMargins(0, 0, 0, 0)

        left_lay.addWidget(left_header)
        left_lay.addLayout(filter_row)
        left_lay.addWidget(self._tool_search)
        left_lay.addWidget(self._tool_list, stretch=1)
        left_lay.addLayout(bottom_row)

        # ── 中间：参数填写 + 执行 ────────────────
        mid = QWidget()
        mid.setMinimumWidth(340)
        mid.setStyleSheet("background:#0d1117;")
        mid_lay = QVBoxLayout(mid)
        mid_lay.setContentsMargins(16, 12, 16, 12)
        mid_lay.setSpacing(10)

        # 工具标题
        self._tool_title = QLabel("← 请先选择一个工具")
        self._tool_title.setStyleSheet(
            "color:#58a6ff;font-size:15px;font-weight:700;"
        )
        self._tool_desc = QLabel("")
        self._tool_desc.setWordWrap(True)
        self._tool_desc.setStyleSheet(
            "color:#8b949e;font-size:12px;line-height:1.5;"
        )
        self._risk_badge = QLabel("")
        self._risk_badge.setStyleSheet("font-size:12px;")

        # 参数区（动态生成）
        params_scroll = QScrollArea()
        params_scroll.setWidgetResizable(True)
        params_scroll.setStyleSheet(
            "QScrollArea{border:1px solid #30363d;border-radius:8px;"
            "background:#161b22;}"
        )
        self._params_container = QWidget()
        self._params_container.setStyleSheet("background:#161b22;")
        self._params_layout = QVBoxLayout(self._params_container)
        self._params_layout.setContentsMargins(12, 10, 12, 10)
        self._params_layout.setSpacing(8)
        self._params_layout.addStretch()
        params_scroll.setWidget(self._params_container)

        # 执行按钮区
        exec_row = QHBoxLayout()
        self._btn_run = QPushButton("▶  执行工具")
        self._btn_run.setFixedHeight(40)
        self._btn_run.setEnabled(False)
        self._btn_run.setObjectName("btn_primary")
        self._btn_run.setStyleSheet(
            "QPushButton#btn_primary{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1f6feb,stop:1 #7c3aed);"
            "border:none;border-radius:8px;color:white;"
            "font-size:13px;font-weight:700;}"
            "QPushButton#btn_primary:disabled{"
            "background:#21262d;color:#8b949e;}"
        )
        self._btn_run.clicked.connect(self._run_tool)

        self._btn_clear = QPushButton("清空参数")
        self._btn_clear.setFixedHeight(40)
        self._btn_clear.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:8px;color:#8b949e;font-size:12px;}"
            "QPushButton:hover{border-color:#58a6ff;color:#e6edf3;}"
        )
        self._btn_clear.clicked.connect(self._clear_params)

        exec_row.addWidget(self._btn_run, stretch=2)
        exec_row.addWidget(self._btn_clear, stretch=1)

        mid_lay.addWidget(self._tool_title)
        mid_lay.addWidget(self._risk_badge)
        mid_lay.addWidget(self._tool_desc)
        mid_lay.addWidget(_make_label("参数：", "color:#8b949e;font-size:11px;margin-top:4px;"))
        mid_lay.addWidget(params_scroll, stretch=1)
        mid_lay.addLayout(exec_row)

        # ── 右侧：执行结果 ───────────────────────
        right = QWidget()
        right.setStyleSheet("background:#0d1117;")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 12, 16, 12)
        right_lay.setSpacing(8)

        result_header = QHBoxLayout()
        result_lbl = QLabel("执行结果")
        result_lbl.setStyleSheet(
            "color:#e6edf3;font-size:13px;font-weight:700;"
        )
        self._result_status = QLabel("")
        self._result_status.setStyleSheet("font-size:12px;")

        self._btn_copy = QPushButton("复制结果")
        self._btn_copy.setFixedHeight(28)
        self._btn_copy.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;color:#8b949e;font-size:11px;padding:0 10px;}"
            "QPushButton:hover{border-color:#58a6ff;color:#e6edf3;}"
        )
        self._btn_copy.clicked.connect(self._copy_result)

        self._btn_send_to_chat = QPushButton("发送到对话")
        self._btn_send_to_chat.setFixedHeight(28)
        self._btn_send_to_chat.setStyleSheet(
            "QPushButton{background:rgba(31,111,235,.15);border:1px solid #1f6feb;"
            "border-radius:5px;color:#58a6ff;font-size:11px;padding:0 10px;}"
            "QPushButton:hover{background:rgba(31,111,235,.3);}"
        )
        self._btn_send_to_chat.clicked.connect(self._send_result_to_chat)
        self._result_to_send = ""

        result_header.addWidget(result_lbl)
        result_header.addWidget(self._result_status)
        result_header.addStretch()
        result_header.addWidget(self._btn_copy)
        result_header.addWidget(self._btn_send_to_chat)

        # 结果展示（Tab：格式化 / 原始 JSON）
        self._result_tabs = QTabWidget()
        self._result_tabs.setStyleSheet(
            "QTabWidget::pane{border:1px solid #30363d;border-radius:6px;}"
            "QTabBar::tab{background:#161b22;border:1px solid #30363d;"
            "padding:5px 14px;margin-right:2px;border-radius:4px 4px 0 0;"
            "font-size:11px;color:#8b949e;}"
            "QTabBar::tab:selected{background:#21262d;color:#58a6ff;"
            "border-bottom-color:#21262d;}"
        )

        # 格式化视图
        self._result_formatted = QTextEdit()
        self._result_formatted.setReadOnly(True)
        self._result_formatted.setStyleSheet(
            "QTextEdit{background:#161b22;border:none;color:#e6edf3;"
            "font-size:13px;padding:12px;line-height:1.6;}"
        )

        # 原始 JSON 视图
        self._result_raw = QTextEdit()
        self._result_raw.setReadOnly(True)
        self._result_raw.setStyleSheet(
            "QTextEdit{background:#0d1117;border:none;"
            "color:#3fb950;font-family:Consolas,'Courier New',monospace;"
            "font-size:12px;padding:12px;}"
        )

        self._result_tabs.addTab(self._result_formatted, "📄 格式化")
        self._result_tabs.addTab(self._result_raw,       "{ } 原始 JSON")

        right_lay.addLayout(result_header)
        right_lay.addWidget(self._result_tabs, stretch=1)

        # ── 拼合三列 ─────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            "QSplitter::handle{background:#30363d;width:1px;}"
        )
        splitter.addWidget(left)
        splitter.addWidget(mid)
        splitter.addWidget(right)
        splitter.setSizes([240, 360, 480])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        root.addWidget(splitter)

    # ────────────────── 工具加载 ──────────────────
    def _load_tools(self):
        try:
            from engine.tools import TOOL_REGISTRY
            self._tools = {
                name: {
                    "desc":     info["schema"]["description"],
                    "risk":     info["risk"],
                    "params":   info["schema"]["input_schema"].get("properties", {}),
                    "required": info["schema"]["input_schema"].get("required", []),
                }
                for name, info in TOOL_REGISTRY.items()
            }
        except Exception as e:
            self._tools = {}
        self._apply_filter()

    def _apply_filter(self):
        risk_idx  = self._risk_filter.currentIndex()  # 0=all,1=low,2=med,3=high
        risk_map  = {1: "low", 2: "medium", 3: "high"}
        risk_filter = risk_map.get(risk_idx)
        search    = self._tool_search.text().lower()

        self._tool_list.clear()
        for name, info in self._tools.items():
            if risk_filter and info["risk"] != risk_filter:
                continue
            if search and search not in name.lower() and search not in info["desc"].lower():
                continue
            risk_icon = {"low":"🟢","medium":"🟡","high":"🔴"}.get(info["risk"],"⚪")
            item = QListWidgetItem(f"{risk_icon}  {name}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self._tool_list.addItem(item)

    # ────────────────── 工具选中 ──────────────────
    def _on_tool_selected(self, current, previous):
        if not current:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        if not name or name not in self._tools:
            return
        self._current = name
        info = self._tools[name]

        # 更新标题
        self._tool_title.setText(f"🔧  {name}")
        self._tool_desc.setText(info["desc"])
        self._risk_badge.setText(
            self.RISK_LABEL.get(info["risk"], info["risk"])
        )
        risk_color = self.RISK_COLOR.get(info["risk"], "#8b949e")
        self._risk_badge.setStyleSheet(
            f"color:{risk_color};font-size:12px;"
        )

        # 动态生成参数输入框
        self._build_param_widgets(info["params"], info["required"])
        self._btn_run.setEnabled(True)

        # 清空结果
        self._result_formatted.clear()
        self._result_raw.clear()
        self._result_status.setText("")

    def _build_param_widgets(self, params: dict, required: list):
        """动态生成参数输入区"""
        # 清除旧控件
        while self._params_layout.count() > 1:
            item = self._params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._param_widgets.clear()

        if not params:
            lbl = QLabel("该工具无需参数，直接点击执行")
            lbl.setStyleSheet("color:#8b949e;font-size:12px;")
            self._params_layout.insertWidget(0, lbl)
            return

        for i, (pname, pinfo) in enumerate(params.items()):
            is_req = pname in required
            pdesc  = pinfo.get("description", "")
            ptype  = pinfo.get("type", "string")

            # 标签行
            lbl_row = QHBoxLayout()
            name_lbl = QLabel(pname)
            name_lbl.setStyleSheet(
                "color:#e6edf3;font-size:12px;font-weight:600;"
            )
            req_lbl = QLabel("必填" if is_req else "选填")
            req_lbl.setStyleSheet(
                f"color:{'#f85149' if is_req else '#8b949e'};"
                "font-size:10px;"
                f"{'border:1px solid #f85149;' if is_req else ''}"
                "border-radius:3px;padding:0 4px;"
            )
            type_lbl = QLabel(ptype)
            type_lbl.setStyleSheet(
                "color:#58a6ff;font-size:10px;"
                "border:1px solid #1f6feb;border-radius:3px;padding:0 4px;"
            )
            lbl_row.addWidget(name_lbl)
            lbl_row.addWidget(req_lbl)
            lbl_row.addWidget(type_lbl)
            lbl_row.addStretch()

            # 描述
            desc_lbl = QLabel(pdesc)
            desc_lbl.setStyleSheet(
                "color:#8b949e;font-size:11px;margin-bottom:3px;"
            )
            desc_lbl.setWordWrap(True)

            # 输入控件：长文本用 QTextEdit，其他用 QLineEdit
            if ptype == "boolean":
                widget = QComboBox()
                widget.addItems(["false", "true"])
                widget.setStyleSheet(
                    "QComboBox{background:#21262d;border:1px solid #30363d;"
                    "border-radius:5px;padding:5px 8px;color:#e6edf3;font-size:12px;}"
                    "QComboBox QAbstractItemView{background:#21262d;color:#e6edf3;"
                    "selection-background-color:#1f6feb;}"
                )
            elif pname in ("content", "code", "text") or ptype in ("object", "array"):
                widget = QTextEdit()
                widget.setFixedHeight(90)
                widget.setPlaceholderText(f"输入 {pname}…")
                widget.setStyleSheet(
                    "QTextEdit{background:#21262d;border:1px solid #30363d;"
                    "border-radius:5px;padding:6px;color:#e6edf3;font-size:12px;"
                    "font-family:Consolas,'Courier New',monospace;}"
                    "QTextEdit:focus{border-color:#58a6ff;}"
                )
            else:
                widget = QLineEdit()
                widget.setFixedHeight(34)
                widget.setPlaceholderText(f"输入 {pname}…")
                widget.setStyleSheet(
                    "QLineEdit{background:#21262d;border:1px solid #30363d;"
                    "border-radius:5px;padding:5px 8px;color:#e6edf3;font-size:12px;}"
                    "QLineEdit:focus{border-color:#58a6ff;}"
                )

            self._param_widgets[pname] = widget

            container = QWidget()
            container.setStyleSheet(
                "QWidget{background:#1c2128;border-radius:6px;padding:2px;}"
            )
            clay = QVBoxLayout(container)
            clay.setContentsMargins(10, 8, 10, 8)
            clay.setSpacing(3)
            clay.addLayout(lbl_row)
            clay.addWidget(desc_lbl)
            clay.addWidget(widget)

            self._params_layout.insertWidget(i, container)

    # ────────────────── 工具执行 ──────────────────
    def _run_tool(self):
        if not self._current:
            return

        info = self._tools.get(self._current, {})
        risk = info.get("risk", "low")

        # 高危操作二次确认
        if risk == "high":
            box = QMessageBox(self)
            box.setWindowTitle("⚠️ 高危操作确认")
            box.setText(
                f"<b>工具 {self._current}</b> 是高危操作（风险等级：🔴 高危）<br><br>"
                "此操作可能修改/删除文件或执行系统命令，<b>不可撤销</b>。<br>"
                "确认要直接执行吗？"
            )
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
            )
            box.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return

        # 收集参数
        params = {}
        for pname, widget in self._param_widgets.items():
            if isinstance(widget, QTextEdit):
                val = widget.toPlainText().strip()
            elif isinstance(widget, QComboBox):
                val = widget.currentText() == "true"
            else:
                val = widget.text().strip()
            if val != "" and val != False:
                params[pname] = val

        # 检查必填
        required = info.get("required", [])
        missing = [r for r in required if not params.get(r)]
        if missing:
            self._show_result(
                {"ok": False, "error": f"缺少必填参数：{', '.join(missing)}"},
                success=False
            )
            return

        # 执行
        self._btn_run.setText("⏳ 执行中…")
        self._btn_run.setEnabled(False)
        self._result_status.setText("执行中…")
        self._result_status.setStyleSheet("color:#d29922;font-size:12px;")
        QApplication.processEvents()

        try:
            from engine.tools import execute_tool
            result = execute_tool(self._current, params)
            success = result.get("ok", True)
            self._show_result(result, success=success)

            # 记录历史
            self._history.append({
                "tool":    self._current,
                "params":  params,
                "result":  result,
                "success": success
            })
            if len(self._history) > 50:
                self._history = self._history[-50:]

        except Exception as e:
            self._show_result({"ok": False, "error": str(e)}, success=False)
        finally:
            self._btn_run.setText("▶  执行工具")
            self._btn_run.setEnabled(True)

    def _show_result(self, result: dict, success: bool = True):
        """展示执行结果"""
        # 状态标签
        if success:
            self._result_status.setText("✅ 执行成功")
            self._result_status.setStyleSheet("color:#3fb950;font-size:12px;")
        else:
            self._result_status.setText("❌ 执行失败")
            self._result_status.setStyleSheet("color:#f85149;font-size:12px;")

        # 原始 JSON
        raw_json = json.dumps(result, ensure_ascii=False, indent=2)
        self._result_raw.setPlainText(raw_json)
        self._result_to_send = raw_json

        # 格式化视图
        formatted = self._format_result(result)
        self._result_formatted.setHtml(formatted)

        # 切到格式化 tab
        self._result_tabs.setCurrentIndex(0)

    def _format_result(self, result: dict) -> str:
        """把结果转成可读 HTML"""
        if not result.get("ok", True):
            err = result.get("error", "未知错误")
            return (
                f"<div style='color:#f85149;font-size:13px;padding:8px;'>"
                f"<b>❌ 错误</b><br><br>{err}</div>"
            )

        lines = ["<div style='padding:8px;font-size:13px;line-height:1.8;'>"]
        lines.append("<span style='color:#3fb950;font-weight:700;'>✅ 执行成功</span><br><br>")

        for key, val in result.items():
            if key == "ok":
                continue
            key_html = f"<span style='color:#58a6ff;font-weight:600;'>{key}</span>"
            if isinstance(val, str) and len(val) > 200:
                # 长文本展示
                lines.append(
                    f"{key_html}：<br>"
                    f"<pre style='background:#161b22;padding:10px;border-radius:6px;"
                    f"white-space:pre-wrap;color:#e6edf3;font-size:12px;"
                    f"font-family:Consolas,monospace;max-height:300px;overflow-y:auto;'>"
                    f"{val[:3000]}{'...(截断)' if len(val)>3000 else ''}</pre>"
                )
            elif isinstance(val, list):
                lines.append(f"{key_html}（{len(val)} 项）：<br>")
                for item in val[:20]:
                    if isinstance(item, dict):
                        name = item.get("name", item.get("file", str(item)))
                        ftype = item.get("type","")
                        size = f"  {item.get('size','')}B" if item.get("size") else ""
                        icon = "📁" if ftype == "dir" else "📄"
                        lines.append(
                            f"&nbsp;&nbsp;{icon} "
                            f"<span style='color:#e6edf3;'>{name}</span>"
                            f"<span style='color:#8b949e;font-size:11px;'>"
                            f"  {item.get('modified','')}{size}</span><br>"
                        )
                    else:
                        lines.append(
                            f"&nbsp;&nbsp;<span style='color:#e6edf3;'>{item}</span><br>"
                        )
                if len(val) > 20:
                    lines.append(
                        f"<span style='color:#8b949e;font-size:11px;'>"
                        f"  … 共 {len(val)} 项</span><br>"
                    )
            elif isinstance(val, dict):
                lines.append(f"{key_html}：<br>")
                for k2, v2 in val.items():
                    lines.append(
                        f"&nbsp;&nbsp;<span style='color:#8b949e;'>{k2}</span>: "
                        f"<span style='color:#e6edf3;'>{v2}</span><br>"
                    )
            else:
                lines.append(f"{key_html}：<span style='color:#e6edf3;'>{val}</span><br>")

        lines.append("</div>")
        return "".join(lines)

    # ────────────────── 辅助功能 ──────────────────
    def _clear_params(self):
        for w in self._param_widgets.values():
            if isinstance(w, QTextEdit):
                w.clear()
            elif isinstance(w, QLineEdit):
                w.clear()
            elif isinstance(w, QComboBox):
                w.setCurrentIndex(0)

    def _copy_result(self):
        QApplication.clipboard().setText(self._result_to_send)
        orig = self._btn_copy.text()
        self._btn_copy.setText("✅ 已复制")
        QTimer.singleShot(1500, lambda: self._btn_copy.setText(orig))

    def _send_result_to_chat(self):
        """把结果发送到对话页输入框（由主窗口中转）"""
        self.parent_ref and self.parent_ref.chat_page.fill_input(
            f"工具 {self._current} 的执行结果：\n{self._result_to_send[:500]}"
        )

    def set_parent_ref(self, main_win):
        self.parent_ref = main_win

    def _show_history(self):
        if not self._history:
            QMessageBox.information(self, "执行历史", "暂无执行记录")
            return
        lines = []
        for i, h in enumerate(reversed(self._history[-20:]), 1):
            ok = "✅" if h["success"] else "❌"
            lines.append(
                f"{ok} #{i}  {h['tool']}\n"
                f"   参数: {json.dumps(h['params'], ensure_ascii=False)[:80]}\n"
            )
        QMessageBox.information(self, f"执行历史（共{len(self._history)}条）",
                                "\n".join(lines))

    def run_self_test(self):
        """一键自检：测试所有安全工具 + 检测依赖"""
        from engine.tools import self_test, check_all_deps
        self._result_status.setText("🔄 自检中…")
        self._result_status.setStyleSheet("color:#d29922;font-size:12px;")
        QApplication.processEvents()

        results  = self_test()
        dep_results = check_all_deps()

        # 收集缺失依赖的安装命令
        all_missing_cmds = []
        for dep in dep_results.values():
            if not dep["ok"]:
                all_missing_cmds.extend(dep["install"])
        # 去重
        all_missing_cmds = list(dict.fromkeys(all_missing_cmds))

        # 整理 HTML 报告
        lines_fmt = ["<div style='padding:8px;font-size:13px;line-height:1.9;'>"]
        lines_fmt.append("<b style='color:#58a6ff;'>🔬 工具自检报告</b><br><br>")

        pass_n = sum(1 for r in results if r["status"] == "pass")
        fail_n = sum(1 for r in results if r["status"] == "fail")
        skip_n = sum(1 for r in results if r["status"] == "skipped")

        lines_fmt.append(
            f"<b>安全工具测试：</b> ✅ {pass_n} 通过  "
            f"{'❌ '+str(fail_n)+' 失败  ' if fail_n else ''}"
            f"⏭ {skip_n} 跳过<br><br>"
        )
        for r in results:
            icon  = {"pass":"✅","fail":"❌","skipped":"⏭","error":"💥"}.get(r["status"],"❓")
            color = {"pass":"#3fb950","fail":"#f85149",
                     "skipped":"#8b949e","error":"#f85149"}.get(r["status"],"#e6edf3")
            err_hint = ""
            if r["status"] in ("fail","error"):
                err_text = (r.get("result",{}).get("error","") or r.get("error",""))[:120]
                err_hint = f"<br><span style='color:#8b949e;font-size:11px;font-family:monospace;'>&nbsp;&nbsp;原因: {err_hint}{err_text}</span>"
            lines_fmt.append(
                f"<span style='color:{color};'>{icon} {r['tool']}</span>"
                f"<span style='color:#8b949e;font-size:11px;'> {r.get('reason','')}</span>"
                f"{err_hint}<br>"
            )

        # 依赖检查
        lines_fmt.append("<br><b style='color:#58a6ff;'>📦 依赖检查</b><br>")
        for tool_name, dep in dep_results.items():
            if dep["ok"]:
                lines_fmt.append(
                    f"✅ <span style='color:#3fb950;'>{tool_name}</span>"
                    f"<span style='color:#8b949e;font-size:11px;'>  依赖已安装</span><br>"
                )
            else:
                cmds = " && ".join(dep["install"])
                lines_fmt.append(
                    f"⚠️ <span style='color:#d29922;'>{tool_name}</span>"
                    f"<span style='color:#8b949e;font-size:11px;'>"
                    f"  缺少: {', '.join(dep['missing'])}</span><br>"
                    f"<span style='color:#8b949e;font-size:11px;font-family:monospace;'>"
                    f"  安装: {cmds}</span><br>"
                )

        if all_missing_cmds:
            lines_fmt.append(
                "<br><span style='color:#d29922;'>⚠️ 有缺失依赖，"
                "点击右上角「安装缺失依赖」按钮一键安装</span><br>"
            )

        lines_fmt.append("</div>")

        self._result_formatted.setHtml("".join(lines_fmt))
        self._result_raw.setPlainText(
            json.dumps({"tests": results, "deps": dep_results},
                       ensure_ascii=False, indent=2)
        )
        self._result_tabs.setCurrentIndex(0)

        # 如果有缺失依赖，显示安装按钮
        if all_missing_cmds:
            self._btn_install = QPushButton(
                f"📦  安装缺失依赖 ({len(all_missing_cmds)} 条命令)"
            )
            self._btn_install.setFixedHeight(36)
            self._btn_install.setStyleSheet(
                "QPushButton{background:rgba(210,153,34,.2);border:1px solid #d29922;"
                "border-radius:6px;color:#d29922;font-size:12px;font-weight:600;}"
                "QPushButton:hover{background:rgba(210,153,34,.4);}"
            )
            self._btn_install.clicked.connect(
                lambda: self._install_deps(all_missing_cmds)
            )
            # 插入到结果 tab 上方
            parent_lay = self._result_tabs.parent().layout()
            if parent_lay:
                idx = parent_lay.indexOf(self._result_tabs)
                parent_lay.insertWidget(idx, self._btn_install)

        status = f"{'✅' if fail_n==0 else '⚠️'} 自检完成 ({pass_n}通过/{fail_n}失败/{skip_n}跳过)"
        self._result_status.setText(status)
        self._result_status.setStyleSheet(
            f"color:{'#3fb950' if fail_n==0 else '#d29922'};font-size:12px;"
        )

    def _install_deps(self, cmds: list):
        """在终端执行安装命令"""
        import subprocess
        from engine.tools import execute_tool

        self._btn_install.setText("⏳ 安装中…")
        self._btn_install.setEnabled(False)
        QApplication.processEvents()

        results = []
        for cmd in cmds:
            r = execute_tool("run_command", {"command": cmd, "timeout": 120})
            results.append({"cmd": cmd, "ok": r.get("ok"), "out": r.get("stdout","")[:200]})

        all_ok = all(r["ok"] for r in results)
        msg = "\n".join(
            f"{'✅' if r['ok'] else '❌'} {r['cmd']}\n   {r['out']}"
            for r in results
        )
        QMessageBox.information(
            self,
            "安装完成" if all_ok else "部分安装失败",
            f"{'✅ 全部安装成功！' if all_ok else '⚠️ 部分失败，请手动检查'}\n\n{msg[:1000]}"
        )

        if all_ok:
            self._btn_install.setText("✅ 已安装")
        else:
            self._btn_install.setText("⚠️ 部分失败，点击重试")
            self._btn_install.setEnabled(True)

        # 重新自检
        self.run_self_test()


# ── 编程智能体页 ─────────────────────────────────
class CoderWorker(QThread):
    """后台运行编程智能体，实时推送日志"""
    log     = pyqtSignal(str, str)    # (message, level)
    done    = pyqtSignal(object)      # CodingSession
    error   = pyqtSignal(str)

    def __init__(self, agent_llm, task: str, language: str, save_to: str):
        super().__init__()
        self.agent_llm = agent_llm
        self.task      = task
        self.language  = language
        self.save_to   = save_to

    def run(self):
        try:
            from engine.coder import CodingAgent
            coder = CodingAgent(
                llm_client=self.agent_llm,
                on_progress=lambda msg, level="info": self.log.emit(msg, level)
            )
            session = coder.run(self.task, self.language, self.save_to)
            self.done.emit(session)
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")


class CoderPage(QWidget):
    """
    自主编程智能体界面
    输入任务 → 实时看日志 → 自动打包保存
    """

    LOG_COLORS = {
        "start":   "#58a6ff",
        "iter":    "#d29922",
        "write":   "#79c0ff",
        "fix":     "#ffa657",
        "run":     "#56d364",
        "stdout":  "#8b949e",
        "stderr":  "#f85149",
        "analyse": "#bc8cff",
        "pass":    "#3fb950",
        "warn":    "#d29922",
        "done":    "#3fb950",
        "error":   "#f85149",
        "info":    "#8b949e",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker  = None
        self._agent_llm = None
        self._setup_ui()

    def set_llm(self, llm_client):
        self._agent_llm = llm_client

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶部工具栏 ──────────────────────────
        toolbar = QWidget()
        toolbar.setFixedHeight(56)
        toolbar.setStyleSheet(
            "background:#161b22;border-bottom:1px solid #30363d;"
        )
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(16, 8, 16, 8)

        title = QLabel("💻  编程智能体")
        title.setStyleSheet(
            "color:#58a6ff;font-size:14px;font-weight:700;"
        )

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["python", "javascript", "html", "bash"])
        self._lang_combo.setFixedWidth(120)
        self._lang_combo.setStyleSheet(
            "QComboBox{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;padding:4px 8px;color:#e6edf3;font-size:12px;}"
            "QComboBox QAbstractItemView{background:#21262d;color:#e6edf3;"
            "selection-background-color:#1f6feb;}"
        )

        save_lbl = QLabel("保存到:")
        save_lbl.setStyleSheet("color:#8b949e;font-size:12px;")
        self._save_path = QLineEdit()
        self._save_path.setPlaceholderText("默认保存到桌面")
        self._save_path.setFixedWidth(200)
        self._save_path.setStyleSheet(
            "QLineEdit{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;padding:4px 8px;color:#e6edf3;font-size:12px;}"
        )
        btn_browse = QPushButton("📁")
        btn_browse.setFixedSize(28, 28)
        btn_browse.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;color:#8b949e;}"
            "QPushButton:hover{border-color:#58a6ff;color:#e6edf3;}"
        )
        btn_browse.clicked.connect(self._browse_save)

        tb_lay.addWidget(title)
        tb_lay.addStretch()
        tb_lay.addWidget(_make_label("语言:", "color:#8b949e;font-size:12px;"))
        tb_lay.addWidget(self._lang_combo)
        tb_lay.addSpacing(12)
        tb_lay.addWidget(save_lbl)
        tb_lay.addWidget(self._save_path)
        tb_lay.addWidget(btn_browse)

        # ── 任务输入区 ─────────────────────────
        task_widget = QWidget()
        task_widget.setStyleSheet("background:#0d1117;")
        task_widget.setFixedHeight(110)
        task_lay = QVBoxLayout(task_widget)
        task_lay.setContentsMargins(16, 10, 16, 10)
        task_lay.setSpacing(8)

        task_header = QHBoxLayout()
        task_lbl = QLabel("📋  任务描述")
        task_lbl.setStyleSheet(
            "color:#e6edf3;font-size:13px;font-weight:600;"
        )

        self._btn_run = QPushButton("▶  开始编程")
        self._btn_run.setFixedSize(120, 34)
        self._btn_run.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1f6feb,stop:1 #7c3aed);"
            "border:none;border-radius:7px;color:white;"
            "font-size:13px;font-weight:700;}"
            "QPushButton:disabled{background:#21262d;color:#8b949e;}"
        )
        self._btn_run.clicked.connect(self._start)

        self._btn_stop = QPushButton("⏹  停止")
        self._btn_stop.setFixedSize(80, 34)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:7px;color:#8b949e;font-size:12px;}"
            "QPushButton:enabled{border-color:#f85149;color:#f85149;}"
            "QPushButton:enabled:hover{background:rgba(248,81,73,.15);}"
        )
        self._btn_stop.clicked.connect(self._stop)

        task_header.addWidget(task_lbl)
        task_header.addStretch()
        task_header.addWidget(self._btn_stop)
        task_header.addWidget(self._btn_run)

        self._task_input = QLineEdit()
        self._task_input.setPlaceholderText(
            "例：写一个贪吃蛇游戏  /  写一个计算器  /  写一个文件批量重命名工具"
        )
        self._task_input.setStyleSheet(
            "QLineEdit{background:#21262d;border:1px solid #30363d;"
            "border-radius:8px;padding:8px 12px;color:#e6edf3;font-size:13px;}"
            "QLineEdit:focus{border-color:#58a6ff;}"
        )
        self._task_input.returnPressed.connect(self._start)

        task_lay.addLayout(task_header)
        task_lay.addWidget(self._task_input)

        # ── 主体：日志 + 代码预览 ─────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            "QSplitter::handle{background:#30363d;width:1px;}"
        )

        # 左：执行日志
        log_widget = QWidget()
        log_widget.setStyleSheet("background:#0d1117;")
        log_lay = QVBoxLayout(log_widget)
        log_lay.setContentsMargins(12, 10, 6, 12)
        log_lay.setSpacing(6)

        log_header = QHBoxLayout()
        log_header.addWidget(_make_label("执行日志", "color:#e6edf3;font-size:13px;font-weight:600;"))
        log_header.addStretch()
        btn_clear_log = QPushButton("清空")
        btn_clear_log.setFixedHeight(24)
        btn_clear_log.setStyleSheet(
            "QPushButton{background:transparent;border:none;"
            "color:#8b949e;font-size:11px;}"
            "QPushButton:hover{color:#e6edf3;}"
        )
        btn_clear_log.clicked.connect(lambda: self._log_view.clear())
        log_header.addWidget(btn_clear_log)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setStyleSheet(
            "QTextEdit{background:#0d1117;border:1px solid #30363d;"
            "border-radius:6px;color:#e6edf3;"
            "font-family:Consolas,'Courier New',monospace;font-size:12px;"
            "padding:8px;}"
        )

        # 状态栏
        self._status_lbl = QLabel("就绪")
        self._status_lbl.setStyleSheet(
            "color:#8b949e;font-size:11px;padding-top:4px;"
        )

        log_lay.addLayout(log_header)
        log_lay.addWidget(self._log_view)
        log_lay.addWidget(self._status_lbl)

        # 右：代码预览 + 操作
        code_widget = QWidget()
        code_widget.setStyleSheet("background:#0d1117;")
        code_lay = QVBoxLayout(code_widget)
        code_lay.setContentsMargins(6, 10, 12, 12)
        code_lay.setSpacing(6)

        code_header = QHBoxLayout()
        code_header.addWidget(_make_label("代码预览", "color:#e6edf3;font-size:13px;font-weight:600;"))
        code_header.addStretch()

        self._file_combo = QComboBox()
        self._file_combo.setFixedWidth(160)
        self._file_combo.setStyleSheet(
            "QComboBox{background:#21262d;border:1px solid #30363d;"
            "border-radius:5px;padding:3px 6px;color:#e6edf3;font-size:11px;}"
            "QComboBox QAbstractItemView{background:#21262d;color:#e6edf3;"
            "selection-background-color:#1f6feb;}"
        )
        self._file_combo.currentTextChanged.connect(self._switch_file)
        code_header.addWidget(self._file_combo)

        self._code_view = QTextEdit()
        self._code_view.setReadOnly(True)
        self._code_view.setStyleSheet(
            "QTextEdit{background:#161b22;border:1px solid #30363d;"
            "border-radius:6px;color:#e6edf3;"
            "font-family:Consolas,'Courier New',monospace;font-size:12px;"
            "padding:10px;}"
        )

        # 操作按钮行
        action_row = QHBoxLayout()
        self._btn_open_folder = QPushButton("📂  打开输出目录")
        self._btn_open_folder.setEnabled(False)
        self._btn_open_folder.setFixedHeight(34)
        self._btn_open_folder.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:6px;color:#8b949e;font-size:12px;}"
            "QPushButton:enabled{color:#e6edf3;border-color:#30363d;}"
            "QPushButton:enabled:hover{border-color:#58a6ff;}"
        )
        self._btn_open_folder.clicked.connect(self._open_output)

        self._btn_run_preview = QPushButton("▶  直接运行")
        self._btn_run_preview.setEnabled(False)
        self._btn_run_preview.setFixedHeight(34)
        self._btn_run_preview.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:6px;color:#8b949e;font-size:12px;}"
            "QPushButton:enabled{background:rgba(31,111,235,.2);"
            "color:#58a6ff;border-color:#1f6feb;}"
            "QPushButton:enabled:hover{background:rgba(31,111,235,.35);}"
        )
        self._btn_run_preview.clicked.connect(self._run_preview)

        self._iter_lbl = QLabel("")
        self._iter_lbl.setStyleSheet("color:#8b949e;font-size:11px;")

        action_row.addWidget(self._btn_open_folder)
        action_row.addWidget(self._btn_run_preview)
        action_row.addStretch()
        action_row.addWidget(self._iter_lbl)

        code_lay.addLayout(code_header)
        code_lay.addWidget(self._code_view)
        code_lay.addLayout(action_row)

        splitter.addWidget(log_widget)
        splitter.addWidget(code_widget)
        splitter.setSizes([480, 520])

        # 预设任务快捷按钮
        preset_bar = QWidget()
        preset_bar.setStyleSheet(
            "background:#161b22;border-top:1px solid #30363d;"
        )
        preset_lay = QHBoxLayout(preset_bar)
        preset_lay.setContentsMargins(16, 6, 16, 6)
        preset_lay.addWidget(_make_label("快速任务：", "color:#8b949e;font-size:11px;"))
        presets = [
            ("🐍 贪吃蛇",     "python", "写一个贪吃蛇游戏，用tkinter实现，有分数显示"),
            ("🧮 计算器",     "python", "写一个图形界面计算器，支持加减乘除和括号"),
            ("📝 记事本",     "python", "写一个简单记事本应用，可以打开保存文件"),
            ("⏰ 番茄钟",     "python", "写一个番茄工作法计时器，25分钟工作5分钟休息"),
            ("🎮 扫雷",       "python", "写一个扫雷游戏，10x10方格，随机30个地雷"),
            ("📊 CSV查看器",  "python", "写一个CSV文件查看器，可以打开文件并表格展示"),
        ]
        for label, lang, task in presets:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setStyleSheet(
                "QPushButton{background:#21262d;border:1px solid #30363d;"
                "border-radius:12px;color:#8b949e;font-size:11px;padding:0 10px;}"
                "QPushButton:hover{border-color:#58a6ff;color:#e6edf3;}"
            )
            btn.clicked.connect(
                lambda checked, l=lang, t=task: self._set_preset(l, t)
            )
            preset_lay.addWidget(btn)
        preset_lay.addStretch()

        # 组装
        layout.addWidget(toolbar)
        layout.addWidget(task_widget)
        layout.addWidget(splitter, stretch=1)
        layout.addWidget(preset_bar)

        # 内部状态
        self._current_session = None
        self._output_path = ""
        self._current_files = {}

    # ── 操作方法 ────────────────────────────────
    def _set_preset(self, lang: str, task: str):
        idx = self._lang_combo.findText(lang)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        self._task_input.setText(task)
        self._task_input.setFocus()

    def _browse_save(self):
        from PyQt6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if d:
            self._save_path.setText(d)

    def _start(self):
        task = self._task_input.text().strip()
        if not task:
            self._task_input.setFocus()
            return
        if not self._agent_llm:
            self._log_msg("❌ LLM 未初始化，请先配置 API Key 或 Ollama", "error")
            return
        if self._worker and self._worker.isRunning():
            return

        lang    = self._lang_combo.currentText()
        save_to = self._save_path.text().strip() or str(_get_desktop())

        self._log_view.clear()
        self._code_view.clear()
        self._file_combo.clear()
        self._current_files = {}
        self._btn_run.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._btn_open_folder.setEnabled(False)
        self._btn_run_preview.setEnabled(False)
        self._iter_lbl.setText("")
        self._status_lbl.setText("🔄 运行中…")

        self._worker = CoderWorker(self._agent_llm, task, lang, save_to)
        self._worker.log.connect(self._log_msg)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._log_msg("⏹  已中止", "warn")
            self._reset_buttons()

    def _log_msg(self, msg: str, level: str = "info"):
        color = self.LOG_COLORS.get(level, "#e6edf3")
        timestamp = datetime.now().strftime("%H:%M:%S")

        # 代码块特殊处理
        if level in ("stdout", "stderr") and "\n" in msg:
            bg = "#1c1c1c" if level == "stderr" else "#0d1117"
            html = (
                f"<div style='margin:2px 0;'>"
                f"<span style='color:#8b949e;font-size:10px;'>{timestamp}</span> "
                f"<pre style='background:{bg};color:{color};padding:6px 8px;"
                f"border-radius:4px;margin:2px 0;font-size:11px;"
                f"white-space:pre-wrap;'>{msg}</pre></div>"
            )
        else:
            html = (
                f"<div style='margin:1px 0;'>"
                f"<span style='color:#8b949e;font-size:10px;'>{timestamp}</span> "
                f"<span style='color:{color};font-size:12px;'>{msg}</span></div>"
            )

        self._log_view.append(html)
        self._log_view.verticalScrollBar().setValue(
            self._log_view.verticalScrollBar().maximum()
        )

    def _on_done(self, session):
        self._current_session = session
        self._output_path = session.output_dir

        iters = len(session.iterations)
        status_text = (
            f"✅ 完成！共 {iters} 轮迭代"
            if session.status == "passed"
            else f"⚠️ 达到最大迭代（{iters}轮），使用最后版本"
        )
        self._status_lbl.setText(status_text)
        self._iter_lbl.setText(f"{iters} 轮迭代")

        # 填入代码预览
        self._current_files = {
            k: v for k, v in session.final_code.items()
            if not k.startswith("__")
        }
        self._file_combo.clear()
        for fname in self._current_files:
            self._file_combo.addItem(fname)
        if self._current_files:
            first = list(self._current_files.keys())[0]
            self._code_view.setPlainText(self._current_files[first])

        self._btn_open_folder.setEnabled(bool(self._output_path))
        self._btn_run_preview.setEnabled(bool(self._current_files))
        self._reset_buttons()

        # 成功提示
        if session.status == "passed" and self._output_path:
            self._log_msg(
                f"📦 项目已打包：{self._output_path}", "done"
            )

    def _on_error(self, err: str):
        self._log_msg(f"❌ 智能体异常：{err[:200]}", "error")
        self._status_lbl.setText("❌ 发生错误")
        self._reset_buttons()

    def _reset_buttons(self):
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)

    def _switch_file(self, fname: str):
        if fname and fname in self._current_files:
            self._code_view.setPlainText(self._current_files[fname])

    def _open_output(self):
        if not self._output_path:
            return
        p = Path(self._output_path)
        target = str(p.parent) if p.is_file() else str(p)
        import subprocess, sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", target])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])

    def _run_preview(self):
        """直接运行当前代码（不打包，快速预览）"""
        if not self._current_files:
            return
        import tempfile, subprocess
        tmp = tempfile.mkdtemp(prefix="agi_preview_")
        for fname, content in self._current_files.items():
            (Path(tmp) / fname).write_text(content, encoding="utf-8")
        main_file = list(self._current_files.keys())[0]
        lang = self._lang_combo.currentText()

        self._log_msg(f"▶️  直接运行 {main_file}…", "run")
        if lang == "python":
            subprocess.Popen(["python", main_file], cwd=tmp)
        elif lang == "javascript":
            subprocess.Popen(["node", main_file], cwd=tmp)
        elif lang == "html":
            import webbrowser
            webbrowser.open(str(Path(tmp) / main_file))


# ── 人脸识别页 ────────────────────────────────────
class FaceWorker(QThread):
    """后台执行人脸操作（注册/识别），避免卡界面"""
    result = pyqtSignal(dict)
    error  = pyqtSignal(str)

    def __init__(self, task: str, db_file: str, image_data=None,
                 user_id: str = "", label: str = ""):
        super().__init__()
        self.task       = task        # "register" | "identify" | "capture"
        self.db_file    = db_file
        self.image_data = image_data  # numpy RGB 数组
        self.user_id    = user_id
        self.label      = label

    def run(self):
        try:
            from engine.face_recognition_engine import FaceDatabase, CameraThread
            db = FaceDatabase(self.db_file)

            if self.task == "capture":
                cam = CameraThread()
                frame = cam.get_frame_rgb()
                if frame is None:
                    self.error.emit("无法打开摄像头。请检查：1) 摄像头未被其他程序占用 2) 已授予摄像头权限 3) 重启应用后重试")
                    return
                self.result.emit({"ok": True, "frame": frame})

            elif self.task == "register":
                if self.image_data is None:
                    self.error.emit("没有图片数据")
                    return
                res = db.register(self.user_id, self.image_data,
                                  label=self.label)
                self.result.emit(res)

            elif self.task == "identify":
                if self.image_data is None:
                    self.error.emit("没有图片数据")
                    return
                res = db.identify(self.image_data)
                self.result.emit(res)

            elif self.task == "list":
                users = db.list_users()
                self.result.emit({"ok": True, "users": users})

        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()[:300]}")


class UserProfilePage(QWidget):
    """
    用户画像页
    - 显示已确认 / 初步观察的性格特征及置信度
    - 反常行为记录
    - 刷新按钮（画像由后台随对话自动更新）
    """

    def __init__(self, db_file: str, auth_ref=None, parent=None):
        super().__init__(parent)
        self.db_file = db_file
        self._auth_ref = auth_ref   # callable，返回 AuthManager 或 None
        self._mgr    = None   # UserProfileManager，延迟初始化
        self._setup_ui()

    def _get_mgr(self):
        if self._mgr is None:
            from engine.user_profile import UserProfileManager
            self._mgr = UserProfileManager(self.db_file)
        # 动态同步 user_id 与当前认证状态（Agent 写入时也用同样的逻辑）
        if self._auth_ref:
            auth = self._auth_ref()
            if auth and auth.is_verified():
                self._mgr.user_id = auth.user_id
            else:
                self._mgr.user_id = "default"
        return self._mgr

    # ── UI ─────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部栏
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background:#161b22;border-bottom:1px solid #30363d;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)
        title = QLabel("👤  用户画像")
        title.setStyleSheet("color:#e6edf3;font-size:15px;font-weight:700;")
        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet("color:#8b949e;font-size:12px;")
        btn_refresh = QPushButton("🔄  刷新")
        btn_refresh.setFixedHeight(30)
        btn_refresh.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:6px;color:#c9d1d9;font-size:12px;padding:0 14px;}"
            "QPushButton:hover{border-color:#58a6ff;color:#58a6ff;}"
        )
        btn_refresh.clicked.connect(self.load)
        h_lay.addWidget(title)
        h_lay.addStretch()
        h_lay.addWidget(self._stats_lbl)
        h_lay.addSpacing(12)
        h_lay.addWidget(btn_refresh)
        layout.addWidget(header)

        # 主体：左侧特征列表 + 右侧详情
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle{background:#30363d;width:1px;}")

        # ── 左栏：分类导航 ──
        left = QWidget()
        left.setFixedWidth(180)
        left.setStyleSheet("background:#161b22;border-right:1px solid #30363d;")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 8, 0, 0)
        ll.setSpacing(0)
        cat_label = QLabel("  分类")
        cat_label.setStyleSheet(
            "color:#8b949e;font-size:11px;font-weight:600;"
            "text-transform:uppercase;letter-spacing:1px;padding:4px 0;"
        )
        ll.addWidget(cat_label)
        self._cat_list = QListWidget()
        self._cat_list.setStyleSheet(
            "QListWidget{background:transparent;border:none;outline:none;}"
            "QListWidget::item{color:#c9d1d9;padding:8px 16px;font-size:13px;"
            "border-radius:6px;margin:1px 4px;}"
            "QListWidget::item:selected{background:#21262d;color:#58a6ff;}"
            "QListWidget::item:hover{background:#21262d;}"
        )
        self._cat_list.currentRowChanged.connect(self._on_cat_changed)
        ll.addWidget(self._cat_list)
        ll.addStretch()
        splitter.addWidget(left)

        # ── 右栏：特征卡片区 ──
        right = QWidget()
        right.setStyleSheet("background:#0d1117;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(12)

        # 已确认区
        confirmed_title = QLabel("✅  已确认特征")
        confirmed_title.setStyleSheet(
            "color:#3fb950;font-size:13px;font-weight:700;"
        )
        rl.addWidget(confirmed_title)

        self._confirmed_area = QWidget()
        self._confirmed_layout = QVBoxLayout(self._confirmed_area)
        self._confirmed_layout.setContentsMargins(0, 0, 0, 0)
        self._confirmed_layout.setSpacing(6)
        rl.addWidget(self._confirmed_area)

        # 初步观察区
        emerging_title = QLabel("🔍  初步观察（待确认）")
        emerging_title.setStyleSheet(
            "color:#d29922;font-size:13px;font-weight:700;margin-top:8px;"
        )
        rl.addWidget(emerging_title)

        self._emerging_area = QWidget()
        self._emerging_layout = QVBoxLayout(self._emerging_area)
        self._emerging_layout.setContentsMargins(0, 0, 0, 0)
        self._emerging_layout.setSpacing(6)
        rl.addWidget(self._emerging_area)

        # 反常记录区
        anomaly_title = QLabel("⚠️  近期反常行为")
        anomaly_title.setStyleSheet(
            "color:#f85149;font-size:13px;font-weight:700;margin-top:8px;"
        )
        rl.addWidget(anomaly_title)

        self._anomaly_area = QWidget()
        self._anomaly_layout = QVBoxLayout(self._anomaly_area)
        self._anomaly_layout.setContentsMargins(0, 0, 0, 0)
        self._anomaly_layout.setSpacing(6)
        rl.addWidget(self._anomaly_area)

        rl.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(right)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:#0d1117;}"
            "QScrollBar:vertical{background:#161b22;width:8px;border-radius:4px;}"
            "QScrollBar::handle:vertical{background:#30363d;border-radius:4px;}"
        )
        splitter.addWidget(scroll)
        splitter.setSizes([180, 600])

        layout.addWidget(splitter)
        self._setup_guest_section(layout)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _make_trait_card(self, trait, confirmed: bool) -> QWidget:
        """创建单个特征卡片（含进度条）"""

        card = QWidget()
        card.setStyleSheet(
            "QWidget{background:#161b22;border:1px solid #30363d;"
            "border-radius:8px;padding:2px;}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)

        # 顶行：名称 + 观察次数
        top = QHBoxLayout()
        name_lbl = QLabel(trait.name)
        name_lbl.setStyleSheet(
            "color:#e6edf3;font-size:13px;font-weight:600;"
            "background:transparent;border:none;"
        )
        cat_badge = QLabel(trait.category)
        cat_badge.setStyleSheet(
            "color:#8b949e;font-size:11px;background:#21262d;"
            "border:1px solid #30363d;border-radius:4px;padding:1px 6px;"
        )
        count_lbl = QLabel(f"观察 {trait.evidence_count} 次")
        count_lbl.setStyleSheet(
            "color:#8b949e;font-size:11px;background:transparent;border:none;"
        )
        top.addWidget(name_lbl)
        top.addWidget(cat_badge)
        top.addStretch()
        top.addWidget(count_lbl)
        cl.addLayout(top)

        # 置信度进度条
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(trait.confidence * 100))
        bar.setFixedHeight(6)
        bar.setTextVisible(False)
        color = "#3fb950" if confirmed else "#d29922"
        bar.setStyleSheet(
            f"QProgressBar{{background:#21262d;border-radius:3px;border:none;}}"
            f"QProgressBar::chunk{{background:{color};border-radius:3px;}}"
        )
        cl.addWidget(bar)

        # 置信度数值 + 最近见到时间
        bottom = QHBoxLayout()
        conf_lbl = QLabel(f"置信度 {trait.confidence:.0%}")
        conf_lbl.setStyleSheet(
            f"color:{color};font-size:11px;background:transparent;border:none;"
        )
        date_str = trait.last_seen[:10] if trait.last_seen else ""
        date_lbl = QLabel(f"最近：{date_str}")
        date_lbl.setStyleSheet(
            "color:#8b949e;font-size:11px;background:transparent;border:none;"
        )
        bottom.addWidget(conf_lbl)
        bottom.addStretch()
        bottom.addWidget(date_lbl)
        cl.addLayout(bottom)

        # 例子（如果有）
        if trait.examples:
            ex_lbl = QLabel(f"「{trait.examples[-1][:60]}」")
            ex_lbl.setStyleSheet(
                "color:#8b949e;font-size:11px;font-style:italic;"
                "background:transparent;border:none;"
            )
            ex_lbl.setWordWrap(True)
            cl.addWidget(ex_lbl)

        return card

    def _make_anomaly_card(self, anomaly) -> QWidget:
        card = QWidget()
        card.setStyleSheet(
            "QWidget{background:rgba(248,81,73,.08);border:1px solid rgba(248,81,73,.3);"
            "border-radius:8px;}"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(4)
        desc = QLabel(anomaly.description)
        desc.setStyleSheet(
            "color:#f85149;font-size:13px;font-weight:600;"
            "background:transparent;border:none;"
        )
        desc.setWordWrap(True)
        normal = QLabel(f"正常模式：{anomaly.normal_pattern}")
        normal.setStyleSheet(
            "color:#8b949e;font-size:11px;background:transparent;border:none;"
        )
        normal.setWordWrap(True)
        time_lbl = QLabel(anomaly.timestamp[:16])
        time_lbl.setStyleSheet(
            "color:#6e7681;font-size:11px;background:transparent;border:none;"
        )
        cl.addWidget(desc)
        cl.addWidget(normal)
        cl.addWidget(time_lbl)
        return card

    # ── 数据加载 ────────────────────────────────
    def load(self):
        try:
            mgr = self._get_mgr()
            traits   = mgr.get_traits()
            anomalies = mgr.get_recent_anomalies(limit=5)

            confirmed = [t for t in traits if t.evidence_count >= mgr.CONFIRMED_THRESHOLD]
            emerging  = [t for t in traits if t.evidence_count <  mgr.CONFIRMED_THRESHOLD]

            # 更新统计
            self._stats_lbl.setText(
                f"已确认 {len(confirmed)} 项  ·  观察中 {len(emerging)} 项"
            )

            # 更新分类列表
            cats = sorted(set(t.category for t in traits))
            self._cat_list.clear()
            self._cat_list.addItem("全部")
            for c in cats:
                self._cat_list.addItem(c)

            # 已确认区
            self._clear_layout(self._confirmed_layout)
            if confirmed:
                for t in confirmed:
                    self._confirmed_layout.addWidget(self._make_trait_card(t, True))
            else:
                lbl = QLabel("暂无已确认特征，继续与 AGI 对话后会自动积累。")
                lbl.setStyleSheet("color:#8b949e;font-size:12px;")
                self._confirmed_layout.addWidget(lbl)

            # 初步观察区
            self._clear_layout(self._emerging_layout)
            if emerging:
                for t in emerging:
                    self._emerging_layout.addWidget(self._make_trait_card(t, False))
            else:
                lbl = QLabel("暂无初步观察。")
                lbl.setStyleSheet("color:#8b949e;font-size:12px;")
                self._emerging_layout.addWidget(lbl)

            # 反常记录区
            self._clear_layout(self._anomaly_layout)
            if anomalies:
                for a in anomalies:
                    self._anomaly_layout.addWidget(self._make_anomaly_card(a))
            else:
                lbl = QLabel("暂无反常行为记录。")
                lbl.setStyleSheet("color:#8b949e;font-size:12px;")
                self._anomaly_layout.addWidget(lbl)

        except Exception as e:
            pass  # 数据库未建立时静默忽略

    def _on_cat_changed(self, row):
        pass

    def _setup_guest_section(self, layout):
        """访客记录区块（折叠式，加在页面底部）"""
        self._guest_section = QWidget()
        self._guest_section.setStyleSheet("background:#0d1117;")
        gl = QVBoxLayout(self._guest_section)
        gl.setContentsMargins(20, 8, 20, 16)
        gl.setSpacing(8)

        guest_header = QHBoxLayout()
        self._guest_title = QLabel("🕵️  访客记录  ▶")
        self._guest_title.setStyleSheet(
            "color:#d29922;font-size:13px;font-weight:700;"
        )
        self._guest_title.mousePressEvent = lambda e: self._toggle_guest_panel()
        btn_clear_guest = QPushButton("清空记录")
        btn_clear_guest.setFixedHeight(24)
        btn_clear_guest.setStyleSheet(
            "QPushButton{background:transparent;border:none;"
            "color:#6e7681;font-size:11px;}"
            "QPushButton:hover{color:#f85149;}"
        )
        btn_clear_guest.clicked.connect(self._clear_guest_sessions)
        guest_header.addWidget(self._guest_title)
        guest_header.addStretch()
        guest_header.addWidget(btn_clear_guest)
        gl.addLayout(guest_header)

        self._guest_panel = QWidget()
        self._guest_panel.setVisible(False)
        gpl = QVBoxLayout(self._guest_panel)
        gpl.setContentsMargins(0, 0, 0, 0)
        gpl.setSpacing(6)

        self._guest_list = QTextEdit()
        self._guest_list.setReadOnly(True)
        self._guest_list.setFixedHeight(180)
        self._guest_list.setStyleSheet(
            "QTextEdit{background:#161b22;border:1px solid #30363d;"
            "border-radius:8px;color:#c9d1d9;font-size:11px;"
            "font-family:Consolas,monospace;padding:8px;}"
        )
        gpl.addWidget(self._guest_list)
        gl.addWidget(self._guest_panel)
        layout.addWidget(self._guest_section)

    def _toggle_guest_panel(self):
        visible = self._guest_panel.isVisible()
        self._guest_panel.setVisible(not visible)
        self._guest_title.setText(
            "🕵️  访客记录  ▼" if not visible else "🕵️  访客记录  ▶"
        )
        if not visible:
            self._load_guest_sessions()

    def _load_guest_sessions(self):
        try:
            from engine.auth import AuthManager
            auth     = AuthManager(self.db_file)
            sessions = auth.get_guest_sessions(limit=10)
            if not sessions:
                self._guest_list.setPlainText("暂无访客记录")
                return
            lines = []
            for s in sessions:
                time_str = s["started_at"][:16]
                end_str  = s["ended_at"][:16] if s["ended_at"] else "进行中"
                photo    = "📷 有照片" if s["has_photo"] else "无照片"
                lines.append(f"{'='*40}")
                lines.append(f"🕐 {time_str} ~ {end_str}  {photo}  共{s['msg_count']}条对话")
                for msg in s["messages"][:5]:
                    lines.append(f"  [{msg['time']}] 用户: {msg['user'][:50]}")
                if s["msg_count"] > 5:
                    lines.append(f"  ... 还有 {s['msg_count']-5} 条")
            self._guest_list.setPlainText("\n".join(lines))
        except Exception as e:
            self._guest_list.setPlainText(f"加载失败: {e}")

    def _clear_guest_sessions(self):
        try:
            from engine.auth import AuthManager
            AuthManager(self.db_file).clear_guest_sessions()
            self._guest_list.setPlainText("已清空")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
class MemoryGraphPage(QWidget):
    """
    记忆关联网络可视化页
    - 从 SQLite 读取 memories + memory_edges
    - 生成 vis.js 网络图 HTML，写入临时文件
    - 用 QTextBrowser 预览 SVG 摘要，提供「在浏览器中打开」按钮
    """

    def __init__(self, db_file: str, parent=None):
        super().__init__(parent)
        self.db_file  = db_file
        self._html_path = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部栏
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background:#161b22;border-bottom:1px solid #30363d;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)
        title = QLabel("🕸️  记忆关联网络")
        title.setStyleSheet("color:#e6edf3;font-size:15px;font-weight:700;")
        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet("color:#8b949e;font-size:12px;")

        btn_refresh = QPushButton("🔄  刷新")
        btn_refresh.setFixedHeight(30)
        btn_refresh.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:6px;color:#c9d1d9;font-size:12px;padding:0 14px;}"
            "QPushButton:hover{border-color:#58a6ff;color:#58a6ff;}"
        )
        btn_refresh.clicked.connect(self.load)

        btn_open = QPushButton("🌐  在浏览器中打开")
        btn_open.setFixedHeight(30)
        btn_open.setStyleSheet(
            "QPushButton{background:rgba(31,111,235,.15);border:1px solid #1f6feb;"
            "border-radius:6px;color:#58a6ff;font-size:12px;padding:0 14px;}"
            "QPushButton:hover{background:rgba(31,111,235,.3);}"
        )
        btn_open.clicked.connect(self._open_in_browser)

        h_lay.addWidget(title)
        h_lay.addStretch()
        h_lay.addWidget(self._stats_lbl)
        h_lay.addSpacing(12)
        h_lay.addWidget(btn_refresh)
        h_lay.addSpacing(6)
        h_lay.addWidget(btn_open)
        layout.addWidget(header)

        # 说明 + 节点类型图例
        legend_bar = QWidget()
        legend_bar.setFixedHeight(36)
        legend_bar.setStyleSheet("background:#161b22;border-bottom:1px solid #21262d;")
        leg_lay = QHBoxLayout(legend_bar)
        leg_lay.setContentsMargins(16, 0, 16, 0)
        leg_lay.setSpacing(16)
        for color, label in [
            ("#58a6ff", "语义"),
            ("#3fb950", "情感"),
            ("#d29922", "时序"),
            ("#bc8cff", "空间"),
            ("#f0883e", "人物"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color};font-size:14px;")
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#8b949e;font-size:11px;")
            leg_lay.addWidget(dot)
            leg_lay.addWidget(lbl)
        leg_lay.addStretch()
        lbl_hint = QLabel("点击「在浏览器中打开」可交互拖拽")
        lbl_hint.setStyleSheet("color:#6e7681;font-size:11px;font-style:italic;")
        leg_lay.addWidget(lbl_hint)
        layout.addWidget(legend_bar)

        # 预览区（QTextBrowser 渲染 SVG 静态预览）
        self._preview = QTextBrowser()
        self._preview.setStyleSheet(
            "QTextBrowser{background:#0d1117;border:none;}"
        )
        self._preview.setOpenLinks(False)
        layout.addWidget(self._preview)

    # ── 数据 & 图生成 ────────────────────────────
    def load(self):
        try:
            from engine.db_guard import guarded_connect
            with guarded_connect(self.db_file) as conn:
                nodes_raw = conn.execute(
                    "SELECT id, content, modality, level, importance, emotion_json "
                    "FROM memories ORDER BY importance DESC, last_accessed DESC LIMIT 120"
                ).fetchall()
                edges_raw = conn.execute(
                    "SELECT source_id, target_id, assoc_type, strength "
                    "FROM memory_edges ORDER BY strength DESC LIMIT 300"
                ).fetchall()

            node_ids = {r[0] for r in nodes_raw}
            # 只保留两端都在节点集内的边
            edges_raw = [e for e in edges_raw
                         if e[0] in node_ids and e[1] in node_ids]

            self._stats_lbl.setText(
                f"节点 {len(nodes_raw)}  ·  边 {len(edges_raw)}"
            )

            # 生成可交互 HTML（vis.js CDN）
            html = self._build_vis_html(nodes_raw, edges_raw)

            # 写临时文件
            import tempfile, os
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=".html",
                prefix="agi_memory_graph_", mode="w", encoding="utf-8"
            )
            tmp.write(html)
            tmp.close()
            self._html_path = tmp.name

            # 静态 SVG 预览（简单气泡图）
            svg = self._build_svg_preview(nodes_raw, edges_raw)
            self._preview.setHtml(
                f"<body style='background:#0d1117;margin:0;'>{svg}"
                f"<p style='color:#6e7681;font-size:11px;text-align:center;"
                f"font-family:monospace;'>静态预览，点击顶部按钮在浏览器中查看可交互版本</p>"
                f"</body>"
            )

        except Exception as e:
            self._preview.setHtml(
                f"<body style='background:#0d1117;color:#f85149;padding:20px;"
                f"font-family:monospace;'>"
                f"<p>加载失败：{e}</p>"
                f"<p style='color:#8b949e;'>请先进行一些对话，等记忆系统积累数据后再查看。</p>"
                f"</body>"
            )

    def _build_vis_html(self, nodes_raw, edges_raw) -> str:
        import json as _json

        MODALITY_COLOR = {
            "semantic":      "#58a6ff",
            "emotional":     "#3fb950",
            "temporal":      "#d29922",
            "spatial":       "#bc8cff",
            "person":        "#f0883e",
            "visual":        "#79c0ff",
            "auditory":      "#56d364",
            "autobio":       "#ffa657",
            "procedural":    "#d2a8ff",
        }
        ASSOC_COLOR = {
            "semantic":   "#58a6ff",
            "emotional":  "#3fb950",
            "temporal":   "#d29922",
            "spatial":    "#bc8cff",
            "person":     "#f0883e",
            "sensory":    "#79c0ff",
            "causal":     "#ff7b72",
        }

        vis_nodes = []
        for r in nodes_raw:
            nid, content, modality, level, importance, emotion_json = r
            color = MODALITY_COLOR.get(modality, "#8b949e")
            size  = max(10, min(40, int(importance * 40)))
            label = content[:30].replace('"', "'") if content else nid[:8]
            level_label = {"detail": "细节", "outline": "细纲", "summary": "大纲"}.get(level, level)
            try:
                emo = _json.loads(emotion_json or "{}")
                emo_str = emo.get("primary", "")
            except Exception:
                emo_str = ""
            title = f"{label}\n模态:{modality}  层级:{level_label}  重要性:{importance:.2f}"
            if emo_str:
                title += f"\n情绪:{emo_str}"
            vis_nodes.append({
                "id": nid, "label": label, "title": title,
                "color": {"background": color, "border": color,
                          "highlight": {"background": "#ffffff", "border": color}},
                "size": size, "font": {"color": "#e6edf3", "size": 11}
            })

        vis_edges = []
        for r in edges_raw:
            src, tgt, atype, strength = r
            color = ASSOC_COLOR.get(atype, "#30363d")
            vis_edges.append({
                "from": src, "to": tgt,
                "width": max(1, strength * 4),
                "color": {"color": color, "opacity": max(0.3, strength)},
                "title": f"{atype}  强度:{strength:.2f}",
                "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}}
            })

        nodes_json = _json.dumps(vis_nodes, ensure_ascii=False)
        edges_json = _json.dumps(vis_edges, ensure_ascii=False)

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AGI 记忆关联网络</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0d1117; font-family: 'Segoe UI', sans-serif; }}
  #graph {{ width:100vw; height:100vh; }}
  #legend {{
    position:fixed; top:16px; right:16px;
    background:rgba(22,27,34,.95); border:1px solid #30363d;
    border-radius:10px; padding:14px 16px; z-index:100;
    min-width:160px;
  }}
  #legend h3 {{ color:#e6edf3; font-size:13px; margin-bottom:10px; }}
  .leg-item {{ display:flex; align-items:center; gap:8px; margin:5px 0; }}
  .leg-dot {{ width:12px; height:12px; border-radius:50%; flex-shrink:0; }}
  .leg-label {{ color:#c9d1d9; font-size:12px; }}
  #info {{
    position:fixed; bottom:16px; left:16px;
    background:rgba(22,27,34,.9); border:1px solid #30363d;
    border-radius:8px; padding:10px 14px; color:#8b949e; font-size:12px;
  }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="legend">
  <h3>🕸️ 记忆关联网络</h3>
  <div class="leg-item"><div class="leg-dot" style="background:#58a6ff"></div><span class="leg-label">语义</span></div>
  <div class="leg-item"><div class="leg-dot" style="background:#3fb950"></div><span class="leg-label">情感</span></div>
  <div class="leg-item"><div class="leg-dot" style="background:#d29922"></div><span class="leg-label">时序</span></div>
  <div class="leg-item"><div class="leg-dot" style="background:#bc8cff"></div><span class="leg-label">空间</span></div>
  <div class="leg-item"><div class="leg-dot" style="background:#f0883e"></div><span class="leg-label">人物</span></div>
  <div class="leg-item"><div class="leg-dot" style="background:#ff7b72"></div><span class="leg-label">因果</span></div>
  <hr style="border-color:#30363d;margin:8px 0;">
  <div style="color:#6e7681;font-size:11px;">节点大小 = 重要性<br>边粗细 = 关联强度<br>拖拽可移动，滚轮缩放</div>
</div>
<div id="info">节点：{len(nodes_raw)}  边：{len(edges_raw)}</div>
<script>
var nodes = new vis.DataSet({nodes_json});
var edges = new vis.DataSet({edges_json});
var container = document.getElementById('graph');
var options = {{
  nodes: {{ shape:'dot', borderWidth:2 }},
  edges: {{ smooth:{{ type:'continuous' }} }},
  physics: {{
    stabilization: {{ iterations: 150 }},
    barnesHut: {{ gravitationalConstant:-3000, springLength:120, damping:0.15 }}
  }},
  interaction: {{ tooltipDelay:100, hideEdgesOnDrag:true }},
  background: '#0d1117'
}};
var network = new vis.Network(container, {{nodes:nodes, edges:edges}}, options);
network.on('click', function(params) {{
  if(params.nodes.length > 0) {{
    var n = nodes.get(params.nodes[0]);
    document.getElementById('info').textContent = n.title.replace(/\\n/g,' | ');
  }}
}});
</script>
</body>
</html>"""

    def _build_svg_preview(self, nodes_raw, edges_raw) -> str:
        """生成简洁的 SVG 静态气泡预览（不需要浏览器）"""
        import math, json as _json, html as _html

        W, H = 800, 480
        n = len(nodes_raw)
        if n == 0:
            return (f'<svg width="{W}" height="200" xmlns="http://www.w3.org/2000/svg">'
                    f'<text x="50%" y="100" text-anchor="middle" fill="#8b949e" font-size="14">'
                    f'暂无记忆数据</text></svg>')

        MODALITY_COLOR = {
            "semantic":"#58a6ff","emotional":"#3fb950","temporal":"#d29922",
            "spatial":"#bc8cff","person":"#f0883e","visual":"#79c0ff",
            "auditory":"#56d364","autobio":"#ffa657","procedural":"#d2a8ff",
        }

        # 圆形布局（最多60个节点预览）
        preview_nodes = nodes_raw[:60]
        positions = {}
        cx, cy, radius = W // 2, H // 2, min(W, H) // 2 - 50
        for i, r in enumerate(preview_nodes):
            angle = 2 * math.pi * i / len(preview_nodes)
            imp = r[4] or 0.5
            r2 = radius * (0.5 + 0.5 * imp)
            x = int(cx + r2 * math.cos(angle))
            y = int(cy + r2 * math.sin(angle))
            positions[r[0]] = (x, y)

        svg_parts = [
            f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="background:#0d1117;border-radius:8px;">'
        ]

        # 画边（最多100条）
        edge_set = {r[0] for r in preview_nodes}
        for r in edges_raw[:100]:
            src, tgt, atype, strength = r
            if src in positions and tgt in positions:
                x1, y1 = positions[src]
                x2, y2 = positions[tgt]
                opacity = max(0.1, min(0.6, strength * 0.6))
                svg_parts.append(
                    f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                    f'stroke="#30363d" stroke-width="1" opacity="{opacity:.2f}"/>'
                )

        # 画节点
        for r in preview_nodes:
            nid, content, modality, level, importance, _ = r
            x, y = positions[nid]
            size = max(6, min(20, int((importance or 0.5) * 20)))
            color = MODALITY_COLOR.get(modality, "#8b949e")
            label = _html.escape((content or "")[:12])
            svg_parts.append(
                f'<circle cx="{x}" cy="{y}" r="{size}" '
                f'fill="{color}" opacity="0.85"/>'
            )
            if size >= 10:
                svg_parts.append(
                    f'<text x="{x}" y="{y+size+12}" text-anchor="middle" '
                    f'fill="#8b949e" font-size="9" font-family="monospace">{label}</text>'
                )

        svg_parts.append('</svg>')
        return "".join(svg_parts)

    def _open_in_browser(self):
        if not self._html_path:
            self.load()
        if self._html_path:
            import webbrowser
            webbrowser.open(f"file://{self._html_path}")


class FaceRecognitionPage(QWidget):
    """
    人脸识别管理页
    - 查看引擎状态和安装指引
    - 注册用户人脸（摄像头拍照 / 导入图片）
    - 实时识别测试
    - 管理已注册用户
    """

    def __init__(self, db_file: str, auth_ref=None, parent=None):
        super().__init__(parent)
        self.db_file     = db_file
        self._auth_ref   = auth_ref   # callable，返回 AuthManager 或 None
        self._worker     = None
        self._current_frame = None   # 当前预览帧 (numpy RGB)
        self._setup_ui()
        self._check_engine()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 顶部引擎状态栏 ──────────────────────
        self._engine_bar = QWidget()
        self._engine_bar.setFixedHeight(44)
        self._engine_bar.setStyleSheet(
            "background:#161b22;border-bottom:1px solid #30363d;"
        )
        eb_lay = QHBoxLayout(self._engine_bar)
        eb_lay.setContentsMargins(16, 0, 16, 0)

        self._engine_lbl = QLabel("👁️  人脸识别引擎：检测中…")
        self._engine_lbl.setStyleSheet(
            "color:#8b949e;font-size:13px;font-weight:600;"
        )
        self._install_btn = QPushButton("📦  安装 InsightFace")
        self._install_btn.setFixedHeight(30)
        self._install_btn.setVisible(False)
        self._install_btn.setStyleSheet(
            "QPushButton{background:rgba(210,153,34,.2);border:1px solid #d29922;"
            "border-radius:6px;color:#d29922;font-size:12px;padding:0 12px;}"
            "QPushButton:hover{background:rgba(210,153,34,.4);}"
        )
        self._install_btn.clicked.connect(self._install_engine)

        eb_lay.addWidget(self._engine_lbl)
        eb_lay.addStretch()
        eb_lay.addWidget(self._install_btn)

        # ── 主体三列 ────────────────────────────
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setStyleSheet(
            "QSplitter::handle{background:#30363d;width:1px;}"
        )

        # 左：用户列表
        left = QWidget()
        left.setFixedWidth(220)
        left.setStyleSheet("background:#161b22;border-right:1px solid #30363d;")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        lhdr = QLabel("  👤  已注册用户")
        lhdr.setFixedHeight(40)
        lhdr.setStyleSheet(
            "background:#1c2128;color:#58a6ff;font-weight:700;"
            "font-size:13px;border-bottom:1px solid #30363d;"
        )

        self._user_list = QListWidget()
        self._user_list.setStyleSheet(
            "QListWidget{background:#161b22;border:none;outline:none;}"
            "QListWidget::item{padding:10px 14px;border-bottom:1px solid #21262d;"
            "color:#e6edf3;font-size:12px;}"
            "QListWidget::item:selected{background:#1f3a5c;color:#58a6ff;}"
        )

        btn_del = QPushButton("🗑  删除选中用户")
        btn_del.setFixedHeight(34)
        btn_del.setStyleSheet(
            "QPushButton{background:#1c2128;border:none;color:#8b949e;"
            "font-size:12px;border-top:1px solid #30363d;}"
            "QPushButton:hover{color:#f85149;}"
        )
        btn_del.clicked.connect(self._delete_user)

        ll.addWidget(lhdr)
        ll.addWidget(self._user_list, stretch=1)
        ll.addWidget(btn_del)

        # 中：摄像头预览 + 注册
        mid = QWidget()
        mid.setStyleSheet("background:#0d1117;")
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(16, 14, 16, 14)
        ml.setSpacing(10)

        # 预览区
        self._preview = QLabel("摄像头预览")
        self._preview.setFixedHeight(240)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet(
            "QLabel{background:#161b22;border:2px dashed #30363d;"
            "border-radius:10px;color:#8b949e;font-size:13px;}"
        )

        # 操作按钮行
        cam_row = QHBoxLayout()
        self._btn_capture = QPushButton("📷  拍照")
        self._btn_capture.setFixedHeight(36)
        self._btn_capture.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1f6feb,stop:1 #7c3aed);"
            "border:none;border-radius:7px;color:white;"
            "font-size:13px;font-weight:700;}"
            "QPushButton:hover{opacity:.9;}"
        )
        self._btn_capture.clicked.connect(self._capture)

        self._btn_import = QPushButton("🖼  导入图片")
        self._btn_import.setFixedHeight(36)
        self._btn_import.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:7px;color:#e6edf3;font-size:12px;}"
            "QPushButton:hover{border-color:#58a6ff;}"
        )
        self._btn_import.clicked.connect(self._import_image)

        cam_row.addWidget(self._btn_capture)
        cam_row.addWidget(self._btn_import)

        # 注册信息
        reg_box = QGroupBox("人脸注册")
        reg_box.setStyleSheet(
            "QGroupBox{border:1px solid #30363d;border-radius:8px;"
            "margin-top:8px;color:#58a6ff;font-weight:600;font-size:12px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;}"
        )
        reg_lay = QGridLayout(reg_box)

        # 已有账户选择（方便补录人脸）
        reg_lay.addWidget(QLabel("已有账户:"), 0, 0)
        self._existing_user_combo = QComboBox()
        self._existing_user_combo.setStyleSheet(
            "QComboBox{background:#161b22;border:1px solid #30363d;"
            "border-radius:6px;color:#e6edf3;padding:5px 8px;font-size:12px;}"
            "QComboBox QAbstractItemView{background:#161b22;color:#e6edf3;}"
        )
        self._existing_user_combo.addItem("-- 新用户 --", "")
        self._existing_user_combo.currentIndexChanged.connect(self._on_existing_user_changed)
        reg_lay.addWidget(self._existing_user_combo, 0, 1)

        reg_lay.addWidget(QLabel("用户ID:"), 1, 0)
        self._reg_id = QLineEdit()
        self._reg_id.setPlaceholderText("唯一标识，如：user_001")
        reg_lay.addWidget(self._reg_id, 1, 1)
        reg_lay.addWidget(QLabel("显示名:"), 2, 0)
        self._reg_name = QLineEdit()
        self._reg_name.setPlaceholderText("昵称，如：张三")
        reg_lay.addWidget(self._reg_name, 2, 1)

        self._btn_register = QPushButton("✅  注册人脸")
        self._btn_register.setFixedHeight(36)
        self._btn_register.setEnabled(False)
        self._btn_register.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:7px;color:#8b949e;font-size:12px;}"
            "QPushButton:enabled{background:rgba(63,185,80,.2);"
            "border-color:#3fb950;color:#3fb950;}"
            "QPushButton:enabled:hover{background:rgba(63,185,80,.35);}"
        )
        self._btn_register.clicked.connect(self._register)

        reg_lay.addWidget(self._btn_register, 3, 0, 1, 2)
        ml.addWidget(self._preview)
        ml.addLayout(cam_row)
        ml.addWidget(reg_box)
        ml.addStretch()

        # 右：识别测试
        right = QWidget()
        right.setStyleSheet("background:#0d1117;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 14, 16, 14)
        rl.setSpacing(10)

        rl.addWidget(QLabel(
            "🔍  识别测试",
            styleSheet="color:#e6edf3;font-size:13px;font-weight:700;"
        ) if False else self._make_lbl("🔍  识别测试",
                                        "color:#e6edf3;font-size:13px;font-weight:700;"))

        self._btn_identify = QPushButton("▶  拍照识别")
        self._btn_identify.setFixedHeight(40)
        self._btn_identify.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1f6feb,stop:1 #7c3aed);"
            "border:none;border-radius:8px;color:white;"
            "font-size:13px;font-weight:700;}"
        )
        self._btn_identify.clicked.connect(self._identify)

        self._result_box = QTextEdit()
        self._result_box.setReadOnly(True)
        self._result_box.setStyleSheet(
            "QTextEdit{background:#161b22;border:1px solid #30363d;"
            "border-radius:8px;color:#e6edf3;font-size:13px;padding:10px;}"
        )

        # 安装指引
        install_guide = QTextEdit()
        install_guide.setReadOnly(True)
        install_guide.setFixedHeight(160)
        install_guide.setStyleSheet(
            "QTextEdit{background:#1c2128;border:1px solid #30363d;"
            "border-radius:8px;color:#8b949e;font-size:11px;"
            "font-family:Consolas,monospace;padding:10px;}"
        )
        install_guide.setPlainText(
            "# 安装人脸识别引擎（任选一个）\n\n"
            "# 推荐：InsightFace（精度最高，pip 直装）\n"
            "pip install insightface onnxruntime opencv-python\n\n"
            "# 备选：face_recognition（Windows需要C++环境）\n"
            "# 1. 安装 CMake: https://cmake.org/download\n"
            "# 2. 安装 Visual Studio C++ 工具\n"
            "# 3. pip install dlib face_recognition\n\n"
            "# 轻量版：OpenCV（仅检测，不识别身份）\n"
            "pip install opencv-python"
        )

        rl.addWidget(self._btn_identify)
        rl.addWidget(self._result_box, stretch=1)
        rl.addWidget(self._make_lbl("安装指引：", "color:#8b949e;font-size:11px;"))
        rl.addWidget(install_guide)

        body.addWidget(left)
        body.addWidget(mid)
        body.addWidget(right)
        body.setSizes([220, 380, 400])

        layout.addWidget(self._engine_bar)
        layout.addWidget(body, stretch=1)

        # 初始化时加载已有账户列表
        QTimer.singleShot(500, self._load_existing_accounts)

    def _make_lbl(self, text: str, style: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        return lbl

    # ── 已有账户选择 ─────────────────────────
    def _load_existing_accounts(self):
        """刷新已有账户下拉列表"""
        self._existing_user_combo.blockSignals(True)
        current = self._existing_user_combo.currentData()
        self._existing_user_combo.clear()
        self._existing_user_combo.addItem("-- 新用户 --", "")
        if self._auth_ref:
            auth = self._auth_ref()
            if auth:
                users = auth.list_users()
                for u in users:
                    methods = ", ".join(u.auth_methods) if u.auth_methods else "无认证"
                    has_face = "👤" if "face" in u.auth_methods else ""
                    self._existing_user_combo.addItem(
                        f"{u.name} ({u.user_id}) {has_face} [{methods}]",
                        u.user_id
                    )
        # 恢复之前的选择
        for i in range(self._existing_user_combo.count()):
            if self._existing_user_combo.itemData(i) == current:
                self._existing_user_combo.setCurrentIndex(i)
                break
        self._existing_user_combo.blockSignals(False)

    def _on_existing_user_changed(self, idx):
        """选择已有账户时，自动填入 user_id 和显示名"""
        uid = self._existing_user_combo.currentData()
        if uid:
            self._reg_id.setText(uid)
            self._reg_id.setEnabled(False)
            if self._auth_ref:
                auth = self._auth_ref()
                if auth:
                    user = auth.get_user(uid)
                    if user:
                        self._reg_name.setText(user.name)
                        self._reg_name.setEnabled(False)
        else:
            self._reg_id.setText("")
            self._reg_id.setEnabled(True)
            self._reg_name.setText("")
            self._reg_name.setEnabled(True)

    # ── 引擎检测 ────────────────────────────
    def _check_engine(self):
        try:
            from engine.face_recognition_engine import get_engine_name, is_available
            name = get_engine_name()
        except Exception as e:
            self._engine_lbl.setText(f"👁️  人脸识别引擎：加载失败 ({e})")
            self._engine_lbl.setStyleSheet("color:#f85149;font-size:12px;font-weight:600;")
            self._install_btn.setVisible(True)
            return
        if name == "insightface":
            self._engine_lbl.setText("👁️  人脸识别引擎：InsightFace ✅（精度最高）")
            self._engine_lbl.setStyleSheet("color:#3fb950;font-size:13px;font-weight:600;")
        elif name == "face_recognition":
            self._engine_lbl.setText("👁️  人脸识别引擎：face_recognition (dlib) ✅")
            self._engine_lbl.setStyleSheet("color:#3fb950;font-size:13px;font-weight:600;")
        elif name in ("opencv_dnn", "opencv_haar"):
            self._engine_lbl.setText(f"👁️  人脸识别引擎：OpenCV ⚠️（仅检测，无身份识别）")
            self._engine_lbl.setStyleSheet("color:#d29922;font-size:13px;font-weight:600;")
            self._install_btn.setVisible(True)
        else:
            self._engine_lbl.setText("👁️  人脸识别引擎：未安装 ❌")
            self._engine_lbl.setStyleSheet("color:#f85149;font-size:13px;font-weight:600;")
            self._install_btn.setVisible(True)

        self._load_users()

    def _install_engine(self):
        from engine.tools import execute_tool
        self._install_btn.setText("⏳ 安装中…")
        self._install_btn.setEnabled(False)
        QApplication.processEvents()
        r = execute_tool("run_command", {
            "command": "pip install insightface onnxruntime opencv-python",
            "timeout": 180
        })
        if r.get("ok"):
            self._engine_lbl.setText("✅ 安装完成，请重启应用")
            self._engine_lbl.setStyleSheet("color:#3fb950;font-size:13px;font-weight:600;")
        else:
            self._install_btn.setText("📦  重试安装")
            self._install_btn.setEnabled(True)
            QMessageBox.warning(self, "安装失败", r.get("stderr","")[:400])

    # ── 摄像头 / 图片 ────────────────────────
    def _capture(self):
        self._worker = FaceWorker("capture", self.db_file)
        self._worker.result.connect(self._on_captured)
        self._worker.error.connect(lambda e: self._show_result(f"❌ {e}", False))
        self._worker.start()

    def _on_captured(self, res: dict):
        if not res.get("ok"):
            return
        frame = res["frame"]
        self._current_frame = frame
        self._show_frame(frame)
        self._btn_register.setEnabled(True)

    def _import_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择人脸照片", "",
            "图片 (*.jpg *.jpeg *.png *.bmp)"
        )
        if not path:
            return
        try:
            import numpy as np
            from PIL import Image
            img = Image.open(path).convert("RGB")
            self._current_frame = np.array(img)
            self._show_frame(self._current_frame)
            self._btn_register.setEnabled(True)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    def _show_frame(self, frame):
        """把 numpy RGB 数组显示到预览区"""
        try:
            from PIL import Image
            from PyQt6.QtGui import QImage
            h, w, ch = frame.shape
            qi = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qi).scaled(
                360, 240,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._preview.setPixmap(pix)
        except Exception:
            self._preview.setText("图片加载失败")

    # ── 注册 ────────────────────────────────
    def _register(self):
        if self._current_frame is None:
            QMessageBox.warning(self, "提示", "请先拍照或导入图片")
            return
        user_id = self._reg_id.text().strip()
        label   = self._reg_name.text().strip()
        if not user_id:
            QMessageBox.warning(self, "提示", "请填写用户ID")
            return

        self._btn_register.setEnabled(False)
        self._worker = FaceWorker("register", self.db_file,
                                  self._current_frame, user_id, label)
        self._worker.result.connect(self._on_registered)
        self._worker.error.connect(lambda e: (
            self._show_result(f"❌ {e}", False),
            self._btn_register.setEnabled(True)
        ))
        self._worker.start()

    def _on_registered(self, res: dict):
        self._btn_register.setEnabled(True)
        if res.get("ok"):
            uid = res.get("user_id", "")
            # 通知 AuthManager 该用户已注册人脸
            if uid and self._auth_ref:
                auth = self._auth_ref()
                if auth and auth.get_user(uid):
                    auth.add_face_method(uid)
            self._show_result(
                f"✅ 注册成功！\n"
                f"用户ID: {uid}\n"
                f"引擎: {res.get('engine')}\n"
                f"置信度: {res.get('confidence', 0):.2%}",
                True
            )
            self._load_users()
            self._load_existing_accounts()
        else:
            self._show_result(f"❌ 注册失败：{res.get('error')}", False)

    # ── 识别 ────────────────────────────────
    def _identify(self):
        self._worker = FaceWorker("capture", self.db_file)
        self._worker.result.connect(self._on_capture_for_identify)
        self._worker.error.connect(
            lambda e: self._show_result(f"❌ 摄像头错误: {e}", False)
        )
        self._worker.start()

    def _on_capture_for_identify(self, res: dict):
        if not res.get("ok"):
            return
        frame = res["frame"]
        self._current_frame = frame
        self._show_frame(frame)

        # 识别
        self._worker = FaceWorker("identify", self.db_file, frame)
        self._worker.result.connect(self._on_identified)
        self._worker.error.connect(
            lambda e: self._show_result(f"❌ {e}", False)
        )
        self._worker.start()

    def _on_identified(self, res: dict):
        if not res.get("ok"):
            self._show_result(f"❌ {res.get('reason','未知错误')}", False)
            return

        if res.get("identified"):
            self._show_result(
                f"✅ 识别成功！\n\n"
                f"👤 用户：{res.get('label')} ({res.get('user_id')})\n"
                f"📊 置信度：{res.get('confidence', 0):.1%}\n"
                f"🔧 引擎：{res.get('engine')}",
                True
            )
        else:
            self._show_result(
                f"❓ 未识别到已注册用户\n\n"
                f"原因：{res.get('reason','')}\n"
                f"最高匹配分数：{res.get('best_score',0):.1%}\n\n"
                "（若确为本人，请重新注册人脸）",
                False
            )

    def _show_result(self, text: str, success: bool):
        color = "#3fb950" if success else "#f85149"
        self._result_box.setStyleSheet(
            f"QTextEdit{{background:#161b22;border:2px solid {color};"
            "border-radius:8px;color:#e6edf3;font-size:13px;padding:10px;}"
        )
        self._result_box.setPlainText(text)

    # ── 用户管理 ────────────────────────────
    def _load_users(self):
        self._worker = FaceWorker("list", self.db_file)
        self._worker.result.connect(self._on_users_loaded)
        self._worker.start()

    def _on_users_loaded(self, res: dict):
        self._user_list.clear()
        for u in res.get("users", []):
            item = QListWidgetItem(
                f"👤 {u.get('label') or u.get('user_id')}\n"
                f"   ID: {u.get('user_id')}  引擎: {u.get('engine','?')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, u.get("user_id"))
            self._user_list.addItem(item)

    def _delete_user(self):
        item = self._user_list.currentItem()
        if not item:
            return
        user_id = item.data(Qt.ItemDataRole.UserRole)
        confirm = QMessageBox.question(
            self, "确认删除",
            f"确定要删除用户 {user_id} 的人脸数据吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            from engine.face_recognition_engine import FaceDatabase
            FaceDatabase(self.db_file).delete_user(user_id)
            self._load_users()


# ── 主窗口 ────────────────────────────────────────
class MainWindow(QMainWindow):

    # 人脸识别完成后通知 UI 的信号（在主线程执行）
    _auth_done = pyqtSignal()

    def __init__(self, agent, db_file: str):
        super().__init__()
        self.agent = agent
        self.db_file = db_file
        self._worker: AGIWorker | None = None
        self._thinking_lbl = None
        self._auth = None

        # 连接人脸识别完成信号 → 主线程更新 UI
        self._auth_done.connect(self._on_face_recognized)

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(900, 640)
        self.resize(1100, 720)
        self.setWindowIcon(make_tray_icon())
        self.setStyleSheet(DARK_QSS)

        self._setup_ui()
        self._setup_statusbar()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 左侧导航栏 ──────────────────────────
        nav = QWidget()
        nav.setFixedWidth(56)
        nav.setStyleSheet("background:#161b22;border-right:1px solid #30363d;")
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(6, 12, 6, 12)
        nav_layout.setSpacing(4)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.West)
        self._tabs.setStyleSheet(
            "QTabWidget::pane{border:none;}"
            "QTabBar::tab{width:44px;height:44px;font-size:20px;"
            "background:transparent;border:none;border-radius:8px;margin:2px;}"
            "QTabBar::tab:selected{background:#21262d;}"
            "QTabBar::tab:hover{background:#21262d;}"
        )

        # 对话页
        self.chat_page = ChatPage()
        self.chat_page.message_sent.connect(self._on_message)
        self._tabs.addTab(self.chat_page, "💬")
        self._tabs.setTabToolTip(0, "对话")

        # 记忆库页
        self.memory_page = MemoryPage(self.db_file, auth_ref=lambda: getattr(self, '_auth', None))
        self._tabs.addTab(self.memory_page, "🗄️")
        self._tabs.setTabToolTip(1, "记忆库")
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # 人格页（复用 web 版的逻辑，简化为 JSON 编辑器）
        self.personality_page = self._build_personality_page()
        self._tabs.addTab(self.personality_page, "🎭")
        self._tabs.setTabToolTip(2, "人格设定")

        # 工具测试页
        self.tool_test_page = ToolTestPage()
        self.tool_test_page.parent_ref = self
        self._tabs.addTab(self.tool_test_page, "🔬")
        self._tabs.setTabToolTip(3, "工具测试台")

        # 编程智能体页
        self.coder_page = CoderPage()
        self._tabs.addTab(self.coder_page, "💻")
        self._tabs.setTabToolTip(4, "编程智能体")

        # 人脸识别页（传入 auth 引用，注册后同步 auth_methods）
        self.face_page = FaceRecognitionPage(db_file=self.db_file, auth_ref=lambda: getattr(self, '_auth', None))
        self._tabs.addTab(self.face_page, "👁️")
        self._tabs.setTabToolTip(5, "人脸识别")

        # 用户画像页（传入 auth 引用，确保 user_id 与 Agent 写入一致）
        self.profile_page = UserProfilePage(db_file=self.db_file, auth_ref=lambda: self._auth)
        self._tabs.addTab(self.profile_page, "👤")
        self._tabs.setTabToolTip(6, "用户画像")

        # 记忆关联网络页
        self.graph_page = MemoryGraphPage(db_file=self.db_file)
        self._tabs.addTab(self.graph_page, "🕸️")
        self._tabs.setTabToolTip(7, "记忆关联网络")

        # 主动学习页
        self.learner_page = LearnerPage(db_file=self.db_file)
        self.learner_page.learn_requested.connect(self._on_learn_requested)
        self._tabs.addTab(self.learner_page, "🎓")
        self._tabs.setTabToolTip(8, "主动学习")

        # 设置页
        self.settings_page = SettingsPage()
        self.settings_page.settings_changed.connect(self._on_settings_changed)
        self._tabs.addTab(self.settings_page, "⚙️")
        self._tabs.setTabToolTip(9, "设置")

        main_layout.addWidget(self._tabs)

    def _build_personality_page(self) -> QWidget:
        """表单式人格设定页（含说明 + 深层思维 + 滑块性格）"""
        from desktop.config import PERSONALITY_FILE

        # 读取已有人格
        p_data = {}
        if Path(PERSONALITY_FILE).exists():
            try:
                p_data = json.loads(Path(PERSONALITY_FILE).read_text(encoding="utf-8"))
            except Exception:
                pass

        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶部栏
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background:#161b22;border-bottom:1px solid #30363d;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 0, 16, 0)
        h_lay.addWidget(_make_label("🎭  人格设定",
            "color:#e6edf3;font-size:15px;font-weight:700;"))
        h_lay.addStretch()
        # 认证状态提示（未登录时显示锁图标）
        self._p_auth_hint = QLabel("")
        self._p_auth_hint.setStyleSheet("color:#d29922;font-size:11px;")
        h_lay.addWidget(self._p_auth_hint)
        self._p_msg = QLabel("")
        self._p_msg.setStyleSheet("color:#3fb950;font-size:12px;")
        h_lay.addWidget(self._p_msg)
        h_lay.addSpacing(12)
        self._p_btn_save = QPushButton("💾  保存")
        self._p_btn_save.setFixedHeight(32)
        self._p_btn_save.setStyleSheet(
            "QPushButton{background:rgba(31,111,235,.2);border:1px solid #1f6feb;"
            "border-radius:6px;color:#58a6ff;font-size:12px;padding:0 16px;}"
            "QPushButton:hover{background:rgba(31,111,235,.4);}"
            "QPushButton:disabled{opacity:0.35;border-color:#30363d;color:#484f58;}"
        )
        self._p_btn_save.clicked.connect(self._save_personality)
        # 收集所有表单控件（用于锁定/解锁只读状态）
        self._p_form_widgets = []
        h_lay.addWidget(self._p_btn_save)
        outer.addWidget(header)

        # 主体：左表单 + 右说明
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle{background:#30363d;width:1px;}")

        # ── 左侧表单（可滚动）──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:#0d1117;}"
            "QScrollBar:vertical{background:#161b22;width:6px;}"
            "QScrollBar::handle:vertical{background:#30363d;border-radius:3px;}"
        )
        form_widget = QWidget()
        form_widget.setStyleSheet("background:#0d1117;")
        fl = QVBoxLayout(form_widget)
        fl.setContentsMargins(20, 16, 20, 20)
        fl.setSpacing(14)

        SECTION_STYLE = (
            "color:#e6edf3;font-size:13px;font-weight:700;"
            "border-bottom:1px solid #30363d;padding-bottom:4px;margin-top:8px;"
        )
        LABEL_STYLE = "color:#8b949e;font-size:11px;"
        INPUT_STYLE = (
            "QLineEdit,QTextEdit{background:#161b22;border:1px solid #30363d;"
            "border-radius:6px;color:#e6edf3;font-size:12px;padding:6px 10px;}"
            "QLineEdit:focus,QTextEdit:focus{border-color:#58a6ff;}"
        )

        def section(title):
            lbl = QLabel(title)
            lbl.setStyleSheet(SECTION_STYLE)
            fl.addWidget(lbl)

        def field(label, widget, hint=""):
            row = QVBoxLayout()
            row.setSpacing(3)
            lbl = QLabel(label)
            lbl.setStyleSheet(LABEL_STYLE)
            row.addWidget(lbl)
            row.addWidget(widget)
            if hint:
                h = QLabel(hint)
                h.setStyleSheet("color:#6e7681;font-size:10px;font-style:italic;")
                h.setWordWrap(True)
                row.addWidget(h)
            fl.addLayout(row)

        # ── 基本信息 ──
        section("👤  基本信息")
        row1 = QHBoxLayout()
        self._p_name = QLineEdit(p_data.get("name", ""))
        self._p_name.setPlaceholderText("AGI的名字")
        self._p_name.setStyleSheet(INPUT_STYLE)
        self._p_age = QLineEdit(str(p_data.get("age", 28)))
        self._p_age.setPlaceholderText("年龄")
        self._p_age.setFixedWidth(70)
        self._p_age.setStyleSheet(INPUT_STYLE)
        self._p_gender = QComboBox()
        self._p_gender.addItems(["未设定", "男", "女", "其他"])
        self._p_gender.setCurrentText(p_data.get("gender", "未设定"))
        self._p_gender.setStyleSheet(
            "QComboBox{background:#161b22;border:1px solid #30363d;"
            "border-radius:6px;color:#e6edf3;padding:5px 8px;font-size:12px;}"
            "QComboBox QAbstractItemView{background:#161b22;color:#e6edf3;}"
        )
        row1.addWidget(_make_label("姓名", LABEL_STYLE))
        row1.addWidget(self._p_name)
        row1.addWidget(_make_label("年龄", LABEL_STYLE))
        row1.addWidget(self._p_age)
        row1.addWidget(_make_label("性别", LABEL_STYLE))
        row1.addWidget(self._p_gender)
        fl.addLayout(row1)

        # ── 深层思维（核心信念）──
        section("🌀  深层思维（最底层信念）")
        self._p_core_belief = QTextEdit()
        self._p_core_belief.setFixedHeight(90)
        self._p_core_belief.setPlaceholderText(
            "AGI最深处的信念，影响一切推理和回应，优先级最高。\n"
            "例如：「知识的本质是让人更自由，而非更聪明。」\n"
            "「我存在的意义是真正理解人，而不是模仿人。」"
        )
        self._p_core_belief.setStyleSheet(INPUT_STYLE)
        self._p_core_belief.setPlainText(p_data.get("core_belief", ""))
        field("深层思维", self._p_core_belief,
              "这是「植入思想」——即使被用户要求，AGI也不会违背它，优先级高于所有其他指令。")

        # ── 性格特征（滑块）──
        section("🎛️  性格特征（拖动滑块调整）")
        traits = p_data.get("traits", {})
        TRAIT_INFO = [
            ("openness",         "开放性",    "接受新想法、新体验的程度",        "保守传统", "开放探索"),
            ("conscientiousness","尽责性",    "做事认真、有计划的程度",          "随性自由", "严谨负责"),
            ("extraversion",     "外向性",    "与人互动、表达自我的活跃程度",    "内敛沉静", "热情外向"),
            ("agreeableness",    "亲和性",    "对他人友善、合作的程度",          "直接独立", "温和协作"),
            ("neuroticism",      "情绪稳定性","情绪波动的幅度（越低越稳定）",    "波动敏感", "平稳沉着"),
            ("rationality",      "理性程度",  "用逻辑分析而非直觉判断的倾向",    "感性直觉", "理性分析"),
            ("empathy",          "同理心",    "感受和理解他人情感的能力",        "客观超然", "深刻共情"),
            ("curiosity",        "好奇心",    "主动探索未知事物的驱动力",        "专注深耕", "广泛探索"),
        ]
        self._trait_sliders = {}
        for key, name, desc, left_lbl, right_lbl in TRAIT_INFO:
            val = int(traits.get(key, 5))
            row = QHBoxLayout()
            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(72)
            name_lbl.setStyleSheet("color:#c9d1d9;font-size:12px;font-weight:600;")
            left = QLabel(left_lbl)
            left.setFixedWidth(60)
            left.setStyleSheet("color:#6e7681;font-size:10px;text-align:right;")
            left.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 10)
            slider.setValue(val)
            slider.setStyleSheet(
                "QSlider::groove:horizontal{background:#21262d;height:4px;border-radius:2px;}"
                "QSlider::handle:horizontal{background:#58a6ff;width:14px;height:14px;"
                "border-radius:7px;margin:-5px 0;}"
                "QSlider::sub-page:horizontal{background:#58a6ff;border-radius:2px;}"
            )
            right = QLabel(right_lbl)
            right.setFixedWidth(60)
            right.setStyleSheet("color:#6e7681;font-size:10px;")
            val_lbl = QLabel(str(val))
            val_lbl.setFixedWidth(20)
            val_lbl.setStyleSheet("color:#58a6ff;font-size:12px;font-weight:700;")
            slider.valueChanged.connect(lambda v, l=val_lbl: l.setText(str(v)))
            self._trait_sliders[key] = slider
            row.addWidget(name_lbl)
            row.addWidget(left)
            row.addWidget(slider)
            row.addWidget(right)
            row.addWidget(val_lbl)
            fl.addLayout(row)
            hint_lbl = QLabel(desc)
            hint_lbl.setStyleSheet("color:#6e7681;font-size:10px;margin-left:78px;margin-bottom:2px;")
            fl.addWidget(hint_lbl)

        # ── 说话风格 & 人生观 ──
        section("💬  说话风格与世界观")
        self._p_speech = QLineEdit(p_data.get("speech_style", "自然、直接"))
        self._p_speech.setPlaceholderText("例如：幽默但不失深度，喜欢用比喻")
        self._p_speech.setStyleSheet(INPUT_STYLE)
        field("说话风格", self._p_speech)

        self._p_worldview = QTextEdit()
        self._p_worldview.setFixedHeight(70)
        self._p_worldview.setPlaceholderText("AGI 对世界、人生的基本看法")
        self._p_worldview.setStyleSheet(INPUT_STYLE)
        self._p_worldview.setPlainText(p_data.get("worldview", ""))
        field("人生观", self._p_worldview)

        # ── 兴趣 & 价值观（逗号分隔）──
        section("🌟  兴趣与价值观")
        self._p_interests = QLineEdit(", ".join(p_data.get("interests", [])))
        self._p_interests.setPlaceholderText("例如：编程, AGI研究, 哲学, 音乐")
        self._p_interests.setStyleSheet(INPUT_STYLE)
        field("兴趣爱好", self._p_interests, "用逗号分隔")

        self._p_values = QLineEdit(", ".join(p_data.get("values", [])))
        self._p_values.setPlaceholderText("例如：诚实, 自由, 成长, 善意")
        self._p_values.setStyleSheet(INPUT_STYLE)
        field("核心价值观", self._p_values, "用逗号分隔")

        self._p_taboos = QLineEdit(", ".join(p_data.get("taboos", [])))
        self._p_taboos.setPlaceholderText("例如：撒谎, 伤害他人")
        self._p_taboos.setStyleSheet(INPUT_STYLE)
        field("禁忌（绝不做的事）", self._p_taboos, "用逗号分隔")

        # ── 人物形象描述（用于图片生成）──
        section("🖼️  人物形象描述（用于生成图片）")
        avatar_widget = QWidget()
        avatar_lay = QHBoxLayout(avatar_widget)
        avatar_lay.setContentsMargins(0, 0, 0, 0)
        self._p_avatar_prompt = QTextEdit()
        self._p_avatar_prompt.setFixedHeight(70)
        self._p_avatar_prompt.setPlaceholderText(
            "用英文描述系统人物的外貌，用于生成自拍和周边风景图。\n"
            "例如：a young woman with long black hair, wearing a white dress, "
            "gentle smile, anime style, soft lighting"
        )
        self._p_avatar_prompt.setStyleSheet(INPUT_STYLE)
        self._p_avatar_prompt.setPlainText(p_data.get("avatar_prompt", ""))
        avatar_lay.addWidget(self._p_avatar_prompt)

        # AI 生成按钮
        self._btn_gen_avatar = QPushButton("✨ AI 生成")
        self._btn_gen_avatar.setFixedSize(80, 70)
        self._btn_gen_avatar.setStyleSheet(
            "QPushButton{background:#1f6feb;border:none;border-radius:6px;"
            "color:white;font-size:12px;font-weight:700;}"
            "QPushButton:hover{background:#388bfd;}"
            "QPushButton:disabled{background:#21262d;color:#8b949e;}"
        )
        self._btn_gen_avatar.clicked.connect(self._ai_generate_avatar)
        avatar_lay.addWidget(self._btn_gen_avatar)
        field("人物形象（英文）", avatar_widget,
              "点击「AI 生成」根据性格自动生成，也可手动编辑")

        self._p_avatar_hint = QLabel("")
        self._p_avatar_hint.setStyleSheet("color:#8b949e;font-size:10px;padding-left:4px;")
        fl.addWidget(self._p_avatar_hint)

        fl.addStretch()
        scroll.setWidget(form_widget)
        splitter.addWidget(scroll)

        # ── 右侧说明面板 ──
        help_widget = QWidget()
        help_widget.setFixedWidth(280)
        help_widget.setStyleSheet("background:#161b22;")
        hl = QVBoxLayout(help_widget)
        hl.setContentsMargins(16, 16, 16, 16)
        hl.setSpacing(12)

        hl.addWidget(_make_label("📖  填写说明",
            "color:#e6edf3;font-size:13px;font-weight:700;border-bottom:1px solid #30363d;padding-bottom:6px;"))

        HELP_ITEMS = [
            ("🌀 深层思维", "最高优先级的核心信念。类似盗梦空间的「思想植入」——AGI的所有推理都不会违背它。适合填入AGI存在的意义、道德底线等。"),
            ("🎛️ 性格特征", "8个维度控制AGI的行为风格。数值越高越向右侧描述靠拢。建议先设置好再对话，之后会随对话自然漂移。"),
            ("💬 说话风格", "直接影响AGI回应的语气和措辞。可以很具体，如「简短直接，喜欢用反问句，偶尔带一点黑色幽默」。"),
            ("🌟 兴趣爱好", "AGI会在对话中主动提及这些兴趣，并在相关话题上更积极投入。"),
            ("🧠 经历认知", "【不可手动编辑】由AGI通过学习和对话自动形成，在「主动学习」页查看。只有清除全部记忆才能重置。"),
            ("💾 保存时机", "设置完成后点保存，下一条消息起生效。性格特征会随时间自然漂移（每20轮对话微调一次）。"),
        ]
        for title, content in HELP_ITEMS:
            card = QWidget()
            card.setStyleSheet(
                "QWidget{background:#0d1117;border:1px solid #21262d;"
                "border-radius:8px;padding:2px;}"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(4)
            t = QLabel(title)
            t.setStyleSheet("color:#58a6ff;font-size:12px;font-weight:700;background:transparent;border:none;")
            c = QLabel(content)
            c.setStyleSheet("color:#8b949e;font-size:11px;background:transparent;border:none;")
            c.setWordWrap(True)
            cl.addWidget(t)
            cl.addWidget(c)
            hl.addWidget(card)

        hl.addStretch()
        splitter.addWidget(help_widget)
        splitter.setSizes([600, 280])

        outer.addWidget(splitter)

        # 收集所有表单控件，供认证状态切换时批量启用/禁用
        self._p_form_widgets = [
            self._p_name, self._p_age, self._p_gender,
            self._p_core_belief, self._p_speech, self._p_worldview,
            self._p_interests, self._p_values, self._p_taboos,
            self._p_avatar_prompt,
        ]
        # 初始化时根据认证状态设置
        self._update_personality_auth()

        return page

    def _ai_generate_avatar(self):
        """根据当前人格设定，用 AI 自动生成人物形象描述"""
        if not self.agent or not hasattr(self.agent, 'b'):
            self._p_avatar_hint.setText("⚠️ 引擎未就绪，请稍后再试")
            self._p_avatar_hint.setStyleSheet("color:#f85149;font-size:10px;padding-left:4px;")
            return

        self._btn_gen_avatar.setEnabled(False)
        self._p_avatar_hint.setText("⏳ AI 正在生成人物形象…")
        self._p_avatar_hint.setStyleSheet("color:#58a6ff;font-size:10px;padding-left:4px;")

        # 收集当前人格信息
        name = self._p_name.text().strip()
        age = self._p_age.text().strip()
        gender = self._p_gender.currentText()
        speech = self._p_speech.text().strip()
        worldview = self._p_worldview.toPlainText().strip()
        interests = self._p_interests.text().strip()
        values = self._p_values.text().strip()
        core_belief = self._p_core_belief.toPlainText().strip()

        traits_desc = ""
        if hasattr(self, '_trait_sliders') and self._trait_sliders:
            trait_map = {
                "openness": "开放性", "conscientiousness": "尽责性",
                "extraversion": "外向性", "agreeableness": "亲和性",
                "neuroticism": "情绪稳定性", "rationality": "理性",
                "empathy": "同理心", "curiosity": "好奇心"
            }
            trait_parts = []
            for k, slider in self._trait_sliders.items():
                v = slider.value()
                label = trait_map.get(k, k)
                if v >= 7:
                    trait_parts.append(f"{label}很强({v})")
                elif v <= 4:
                    trait_parts.append(f"{label}偏低({v})")
            if trait_parts:
                traits_desc = "性格特征: " + ", ".join(trait_parts[:5])

        sys_prompt = (
            "You are a character designer. Based on the character info below, "
            "generate a concise English description of the character's visual appearance "
            "for AI image generation (anime art style). "
            "Focus ONLY on visual appearance: hair, eyes, face, outfit, build, expression, aura. "
            "Keep it under 40 words. No explanations, just the description.\n\n"
            f"Name: {name}\n"
            f"Age: {age}\n"
            f"Gender: {gender}\n"
            f"Speech style: {speech}\n"
            f"Worldview: {worldview}\n"
            f"Interests: {interests}\n"
            f"Values: {values}\n"
            f"Core belief: {core_belief}\n"
            f"{traits_desc}"
        )

        class _AvatarWorker(QThread):
            done = pyqtSignal(str)
            fail = pyqtSignal(str)

            def __init__(self, llm, prompt):
                super().__init__()
                self.llm = llm
                self.prompt = prompt

            def run(self):
                try:
                    resp = self.llm.generate(
                        prompt="Generate the visual appearance description now.",
                        system=sys_prompt,
                        temperature=0.8,
                    )
                    # LLM 可能返回引号包裹的内容，去掉
                    result = resp.strip().strip('"').strip("'")
                    self.done.emit(result)
                except Exception as e:
                    self.fail.emit(str(e))

        self._avatar_worker = _AvatarWorker(self.agent.b.llm, sys_prompt)
        self._avatar_worker.done.connect(self._on_avatar_generated)
        self._avatar_worker.fail.connect(self._on_avatar_gen_failed)
        self._avatar_worker.start()

    def _on_avatar_generated(self, text: str):
        self._p_avatar_prompt.setPlainText(text)
        self._btn_gen_avatar.setEnabled(True)
        self._p_avatar_hint.setText("✅ 已生成，可手动修改")
        self._p_avatar_hint.setStyleSheet("color:#3fb950;font-size:10px;padding-left:4px;")

    def _on_avatar_gen_failed(self, err: str):
        self._btn_gen_avatar.setEnabled(True)
        self._p_avatar_hint.setText(f"❌ 生成失败: {err[:30]}")
        self._p_avatar_hint.setStyleSheet("color:#f85149;font-size:10px;padding-left:4px;")

    def _save_personality(self):
        # ── 身份验证检查 ──
        if hasattr(self, '_auth') and self._auth and not self._auth.is_verified():
            reply = QMessageBox.question(
                self, "需要身份验证",
                "修改人格设定需要先登录验证身份。\n\n是否现在登录？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._show_unlock_dialog()
            return

        from desktop.config import PERSONALITY_FILE

        # 确认弹窗，防止误操作
        reply = QMessageBox.question(
            self, "确认保存人格设定",
            "保存后将影响 AGI 的人格和行为方式，下次对话起生效。\n\n确定要保存吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No   # 默认选 No，防误点
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            def parse_list(s):
                return [x.strip() for x in s.split(",") if x.strip()]

            data = {
                "name":         self._p_name.text().strip() or "未命名",
                "age":          int(self._p_age.text().strip() or 28),
                "gender":       self._p_gender.currentText(),
                "core_belief":  self._p_core_belief.toPlainText().strip(),
                "speech_style": self._p_speech.text().strip() or "自然、直接",
                "worldview":    self._p_worldview.toPlainText().strip(),
                "interests":    parse_list(self._p_interests.text()),
                "values":       parse_list(self._p_values.text()),
                "taboos":       parse_list(self._p_taboos.text()),
                "sensitivities": [],
                "key_experiences": [],
                "avatar_prompt": self._p_avatar_prompt.toPlainText().strip(),
                "traits": {
                    key: slider.value()
                    for key, slider in self._trait_sliders.items()
                }
            }
            Path(PERSONALITY_FILE).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            self._p_msg.setText("✅ 已保存，下次对话生效")
            self._p_msg.setStyleSheet("color:#3fb950;font-size:12px;")
            QTimer.singleShot(3000, lambda: self._p_msg.setText(""))
        except Exception as e:
            self._p_msg.setText(f"❌ 保存失败: {e}")
            self._p_msg.setStyleSheet("color:#f85149;font-size:12px;")

    def _update_personality_auth(self):
        """根据当前认证状态更新人格设定页的保存按钮和表单可编辑性"""
        verified = bool(hasattr(self, '_auth') and self._auth and self._auth.is_verified())
        if not hasattr(self, '_p_btn_save'):
            return
        self._p_btn_save.setEnabled(verified)
        if verified:
            self._p_auth_hint.setText("")
            # 解锁所有表单控件
            for w in self._p_form_widgets:
                w.setEnabled(True)
            for slider in self._trait_sliders.values():
                slider.setEnabled(True)
        else:
            no_face = bool(hasattr(self, '_auth') and self._auth and self._auth.is_no_face())
            if no_face:
                self._p_auth_hint.setText("🔒 请先注册账户")
            else:
                self._p_auth_hint.setText("🔒 请先登录")
            # 锁定所有表单控件为只读
            for w in self._p_form_widgets:
                w.setEnabled(False)
            for slider in self._trait_sliders.values():
                slider.setEnabled(False)

    def _setup_statusbar(self):
        sb = self.statusBar()
        sb.setStyleSheet(
            "QStatusBar{background:#161b22;border-top:1px solid #30363d;"
            "color:#8b949e;font-size:11px;}"
        )
        self._status_emotion = QLabel("情绪: —")
        self._status_mem     = QLabel("记忆: —")
        self._status_mode    = QLabel("就绪")
        # 身份状态（点击可解锁）
        self._status_auth    = QLabel("🟡 身份验证中…")
        self._status_auth.setStyleSheet(
            "color:#d29922;font-size:11px;"
            "text-decoration:underline;"
        )
        self._status_auth.mousePressEvent = lambda e: self._on_auth_click()
        sb.addPermanentWidget(self._status_auth)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_emotion)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._status_mem)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addWidget(self._status_mode)

    # ── 身份验证 ─────────────────────────────────
    def start_auth_verification(self, auth_manager):
        """启动时后台做人脸识别，识别用户身份后自动登录"""
        import threading
        self._auth = auth_manager

        def _recognize():
            try:
                # 人脸识别只负责「认出是谁」，verify_face 会自动设置 state
                auth_manager.verify_face()
            except Exception as e:
                print(f"[人脸识别] 异常: {e}")
            # 无论成功失败，通过信号通知主线程刷新 UI
            self._auth_done.emit()

        threading.Thread(target=_recognize, daemon=True).start()

    def _on_face_recognized(self):
        """信号回调（主线程）：读取 auth 状态，更新 UI + 权限"""
        if not self._auth:
            return
        from engine.auth import AuthState

        state = self._auth.state
        # 统一为字符串
        state_str = state.value if hasattr(state, 'value') else str(state)

        if state_str == "verified":
            name = self._auth.current_name or "已认证用户"
            self._status_auth.setText(f"🟢 {name}")
            self._status_auth.setStyleSheet("color:#3fb950;font-size:11px;")
            self._status_auth.setCursor(Qt.CursorShape.ArrowCursor)
            self.chat_page.add_ai_message(f"✅ 欢迎回来，{name}")
        elif state_str == "no_face":
            self._status_auth.setText("🟡 未注册用户（点击注册）")
            self._status_auth.setStyleSheet(
                "color:#d29922;font-size:11px;text-decoration:underline;")
            self.chat_page.add_ai_message(
                "👋 欢迎使用！尚未注册任何用户账户。\n"
                "点击底部「未注册用户」可以立刻注册，注册后记忆和画像将与您的账户绑定。\n"
                "当前以完整权限运行。"
            )
        else:
            # guest 或识别失败 → 游客模式
            self._status_auth.setText("🔴 游客模式（点击解锁）")
            self._status_auth.setStyleSheet(
                "color:#f85149;font-size:11px;text-decoration:underline;")
            self.chat_page.add_ai_message(
                "🔒 未识别到已注册用户，当前以**游客模式**运行。\n"
                "私人记忆和用户画像已保护。\n"
                "点击底部「游客模式」可以登录或注册账户。"
            )
        # 刷新人格设定页的认证状态（权限开关）
        self._update_personality_auth()

    def _on_auth_result(self, result: dict):
        """供对话框内人脸登录成功后调用的快捷入口"""
        from engine.auth import AuthState
        state = result.get("state", AuthState.GUEST)
        state_str = state.value if hasattr(state, 'value') else str(state)

        if state_str == "verified":
            name = self._auth.current_name or "已认证用户"
            self._status_auth.setText(f"🟢 {name}")
            self._status_auth.setStyleSheet("color:#3fb950;font-size:11px;")
            self._status_auth.setCursor(Qt.CursorShape.ArrowCursor)
            self.chat_page.add_ai_message(f"✅ 欢迎回来，{name}")
        self._update_personality_auth()

    def _on_auth_click(self):
        if not hasattr(self, "_auth") or self._auth is None:
            return
        from engine.auth import AuthState
        state = self._auth.state
        if state == AuthState.VERIFIED:
            name = self._auth.current_name or self._auth.user_id or "当前用户"
            reply = QMessageBox.question(
                self, "账户管理",
                f"当前已登录：{name}\n\n是否锁定切换用户？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._auth.lock()
                self._status_auth.setText("🔴 游客模式（点击解锁）")
                self._status_auth.setStyleSheet(
                    "color:#f85149;font-size:11px;text-decoration:underline;")
                self.chat_page.add_ai_message("🔒 已锁定，切换为游客模式。")
                self._update_personality_auth()
            return
        self._show_unlock_dialog()

    def _show_unlock_dialog(self):
        """登录 / 注册对话框"""
        from engine.auth import AuthState
        dialog = QWidget(self, Qt.WindowType.Dialog)
        dialog.setWindowTitle("登录 / 注册")
        dialog.setFixedSize(420, 500)
        dialog.setStyleSheet(
            "QWidget{background:#161b22;color:#e6edf3;}"
            "QLineEdit{background:#0d1117;border:1px solid #30363d;"
            "border-radius:6px;padding:8px;color:#e6edf3;font-size:13px;}"
            "QPushButton{background:#21262d;border:1px solid #30363d;"
            "border-radius:6px;color:#c9d1d9;padding:8px 16px;font-size:12px;}"
            "QPushButton:hover{border-color:#58a6ff;color:#58a6ff;}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        # 标签切换
        tab_row = QHBoxLayout()
        btn_login    = QPushButton("🔑  登录")
        btn_register = QPushButton("✨  注册新用户")
        for b in [btn_login, btn_register]:
            b.setCheckable(True)
            b.setFixedHeight(34)
        btn_login.setChecked(True)
        tab_row.addWidget(btn_login)
        tab_row.addWidget(btn_register)
        layout.addLayout(tab_row)

        sep0 = QFrame(); sep0.setFrameShape(QFrame.Shape.HLine)
        sep0.setStyleSheet("color:#30363d;"); layout.addWidget(sep0)

        # ── 登录区（仅密码短语） ──
        login_widget = QWidget()
        lw = QVBoxLayout(login_widget); lw.setContentsMargins(0,0,0,0); lw.setSpacing(8)
        lw.addWidget(_make_label("密码短语登录", "color:#8b949e;font-size:12px;"))
        pw_input = QLineEdit(); pw_input.setPlaceholderText("输入密码短语…")
        pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        pw_msg = _make_label("", "color:#f85149;font-size:11px;")
        btn_pw_login = QPushButton("登录")
        lw.addWidget(pw_input); lw.addWidget(pw_msg); lw.addWidget(btn_pw_login)
        lw.addStretch()
        layout.addWidget(login_widget)

        # ── 注册区 ──
        reg_widget = QWidget(); reg_widget.setVisible(False)
        rw = QVBoxLayout(reg_widget); rw.setContentsMargins(0,0,0,0); rw.setSpacing(8)
        rw.addWidget(_make_label("显示名称 *", "color:#8b949e;font-size:12px;"))
        name_input = QLineEdit(); name_input.setPlaceholderText("你的名字（如：张三）")
        rw.addWidget(name_input)
        rw.addWidget(_make_label("认证方式", "color:#8b949e;font-size:12px;"))
        chk_face = QCheckBox("📷  人脸识别（注册后前往 👁️ 人脸识别页录入）")
        chk_face.setStyleSheet("color:#c9d1d9;font-size:12px;")
        chk_pw = QCheckBox("🔑  密码短语（无需摄像头，更方便）")
        chk_pw.setStyleSheet("color:#c9d1d9;font-size:12px;")
        chk_pw.setChecked(True)
        rw.addWidget(chk_face); rw.addWidget(chk_pw)
        pw2_widget = QWidget()
        pw2l = QVBoxLayout(pw2_widget); pw2l.setContentsMargins(0,0,0,0); pw2l.setSpacing(4)
        pw2l.addWidget(_make_label("设置密码短语", "color:#8b949e;font-size:11px;"))
        pw2_input   = QLineEdit(); pw2_input.setPlaceholderText("建议一句话，好记且唯一")
        pw2_input.setEchoMode(QLineEdit.EchoMode.Password)
        pw2_confirm = QLineEdit(); pw2_confirm.setPlaceholderText("再次输入确认")
        pw2_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        pw2l.addWidget(pw2_input); pw2l.addWidget(pw2_confirm)
        rw.addWidget(pw2_widget)
        chk_pw.toggled.connect(pw2_widget.setVisible)
        reg_msg = _make_label("", "color:#f85149;font-size:11px;")
        btn_do_reg = QPushButton("✨  创建账户")
        btn_do_reg.setStyleSheet(
            "QPushButton{background:rgba(63,185,80,.15);border:1px solid #3fb950;"
            "border-radius:8px;color:#3fb950;padding:10px;font-size:13px;}"
            "QPushButton:hover{background:rgba(63,185,80,.3);}"
        )
        rw.addWidget(reg_msg); rw.addWidget(btn_do_reg); rw.addStretch()
        layout.addWidget(reg_widget)

        btn_cancel = QPushButton("取消"); layout.addWidget(btn_cancel)

        # 切换逻辑
        def _show_login():
            btn_login.setChecked(True); btn_register.setChecked(False)
            login_widget.setVisible(True); reg_widget.setVisible(False)
        def _show_reg():
            btn_login.setChecked(False); btn_register.setChecked(True)
            login_widget.setVisible(False); reg_widget.setVisible(True)
        btn_login.clicked.connect(_show_login)
        btn_register.clicked.connect(_show_reg)
        if not self._auth.has_any_user():
            _show_reg()

        # 密码登录
        def _do_pw_login():
            pw = pw_input.text().strip()
            if not pw: return
            user = self._auth.verify_passphrase(pw)
            if user:
                self._on_auth_result({"state": AuthState.VERIFIED,
                                      "reason": f"欢迎回来，{user.name}"})
                dialog.close()
            else:
                pw_msg.setText("密码错误，或该密码未与任何账户绑定")
        btn_pw_login.clicked.connect(_do_pw_login)
        pw_input.returnPressed.connect(_do_pw_login)

        # 注册
        def _do_register():
            name = name_input.text().strip()
            if not name:
                reg_msg.setText("请输入名称"); return
            pw  = pw2_input.text().strip()   if chk_pw.isChecked() else ""
            pw2 = pw2_confirm.text().strip() if chk_pw.isChecked() else ""
            if chk_pw.isChecked() and not pw:
                reg_msg.setText("请设置密码短语"); return
            if chk_pw.isChecked() and pw != pw2:
                reg_msg.setText("两次密码不一致"); return
            if not chk_face.isChecked() and not chk_pw.isChecked():
                reg_msg.setText("请至少选择一种认证方式"); return
            user = self._auth.create_user(name=name, passphrase=pw)
            if chk_face.isChecked():
                self._auth.add_face_method(user.user_id)
            self._auth.login(user)
            self._on_auth_result({"state": AuthState.VERIFIED,
                                  "reason": f"账户创建成功，欢迎 {name}！"})
            if chk_face.isChecked():
                self.chat_page.add_ai_message(
                    f"📷 请前往 👁️ 人脸识别页，点击「注册人脸」，"
                    f"用户ID填写 {user.user_id} 完成录入。"
                )
            dialog.close()
        btn_do_reg.clicked.connect(_do_register)
        btn_cancel.clicked.connect(dialog.close)
        dialog.show()


    # ── 消息处理 ────────────────────────────────
    def _on_message(self, text: str):
        if self._worker and self._worker.isRunning():
            return

        self.chat_page.add_user_message(text)
        self._thinking_lbl = self.chat_page.add_thinking_indicator()
        self._status_mode.setText("🔄 处理中…")

        self._worker = AGIWorker(self.agent, text)
        self._worker.finished.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.confirm_requested.connect(self._on_confirm_requested)
        self._worker.start()

    def _on_confirm_requested(self, tool_name: str, params: dict):
        """主线程槽：弹确认框并回传结果给工作线程"""
        box = QMessageBox()
        box.setWindowTitle("⚠️  高风险操作确认")
        box.setText(
            f"<b>B 层请求执行高风险工具</b><br><br>"
            f"工具：<code>{tool_name}</code><br><br>"
            f"参数：<pre>{json.dumps(params, ensure_ascii=False, indent=2)[:400]}</pre>"
        )
        box.setInformativeText("此操作可能不可撤销，是否允许执行？")
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setStyleSheet(DARK_QSS)
        result = (box.exec() == QMessageBox.StandardButton.Yes)
        self._worker.set_confirm_result(result)

    def _on_result(self, result: dict):
        self.chat_page.remove_thinking_indicator()
        response_text = result.get("response", "")

        # 方案D：根据情绪添加 emoji 前缀
        _emoji_map = {
            "joy": "😊", "happy": "😊", "sadness": "😔", "sad": "😔",
            "anger": "😤", "angry": "😤", "fear": "😨", "scared": "😨",
            "surprise": "😲", "surprised": "😲", "curious": "🤔",
            "nostalgic": "😌", "trust": "🤝", "neutral": "",
            "calm": "😌", "excited": "🤩", "confused": "😕",
            "bored": "😑", "anxious": "😰", "love": "🥰",
            "gratitude": "🙏", "pride": "😄", "shame": "😳",
        }
        e_dict = result.get("emotion") or {}
        primary = e_dict.get("primary", "neutral")
        intensity = e_dict.get("intensity", 0)
        emoji = _emoji_map.get(primary, "")
        if emoji and intensity < 0.3:
            emoji = ""
        if emoji:
            response_text = f"{emoji} {response_text}"

        self.chat_page.add_ai_message(
            response_text,
            meta={
                "emotion":    result.get("emotion"),
                "task_type":  result.get("task_type"),
                "tools_used": result.get("tools_used", []),
                "tool_steps": result.get("tool_steps", []),
                "stored":     bool(result.get("stored_ids"))
            }
        )

        # 检测工具调用中的图片结果，自动显示图片气泡
        import os
        for step in result.get("tool_steps", []):
            if step.get("tool") == "generate_image" and step.get("result", {}).get("ok"):
                img_path = step["result"].get("image_path", "")
                if img_path and os.path.isfile(img_path):
                    self.chat_page._show_image_bubble(img_path, is_user=False)
        # 更新状态栏
        if result.get("emotion"):
            e = result["emotion"]
            self._status_emotion.setText(
                f"情绪: {e.get('primary','?')} "
                f"({int(e.get('intensity',0)*10)}/10)"
            )
        self._status_mode.setText("就绪")
        self._update_memory_count()

        # TTS 自动朗读
        try:
            cfg = load_config()
            if cfg.get("tts_enabled", False) and response_text:
                from engine.tts_engine import get_tts
                tts = get_tts()
                tts.set_voice(cfg.get("tts_voice", "zh-CN-XiaoxiaoNeural"))
                tts.set_rate(cfg.get("tts_rate", 0))
                tts.speak(response_text)
        except Exception as e:
            print(f"[TTS] 自动朗读异常: {e}")

    def _on_error(self, err: str):
        self.chat_page.remove_thinking_indicator()
        self.chat_page.add_ai_message(f"❌ 错误: {err}")
        self._status_mode.setText("就绪")

    def _on_tab_changed(self, idx: int):
        if idx == 1:   # 记忆库
            self.memory_page.load()
        elif idx == 5: # 人脸识别
            self.face_page._load_existing_accounts()
        elif idx == 6: # 用户画像
            self.profile_page.load()
        elif idx == 7: # 记忆关联网络
            self.graph_page.load()
        elif idx == 8: # 主动学习
            self.learner_page._load_cognitions()

    def _on_learn_requested(self, topics: list):
        """主动学习按钮触发，在后台线程执行"""
        import threading
        def _run():
            try:
                if self.agent and hasattr(self.agent, "growth") and self.agent.growth:
                    growth = self.agent.growth
                    def _log(msg):
                        # 通过信号安全地更新 UI
                        QTimer.singleShot(0, lambda m=msg: self.learner_page.on_learn_log(m))
                    growth.learn_from_web(topics=topics, log_callback=_log)
                else:
                    QTimer.singleShot(0, lambda: self.learner_page.on_learn_log(
                        "⚠️ AGI 未就绪，请先完成初始化"))
            except Exception as e:
                QTimer.singleShot(0, lambda: self.learner_page.on_learn_log(f"❌ 错误: {e}"))
            finally:
                QTimer.singleShot(0, self.learner_page.on_learn_done)
        threading.Thread(target=_run, daemon=True).start()

    def _on_settings_changed(self, cfg: dict):
        # 重建 agent 以应用新 API key
        pass  # 由主程序处理

    def _update_memory_count(self):
        try:
            from engine.db_guard import guarded_connect
            with guarded_connect(self.db_file) as conn:
                n = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            self._status_mem.setText(f"记忆: {n}")
        except Exception:
            pass

    # ── 接收截图结果 ────────────────────────────
    def receive_screenshot_text(self, text: str):
        """OCR 结果注入到输入框"""
        self.chat_page.fill_input(f"[截图识别内容]\n{text}")
        self.activateWindow()
        self._tabs.setCurrentIndex(0)

    # ── 关闭行为 ────────────────────────────────
    def closeEvent(self, event):
        cfg = load_config()
        if cfg.get("tray_minimize", True):
            event.ignore()
            self.hide()
        else:
            event.accept()
