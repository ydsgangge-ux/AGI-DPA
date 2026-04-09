"""
截图 + OCR 模块
支持：全屏截图、区域选择截图、OCR 文字识别
"""

import base64
import io
import os
import sys
import tempfile
from typing import Optional, Tuple

from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QThread
from PyQt6.QtGui import (QPixmap, QPainter, QColor, QPen,
                          QGuiApplication, QFont)
from PyQt6.QtWidgets import QWidget, QApplication, QRubberBand


# ── OCR 引擎（自动降级）──────────────────────────
def ocr_from_pixmap(pixmap: QPixmap, lang: str = "chi_sim+eng") -> str:
    """从 QPixmap 提取文字，自动选择可用引擎"""

    # 转为 PIL Image
    buf = io.BytesIO()
    ba = pixmap.toImage()
    ba.save(buf := io.BytesIO(), "PNG")  # type: ignore
    buf.seek(0)

    try:
        from PIL import Image as PILImage
        pil_img = PILImage.open(buf)
    except ImportError:
        return "[需要安装 Pillow: pip install Pillow]"

    # 优先 pytesseract
    try:
        import pytesseract
        text = pytesseract.image_to_string(pil_img, lang=lang)
        return text.strip()
    except Exception:
        pass

    # 降级 easyocr
    try:
        import easyocr
        import numpy as np
        reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        arr = np.array(pil_img)
        results = reader.readtext(arr)
        return "\n".join(r[1] for r in results)
    except Exception:
        pass

    return "[OCR 不可用：请安装 pytesseract 或 easyocr]"


def pixmap_to_base64(pixmap: QPixmap) -> str:
    buf = io.BytesIO()
    img = pixmap.toImage()
    ba = io.BytesIO()
    # 通过临时文件转换
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    pixmap.save(tmp, "PNG")
    with open(tmp, "rb") as f:
        data = f.read()
    os.unlink(tmp)
    return base64.b64encode(data).decode()


# ── 区域选择截图窗口 ──────────────────────────────
class ScreenshotSelector(QWidget):
    """
    全屏半透明遮罩，拖拽选择截图区域
    选完后发出 captured(QPixmap) 信号
    """

    captured = pyqtSignal(QPixmap, QRect)   # 截图内容 + 区域
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()

        # 捕获整个虚拟桌面（多显示器）
        screen = QGuiApplication.primaryScreen()
        self._full_pixmap = screen.grabWindow(0)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())
        self.showFullScreen()

        self._origin: Optional[QPoint] = None
        self._rubber  = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._rect: Optional[QRect] = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin = e.pos()
            self._rubber.setGeometry(QRect(self._origin, self._origin))
            self._rubber.show()

    def mouseMoveEvent(self, e):
        if self._origin:
            self._rect = QRect(self._origin, e.pos()).normalized()
            self._rubber.setGeometry(self._rect)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._rect:
            self._rubber.hide()
            self.hide()
            # 裁剪截图
            cropped = self._full_pixmap.copy(self._rect)
            self.captured.emit(cropped, self._rect)
            self.close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()

    def paintEvent(self, e):
        painter = QPainter(self)
        # 半透明遮罩
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        # 提示文字
        painter.setPen(QColor(255, 255, 255, 200))
        painter.setFont(QFont(
            "Microsoft YaHei" if sys.platform == "win32" else "sans-serif", 14
        ))
        painter.drawText(
            self.rect(), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            "\n拖拽选择截图区域  ·  ESC 取消"
        )


def take_fullscreen() -> QPixmap:
    """全屏截图"""
    screen = QGuiApplication.primaryScreen()
    return screen.grabWindow(0)


# ── OCR 异步线程 ──────────────────────────────────
class OCRThread(QThread):
    """后台运行 OCR，避免卡界面"""

    finished = pyqtSignal(str)   # OCR 结果文字
    error    = pyqtSignal(str)

    def __init__(self, pixmap: QPixmap, lang: str = "chi_sim+eng"):
        super().__init__()
        self.pixmap = pixmap
        self.lang   = lang

    def run(self):
        try:
            text = ocr_from_pixmap(self.pixmap, self.lang)
            self.finished.emit(text)
        except Exception as e:
            self.error.emit(str(e))
