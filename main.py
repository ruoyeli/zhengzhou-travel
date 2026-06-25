import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import BaseModel

from db import verify_postgres_connection
from graph import build_graph


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
    return {"status": "ok"}


@app.post("/api/chat")
def chat_with_agent(req: ChatRequest):
    config = {"configurable": {"thread_id": req.session_id}}
    input_state = {
        "messages": [HumanMessage(content=req.message)],
        "intent": "",
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
