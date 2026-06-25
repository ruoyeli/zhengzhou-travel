import os
import sys

import psycopg
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver

from db import verify_postgres_connection
from graph import build_graph

load_dotenv()


def normalize_db_uri(db_uri: str) -> str:
    """本地运行时把 Docker 服务名 db 替换为 localhost。"""
    return db_uri.replace("@db:", "@localhost:")


def main():
    db_uri = os.getenv("DB_URI")
    if not db_uri:
        print("错误：未配置 DB_URI，请复制 .env.example 为 .env 并填写。")
        sys.exit(1)

    db_uri = normalize_db_uri(db_uri)

    try:
        verify_postgres_connection()
    except RuntimeError as e:
        print(f"错误：{e}")
        sys.exit(1)

    try:
        with PostgresSaver.from_conn_string(db_uri) as checkpointer:
            checkpointer.setup()
            graph = build_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": "local_debug_user"}}

            print("--- 郑州旅行助手 (本地调试模式) 已启动 ---")
            print("输入 quit / exit / 退出 结束对话\n")

            while True:
                user_input = input("你：").strip()
                if user_input.lower() in ["quit", "exit", "退出"]:
                    break
                if not user_input:
                    continue

                input_state = {"messages": [HumanMessage(content=user_input)], "intent": ""}
                try:
                    result = graph.invoke(input_state, config=config)
                    print(f"助手：{result['messages'][-1].content}")
                except psycopg.Error as e:
                    print(f"PostgreSQL 错误：{e}")
                except Exception as e:
                    print(f"运行错误：{e}")
    except psycopg.Error as e:
        print(f"PostgreSQL 初始化失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
