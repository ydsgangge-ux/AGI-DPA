#!/bin/bash
# SimLife 启动脚本

cd "$(dirname "$0")/.."

echo ""
echo "  ╔═══════════════════════════════╗"
echo "  ║       SimLife 生活模拟        ║"
echo "  ╚═══════════════════════════════╝"
echo ""
echo "[SimLife] 启动中... (端口 8765)"
echo "[SimLife] 浏览器将自动打开 http://127.0.0.1:8765"
echo ""

python -m simlife.backend.main --port 8765
