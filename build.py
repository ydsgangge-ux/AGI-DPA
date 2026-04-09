"""
打包脚本 - 合并版
python build.py windows   → dist/AGI-Desktop.exe
python build.py linux     → dist/AGI-Desktop
"""

import os, sys, subprocess, shutil
from pathlib import Path

APP_NAME = "AGI-Desktop"
BASE     = Path(__file__).parent


def _run(cmd):
    print(f"$ {' '.join(cmd[:6])} …")
    return subprocess.run(cmd, cwd=str(BASE)).returncode


def build(platform: str):
    sep = ";" if platform == "windows" else ":"

    cmd = [
        "pyinstaller",
        "--onefile",
        f"--name={APP_NAME}",
        f"--add-data=engine{sep}engine",
        f"--add-data=ui{sep}ui",
        f"--add-data=desktop{sep}desktop",
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=sqlite3",
        "--hidden-import=keyboard",
        "--hidden-import=docx",
        "--hidden-import=openpyxl",
        "--hidden-import=pptx",
        "--hidden-import=reportlab",
        "--hidden-import=reportlab.pdfbase",
        "--hidden-import=reportlab.pdfbase.ttfonts",
        "--hidden-import=reportlab.pdfgen",
        "--hidden-import=pdfplumber",
        "--collect-all=PyQt6",
    ]

    if platform == "windows":
        cmd.append("--windowed")   # 无控制台
        if (BASE / "assets/icon.ico").exists():
            cmd.append("--icon=assets/icon.ico")

    cmd.append("main.py")

    rc = _run(cmd)
    if rc == 0:
        out = BASE / "dist" / (f"{APP_NAME}.exe" if platform == "windows" else APP_NAME)
        size = out.stat().st_size / 1024 / 1024
        print(f"\n✅ 打包成功: {out}  ({size:.1f} MB)")
        if platform == "linux":
            os.chmod(str(out), 0o755)
    else:
        print("\n❌ 打包失败")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else ""
    if target in ("windows", "linux"):
        build(target)
    else:
        print("用法：python build.py [windows|linux]")
