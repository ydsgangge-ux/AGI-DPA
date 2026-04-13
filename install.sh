#!/bin/bash
set -e

echo ""
echo " ========================================"
echo "   AGI Cognitive Assistant Installer"
echo " ========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo " [ERROR] Python 3 not found."
    echo " macOS:  brew install python3"
    echo " Ubuntu: sudo apt install python3 python3-pip"
    exit 1
fi

PYVER=$(python3 --version 2>&1 | cut -d' ' -f2)
echo " [OK] Python $PYVER found"

# Install core packages from requirements.txt
echo ""
echo " Installing required packages..."
python3 -m pip install --upgrade pip -q
python3 -m pip install -r requirements.txt -q
echo " [OK] Core packages installed"

# Install optional packages (one by one, with check)
echo ""
echo " Checking optional packages..."
echo ""

OFFICE_OK=true
TTS_OK=true

# edge-tts
if python3 -c "import edge_tts" 2>/dev/null; then
    echo " [OK] edge-tts        - already installed"
else
    echo " [..] edge-tts        - installing..."
    if python3 -m pip install edge-tts -q 2>/dev/null; then
        echo " [OK] edge-tts        - installed"
    else
        echo " [!!] edge-tts        - FAILED"
        TTS_OK=false
    fi
fi

# python-docx
if python3 -c "import docx" 2>/dev/null; then
    echo " [OK] python-docx    - already installed"
else
    echo " [..] python-docx    - installing..."
    if python3 -m pip install python-docx -q 2>/dev/null; then
        echo " [OK] python-docx    - installed"
    else
        echo " [!!] python-docx    - FAILED"
        OFFICE_OK=false
    fi
fi

# openpyxl
if python3 -c "import openpyxl" 2>/dev/null; then
    echo " [OK] openpyxl       - already installed"
else
    echo " [..] openpyxl       - installing..."
    if python3 -m pip install openpyxl -q 2>/dev/null; then
        echo " [OK] openpyxl       - installed"
    else
        echo " [!!] openpyxl       - FAILED"
        OFFICE_OK=false
    fi
fi

# python-pptx
if python3 -c "import pptx" 2>/dev/null; then
    echo " [OK] python-pptx    - already installed"
else
    echo " [..] python-pptx    - installing..."
    if python3 -m pip install python-pptx -q 2>/dev/null; then
        echo " [OK] python-pptx    - installed"
    else
        echo " [!!] python-pptx    - FAILED"
        OFFICE_OK=false
    fi
fi

# reportlab
if python3 -c "import reportlab" 2>/dev/null; then
    echo " [OK] reportlab      - already installed"
else
    echo " [..] reportlab      - installing..."
    if python3 -m pip install reportlab -q 2>/dev/null; then
        echo " [OK] reportlab      - installed"
    else
        echo " [!!] reportlab      - FAILED"
        OFFICE_OK=false
    fi
fi

# pdfplumber
if python3 -c "import pdfplumber" 2>/dev/null; then
    echo " [OK] pdfplumber     - already installed"
else
    echo " [..] pdfplumber     - installing..."
    if python3 -m pip install pdfplumber -q 2>/dev/null; then
        echo " [OK] pdfplumber     - installed"
    else
        echo " [!!] pdfplumber     - FAILED"
        OFFICE_OK=false
    fi
fi

# Pillow
if python3 -c "import PIL" 2>/dev/null; then
    echo " [OK] Pillow         - already installed"
else
    echo " [..] Pillow         - installing..."
    if python3 -m pip install Pillow -q 2>/dev/null; then
        echo " [OK] Pillow         - installed"
    else
        echo " [!!] Pillow         - FAILED"
        OFFICE_OK=false
    fi
fi

# yfinance
if python3 -c "import yfinance" 2>/dev/null; then
    echo " [OK] yfinance       - already installed"
else
    echo " [..] yfinance       - installing..."
    if python3 -m pip install yfinance -q 2>/dev/null; then
        echo " [OK] yfinance       - installed"
    else
        echo " [!!] yfinance       - FAILED"
    fi
fi

# newspaper3k
if python3 -c "import newspaper" 2>/dev/null; then
    echo " [OK] newspaper3k    - already installed"
else
    echo " [..] newspaper3k    - installing..."
    if python3 -m pip install newspaper3k lxml_html_clean -q 2>/dev/null; then
        echo " [OK] newspaper3k    - installed"
    else
        echo " [!!] newspaper3k    - FAILED"
    fi
fi

# lxml_html_clean (newspaper3k 依赖)
if python3 -c "import lxml_html_clean" 2>/dev/null; then
    echo " [OK] lxml_html_clean - already installed"
else
    echo " [..] lxml_html_clean - installing..."
    if python3 -m pip install lxml_html_clean -q 2>/dev/null; then
        echo " [OK] lxml_html_clean - installed"
    else
        echo " [!!] lxml_html_clean - FAILED"
    fi
fi

# fastapi / uvicorn / PyJWT (手机端 Web 服务)
if python3 -c "import fastapi" 2>/dev/null; then
    echo " [OK] fastapi/uvicorn/PyJWT - already installed"
else
    echo " [..] fastapi/uvicorn/PyJWT - installing..."
    if python3 -m pip install fastapi uvicorn PyJWT -q 2>/dev/null; then
        echo " [OK] fastapi/uvicorn/PyJWT - installed"
    else
        echo " [!!] fastapi/uvicorn/PyJWT - FAILED"
    fi
fi

# httpx / feedparser / beautifulsoup4 (热点趋势工具)
if python3 -c "import httpx" 2>/dev/null; then
    echo " [OK] httpx/feedparser/bs4 - already installed"
else
    echo " [..] httpx/feedparser/bs4 - installing..."
    if python3 -m pip install httpx feedparser beautifulsoup4 -q 2>/dev/null; then
        echo " [OK] httpx/feedparser/bs4 - installed"
    else
        echo " [!!] httpx/feedparser/bs4 - FAILED"
    fi
fi

# pydantic (SimLife 生活模拟模块依赖)
if python3 -c "import pydantic" 2>/dev/null; then
    echo " [OK] pydantic         - already installed"
else
    echo " [..] pydantic         - installing..."
    if python3 -m pip install pydantic -q 2>/dev/null; then
        echo " [OK] pydantic         - installed"
    else
        echo " [!!] pydantic         - FAILED"
    fi
fi

echo ""
if $OFFICE_OK; then
    echo " [OK] All Office dependencies ready (.docx .xlsx .pptx .pdf)."
else
    echo " [WARN] Some Office packages failed to install."
    echo "         Run this script again or install manually:"
    echo "           pip install python-docx openpyxl python-pptx reportlab pdfplumber"
fi
if ! $TTS_OK; then
    echo " [WARN] edge-tts failed. Voice synthesis will be unavailable."
    echo "         Fix: pip install edge-tts"
fi

# Create launch script
cat > launch.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
python3 main.py
EOF
chmod +x launch.sh

echo ""
echo " ========================================"
echo "  Installation complete!"
echo ""
echo "  To start: ./launch.sh"
echo "           or: python3 main.py"
echo ""
echo "  Supported LLM providers (configure in Settings):"
echo "  - DeepSeek  https://platform.deepseek.com"
echo "  - OpenAI    https://platform.openai.com"
echo "  - Groq      https://console.groq.com  (FREE tier)"
echo "  - Claude    https://console.anthropic.com"
echo "  - Gemini    https://aistudio.google.com"
echo "  - Qwen      https://dashscope.console.aliyun.com"
echo "  - Zhipu GLM https://open.bigmodel.cn"
echo "  - Doubao    https://console.volcengine.com/ark"
echo "  - Kimi      https://platform.moonshot.cn"
echo "  - Baidu     https://console.bce.baidu.com/qianfan"
echo "  - SparkDesk https://xinghuo.xfyun.cn"
echo "  - Ollama    https://ollama.ai  (100%% local)"
echo " ========================================"
echo ""
