import os
from contextlib import asynccontextmanager
from typing import Optional

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import BaseModel
from dotenv import load_dotenv

from db import verify_postgres_connection
from graph import build_graph

load_dotenv()

# ---------- API Key 鉴权 ----------

API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="x-api-key")) -> Optional[str]:
    """验证请求头中的 API Key。不通过直接返回 401。"""
    if not API_SECRET_KEY:
        # 未配置则不校验（本地开发）
        return x_api_key
    if not x_api_key:
        raise HTTPException(status_code=401, detail="缺少 API Key")
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return x_api_key


# ---------- 应用启动 ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_uri = os.getenv("DB_URI")
    if not db_uri:
        raise RuntimeError("未配置 DB_URI")

    try:
        verify_postgres_connection()
        with PostgresSaver.from_conn_string(db_uri) as checkpointer:
            checkpointer.setup()
            app.state.graph = build_graph(checkpointer=checkpointer)
            yield
    except psycopg.Error as e:
        raise RuntimeError(f"PostgreSQL 初始化失败: {e}") from e


app = FastAPI(
    title="郑州旅行助手 API",
    description="基于 LangGraph 的多会话智能体",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.get("/health")
def health():
    """健康检查，无需鉴权"""
    return {"status": "ok"}


@app.post("/api/chat")
def chat_with_agent(req: ChatRequest, api_key: Optional[str] = Depends(verify_api_key)):
    """对话接口，需要 x-api-key 鉴权"""
    config = {"configurable": {"thread_id": req.session_id}}
    input_state = {
        "messages": [HumanMessage(content=req.message)],
        "intents": [],
    }

    try:
        result = app.state.graph.invoke(input_state, config=config)
        reply_text = result["messages"][-1].content
        return {
            "session_id": req.session_id,
            "reply": reply_text,
        }
    except psycopg.Error as e:
        raise HTTPException(status_code=500, detail=f"PostgreSQL 错误: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 运行错误: {e}")
