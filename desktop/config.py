"""
应用配置和常量
"""
import os
import sys
import json
from pathlib import Path

# ── 路径 ──────────────────────────────────────────
APP_NAME    = "AGI 认知助手"
APP_VERSION = "1.0.0"

# 数据目录（跨平台）
if sys.platform == "win32":
    DATA_ROOT = Path(os.environ.get("APPDATA", str(Path.home()))) / "AGI-Desktop"
else:
    DATA_ROOT = Path.home() / ".agi-desktop"

DATA_ROOT.mkdir(parents=True, exist_ok=True)

CONFIG_FILE      = DATA_ROOT / "config.json"
PERSONALITY_FILE = DATA_ROOT / "personality.json"
DB_FILE          = str(DATA_ROOT / "memory.db")
LOG_FILE         = DATA_ROOT / "agi.log"

# ── 默认配置 ──────────────────────────────────────
DEFAULT_CONFIG = {
    "api_key":           "",
    "api_provider":      "deepseek",        # "deepseek" | "ollama"
    "ollama_url":        "http://localhost:11434",
    "ollama_model":      "qwen2.5:7b",
    "hotkey_activate":   "ctrl+shift+space",
    "hotkey_screenshot": "ctrl+shift+s",
    "autostart":         False,
    "tray_minimize":     True,
    "float_opacity":     0.95,
    "theme":             "dark",
    "window_geometry":   None,
    "ocr_language":      "chi_sim+eng",
    "verbose":           True,
    "newsapi_key":       "",     # NewsAPI.org API Key（可选，用于新闻工具）
    # ── 多模态模型配置（Vision）──
    "vision_provider":   "",     # 空则自动继承主 LLM，可设 "openai"/"claude"/"gemini"/"qwen"/"zhipu"/"ollama"
    "vision_model":      "",     # 空则用 provider 默认 vision 模型
    "vision_api_key":    "",     # 空则继承主 API Key
    "vision_base_url":   "",     # 自定义 API 地址（一般不用填）
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(saved)
            return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ── 样式表 ────────────────────────────────────────
DARK_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: 'Segoe UI', 'Microsoft YaHei', system-ui;
    font-size: 13px;
}
QSplitter::handle { background: #21262d; width: 1px; }

/* 输入框 */
QLineEdit, QTextEdit, QPlainTextEdit {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 7px 10px;
    color: #e6edf3;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QTextEdit:focus { border-color: #58a6ff; }

/* 按钮 */
QPushButton {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 7px 16px;
    color: #e6edf3;
    font-weight: 600;
}
QPushButton:hover  { background: #30363d; border-color: #58a6ff; }
QPushButton:pressed { background: #161b22; }
QPushButton#btn_primary {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #1f6feb, stop:1 #7c3aed);
    border: none; color: white;
}
QPushButton#btn_primary:hover { opacity: 0.9; }
QPushButton#btn_danger {
    background: #da3633; border: none; color: white;
}

/* 列表 / 树 */
QListWidget, QTreeWidget {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    outline: none;
}
QListWidget::item { padding: 6px 10px; border-radius: 4px; }
QListWidget::item:selected { background: #1f6feb; }
QListWidget::item:hover    { background: #21262d; }

/* 滚动条 */
QScrollBar:vertical {
    width: 6px; background: transparent;
}
QScrollBar::handle:vertical {
    background: #30363d; border-radius: 3px; min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #58a6ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* 标签页 */
QTabWidget::pane { border: 1px solid #30363d; border-radius: 6px; }
QTabBar::tab {
    background: #161b22; border: 1px solid #30363d;
    padding: 7px 16px; margin-right: 2px; border-radius: 4px 4px 0 0;
}
QTabBar::tab:selected { background: #21262d; border-bottom-color: #21262d; color: #58a6ff; }
QTabBar::tab:hover    { background: #21262d; }

/* 滑块 */
QSlider::groove:horizontal { height: 4px; background: #30363d; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0;
    background: #58a6ff; border-radius: 7px;
}

/* 复选框 */
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #30363d; border-radius: 3px; }
QCheckBox::indicator:checked { background: #1f6feb; border-color: #1f6feb; }

/* 分组框 */
QGroupBox {
    border: 1px solid #30363d; border-radius: 8px;
    margin-top: 10px; padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #58a6ff; }

/* 状态栏 */
QStatusBar { background: #161b22; border-top: 1px solid #30363d; color: #8b949e; }

/* 工具提示 */
QToolTip { background: #21262d; border: 1px solid #58a6ff; color: #e6edf3; padding: 4px 8px; }

/* 菜单 */
QMenu { background: #161b22; border: 1px solid #30363d; border-radius: 6px; }
QMenu::item { padding: 6px 20px; }
QMenu::item:selected { background: #1f6feb; }
QMenu::separator { background: #30363d; height: 1px; margin: 4px 0; }
"""
