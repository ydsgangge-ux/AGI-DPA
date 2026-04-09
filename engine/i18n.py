"""
国际化（i18n）模块
支持：中文 / English / 日本語 / 한국어 / Español / العربية
"""

LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "es": "Español",
    "ar": "العربية",
}

_STRINGS = {
    # ── App ──
    "app_name": {
        "zh": "AGI 认知助手",
        "en": "AGI Cognitive Assistant",
        "ja": "AGI 認知アシスタント",
        "ko": "AGI 인지 어시스턴트",
        "es": "Asistente Cognitivo AGI",
        "ar": "مساعد AGI المعرفي",
    },

    # ── Tabs ──
    "tab_chat":        {"zh":"💬 对话","en":"💬 Chat","ja":"💬 チャット","ko":"💬 대화","es":"💬 Chat","ar":"💬 محادثة"},
    "tab_memory":      {"zh":"🗄️ 记忆库","en":"🗄️ Memory","ja":"🗄️ メモリ","ko":"🗄️ 기억","es":"🗄️ Memoria","ar":"🗄️ الذاكرة"},
    "tab_personality": {"zh":"🎭 人格设定","en":"🎭 Personality","ja":"🎭 性格","ko":"🎭 성격","es":"🎭 Personalidad","ar":"🎭 الشخصية"},
    "tab_tools":       {"zh":"🔬 工具测试","en":"🔬 Tools","ja":"🔬 ツール","ko":"🔬 도구","es":"🔬 Herramientas","ar":"🔬 الأدوات"},
    "tab_coder":       {"zh":"💻 编程","en":"💻 Coder","ja":"💻 コーダー","ko":"💻 코더","es":"💻 Programador","ar":"💻 البرمجة"},
    "tab_face":        {"zh":"👁️ 人脸","en":"👁️ Face","ja":"👁️ 顔認識","ko":"👁️ 얼굴","es":"👁️ Rostro","ar":"👁️ الوجه"},
    "tab_profile":     {"zh":"👤 用户画像","en":"👤 Profile","ja":"👤 プロフィール","ko":"👤 프로필","es":"👤 Perfil","ar":"👤 الملف الشخصي"},
    "tab_graph":       {"zh":"🕸️ 记忆网络","en":"🕸️ Memory Graph","ja":"🕸️ 記憶グラフ","ko":"🕸️ 기억 그래프","es":"🕸️ Grafo de Memoria","ar":"🕸️ شبكة الذاكرة"},
    "tab_learner":     {"zh":"🎓 主动学习","en":"🎓 Learning","ja":"🎓 学習","ko":"🎓 학습","es":"🎓 Aprendizaje","ar":"🎓 التعلم"},
    "tab_settings":    {"zh":"⚙️ 设置","en":"⚙️ Settings","ja":"⚙️ 設定","ko":"⚙️ 설정","es":"⚙️ Ajustes","ar":"⚙️ الإعدادات"},

    # ── Chat ──
    "input_placeholder": {
        "zh": "输入消息，Enter 发送，Shift+Enter 换行",
        "en": "Type a message, Enter to send, Shift+Enter for newline",
        "ja": "メッセージを入力，Enter で送信，Shift+Enter で改行",
        "ko": "메시지 입력, Enter 전송, Shift+Enter 줄바꿈",
        "es": "Escribe un mensaje, Enter para enviar, Shift+Enter para nueva línea",
        "ar": "اكتب رسالة، Enter للإرسال، Shift+Enter لسطر جديد",
    },
    "thinking":    {"zh":"⏳ 思考中…","en":"⏳ Thinking…","ja":"⏳ 考え中…","ko":"⏳ 생각 중…","es":"⏳ Pensando…","ar":"⏳ يفكر…"},
    "send":        {"zh":"发送","en":"Send","ja":"送信","ko":"보내기","es":"Enviar","ar":"إرسال"},
    "ready":       {"zh":"就绪","en":"Ready","ja":"準備完了","ko":"준비","es":"Listo","ar":"جاهز"},
    "processing":  {"zh":"🔄 处理中…","en":"🔄 Processing…","ja":"🔄 処理中…","ko":"🔄 처리 중…","es":"🔄 Procesando…","ar":"🔄 جاري المعالجة…"},

    # ── Settings ──
    "settings_llm":      {"zh":"LLM 配置","en":"LLM Configuration","ja":"LLM 設定","ko":"LLM 설정","es":"Configuración LLM","ar":"إعداد نموذج اللغة"},
    "settings_provider": {"zh":"服务商","en":"Provider","ja":"プロバイダー","ko":"공급자","es":"Proveedor","ar":"المزود"},
    "settings_api_key":  {"zh":"API Key","en":"API Key","ja":"APIキー","ko":"API 키","es":"Clave API","ar":"مفتاح API"},
    "settings_model":    {"zh":"模型","en":"Model","ja":"モデル","ko":"모델","es":"Modelo","ar":"النموذج"},
    "settings_save":     {"zh":"💾 保存设置","en":"💾 Save Settings","ja":"💾 設定を保存","ko":"💾 설정 저장","es":"💾 Guardar Ajustes","ar":"💾 حفظ الإعدادات"},
    "settings_saved":    {"zh":"✅ 已保存，重启后生效","en":"✅ Saved. Restart to apply.","ja":"✅ 保存済み。再起動後に反映。","ko":"✅ 저장됨. 재시작 후 적용.","es":"✅ Guardado. Reinicia para aplicar.","ar":"✅ تم الحفظ. أعد التشغيل للتطبيق."},
    "language":          {"zh":"界面语言","en":"Interface Language","ja":"インターフェース言語","ko":"인터페이스 언어","es":"Idioma de interfaz","ar":"لغة الواجهة"},

    # ── Memory ──
    "memory_search":   {"zh":"语义搜索记忆…","en":"Search memories…","ja":"記憶を検索…","ko":"기억 검색…","es":"Buscar memorias…","ar":"البحث في الذاكرة…"},
    "memory_refresh":  {"zh":"刷新","en":"Refresh","ja":"更新","ko":"새로고침","es":"Actualizar","ar":"تحديث"},
    "memory_clear":    {"zh":"🗑 清除记忆","en":"🗑 Clear Memory","ja":"🗑 記憶をクリア","ko":"🗑 기억 지우기","es":"🗑 Limpiar Memoria","ar":"🗑 مسح الذاكرة"},
    "memory_dblclick": {"zh":"双击查看完整内容","en":"Double-click for full content","ja":"ダブルクリックで全文表示","ko":"더블클릭으로 전체 내용 보기","es":"Doble clic para contenido completo","ar":"انقر نقرًا مزدوجًا للمحتوى الكامل"},

    # ── Auth ──
    "auth_verified":   {"zh":"🟢 已认证","en":"🟢 Verified","ja":"🟢 認証済み","ko":"🟢 인증됨","es":"🟢 Verificado","ar":"🟢 موثق"},
    "auth_guest":      {"zh":"🔴 游客模式（点击解锁）","en":"🔴 Guest Mode (click to unlock)","ja":"🔴 ゲストモード（クリックで解除）","ko":"🔴 게스트 모드 (클릭하여 잠금 해제)","es":"🔴 Modo Invitado (clic para desbloquear)","ar":"🔴 وضع الضيف (انقر للفتح)"},
    "auth_no_user":    {"zh":"🟡 未注册用户（点击注册）","en":"🟡 No user registered (click to register)","ja":"🟡 未登録（クリックで登録）","ko":"🟡 미등록 사용자 (클릭하여 등록)","es":"🟡 Sin usuario registrado (clic para registrar)","ar":"🟡 لا يوجد مستخدم مسجل (انقر للتسجيل)"},
    "login":           {"zh":"🔑  登录","en":"🔑  Login","ja":"🔑  ログイン","ko":"🔑  로그인","es":"🔑  Iniciar sesión","ar":"🔑  تسجيل الدخول"},
    "register":        {"zh":"✨  注册新用户","en":"✨  Register","ja":"✨  新規登録","ko":"✨  등록","es":"✨  Registrarse","ar":"✨  التسجيل"},

    # ── Personality ──
    "personality_save":    {"zh":"💾  保存","en":"💾  Save","ja":"💾  保存","ko":"💾  저장","es":"💾  Guardar","ar":"💾  حفظ"},
    "personality_confirm": {"zh":"确认保存人格设定","en":"Confirm Save Personality","ja":"性格設定を保存しますか","ko":"성격 설정 저장 확인","es":"Confirmar guardar personalidad","ar":"تأكيد حفظ الشخصية"},

    # ── TTS ──
    "tts_speak":  {"zh":"朗读","en":"Speak","ja":"読み上げ","ko":"읽기","es":"Leer","ar":"قراءة"},
    "tts_stop":   {"zh":"停止","en":"Stop","ja":"停止","ko":"중지","es":"Detener","ar":"إيقاف"},

    # ── Float Window ──
    "screenshot": {
        "zh": "截图识别", "en": "Screenshot OCR", "ja": "スクリーンショット",
        "ko": "스크린샷", "es": "Captura de pantalla", "ar": "لقطة شاشة",
    },
    "float_input_placeholder": {
        "zh": "说话或下达任务…", "en": "Talk or give a task…", "ja": "話しかけるか指示を…",
        "ko": "말하거나 명령하세요…", "es": "Habla o da una tarea…", "ar": "تحدث أو أعطِ مهمة…",
    },

    # ── AGI system prompt language instruction ──
    "system_lang_instruction": {
        "zh": "请始终用中文回复用户。",
        "en": "Always reply to the user in English.",
        "ja": "常に日本語でユーザーに返信してください。",
        "ko": "항상 한국어로 사용자에게 답하세요.",
        "es": "Siempre responde al usuario en español.",
        "ar": "الرجاء الرد دائمًا على المستخدم باللغة العربية.",
    },
}


_current_lang = "zh"


def set_language(lang: str):
    global _current_lang
    if lang in LANGUAGES:
        _current_lang = lang


def get_language() -> str:
    return _current_lang


def t(key: str, lang: str = None) -> str:
    """翻译一个 key，返回当前语言的文本"""
    lang = lang or _current_lang
    entry = _STRINGS.get(key, {})
    return entry.get(lang) or entry.get("en") or key


def get_system_lang_instruction() -> str:
    """返回注入 AGI 系统提示的语言指令"""
    return t("system_lang_instruction")
