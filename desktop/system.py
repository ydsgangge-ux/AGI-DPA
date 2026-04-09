"""
系统托盘 + 全局热键 + 开机自启动
"""

import os
import sys
import json
from pathlib import Path

from PyQt6.QtCore    import QObject, pyqtSignal, Qt
from PyQt6.QtGui     import QIcon, QPixmap, QPainter, QColor, QFont, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

from desktop.config import APP_NAME, DATA_ROOT


# ── 生成默认图标（无需外部图片文件）────────────────
def make_tray_icon(color: str = "#58a6ff") -> QIcon:
    """动态生成托盘图标"""
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 28, 28)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 16, QFont.Weight.Bold))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "A")
    p.end()
    return QIcon(px)


# ── 系统托盘 ──────────────────────────────────────
class SystemTray(QObject):

    show_main    = pyqtSignal()
    show_float   = pyqtSignal()
    take_screenshot = pyqtSignal()
    quit_app     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(make_tray_icon())
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()

        act_main = QAction("🖥  打开主窗口", menu)
        act_main.triggered.connect(self.show_main)

        act_float = QAction("💬  悬浮窗", menu)
        act_float.triggered.connect(self.show_float)

        act_shot = QAction("📷  截图识别", menu)
        act_shot.triggered.connect(self.take_screenshot)

        menu.addAction(act_main)
        menu.addAction(act_float)
        menu.addSeparator()
        menu.addAction(act_shot)
        menu.addSeparator()

        act_quit = QAction("✕  退出", menu)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main.emit()

    def notify(self, title: str, msg: str, duration: int = 3000):
        self.tray.showMessage(title, msg,
            QSystemTrayIcon.MessageIcon.Information, duration)


# ── 全局热键（跨平台）────────────────────────────
class GlobalHotkey(QObject):
    """
    全局热键监听
    Windows: 使用 keyboard 库
    Linux:   使用 keyboard 库
    macOS:   使用 pynput
    """

    triggered = pyqtSignal(str)   # 发出热键名称

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hooks = {}
        self._active = False

    def register(self, hotkey_id: str, combo: str):
        """
        注册热键
        hotkey_id: 标识符，如 'activate' / 'screenshot'
        combo:     组合键字符串，如 'ctrl+shift+space'
        """
        try:
            import keyboard
            if hotkey_id in self._hooks:
                try:
                    keyboard.remove_hotkey(self._hooks[hotkey_id])
                except Exception:
                    pass

            hook = keyboard.add_hotkey(
                combo,
                lambda hid=hotkey_id: self.triggered.emit(hid),
                suppress=False
            )
            self._hooks[hotkey_id] = hook
            self._active = True
            return True
        except ImportError:
            print(f"[热键] keyboard 库未安装：pip install keyboard")
            return False
        except Exception as e:
            print(f"[热键] 注册失败 {combo}: {e}")
            return False

    def unregister_all(self):
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self._hooks.clear()

    @property
    def is_active(self) -> bool:
        return self._active


# ── 开机自启动 ────────────────────────────────────
class AutoStart:
    """管理开机自启动（Windows + Linux）"""

    APP_ID  = "agi-desktop"
    EXE     = sys.executable
    SCRIPT  = os.path.abspath(sys.argv[0])

    @classmethod
    def enable(cls) -> bool:
        try:
            if sys.platform == "win32":
                return cls._enable_windows()
            else:
                return cls._enable_linux()
        except Exception as e:
            print(f"[自启动] 启用失败: {e}")
            return False

    @classmethod
    def disable(cls) -> bool:
        try:
            if sys.platform == "win32":
                return cls._disable_windows()
            else:
                return cls._disable_linux()
        except Exception as e:
            print(f"[自启动] 禁用失败: {e}")
            return False

    @classmethod
    def is_enabled(cls) -> bool:
        try:
            if sys.platform == "win32":
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0, winreg.KEY_READ
                )
                winreg.QueryValueEx(key, cls.APP_ID)
                winreg.CloseKey(key)
                return True
            else:
                return cls._autostart_file().exists()
        except Exception:
            return False

    @classmethod
    def _enable_windows(cls) -> bool:
        import winreg
        cmd = f'"{cls.EXE}" "{cls.SCRIPT}" --minimized'
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, cls.APP_ID, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return True

    @classmethod
    def _disable_windows(cls) -> bool:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, cls.APP_ID)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return True

    @classmethod
    def _autostart_file(cls) -> Path:
        return (Path.home() / ".config" / "autostart" /
                f"{cls.APP_ID}.desktop")

    @classmethod
    def _enable_linux(cls) -> bool:
        desktop_file = cls._autostart_file()
        desktop_file.parent.mkdir(parents=True, exist_ok=True)
        desktop_file.write_text(
            f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Exec={cls.EXE} {cls.SCRIPT} --minimized
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
""")
        return True

    @classmethod
    def _disable_linux(cls) -> bool:
        f = cls._autostart_file()
        if f.exists():
            f.unlink()
        return True
