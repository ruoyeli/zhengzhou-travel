import os

import psycopg
from dotenv import load_dotenv
load_dotenv()  # 这会从 .env 文件加载变量
DB_URI = os.getenv("DB_URI")


def verify_postgres_connection() -> None:
    """启动时验证 PostgreSQL 是否可达（LangGraph 会话记忆）。"""
    if not DB_URI:
        raise RuntimeError("未配置 DB_URI")

    try:
        with psycopg.connect(DB_URI) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except psycopg.Error as e:
        raise RuntimeError(f"PostgreSQL 连接失败: {e}") from e
