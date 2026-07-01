import os
import sys
from pathlib import Path

# 测试环境占位，避免 import nodes/graph 时因缺少 Key 报错
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("DB_URI", "postgresql://postgres:pass@localhost:5432/test")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
