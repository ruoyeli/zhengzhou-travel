import os

# 测试环境占位，避免 import nodes/graph 时因缺少 Key 报错
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")
os.environ.setdefault("DB_URI", "postgresql://postgres:pass@localhost:5432/test")
