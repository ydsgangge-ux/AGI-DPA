"""
AGI-DPA Mobile Server v2
- 由 main.py 调用 start_server(agent, auth_manager) 启动
- 完全共享同一个 ConsciousnessAgent 实例和 memory.db
- 手机用桌面端密码短语登录，记忆/人格完全互通
"""

import os
import secrets
import threading
from datetime import datetime, timedelta
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, Depends, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    raise ImportError("请先安装依赖：pip install fastapi uvicorn")

try:
    import jwt as pyjwt
except ImportError:
    raise ImportError("请先安装：pip install PyJWT")

# ── 全局共享实例（由 start_server 注入）─────────────────────
_agent        = None
_auth_manager = None
_SECRET_KEY   = os.environ.get("AGI_SECRET_KEY", secrets.token_hex(32))
ALGORITHM     = "HS256"
TOKEN_EXPIRE_DAYS = 30

# ── JWT ──────────────────────────────────────────────────────
def _create_token(user_id: str, name: str) -> str:
    payload = {
        "sub":  user_id,
        "name": name,
        "exp":  datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS),
    }
    return pyjwt.encode(payload, _SECRET_KEY, algorithm=ALGORITHM)

def _decode_token(token: str) -> Optional[dict]:
    try:
        return pyjwt.decode(token, _SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None

def _get_current_user(request: Request) -> dict:
    token = request.cookies.get("agi_token")
    if not token:
        ah = request.headers.get("Authorization", "")
        if ah.startswith("Bearer "):
            token = ah[7:]
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    payload = _decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期")
    if _auth_manager:
        user = _auth_manager.get_user(payload["sub"])
        if not user:
            raise HTTPException(status_code=401, detail="账户不存在")
    return {"user_id": payload["sub"], "name": payload.get("name", "")}

# ── FastAPI ──────────────────────────────────────────────────
app = FastAPI(title="AGI-DPA Mobile", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 简易登录速率限制 ──────────────────────────────────────
_login_attempts: dict[str, list[float]] = {}
_LOGIN_MAX = 5          # 最大尝试次数
_LOGIN_WINDOW = 300     # 时间窗口（秒）
_LOGIN_LOCKOUT = 60     # 锁定时长（秒）

class LoginRequest(BaseModel):
    passphrase: str

class ChatRequest(BaseModel):
    message: str

# ── 路由 ─────────────────────────────────────────────────────
@app.post("/api/login")
async def login(req: LoginRequest, response: Response):
    if not _auth_manager:
        raise HTTPException(status_code=503, detail="认证服务未就绪")

    # 速率限制
    import time as _time
    now = _time.time()
    ip = "unknown"
    attempts = _login_attempts.get(ip, [])
    # 清除过期记录
    attempts = [t for t in attempts if now - t < _LOGIN_WINDOW]
    # 检查是否锁定
    if len(attempts) >= _LOGIN_MAX:
        last = attempts[-_LOGIN_MAX]
        if now - last < _LOGIN_LOCKOUT:
            raise HTTPException(status_code=429, detail="登录尝试过多，请稍后再试")
        attempts = attempts[-(_LOGIN_MAX - 1):]  # 允许再试
    attempts.append(now)
    _login_attempts[ip] = attempts

    user = _auth_manager.verify_passphrase(req.passphrase)
    if not user:
        raise HTTPException(status_code=401, detail="密码短语错误")
    # 登录成功，清除记录
    _login_attempts.pop(ip, None)
    token = _create_token(user.user_id, user.name)
    response.set_cookie(
        key="agi_token", value=token,
        max_age=TOKEN_EXPIRE_DAYS * 86400,
        httponly=True, samesite="lax"
    )
    return {"ok": True, "name": user.name}

@app.post("/api/logout")
async def logout(response: Response, current: dict = Depends(_get_current_user)):
    response.delete_cookie("agi_token")
    return {"ok": True}

@app.get("/api/me")
async def me(current: dict = Depends(_get_current_user)):
    return {"user_id": current["user_id"], "name": current["name"]}

@app.post("/api/chat")
async def chat(req: ChatRequest, current: dict = Depends(_get_current_user)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    if _agent is None:
        raise HTTPException(status_code=503, detail="AGI引擎未就绪")

    user_id = current["user_id"]
    user    = _auth_manager.get_user(user_id) if _auth_manager else None

    # 临时切换 auth 为该用户，让 agent.process() 读到正确的 user_id
    if _auth_manager and user:
        _auth_manager.login(user)

    try:
        import asyncio
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _agent.process, req.message)
        reply  = result.get("response", str(result))
    except Exception as e:
        reply = f"引擎错误：{e}"

    return {"reply": reply, "timestamp": datetime.now().isoformat()}

@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML

# ── 对外启动接口（由 main.py 的 _on_engine_ready 调用）───────
def start_server(agent, auth_manager, host="0.0.0.0", port=18765):
    """在 daemon 线程里启动 uvicorn，不阻塞 Qt 主线程"""
    global _agent, _auth_manager
    _agent        = agent
    _auth_manager = auth_manager

    def _run():
        try:
            import socket
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "本机IP"
        print(f"\n📱 手机访问 → http://{ip}:{port}")
        print(f"💻 本机访问 → http://localhost:{port}")
        print(f"🔑 登录方式：桌面端密码短语\n")
        uvicorn.run(app, host=host, port=port, log_level="warning")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ── 内嵌前端 HTML ────────────────────────────────────────────
_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>AGI</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --ink:    #0a0c12;
  --paper:  #111520;
  --layer:  #181d2a;
  --rim:    #252d42;
  --muted:  #3d4a63;
  --dim:    #5a6a85;
  --soft:   #8899b8;
  --text:   #dde4f0;
  --bright: #f0f4ff;
  --blue:   #4a8fff;
  --indigo: #6c63f7;
  --teal:   #2dd4bf;
  --danger: #f04f5a;
  --ok:     #34d78a;
}

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;height:100dvh;background:var(--ink);color:var(--text);
  font-family:'Sora',sans-serif;overflow:hidden;-webkit-tap-highlight-color:transparent}

/* 登录页 */
#login{height:100dvh;display:flex;flex-direction:column;align-items:center;
  justify-content:center;padding:2rem;
  background:radial-gradient(ellipse 60% 40% at 50% 0%,rgba(74,143,255,.12) 0%,transparent 70%),
             radial-gradient(ellipse 40% 30% at 80% 80%,rgba(108,99,247,.08) 0%,transparent 60%)}

.brand{display:flex;align-items:center;gap:.6rem;margin-bottom:2.5rem}
.brand-mark{width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,var(--blue),var(--indigo));
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 24px rgba(74,143,255,.25)}
.brand-mark svg{width:18px;height:18px;fill:white}
.brand-name{font-family:'JetBrains Mono',monospace;font-size:1.1rem;font-weight:500;
  letter-spacing:.15em;color:var(--bright)}
.brand-name span{color:var(--blue)}

.card{width:100%;max-width:360px;background:var(--paper);border:1px solid var(--rim);
  border-radius:20px;padding:2rem;
  box-shadow:0 0 0 1px rgba(255,255,255,.03),0 32px 64px rgba(0,0,0,.6)}
.card-title{font-size:1.25rem;font-weight:600;color:var(--bright);margin-bottom:.3rem}
.card-sub{font-size:.8rem;color:var(--dim);margin-bottom:1.75rem;line-height:1.5}

.field{margin-bottom:1.1rem}
.field label{display:block;font-size:.7rem;font-weight:500;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);margin-bottom:.45rem}
.field input{width:100%;background:var(--layer);border:1px solid var(--rim);
  border-radius:10px;padding:.8rem 1rem;color:var(--text);
  font-family:'Sora',sans-serif;font-size:.95rem;outline:none;
  transition:border-color .2s,box-shadow .2s}
.field input:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(74,143,255,.12)}

.btn{width:100%;padding:.85rem;
  background:linear-gradient(135deg,var(--blue) 0%,var(--indigo) 100%);
  border:none;border-radius:10px;color:white;font-family:'Sora',sans-serif;
  font-size:.95rem;font-weight:600;cursor:pointer;
  box-shadow:0 4px 20px rgba(74,143,255,.3);transition:opacity .2s,transform .1s}
.btn:active{transform:scale(.98);opacity:.9}
.btn:disabled{opacity:.45;cursor:not-allowed}
.err{font-size:.8rem;color:var(--danger);min-height:1.2em;margin-top:.75rem;text-align:center}

/* 聊天页 */
#chat{display:none;flex-direction:column;height:100dvh}

.topbar{display:flex;align-items:center;justify-content:space-between;
  padding:.9rem 1.1rem;background:var(--paper);border-bottom:1px solid var(--rim);flex-shrink:0}
.topbar-left{display:flex;align-items:center;gap:.7rem}
.avatar{width:34px;height:34px;border-radius:50%;
  background:linear-gradient(135deg,var(--blue),var(--teal));
  display:flex;align-items:center;justify-content:center;
  font-size:.85rem;font-weight:600;color:white;
  box-shadow:0 0 12px rgba(45,212,191,.2);flex-shrink:0}
.topbar-info{line-height:1.3}
.topbar-name{font-size:.9rem;font-weight:600;color:var(--bright)}
.topbar-status{display:flex;align-items:center;gap:.35rem;font-size:.68rem;
  color:var(--dim);font-family:'JetBrains Mono',monospace}
.dot-live{width:6px;height:6px;border-radius:50%;background:var(--ok);
  box-shadow:0 0 6px var(--ok);animation:blink 2.4s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.btn-exit{background:none;border:1px solid var(--rim);border-radius:8px;
  padding:.38rem .75rem;color:var(--dim);font-family:'Sora',sans-serif;
  font-size:.75rem;cursor:pointer;transition:color .2s,border-color .2s}
.btn-exit:hover{color:var(--text);border-color:var(--muted)}

.msgs{flex:1;overflow-y:auto;padding:1.2rem 1rem;display:flex;flex-direction:column;
  gap:1rem;scroll-behavior:smooth;overscroll-behavior:contain}
.msgs::-webkit-scrollbar{width:3px}
.msgs::-webkit-scrollbar-thumb{background:var(--rim);border-radius:2px}

.empty{margin:auto;text-align:center;padding:2rem}
.empty-icon{width:52px;height:52px;margin:0 auto 1rem;border-radius:16px;
  background:linear-gradient(135deg,var(--blue),var(--indigo));
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 30px rgba(74,143,255,.2)}
.empty-icon svg{width:24px;height:24px;fill:white}
.empty-title{font-size:1rem;font-weight:600;color:var(--soft);margin-bottom:.3rem}
.empty-sub{font-size:.8rem;color:var(--muted);line-height:1.6}

.row{display:flex;flex-direction:column;max-width:80%;animation:rise .22s ease}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
.row.me{align-self:flex-end;align-items:flex-end}
.row.agi{align-self:flex-start;align-items:flex-start}
.row-label{font-size:.62rem;color:var(--muted);margin-bottom:.28rem;
  font-family:'JetBrains Mono',monospace;letter-spacing:.04em}
.bubble{padding:.72rem 1rem;border-radius:16px;font-size:.92rem;line-height:1.65;
  word-break:break-word;white-space:pre-wrap}
.row.me .bubble{background:linear-gradient(135deg,#1a3a6e,#1e2f5a);
  border:1px solid #2a4a8a;border-bottom-right-radius:4px;color:#d4e4ff}
.row.agi .bubble{background:var(--layer);border:1px solid var(--rim);
  border-bottom-left-radius:4px;color:var(--text)}

.typing{display:flex;gap:5px;align-items:center;padding:.72rem 1rem}
.typing span{width:7px;height:7px;border-radius:50%;background:var(--muted);
  animation:hop 1.3s ease-in-out infinite}
.typing span:nth-child(2){animation-delay:.18s}
.typing span:nth-child(3){animation-delay:.36s}
@keyframes hop{0%,60%,100%{transform:translateY(0);opacity:.6}30%{transform:translateY(-7px);opacity:1}}

.inputbar{display:flex;align-items:flex-end;gap:.6rem;padding:.8rem 1rem;
  padding-bottom:max(.8rem,env(safe-area-inset-bottom));
  background:var(--paper);border-top:1px solid var(--rim);flex-shrink:0}
.inputbar textarea{flex:1;background:var(--layer);border:1px solid var(--rim);
  border-radius:12px;padding:.65rem .9rem;color:var(--text);
  font-family:'Sora',sans-serif;font-size:.9rem;line-height:1.5;resize:none;outline:none;
  min-height:42px;max-height:130px;transition:border-color .2s,box-shadow .2s}
.inputbar textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(74,143,255,.1)}
.inputbar textarea::placeholder{color:var(--muted)}
.sendbtn{width:42px;height:42px;flex-shrink:0;border-radius:12px;
  background:linear-gradient(135deg,var(--blue),var(--indigo));border:none;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 4px 14px rgba(74,143,255,.35);transition:opacity .2s,transform .1s}
.sendbtn:active{transform:scale(.9);box-shadow:none}
.sendbtn:disabled{opacity:.35;cursor:not-allowed;box-shadow:none}
.sendbtn svg{width:17px;height:17px;fill:white}
</style>
</head>
<body>

<div id="login">
  <div class="brand">
    <div class="brand-mark">
      <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z"/></svg>
    </div>
    <div class="brand-name">AGI·<span>DPA</span></div>
  </div>
  <div class="card">
    <div class="card-title">欢迎回来</div>
    <div class="card-sub">使用桌面端设置的密码短语登录，<br>记忆与人格完全互通。</div>
    <div class="field">
      <label>密码短语</label>
      <input id="pp" type="password" placeholder="输入密码短语…" autocomplete="current-password">
    </div>
    <button class="btn" id="loginBtn" onclick="doLogin()">登录</button>
    <div class="err" id="loginErr"></div>
  </div>
</div>

<div id="chat">
  <div class="topbar">
    <div class="topbar-left">
      <div class="avatar" id="av">A</div>
      <div class="topbar-info">
        <div class="topbar-name" id="topName">AGI 助手</div>
        <div class="topbar-status"><div class="dot-live"></div><span id="topUid">在线</span></div>
      </div>
    </div>
    <button class="btn-exit" onclick="doLogout()">退出</button>
  </div>

  <div class="msgs" id="msgs">
    <div class="empty">
      <div class="empty-icon"><svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg></div>
      <div class="empty-title">你好</div>
      <div class="empty-sub">有什么我可以帮你的？</div>
    </div>
  </div>

  <div class="inputbar">
    <textarea id="inp" placeholder="输入消息…" rows="1"
      oninput="rsz(this)" onkeydown="onKey(event)"></textarea>
    <button class="sendbtn" id="sendBtn" onclick="send()">
      <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
    </button>
  </div>
</div>

<script>
async function checkAuth(){
  try{const r=await fetch('/api/me');if(r.ok){const d=await r.json();showChat(d.name,d.user_id);}}catch(e){}
}

async function doLogin(){
  const pp=document.getElementById('pp').value;
  const btn=document.getElementById('loginBtn');
  const err=document.getElementById('loginErr');
  if(!pp.trim()){err.textContent='请输入密码短语';return;}
  btn.disabled=true;btn.textContent='验证中…';err.textContent='';
  try{
    const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({passphrase:pp})});
    const d=await r.json();
    if(r.ok){showChat(d.name,'');}else{err.textContent=d.detail||'密码短语错误';}
  }catch(e){err.textContent='网络错误，请检查连接';}
  finally{btn.disabled=false;btn.textContent='登录';}
}

async function doLogout(){
  await fetch('/api/logout',{method:'POST'});
  document.getElementById('chat').style.display='none';
  document.getElementById('login').style.display='flex';
  document.getElementById('msgs').innerHTML=emptyHTML();
  document.getElementById('pp').value='';
}

function showChat(name,uid){
  document.getElementById('login').style.display='none';
  document.getElementById('chat').style.display='flex';
  document.getElementById('topName').textContent=name||'AGI 助手';
  document.getElementById('topUid').textContent=uid||'在线';
  document.getElementById('av').textContent=(name||'A')[0].toUpperCase();
  document.getElementById('inp').focus();
}

async function send(){
  const inp=document.getElementById('inp');
  const msg=inp.value.trim();if(!msg)return;
  clearEmpty();addRow('me',msg);inp.value='';rsz(inp);
  const t=addTyping();
  document.getElementById('sendBtn').disabled=true;
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});
    t.remove();
    if(r.status===401){doLogout();return;}
    const d=await r.json();addRow('agi',d.reply||'…');
  }catch(e){t.remove();addRow('agi','⚠️ 网络错误，请检查连接');}
  finally{document.getElementById('sendBtn').disabled=false;}
}

function addRow(who,text){
  const box=document.getElementById('msgs');
  const now=new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'});
  const el=document.createElement('div');el.className=`row ${who}`;
  el.innerHTML=`<div class="row-label">${who==='me'?'你':'AGI'}  ${now}</div><div class="bubble">${esc(text)}</div>`;
  box.appendChild(el);box.scrollTop=box.scrollHeight;
}

function addTyping(){
  const box=document.getElementById('msgs');
  const el=document.createElement('div');el.className='row agi';
  el.innerHTML='<div class="row-label">AGI</div><div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div>';
  box.appendChild(el);box.scrollTop=box.scrollHeight;return el;
}

function clearEmpty(){const e=document.querySelector('.empty');if(e)e.remove();}
function emptyHTML(){return'<div class="empty"><div class="empty-icon"><svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg></div><div class="empty-title">你好</div><div class="empty-sub">有什么我可以帮你的？</div></div>';}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function rsz(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,130)+'px';}
function onKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}}
document.getElementById('pp').addEventListener('keydown',e=>{if(e.key==='Enter')doLogin();});
checkAuth();
</script>
</body>
</html>
"""
