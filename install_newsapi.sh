#!/bin/bash
# NewsAPI Python SDK Installer
# Usage: bash install_newsapi.sh

echo ""
echo "========================================"
echo "  NewsAPI Python SDK Installer"
echo "========================================"
echo ""
echo "  NewsAPI 用于获取全球新闻资讯"
echo "  免费申请: https://newsapi.org/register"
echo ""

# 检测 Python
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
elif command -v python &>/dev/null; then
    PYTHON_CMD=python
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] 未找到 Python，请先安装 Python 3.9+"
    echo "        https://www.python.org/downloads/"
    exit 1
fi

echo "[INFO] 使用 $PYTHON_CMD"
echo ""

# 检查是否已安装
if $PYTHON_CMD -c "import newsapi" 2>/dev/null; then
    echo "[OK] newsapi-python 已安装，无需重复操作。"
    echo ""
    echo "若需要配置 API Key，请在应用设置中填写 newsapi_key。"
    exit 0
fi

# 安装
echo "[..] 正在安装 newsapi-python..."
echo ""
$PYTHON_CMD -m pip install newsapi-python

# 验证
if $PYTHON_CMD -c "import newsapi" 2>/dev/null; then
    echo ""
    echo "========================================"
    echo "  安装成功！"
    echo "========================================"
    echo ""
    echo "  下一步：配置 NewsAPI Key"
    echo "  1. 访问 https://newsapi.org/register 免费申请"
    echo "  2. 在 AGI 应用 "设置" 页面填写 newsapi_key"
    echo "  3. 或设置环境变量: export NEWSAPI_KEY=你的key"
    echo ""
    echo "  配置完成后即可使用新闻搜索功能。"
    echo "========================================"
    echo ""
else
    echo ""
    echo "[FAILED] 安装失败，请检查网络后重试："
    echo "          $PYTHON_CMD -m pip install newsapi-python"
    exit 1
fi
