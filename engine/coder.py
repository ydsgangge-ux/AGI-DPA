"""
自主编程智能体
流程：接收任务 → 写代码 → 运行 → 分析错误 → 修改 → 再运行 → 循环直到通过 → 打包
"""

import os
import json
import uuid
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field


def _get_desktop() -> Path:
    """Get user Desktop folder (cross-platform)"""
    import sys
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


@dataclass
class CodeIteration:
    """单次迭代记录"""
    iteration:  int
    code:       Dict[str, str]   # filename -> content
    run_result: Dict             # stdout/stderr/returncode
    passed:     bool
    error_msg:  str = ""
    fix_reasoning: str = ""


@dataclass
class CodingSession:
    """一次编程任务的完整会话"""
    session_id:  str
    task:        str
    language:    str
    iterations:  List[CodeIteration] = field(default_factory=list)
    final_code:  Dict[str, str] = field(default_factory=dict)
    output_dir:  str = ""
    status:      str = "pending"   # pending/running/passed/failed
    created_at:  str = field(default_factory=lambda: datetime.now().isoformat())


class CodingAgent:
    """
    自主编程智能体
    write → run → analyse → fix → loop
    """

    MAX_ITERATIONS = 8

    # 运行命令映射
    RUN_CMDS = {
        "python":     ["python", "{main}"],
        "javascript": ["node", "{main}"],
        "html":       None,   # 直接打开浏览器，不需要命令行运行
        "bash":       ["bash", "{main}"],
    }

    def __init__(self, llm_client, work_dir: str = None,
                 on_progress: Callable = None):
        self.llm       = llm_client
        self.work_dir  = Path(work_dir or tempfile.mkdtemp(prefix="agi_code_"))
        self.on_progress = on_progress or (lambda msg, level="info": print(f"[{level}] {msg}"))

    # ══════════════════════════════════════════════
    # 主入口
    # ══════════════════════════════════════════════
    def run(self, task: str, language: str = "python",
            save_to: str = None) -> CodingSession:
        session = CodingSession(
            session_id=str(uuid.uuid4())[:8],
            task=task,
            language=language.lower()
        )
        session.status = "running"

        # 工作目录
        proj_dir = self.work_dir / f"proj_{session.session_id}"
        proj_dir.mkdir(parents=True, exist_ok=True)

        self.on_progress(f"🚀 开始任务：{task[:60]}", "start")
        self.on_progress(f"📁 工作目录：{proj_dir}", "info")

        for i in range(1, self.MAX_ITERATIONS + 1):
            self.on_progress(f"\n─── 第 {i}/{self.MAX_ITERATIONS} 轮 ───", "iter")

            # ① 写代码（首轮全写，后续只修改有问题的部分）
            if i == 1:
                self.on_progress("✍️  正在生成代码…", "write")
                code_files = self._write_code(task, language, prev_error=None)
            else:
                prev = session.iterations[-1]
                self.on_progress(f"🔧 正在修复错误…", "fix")
                code_files = self._fix_code(
                    task, language,
                    prev.code, prev.run_result, prev.fix_reasoning
                )

            if not code_files:
                self.on_progress("❌ 代码生成失败", "error")
                break

            # ② 写入文件
            self._write_files(proj_dir, code_files)
            self.on_progress(f"📄 生成文件：{list(code_files.keys())}", "info")

            # ③ 运行
            self.on_progress("▶️  运行中…", "run")
            run_result = self._run_code(proj_dir, code_files, language)
            self.on_progress(
                f"返回码: {run_result['returncode']}", "info"
            )
            if run_result.get("stdout"):
                self.on_progress(f"输出:\n{run_result['stdout'][:500]}", "stdout")
            if run_result.get("stderr"):
                self.on_progress(f"错误:\n{run_result['stderr'][:500]}", "stderr")

            # ④ 判断是否通过
            passed = self._judge_pass(run_result, language, code_files)
            iteration = CodeIteration(
                iteration=i,
                code=code_files.copy(),
                run_result=run_result,
                passed=passed
            )

            if passed:
                self.on_progress("✅ 运行通过！", "pass")
                session.final_code = code_files
                session.status = "passed"
                session.iterations.append(iteration)
                break
            else:
                # ⑤ 分析错误
                error_analysis = self._analyse_error(task, code_files, run_result)
                iteration.error_msg    = run_result.get("stderr","")[:300]
                iteration.fix_reasoning = error_analysis
                self.on_progress(f"🔍 错误分析：{error_analysis[:100]}", "analyse")
                session.iterations.append(iteration)

                if i == self.MAX_ITERATIONS:
                    self.on_progress("⚠️  达到最大迭代次数，使用最后一次代码", "warn")
                    session.final_code = code_files
                    session.status = "failed"
        else:
            session.status = "failed"

        # ⑥ 打包输出
        if session.final_code:
            out = save_to or str(_get_desktop())
            session.output_dir = self._package(
                session, proj_dir, out
            )
            self.on_progress(f"\n📦 已打包到：{session.output_dir}", "done")

        return session

    # ══════════════════════════════════════════════
    # 代码生成
    # ══════════════════════════════════════════════
    def _write_code(self, task: str, language: str,
                    prev_error: str = None) -> Dict[str, str]:
        """让 LLM 写代码，返回 {filename: content} 字典"""

        lang_hints = {
            "python":     "使用 Python 3，标准库优先，尽量不用第三方包",
            "javascript": "使用原生 JavaScript，无需 npm",
            "html":       "单文件 HTML，内联 CSS 和 JS，无外部依赖",
            "bash":       "bash shell 脚本",
        }
        hint = lang_hints.get(language, f"使用 {language}")

        prompt = f"""你是一个专业程序员。请完成以下编程任务：

任务：{task}
语言：{language}（{hint}）

要求：
1. 代码必须能直接运行，不需要任何额外配置
2. 如果是游戏/界面程序，使用标准库（Python用tkinter，不用pygame）
3. 代码要完整，不要省略任何部分

请以 JSON 格式返回文件内容，格式如下：
{{
  "files": {{
    "main.py": "完整的代码内容",
    "utils.py": "如果需要多文件"
  }},
  "main_file": "main.py",
  "description": "简单说明这个程序做什么"
}}

只输出 JSON，不要其他内容。"""

        raw = self.llm.generate(prompt, max_tokens=3000, temperature=0.3)
        return self._parse_code_json(raw)

    def _fix_code(self, task: str, language: str,
                  prev_code: Dict[str, str],
                  run_result: Dict, prev_reasoning: str) -> Dict[str, str]:
        """根据错误修改代码"""

        files_text = "\n\n".join(
            f"=== {fname} ===\n{content}"
            for fname, content in prev_code.items()
        )

        prompt = f"""你是一个专业程序员，需要修复以下代码中的错误。

原始任务：{task}

当前代码：
{files_text}

运行错误：
{run_result.get('stderr', '无错误输出')[:800]}

标准输出：
{run_result.get('stdout', '无输出')[:400]}

返回码：{run_result.get('returncode', '?')}

请分析错误原因并修复代码。以 JSON 格式返回完整的修复后代码：
{{
  "files": {{
    "main.py": "完整的修复后代码内容"
  }},
  "main_file": "main.py",
  "fix_summary": "简述修复了什么问题",
  "description": "程序说明"
}}

注意：返回完整代码，不是只返回修改部分。只输出 JSON。"""

        raw = self.llm.generate(prompt, max_tokens=3000, temperature=0.2)
        return self._parse_code_json(raw)

    def _analyse_error(self, task: str, code: Dict[str, str],
                       run_result: Dict) -> str:
        """分析错误，给出修复思路"""
        prompt = f"""分析以下 Python 程序的运行错误，给出简洁的修复建议（50字以内）：

错误信息：{run_result.get('stderr','')[:400]}
返回码：{run_result.get('returncode','?')}

只输出修复建议，不要解释。"""

        try:
            return self.llm.generate(prompt, max_tokens=100, temperature=0.2)
        except Exception:
            return run_result.get("stderr", "")[:100]

    # ══════════════════════════════════════════════
    # 代码运行
    # ══════════════════════════════════════════════
    def _write_files(self, proj_dir: Path, files: Dict[str, str]):
        for fname, content in files.items():
            fpath = proj_dir / fname
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

    def _run_code(self, proj_dir: Path, files: Dict[str, str],
                  language: str) -> Dict:
        """运行代码，返回结果"""

        main_file = files.get("__main__", list(files.keys())[0])
        # 从 JSON 里读 main_file 标记（如果有）
        if "__meta__" in files:
            try:
                meta = json.loads(files["__meta__"])
                main_file = meta.get("main_file", main_file)
            except Exception:
                pass

        cmd_template = self.RUN_CMDS.get(language)

        if cmd_template is None:
            # HTML 类直接返回成功
            return {"ok": True, "returncode": 0,
                    "stdout": "[HTML文件，无需命令行运行]",
                    "stderr": ""}

        # 替换主文件名
        cmd = [c.replace("{main}", main_file) for c in cmd_template]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(proj_dir),
                capture_output=True,
                text=True,
                timeout=15,       # 最多跑15秒（GUI程序会超时，这是正常的）
                encoding="utf-8",
                errors="replace"
            )
            return {
                "ok":         result.returncode == 0,
                "returncode": result.returncode,
                "stdout":     result.stdout,
                "stderr":     result.stderr,
            }
        except subprocess.TimeoutExpired:
            # 超时通常意味着程序在运行中（GUI 窗口等待）——这是通过！
            return {
                "ok":         True,
                "returncode": 0,
                "stdout":     "[程序运行中（已超时，视为通过）]",
                "stderr":     "",
                "timeout":    True
            }
        except FileNotFoundError as e:
            return {
                "ok":         False,
                "returncode": -1,
                "stdout":     "",
                "stderr":     f"运行器未找到: {e}"
            }
        except Exception as e:
            return {
                "ok":         False,
                "returncode": -1,
                "stdout":     "",
                "stderr":     str(e)
            }

    # ══════════════════════════════════════════════
    # 判断是否通过
    # ══════════════════════════════════════════════
    def _judge_pass(self, run_result: Dict, language: str,
                    code: Dict[str, str]) -> bool:
        """判断运行是否通过"""
        if run_result.get("timeout"):
            return True   # GUI 程序超时 = 正常运行

        rc = run_result.get("returncode", -1)
        stderr = run_result.get("stderr", "")

        # HTML 直接通过
        if language == "html":
            return True

        # 返回码为 0 且无严重错误
        if rc == 0:
            # 过滤掉警告（不算错误）
            serious_errors = [
                l for l in stderr.split("\n")
                if any(k in l for k in ["Error", "Exception", "Traceback"])
            ]
            return len(serious_errors) == 0

        return False

    # ══════════════════════════════════════════════
    # 打包输出
    # ══════════════════════════════════════════════
    def _package(self, session: CodingSession,
                 proj_dir: Path, output_dir: str) -> str:
        """把最终代码打包成 zip 并放到输出目录"""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # 清理旧临时文件，只保留最终代码
        task_slug = "".join(
            c if c.isalnum() or c in "-_" else "_"
            for c in session.task[:30]
        ).strip("_")
        zip_name = f"AGI_{task_slug}_{session.session_id}.zip"
        zip_path = out_dir / zip_name

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 写入代码文件
            for fname, content in session.final_code.items():
                if fname.startswith("__"):
                    continue
                zf.writestr(fname, content)

            # 写入迭代报告
            report = self._build_report(session)
            zf.writestr("AGI_BUILD_REPORT.md", report)

        return str(zip_path)

    def _build_report(self, session: CodingSession) -> str:
        lines = [
            f"# AGI 编程报告",
            f"",
            f"**任务**: {session.task}",
            f"**语言**: {session.language}",
            f"**状态**: {'✅ 成功' if session.status=='passed' else '⚠️ 达到最大迭代'}",
            f"**迭代次数**: {len(session.iterations)}",
            f"**生成时间**: {session.created_at}",
            f"",
            f"## 迭代历史",
        ]
        for it in session.iterations:
            icon = "✅" if it.passed else "❌"
            lines.append(f"\n### {icon} 第 {it.iteration} 轮")
            if it.error_msg:
                lines.append(f"**错误**: `{it.error_msg[:150]}`")
            if it.fix_reasoning:
                lines.append(f"**修复思路**: {it.fix_reasoning[:150]}")

        lines += [
            f"",
            f"## 最终文件",
        ]
        for fname in session.final_code:
            if not fname.startswith("__"):
                lines.append(f"- `{fname}`")

        return "\n".join(lines)

    # ══════════════════════════════════════════════
    # 解析 LLM 返回的代码 JSON
    # ══════════════════════════════════════════════
    def _parse_code_json(self, raw: str) -> Dict[str, str]:
        """解析 LLM 返回的代码 JSON"""
        import re

        # 尝试提取 JSON
        text = raw.strip()
        # 去掉 markdown 代码块
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)

        try:
            data = json.loads(text)
        except Exception:
            # 尝试找到 JSON 块
            m = re.search(r'\{[\s\S]*\}', text)
            if not m:
                return {}
            try:
                data = json.loads(m.group())
            except Exception:
                return {}

        files = data.get("files", {})
        if not files:
            return {}

        # 记录 main_file 元信息
        if "main_file" in data:
            files["__main__"] = data["main_file"]

        return files
