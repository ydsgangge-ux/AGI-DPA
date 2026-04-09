"""
engine/db_guard.py  —  SQLite 数据库保护层

功能：
1. 启动时完整性检查 (PRAGMA integrity_check)
2. 自动开启 WAL 模式（崩溃安全）
3. 自动轮转备份（最多保留 N 份）
4. Schema 版本管理（替代 try/except 猜测写法）
5. 自动迁移缺失列（安全、幂等）

用法：
    from engine.db_guard import guarded_connect, init_guard

    # 启动时调用一次（检查 + 备份 + WAL）
    init_guard(db_path)

    # 日常使用（替代 sqlite3.connect）
    with guarded_connect(db_path) as conn:
        conn.execute("INSERT ...")
"""

import sqlite3
import shutil
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════
MAX_BACKUPS = 3          # 最多保留几份备份
BACKUP_ON_WRITE = False  # 是否每次写入前备份（默认关闭，由 init_guard 的 backup_first 开启）

_lock = threading.Lock()
_initialized_paths = set()

# Schema 版本号：每次改表结构时递增
# 存储在 _schema_versions 表中，格式 {table_name: version}
SCHEMA_VERSIONS = {
    "formed_cognition": 2,   # v1: 原始6列, v2: 新增 last_activated
    "memories": 2,           # v1: 原始列, v2: 新增 user_id
    "user_profile": 2,       # v1: (key,value,updated_at), v2: 新增 user_id
    "personality_traits": 2, # v1: (name,data_json,updated_at), v2: 新增 user_id
    "anomaly_records": 2,    # v1: (id,data_json,timestamp), v2: 新增 user_id
}


# ══════════════════════════════════════════════════════════
# 完整性检查 & 恢复
# ══════════════════════════════════════════════════════════
def _check_integrity(db_path: str) -> bool:
    """返回 True 表示数据库健康"""
    try:
        with sqlite3.connect(db_path) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result and result[0] == "ok"
    except Exception:
        return False


def _find_latest_backup(db_path: str) -> Optional[str]:
    """找到最新的备份文件"""
    db_dir = os.path.dirname(db_path) or "."
    db_name = os.path.basename(db_path)
    backups = []
    for f in os.listdir(db_dir):
        if f.startswith(db_name + ".bak.") and f.endswith(".db"):
            fpath = os.path.join(db_dir, f)
            backups.append((fpath, os.path.getmtime(fpath)))
    if not backups:
        return None
    backups.sort(key=lambda x: x[1], reverse=True)
    return backups[0][0]


def _recover_from_backup(db_path: str) -> bool:
    """尝试从备份恢复，返回是否成功"""
    backup = _find_latest_backup(db_path)
    if not backup:
        return False
    try:
        # 先把损坏的文件重命名
        corrupted = db_path + ".corrupted." + datetime.now().strftime("%Y%m%d%H%M%S")
        if os.path.exists(db_path):
            os.rename(db_path, corrupted)
        shutil.copy2(backup, db_path)
        return _check_integrity(db_path)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════
# 备份管理
# ══════════════════════════════════════════════════════════
def _rotate_backups(db_path: str, max_backups: int = MAX_BACKUPS):
    """轮转备份：保留最近 N 份，删除旧的"""
    db_dir = os.path.dirname(db_path) or "."
    db_name = os.path.basename(db_path)

    # 收集已有备份
    backups = []
    for f in os.listdir(db_dir):
        if f.startswith(db_name + ".bak.") and f.endswith(".db"):
            fpath = os.path.join(db_dir, f)
            backups.append((fpath, os.path.getmtime(fpath)))

    # 按时间倒序，删除超出限制的
    backups.sort(key=lambda x: x[1], reverse=True)
    for fpath, _ in backups[max_backups:]:
        try:
            os.remove(fpath)
        except OSError:
            pass


def create_backup(db_path: str) -> str:
    """创建一份备份，返回备份文件路径"""
    db_dir = os.path.dirname(db_path) or "."
    db_name = os.path.basename(db_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(db_dir, f"{db_name}.bak.{timestamp}.db")

    # 使用 SQLite 的 backup API 确保一致性
    try:
        source = sqlite3.connect(db_path)
        dest = sqlite3.connect(backup_path)
        source.backup(dest)
        dest.close()
        source.close()
    except Exception:
        # fallback: 文件复制
        if os.path.exists(db_path):
            shutil.copy2(db_path, backup_path)

    _rotate_backups(db_path)
    return backup_path


# ══════════════════════════════════════════════════════════
# WAL 模式
# ══════════════════════════════════════════════════════════
def _enable_wal(db_path: str):
    """开启 WAL 模式，大幅降低崩溃损坏风险"""
    try:
        with sqlite3.connect(db_path) as conn:
            # journal_mode=WAL: 写入不阻塞读，崩溃恢复更好
            conn.execute("PRAGMA journal_mode=WAL")
            # synchronous=NORMAL: 性能与安全平衡
            conn.execute("PRAGMA synchronous=NORMAL")
            # busy_timeout: 避免并发锁冲突立即报错
            conn.execute("PRAGMA busy_timeout=5000")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
# Schema 迁移（版本管理）
# ══════════════════════════════════════════════════════════
def _get_table_version(conn, table: str) -> int:
    """获取表的当前 schema 版本"""
    try:
        row = conn.execute(
            "SELECT version FROM _schema_versions WHERE table_name = ?",
            (table,)
        ).fetchone()
        return row[0] if row else 0
    except sqlite3.OperationalError:
        return 0  # _schema_versions 表不存在


def _set_table_version(conn, table: str, version: int):
    """记录表的 schema 版本"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _schema_versions (
            table_name TEXT PRIMARY KEY, version INTEGER NOT NULL
        )
    """)
    conn.execute(
        "INSERT OR REPLACE INTO _schema_versions (table_name, version) VALUES (?, ?)",
        (table, version)
    )


def _rebuild_formed_cognition(conn):
    """formed_cognition 表 schema 损坏时：读数据 → 删表 → 重建 → 灌回"""
    now = datetime.now().isoformat()
    rows = []
    try:
        rows = conn.execute(
            "SELECT id, content, source, \"trigger\", formed_at, strength FROM formed_cognition"
        ).fetchall()
    except Exception:
        try:
            rows = conn.execute("SELECT * FROM formed_cognition").fetchall()
            rows = [r[:6] for r in rows]
        except Exception:
            return  # 连数据都读不出来，放弃

    conn.execute("DROP TABLE IF EXISTS formed_cognition")
    conn.execute("""
        CREATE TABLE formed_cognition (
            id              TEXT PRIMARY KEY,
            content         TEXT NOT NULL,
            source          TEXT NOT NULL,
            "trigger"       TEXT,
            formed_at       TEXT NOT NULL,
            strength        REAL DEFAULT 1.0,
            last_activated  TEXT NOT NULL
        )
    """)
    for r in rows:
        conn.execute(
            'INSERT OR IGNORE INTO formed_cognition (id, content, source, "trigger", formed_at, strength, last_activated) VALUES (?,?,?,?,?,?,?)',
            (r[0], r[1], r[2], r[3], r[4], r[5] if len(r) > 5 else 1.0, now)
        )


def _migrate_table(conn, table: str, target_version: int):
    """执行指定表的迁移，幂等、安全"""
    current = _get_table_version(conn, table)
    if current >= target_version:
        return  # 已是最新

    now = datetime.now().isoformat()

    # ── formed_cognition 迁移 ──
    if table == "formed_cognition" and target_version >= 2:
        try:
            # 先测试表是否健康
            conn.execute("SELECT last_activated FROM formed_cognition LIMIT 1")
            # 查询成功，检查列是否存在
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "last_activated" not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN last_activated TEXT NOT NULL DEFAULT ?",
                    (now,)
                )
        except sqlite3.OperationalError as e:
            if "no such column" in str(e):
                # 列不存在，尝试 ALTER
                try:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN last_activated TEXT NOT NULL DEFAULT ?",
                        (now,)
                    )
                except Exception:
                    # ALTER 也失败，重建表
                    print("[db_guard] formed_cognition 迁移失败，重建表...")
                    _rebuild_formed_cognition(conn)
            else:
                # 其他错误（如 syntax error = schema 损坏），重建表
                print(f"[db_guard] formed_cognition 表异常 ({e})，重建表...")
                _rebuild_formed_cognition(conn)

    # ── memories 迁移 ──
    if table == "memories" and target_version >= 2:
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "user_id" not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT 'default'"
                )
        except Exception:
            pass

    # ── user_profile / personality_traits / anomaly_records 迁移 ──
    if table in ("user_profile", "personality_traits", "anomaly_records") and target_version >= 2:
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "user_id" not in cols:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT 'default'"
                )
        except Exception:
            pass

    _set_table_version(conn, table, target_version)


def run_migrations(db_path: str):
    """执行所有表的 schema 迁移"""
    try:
        with sqlite3.connect(db_path) as conn:
            for table, version in SCHEMA_VERSIONS.items():
                _migrate_table(conn, table, version)
            conn.commit()
    except Exception:
        pass  # 迁移失败不阻塞启动


# ══════════════════════════════════════════════════════════
# 公开 API
# ══════════════════════════════════════════════════════════
def init_guard(db_path: str, backup_first: bool = True) -> bool:
    """
    初始化数据库保护层，启动时调用一次。
    
    Args:
        db_path: 数据库文件路径
        backup_first: 是否在初始化时先备份一份
    
    Returns:
        True 表示数据库健康，False 表示经过了恢复
    """
    with _lock:
        if db_path in _initialized_paths:
            return True
        _initialized_paths.add(db_path)

    db_dir = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(db_dir, exist_ok=True)

    db_exists = os.path.exists(db_path)

    if db_exists:
        # 1. 完整性检查
        if not _check_integrity(db_path):
            print(f"[db_guard] ⚠ 数据库损坏，尝试从备份恢复: {db_path}")
            if _recover_from_backup(db_path):
                print("[db_guard] ✅ 从备份恢复成功")
            else:
                print("[db_guard] ❌ 无可用备份，数据库需要重建")

        # 2. 初始化前备份
        if backup_first:
            try:
                bak = create_backup(db_path)
                print(f"[db_guard] 备份已创建: {bak}")
            except Exception as e:
                print(f"[db_guard] 备份失败(不影响运行): {e}")

    # 3. 开启 WAL 模式
    _enable_wal(db_path)

    # 4. 执行 schema 迁移
    run_migrations(db_path)

    return _check_integrity(db_path)


def guarded_connect(db_path: str, timeout: float = 10.0):
    """
    安全连接数据库。
    
    自动开启 WAL + busy_timeout，替代裸 sqlite3.connect()。
    用法与 sqlite3.connect 完全一致，支持 with 上下文管理器。
    """
    conn = sqlite3.connect(db_path, timeout=timeout)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
    except Exception:
        pass
    return conn
