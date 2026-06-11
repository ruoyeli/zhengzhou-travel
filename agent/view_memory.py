import os
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from agent.graph import build_graph

load_dotenv()

def view_history(thread_id: str):
    db_uri = os.getenv("DB_URI")
    
    # 1. 连接数据库
    with PostgresSaver.from_conn_string(db_uri) as checkpointer:
        # 2. 加载你的图（不需要编译节点，只需要结构）
        app = build_graph(checkpointer=checkpointer)
        
        # 3. 指定要查看的对话 ID
        config = {"configurable": {"thread_id": thread_id}}
        
        # 4. 获取该 ID 下的最新状态
        state = app.get_state(config)
        
        if not state.values:
            print(f"找不到 ID 为 {thread_id} 的记忆。")
            return

        print(f"=== 线程 {thread_id} 的历史记忆 ===")
        
        # 打印聊天记录
        messages = state.values.get("messages", [])
        for msg in messages:
            role = "用户" if msg.type == "human" else "助手"
            print(f"[{role}]: {msg.content}")
            
        # 打印保存的变量
        print("\n=== 存储的变量状态 ===")
        print(f"酒店列表数量: {len(state.values.get('hotels_list', []))}")
        print(f"当前意图: {state.values.get('intent')}")
        print(f"预订信息: {state.values.get('booking_info')}")

if __name__ == "__main__":
    # 输入你在 main.py 里使用的 thread_id
    view_history("test_user_001")