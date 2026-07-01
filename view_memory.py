import os
import sys

import psycopg
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

from graph import build_graph

load_dotenv()


def normalize_db_uri(db_uri: str) -> str:
    """本地运行时把 Docker 服务名 db 替换为 localhost。"""
    return db_uri.replace("@db:", "@localhost:")


def view_history(thread_id: str):
    db_uri = os.getenv("DB_URI")
    if not db_uri:
        print("错误：未配置 DB_URI")
        sys.exit(1)

    db_uri = normalize_db_uri(db_uri)

    try:
        with PostgresSaver.from_conn_string(db_uri) as checkpointer:
            app = build_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}
            state = app.get_state(config)
    except psycopg.Error as e:
        print(f"PostgreSQL 错误：{e}")
        sys.exit(1)

    if not state.values:
        print(f"找不到 ID 为 {thread_id} 的记忆。")
        return

    print(f"=== 线程 {thread_id} 的历史记忆 ===")

    messages = state.values.get("messages", [])
    for msg in messages:
        role = "用户" if msg.type == "human" else "助手"
        print(f"[{role}]: {msg.content}")

    print("\n=== 存储的变量状态 ===")
    print(f"酒店列表数量: {len(state.values.get('hotels_list', []))}")
    print(f"当前意图: {state.values.get('intents')}")
    print(f"预订信息: {state.values.get('booking_info')}")


if __name__ == "__main__":
    thread_id = sys.argv[1] if len(sys.argv) > 1 else "local_debug_user"
    view_history(thread_id)
