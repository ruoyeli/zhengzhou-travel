import os
import psycopg
from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage
from agent.graph import build_graph
from langgraph.checkpoint.postgres import PostgresSaver

# ----------------- 会话管理数据库操作 -----------------

def get_db_connection():
    """获取一个支持自动提交的数据库连接"""
    return psycopg.connect(os.getenv("DB_URI"), autocommit=True)

def list_sessions():
    """从数据库中查询所有存在的会话名称"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # checkpoints 表里存了所有出现过的 thread_id
            cur.execute("SELECT DISTINCT thread_id FROM checkpoints;")
            return [r[0] for r in cur.fetchall()]

def delete_session(thread_id):
    """彻底从数据库中删除某个会话的记忆"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 必须同时删除这三张表里的数据，保证清理干净
            cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
            cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
            cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))

def rename_session(old_id, new_id):
    """重命名会话（实际上就是把旧的 thread_id 更新为新的）"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE checkpoint_writes SET thread_id = %s WHERE thread_id = %s", (new_id, old_id))
            cur.execute("UPDATE checkpoint_blobs SET thread_id = %s WHERE thread_id = %s", (new_id, old_id))
            cur.execute("UPDATE checkpoints SET thread_id = %s WHERE thread_id = %s", (new_id, old_id))

# ----------------- 主程序 -----------------

def main():
    db_uri = os.getenv("DB_URI")
    if not db_uri:
        raise ValueError("请在 .env 文件中设置 DB_URI！")

    # 默认启动时的会话名称
    current_session = "user_name:1" 
    config = {"configurable": {"thread_id": current_session}}

    with PostgresSaver.from_conn_string(db_uri) as checkpointer:
        checkpointer.setup()
        graph = build_graph(checkpointer=checkpointer)

        print("===" * 15)
        print(" 旅行助手  已启动！")
        print("当前所在会话:", current_session)
        print("\n✨ 支持的管理指令（直接在对话框输入）：")
        print("  /list           -  查看所有历史会话")
        print("  /new <名称>     -  新建并切换到一个新会话")
        print("  /switch <名称>  -  切换到指定的历史会话")
        print("  /rename <新名>  -  把当前会话重命名")
        print("  /del <名称>     -  删除指定会话的所有记忆")
        print("  quit            -  退出程序")
        print("===" * 15)

        while True:
            # 提示符会显示当前的会话名称，体验极佳
            user_input = input(f"\n[{current_session}] 你：").strip()
            
            if user_input.lower() in ["quit", "exit", "退出"]:
                print("👋 再见！所有记忆已安全保存在数据库中。")
                break
            if not user_input:
                continue

            # ================= 处理斜杠指令 =================
            if user_input.startswith("/"):
                parts = user_input.split(" ", 1)
                cmd = parts[0].lower()
                arg = parts[1].strip() if len(parts) > 1 else ""

                if cmd == "/list":
                    sessions = list_sessions()
                    print("\n📂 数据库中保存的会话：")
                    if not sessions:
                        print("  (暂无历史记录)")
                    for s in sessions:
                        marker = " 👈 (当前)" if s == current_session else ""
                        print(f"  - {s}{marker}")
                    continue

                elif cmd == "/new":
                    if not arg:
                        print("⚠️ 请提供新会话名称，例如: /new 北京之行")
                        continue
                    current_session = arg
                    config["configurable"]["thread_id"] = current_session
                    print(f"✨ 已开辟新时空，当前处于纯净会话: {current_session}")
                    continue

                elif cmd == "/switch":
                    if not arg:
                        print("⚠️ 请提供会话名称，例如: /switch user_name:1")
                        continue
                    if arg not in list_sessions():
                        print(f"⚠️ 找不到会话 '{arg}'，请用 /list 查看可用列表。")
                        continue
                    current_session = arg
                    config["configurable"]["thread_id"] = current_session
                    print(f"🔄 已成功切换，记忆已同步至会话: {current_session}")
                    continue

                elif cmd == "/rename":
                    if not arg:
                        print("⚠️ 请提供新名称，例如: /rename 老张的旅行")
                        continue
                    try:
                        rename_session(current_session, arg)
                        print(f"✏️ 成功将 '{current_session}' 重命名为 '{arg}'")
                        current_session = arg
                        config["configurable"]["thread_id"] = current_session
                    except Exception as e:
                        print(f"❌ 重命名失败: {e}")
                    continue

                elif cmd == "/del":
                    if not arg:
                        print("⚠️ 请提供要删除的会话名称，例如: /del user_name:1")
                        continue
                    try:
                        delete_session(arg)
                        print(f"🗑️ 轰！会话 '{arg}' 的所有记忆已从数据库中抹除。")
                        # 如果删除了当前会话，自动跳回一个默认的空会话
                        if arg == current_session:
                            current_session = "默认会话"
                            config["configurable"]["thread_id"] = current_session
                            print(f"⚠️ 由于删除了当前会话，已自动退回: {current_session}")
                    except Exception as e:
                        print(f"❌ 删除失败: {e}")
                    continue
                else:
                    print(f"⚠️ 未知指令: {cmd}。可用的有: /list, /new, /switch, /rename, /del")
                    continue

            # ================= 正常对话业务逻辑 =================
            input_state = {
                "messages": [HumanMessage(content=user_input)],
                "intent": "" 
            }

            try:
                # 把状态传给图运行
                graph.invoke(input_state, config=config)
            except Exception as e:
                print(f"\n❌ 运行出错，请检查节点逻辑: {e}")

if __name__ == "__main__":
    main()