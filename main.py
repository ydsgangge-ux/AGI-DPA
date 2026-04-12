"""
AGI 桌面应用 - 合并版主入口
所有模块自包含，无外部项目依赖
"""

import sys
import os
import json
import random
import time
import threading
from pathlib import Path
from datetime import datetime

# 把项目根目录加入路径（确保 engine / ui / desktop 都能找到）
APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR))


def _default_font():
    """Pick a reasonable default font based on platform"""
    if sys.platform == "win32":
        return "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        return "PingFang SC"
    else:
        return "Noto Sans CJK SC"

# 导入核心 Qt 模块（这里报错说明 PyQt6 没有安装）
try:
    from PyQt6.QtCore    import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen
    from PyQt6.QtGui     import QFont, QPixmap, QPainter, QColor
except ImportError as e:
    print(f"[致命错误] PyQt6 未安装: {e}")
    print("请运行：pip install PyQt6")
    input("按回车退出…")
    sys.exit(1)

# 导入应用模块（这里报错说明项目文件有问题）
try:
    from desktop.config  import APP_NAME, APP_VERSION, load_config, save_config, DARK_QSS, DB_FILE
    from desktop.system  import SystemTray, GlobalHotkey, AutoStart
    from desktop.screenshot import ScreenshotSelector, OCRThread
    from ui.main_window  import MainWindow, AGIWorker
    from ui.float_window import FloatingWindow
except Exception as e:
    import traceback
    err = traceback.format_exc()
    print(f"[启动错误] 模块加载失败:\n{err}")
    # 尝试弹窗
    try:
        _app = QApplication(sys.argv)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("模块加载失败")
        msg.setText(f"<b>启动失败：</b><br>{str(e)}")
        msg.setDetailedText(err)
        msg.exec()
    except Exception:
        input("按回车退出…")
    sys.exit(1)


# ── 情绪 → emoji 前缀映射（方案 D）─────────────────
EMOJI_MAP = {
    "joy":       "😊", "happy":     "😊",
    "sadness":   "😔", "sad":       "😔",
    "anger":     "😤", "angry":     "😤",
    "fear":      "😨", "scared":    "😨",
    "surprise":  "😲", "surprised": "😲",
    "curious":   "🤔", "nostalgic": "😌",
    "trust":     "🤝", "neutral":   "",
    "calm":      "😌", "excited":   "🤩",
    "confused":  "😕", "bored":     "😑",
    "anxious":   "😰", "love":      "🥰",
    "gratitude": "🙏", "pride":     "😄",
    "shame":     "😳", "disgust":   "🤢",
}


def _emotion_emoji(emotion: dict) -> str:
    """根据情绪字典返回 emoji 前缀"""
    if not emotion:
        return ""
    primary = emotion.get("primary", "neutral")
    intensity = emotion.get("intensity", 0)
    emoji = EMOJI_MAP.get(primary, "")
    if emoji and intensity < 0.3:
        return ""
    return emoji


# ── 启动闪屏 ─────────────────────────────────────
def make_splash() -> QSplashScreen:
    px = QPixmap(480, 280)
    px.fill(QColor("#0d1117"))
    p = QPainter(px)
    p.setPen(QColor("#58a6ff"))
    p.setFont(QFont(_default_font(), 36, QFont.Weight.Bold))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "🧠 AGI")
    p.setPen(QColor("#8b949e"))
    p.setFont(QFont(_default_font(), 13))
    from PyQt6.QtCore import QRect
    p.drawText(
        QRect(0, 170, 480, 40),
        Qt.AlignmentFlag.AlignCenter,
        "认知模拟系统 · 初始化中…"
    )
    p.setPen(QColor("#30363d"))
    p.drawRect(0, 0, 479, 279)
    p.end()
    splash = QSplashScreen(px)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    return splash


# ── AGI 核心异步加载线程 ─────────────────────────
class EngineLoader(QThread):
    """
    在后台线程初始化 AGI 核心
    界面先显示，核心加载完再激活
    """
    ready  = pyqtSignal(object)   # 加载成功，返回 agent
    failed = pyqtSignal(str)      # 加载失败，返回错误信息

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg

    def run(self):
        try:
            # 数据库保护层：完整性检查 + 备份 + WAL + 迁移
            from engine.db_guard import init_guard
            init_guard(DB_FILE)

            from engine.models         import PersonalityCore
            from engine.memory         import MemoryStore
            from engine.memory_manager import HierarchicalMemoryManager
            from engine.association    import MemoryAssociationNetwork
            from engine.llm_client     import create_client
            from engine.executor       import BLayerExecutor
            from engine.agent          import ConsciousnessAgent
            from engine.user_profile   import UserProfileManager
            from engine.learner        import GrowthEngine, FormedCognitionStore
            from engine.auth           import AuthManager
            from desktop.config        import PERSONALITY_FILE

            # 人格
            if Path(PERSONALITY_FILE).exists():
                with open(PERSONALITY_FILE, encoding="utf-8") as f:
                    personality = PersonalityCore.from_dict(json.load(f))
            else:
                personality = PersonalityCore(
                    name="AGI助手", worldview="保持好奇，认真生活"
                )

            # LLM 客户端
            provider = self.cfg.get("api_provider", "deepseek")
            llm = create_client(
                api_key      = self.cfg.get("api_key", "") or os.environ.get("DEEPSEEK_API_KEY", ""),
                provider     = provider,
                model        = self.cfg.get("llm_model", None),
                ollama_model = self.cfg.get("ollama_model", "qwen2.5:7b"),
                ollama_url   = self.cfg.get("ollama_url", "http://localhost:11434"),
            )

            # 语言设置
            try:
                from engine.i18n import set_language
                set_language(self.cfg.get("language", "zh"))
            except Exception:
                pass

            # 记忆 + 关联网络
            store  = MemoryStore(DB_FILE)
            net    = MemoryAssociationNetwork(DB_FILE)
            memory = HierarchicalMemoryManager(store, net, llm_client=llm)

            executor = BLayerExecutor(
                llm_client=llm,
                confirm_callback=None,  # 由主程序在运行时注入
                max_tool_steps=8,
                verbose=True
            )

            # 用户画像（与记忆数据库共用同一个文件）
            user_profile = UserProfileManager(DB_FILE)

            # 成长引擎（经历认知 + 人格漂移 + 主动学习）
            growth = GrowthEngine(
                db_path=DB_FILE,
                personality_file=str(PERSONALITY_FILE),
                llm_client=llm
            )
            cognition = FormedCognitionStore(DB_FILE)

            # 身份验证管理器
            auth = AuthManager(DB_FILE)

            # SimLife 生活状态客户端（可选，SimLife 未初始化不影响主系统）
            simlife_client = None
            try:
                from engine.simlife_client import SimLifeClient
                _sl = SimLifeClient()
                if _sl.is_available():
                    simlife_client = _sl
                    print("[SimLife] 生活状态模块已连接")
            except Exception as e:
                print(f"[SimLife] 未启用（{e}）")

            # SimLife 后端自动启动（后台线程，不依赖前端打开网页）
            try:
                from simlife.backend.main import app as simlife_app
                import uvicorn as _uvicorn
                def _run_simlife():
                    _uvicorn.run(simlife_app, host="127.0.0.1", port=8765,
                                  log_level="warning", access_log=False)
                _simlife_thread = threading.Thread(target=_run_simlife, daemon=True)
                _simlife_thread.start()
                print("[SimLife] 后端服务已在后台启动（端口 8765）")
            except Exception as e:
                print(f"[SimLife] 后端自动启动失败（{e}），将回退到文件读取模式")

            # SimLife 新用户引导：检测是否已初始化
            if not simlife_client or not simlife_client.is_available():
                print()
                print("=" * 56)
                print("  [SimLife] 生活模拟模块尚未初始化")
                print("  请在浏览器中打开 http://127.0.0.1:8765")
                print("  填写基本信息后点击「开始生成」即可")
                print("  初始化后重启本程序即可生效")
                print("=" * 56)
                print()

            agent = ConsciousnessAgent(
                personality=personality,
                memory_manager=memory,
                b_layer_executor=executor,
                user_profile=user_profile,
                growth_engine=growth,
                cognition_store=cognition,
                auth_manager=auth,
                simlife_client=simlife_client,
                verbose=True
            )
            self.ready.emit(agent)

        except Exception as e:
            import traceback
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")


# ── 主控制器 ─────────────────────────────────────
class AGIApp:

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName(APP_NAME)
        self.app.setApplicationVersion(APP_VERSION)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyleSheet(DARK_QSS)
        self.app.setFont(QFont(_default_font(), 9))

        self.cfg    = load_config()
        self.agent  = None
        self._float_worker = None
        self._ocr_thread   = None
        self._screenshot_selector = None

        # ── 闪屏 ──────────────────────────────────
        self.splash = make_splash()
        self.splash.show()
        self.app.processEvents()

        # ── 界面（先建好，核心后台加载）──────────
        self.main_win  = MainWindow(agent=None, db_file=DB_FILE)
        self.float_win = FloatingWindow(
            opacity=self.cfg.get("float_opacity", 0.95)
        )
        self.tray   = SystemTray()
        self.hotkey = GlobalHotkey()

        # ── 主动发言状态（全局，主窗口/悬浮窗共享）────────
        self._last_chat_time = time.time()
        self._proactive_wait_minutes = None
        self._proactive_scheduled_at = None
        self._proactive_count_today = 0
        self._proactive_date = datetime.now().date()
        self._pending_proactive_msg = None   # 最近一条待关联的主动发言

        # ── 图片生成状态（每 ~3 小时主动生成一张图）──────
        self._last_image_time = time.time()      # 上次生成图片的时间
        self._image_gen_interval = None           # 随机间隔（2.5~3.5 小时）
        self._image_gen_count_today = 0
        self._image_gen_date = datetime.now().date()

        self._connect_signals()
        self._register_hotkeys()

        # ── 空闲检测定时器（全局，不依赖悬浮窗）────────
        self._idle_timer = QTimer()
        self._idle_timer.timeout.connect(self._check_proactive)
        self._idle_timer.start(60_000)  # 每 60 秒检查一次

        # ── 图片生成定时器（每 5 分钟检查一次）──────────
        self._image_timer = QTimer()
        self._image_timer.timeout.connect(self._check_image_gen)
        self._image_timer.start(5 * 60_000)

        # ── 后台加载引擎 ─────────────────────────
        self.splash.showMessage(
            "  正在初始化 AGI 核心…",
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
            QColor("#58a6ff")
        )
        self._loader = EngineLoader(self.cfg)
        self._loader.ready.connect(self._on_engine_ready)
        self._loader.failed.connect(self._on_engine_failed)
        self._loader.start()

    # ── 引擎加载回调 ────────────────────────────
    def _on_engine_ready(self, agent):
        self.agent = agent
        self.main_win.agent = agent
        self.float_win.agent = agent  # 注入 agent 给悬浮窗主动发言用

        # 注入 simlife_client 给悬浮窗
        if hasattr(agent, 'simlife') and agent.simlife:
            self.float_win.simlife_client = agent.simlife
            # SimLife 状态刷新定时器（每 30 秒）
            self._simlife_timer = QTimer()
            self._simlife_timer.timeout.connect(self._refresh_simlife_float)
            self._simlife_timer.start(30_000)
            print("[SimLife] 悬浮窗状态面板已启用")

        # 把 LLM 客户端共享给编程智能体页
        self.main_win.coder_page.set_llm(agent.b.llm)

        # 启动记忆衰减定时器（每2小时衰减一次）
        self._decay_timer = QTimer()
        self._decay_timer.timeout.connect(self._apply_memory_decay)
        self._decay_timer.start(2 * 60 * 60 * 1000)   # 2小时

        self.splash.finish(self.main_win)
        self.tray.notify(APP_NAME, "AGI 核心就绪 ✅")

        from engine.memory import MemoryStore, _embedding_mode
        stats = MemoryStore(DB_FILE).get_stats()
        print(f"[就绪] 角色：{agent.personality.name}")
        print(f"[就绪] 记忆库：{stats['total']} 条")
        print(f"[就绪] 向量模式：{_embedding_mode}")

        # 启动身份验证（后台线程，不阻塞界面）
        if agent.auth:
            self.main_win.start_auth_verification(agent.auth)

        # 启动手机端 Web 服务（共享同一个 agent 实例）
        try:
            from server import start_server
            start_server(agent=agent, auth_manager=agent.auth)
        except ImportError as e:
            print(f"[手机端] Web 服务未启动（缺少依赖）：{e}")

    def _apply_memory_decay(self):
        """定时记忆衰减"""
        try:
            from engine.memory import MemoryStore
            store = MemoryStore(DB_FILE)
            store.apply_decay(decay_rate=0.995)
            print("[记忆衰减] 已执行")
        except Exception as e:
            print(f"[记忆衰减] 失败: {e}")

    def _refresh_simlife_float(self):
        """定时刷新悬浮窗 SimLife 状态面板"""
        if self.float_win.isVisible():
            self.float_win.refresh_simlife_state()

    # ── 全局主动发言（主窗口/悬浮窗共享）────────────────
    def _update_chat_time(self):
        """用户在任一窗口发消息时调用，重置空闲计时"""
        self._last_chat_time = time.time()
        self._proactive_wait_minutes = None

    def _on_main_message(self, text: str):
        """主窗口发消息时：重置空闲计时 + 注入主动发言上下文"""
        self._update_chat_time()
        if self._pending_proactive_msg and self.agent:
            self.agent._proactive_context = self._pending_proactive_msg
            self._pending_proactive_msg = None

    def _check_proactive(self):
        """每分钟检查是否该主动发言"""
        if not self.agent:
            return
        # 主窗口或悬浮窗至少有一个可见
        if not self.main_win.isVisible() and not self.float_win.isVisible():
            return

        # 每日上限5条
        today = datetime.now().date()
        if today != self._proactive_date:
            self._proactive_date = today
            self._proactive_count_today = 0
        if self._proactive_count_today >= 5:
            return

        idle_minutes = (time.time() - self._last_chat_time) / 60

        # 空闲不足30分钟，重置计划
        if idle_minutes < 30:
            self._proactive_wait_minutes = None
            return

        # 空闲刚满30分钟时，随机安排一个等待时间
        if self._proactive_wait_minutes is None:
            self._proactive_wait_minutes = random.randint(1, 30)
            self._proactive_scheduled_at = time.time()
            return

        # 检查是否到了预定时间
        waited = (time.time() - self._proactive_scheduled_at) / 60
        if waited < self._proactive_wait_minutes:
            return

        # 触发主动发言
        self._proactive_wait_minutes = None
        self._do_proactive_speak()

    def _do_proactive_speak(self):
        """在子线程里生成主动消息"""
        if not self.agent:
            return

        class _ProactiveWorker(QThread):
            done = pyqtSignal(str)
            def __init__(self, agent):
                super().__init__()
                self.agent = agent
            def run(self):
                try:
                    msg = self.agent.proactive_message()
                    if msg:
                        self.done.emit(msg)
                    else:
                        print("[主动发言] LLM 返回空，跳过")
                except Exception as e:
                    print(f"[主动发言] 生成失败: {e}")

        self._proactive_worker = _ProactiveWorker(self.agent)
        self._proactive_worker.done.connect(self._on_proactive_message)
        self._proactive_worker.start()

    def _on_proactive_message(self, message: str):
        """主动消息展示到可见的窗口（带勾选回复框）"""
        self._proactive_count_today += 1
        self._last_chat_time = time.time()
        print(f"[主动发言] 今日第 {self._proactive_count_today} 条: {message[:50]}")

        # 记录 pending，任何窗口的下次回复都会自动关联
        self._pending_proactive_msg = message

        # 追加到对话历史，用户回复时 process() 能看到上下文并一起存入记忆
        if self.agent:
            self.agent.conversation_history.append(
                {"role": "assistant", "content": message}
            )

        # 优先展示到悬浮窗（如果可见），否则展示到主窗口
        if self.float_win.isVisible():
            self.float_win.add_message(message, is_user=False, is_proactive=True)
            if not self.float_win._expanded:
                self.float_win._expand()
        elif self.main_win.isVisible():
            self.main_win.chat_page.add_ai_message(
                message, meta={"proactive": True}
            )
        else:
            # 两个窗口都不可见，用托盘通知
            self.tray.notify("AGI 主动消息", message)

    def _on_proactive_replied(self, proactive_msg: str, user_reply: str):
        """主动消息被回复：设标记，让 process() 存储时前面多拼一句"""
        if user_reply and self.agent:
            self.agent._proactive_context = proactive_msg

    # ── 主动图片生成（每 ~3 小时生成一张）────────────────
    def _check_image_gen(self):
        """定时检查是否该生成图片"""
        if not self.agent:
            return

        # 每日上限3张
        today = datetime.now().date()
        if today != self._image_gen_date:
            self._image_gen_date = today
            self._image_gen_count_today = 0
        if self._image_gen_count_today >= 3:
            return

        # 首次运行时随机设置间隔（2.5~3.5 小时）
        if self._image_gen_interval is None:
            self._image_gen_interval = random.randint(150, 210) * 60  # 秒

        elapsed = time.time() - self._last_image_time
        if elapsed < self._image_gen_interval:
            return

        # 触发图片生成
        self._image_gen_interval = random.randint(150, 210) * 60
        self._last_image_time = time.time()
        self._do_generate_image()

    def _do_generate_image(self):
        """在子线程中生成图片"""
        if not self.agent:
            return
        personality_dict = self.agent.personality.to_dict()

        class _ImageGenWorker(QThread):
            done = pyqtSignal(str, str)   # (image_path, caption)
            fail = pyqtSignal(str)

            def __init__(self, personality_dict):
                super().__init__()
                self.personality_dict = personality_dict

            def run(self):
                try:
                    from engine.image_gen import generate_and_download
                    result = generate_and_download(self.personality_dict)
                    if result:
                        prompt, image_path, image_type = result
                        caption = self._make_caption(image_type)
                        self.done.emit(image_path, caption)
                    else:
                        self.fail.emit("图片生成返回空结果")
                except Exception as e:
                    self.fail.emit(str(e))

            @staticmethod
            def _make_caption(image_type: str) -> str:
                """根据图片类型生成配文"""
                import random
                if image_type == "selfie":
                    captions = [
                        "拍了一张照，给你看看~",
                        "今天心情不错，分享一张自拍 ✨",
                        "刚拍的，觉得还不错~",
                        "路过这个场景忍不住拍了一张",
                        "给你看看我现在的样子~",
                    ]
                else:
                    captions = [
                        "这个风景好美，分享给你 ✨",
                        "看到了好美的景色~",
                        "今天的天空特别好看",
                        "这画面太治愈了，送给你",
                        "拍到的风景，想和你分享",
                    ]
                return random.choice(captions)

        self._image_worker = _ImageGenWorker(personality_dict)
        self._image_worker.done.connect(self._on_image_generated)
        self._image_worker.fail.connect(lambda e: print(f"[图片生成] 失败: {e}"))
        self._image_worker.start()

    def _on_image_generated(self, image_path: str, caption: str):
        """图片生成完成，展示到聊天区"""
        self._image_gen_count_today += 1
        print(f"[图片生成] 今日第 {self._image_gen_count_today} 张")

        # 追加到对话历史
        if self.agent:
            self.agent.conversation_history.append(
                {"role": "assistant", "content": f"[主动图片: {image_path}]\n{caption}"}
            )

        # 展示到可见窗口
        if self.float_win.isVisible():
            self.float_win.add_message(caption, is_user=False, is_proactive=True)
            if not self.float_win._expanded:
                self.float_win._expand()
        elif self.main_win.isVisible():
            chat = self.main_win.chat_page
            # 先显示文字消息
            chat.add_ai_message(caption, meta={"proactive": True})
            # 再显示图片气泡（AI 生成，靠左）
            chat._show_image_bubble(image_path, is_user=False)
        else:
            # 窗口都不可见，用托盘通知
            self.tray.notify("AGI 给你分享了一张图", caption)

    def _on_engine_failed(self, err: str):
        self.splash.finish(self.main_win)
        print(f"[警告] AGI 核心加载失败，进入降级模式\n{err[:300]}")
        # 不崩溃，只是功能降级——界面照常打开
        self.tray.notify(
            APP_NAME,
            "AGI 核心未就绪，请在设置中检查 API Key",
            duration=5000
        )



    # ── 信号连接 ─────────────────────────────────
    def _connect_signals(self):
        self.tray.show_main.connect(self._show_main)
        self.tray.show_float.connect(self._show_float)
        self.tray.take_screenshot.connect(self._start_screenshot)
        self.tray.quit_app.connect(self._quit)

        self.float_win.message_sent.connect(self._float_message)
        self.float_win.screenshot_requested.connect(self._start_screenshot)
        self.float_win.proactive_replied.connect(self._on_proactive_replied)

        self.hotkey.triggered.connect(self._on_hotkey)
        self.main_win.settings_page.settings_changed.connect(self._on_settings)

        # 主窗口发消息时重置空闲计时 + 注入主动发言上下文
        self.main_win.chat_page.message_sent.connect(self._on_main_message)

    def _register_hotkeys(self):
        self.hotkey.register(
            "activate",   self.cfg.get("hotkey_activate",   "ctrl+shift+space"))
        self.hotkey.register(
            "screenshot", self.cfg.get("hotkey_screenshot",  "ctrl+shift+s"))

    # ── 窗口控制 ─────────────────────────────────
    def _show_main(self):
        self.main_win.show()
        self.main_win.raise_()
        self.main_win.activateWindow()

    def _show_float(self):
        self.float_win.show()
        self.float_win.raise_()

    def _toggle_float(self):
        if self.float_win.isVisible():
            self.float_win.hide()
        else:
            self._show_float()

    def _on_hotkey(self, hid: str):
        if hid == "activate":
            self._toggle_float()
        elif hid == "screenshot":
            self._start_screenshot()

    # ── 截图 + OCR ───────────────────────────────
    def _start_screenshot(self):
        self._screenshot_selector = ScreenshotSelector()
        self._screenshot_selector.captured.connect(self._on_captured)

    def _on_captured(self, pixmap, rect):
        self.tray.notify("截图识别", "正在识别文字…", 2000)
        if self.float_win.isVisible():
            self.float_win.add_message("[截图已捕获，正在识别…]")
        self._ocr_thread = OCRThread(
            pixmap, self.cfg.get("ocr_language", "chi_sim+eng")
        )
        self._ocr_thread.finished.connect(self._on_ocr_done)
        self._ocr_thread.error.connect(
            lambda e: self.tray.notify("OCR 失败", e)
        )
        self._ocr_thread.start()

    def _on_ocr_done(self, text: str):
        self.main_win.receive_screenshot_text(text)
        if self.float_win.isVisible():
            self.float_win.add_message(f"识别到：{text[:60]}…")
        self.tray.notify("识别完成", f"{len(text)} 个字符")

    # ── 悬浮窗消息 ───────────────────────────────
    def _float_message(self, text: str):
        if not self.agent:
            self.float_win.add_message(
                "AGI 核心还未就绪，请稍候或检查设置"
            )
            return

        self._update_chat_time()
        # 注入主动发言上下文（如果有的话）
        if self._pending_proactive_msg:
            self.agent._proactive_context = self._pending_proactive_msg
            self._pending_proactive_msg = None

        self.float_win.set_thinking(True)
        worker = AGIWorker(self.agent, text)

        def on_done(r):
            self.float_win.set_thinking(False)
            e = r.get("emotion", {})
            self.float_win.update_emotion(
                e.get("primary", "neutral"),
                e.get("intensity", 0.3)
            )
            emoji = _emotion_emoji(e)
            resp = r.get("response", "…")
            self.float_win.add_message(f"{emoji} {resp}" if emoji else resp)

        def on_err(err):
            self.float_win.set_thinking(False)
            self.float_win.add_message(f"❌ {err}")

        worker.finished.connect(on_done)
        worker.error.connect(on_err)
        worker.start()
        self._float_worker = worker   # 防 GC

    # ── 设置变化 ─────────────────────────────────
    def _on_settings(self, cfg: dict):
        self.cfg = cfg
        save_config(cfg)
        # 重注册热键
        self.hotkey.unregister_all()
        self._register_hotkeys()
        # 重新加载引擎（新 API Key）
        self._loader = EngineLoader(cfg)
        self._loader.ready.connect(self._on_engine_ready)
        self._loader.failed.connect(self._on_engine_failed)
        self._loader.start()
        self.tray.notify("设置已更新", "正在重新连接 API…")

    def _quit(self):
        self.hotkey.unregister_all()
        self.app.quit()

    # ── 运行 ─────────────────────────────────────
    def run(self) -> int:
        start_minimized = "--minimized" in sys.argv
        if not start_minimized:
            # 引擎加载完再显示主窗口（最多等 15 秒）
            QTimer.singleShot(300, self._show_main)
        else:
            self.tray.notify(APP_NAME, "已在后台运行")

        print(f"[{APP_NAME} v{APP_VERSION}] 启动")
        print(f"  热键唤醒：{self.cfg.get('hotkey_activate')}")
        print(f"  热键截图：{self.cfg.get('hotkey_screenshot')}")
        return self.app.exec()


def main():
    # 顶层异常捕获：任何启动错误都弹窗显示，不再闪退
    try:
        app = AGIApp()
        sys.exit(app.run())
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[启动失败]\n{tb}")
        # 尝试用 Qt 显示错误弹窗
        try:
            if not QApplication.instance():
                _app = QApplication(sys.argv)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("启动失败")
            msg.setText(f"<b>AGI 启动时发生错误：</b><br><br>{str(e)}")
            msg.setDetailedText(tb)
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
